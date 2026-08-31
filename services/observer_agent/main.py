import asyncio
import logging
import os
import shutil
import json
import glob
import time
from typing import Dict, Any, List
import redis.asyncio as redis
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
import uvicorn
import subprocess
import docker
import httpx

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("observer-agent")

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OBSERVER_MODEL = os.getenv("OBSERVER_MODEL", "gemma-3-4b-it") 
TOOLBOX_PATH = "/app/shared_storage/observer_toolbox"

# Channels
CH_ALERTS = "arca:alert:critical"
CH_ESCALATION = "arca:alert:serena" 
CH_GEOMETRY = "arca:geometry:tick:latest" 

# Setup Google AI
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    logger.warning("⚠️ GOOGLE_API_KEY not set. Independent reasoning will fail.")

app = FastAPI(title="ARCA Observer Agent (Cognitive Reflex Layer)")

class CognitiveEngine:
    """Independent Reasoning System reading directly from local Toolbox"""
    def __init__(self):
        self.skills_path = os.path.join(TOOLBOX_PATH, "skills")
        self.reasoning_path = os.path.join(TOOLBOX_PATH, "reasoning_bank")

    def retrieve_context(self, query: str) -> str:
        """Simple RAG-like retrieval from local files (Independent of Vector DB)"""
        context = []
        
        # 1. Retrieve Relevant Skills
        skills = glob.glob(os.path.join(self.skills_path, "*.md"))
        for skill_file in skills:
            # Naive match for robustness
            if any(term in os.path.basename(skill_file).lower() for term in query.lower().split()):
                try:
                    with open(skill_file, 'r') as f:
                        content = f.read(2000) # Read first 2KB
                        context.append(f"xxx SKILL: {os.path.basename(skill_file)} xxx\n{content}\n")
                except Exception:
                    pass

        # 2. Retrieve Reasoning Bank (Past Successes)
        reasoning_files = glob.glob(os.path.join(self.reasoning_path, "**/*.json"), recursive=True)
        for rf in reasoning_files:
             # Basic similarity check
             if any(term in os.path.basename(rf).lower() for term in query.lower().split()):
                 try:
                    with open(rf, 'r') as f:
                         data = json.load(f)
                         outcome = data.get("outcome", "")
                         if outcome == "success":
                             context.append(f"xxx PAST SUCCESS: {os.path.basename(rf)} xxx\n{json.dumps(data)}\n")
                 except Exception:
                     pass
        
        return "\n".join(context[:5]) # Limit context

    def record_outcome(self, failure_type: str, outcome: str, details: str, context_used: str):
        """Write reasoning trace to local bank"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        record = {
            "timestamp": timestamp,
            "failure_type": failure_type,
            "outcome": outcome,
            "details": details,
            "context_used": context_used
        }
        
        # Save to outcome-specific folder (Toolbox Priority - No Redis Required)
        folder = os.path.join(self.reasoning_path, "observer_outcomes")
        try:
            os.makedirs(folder, exist_ok=True)
            filepath = os.path.join(folder, f"{failure_type}_{outcome}_{timestamp}.json")
            with open(filepath, 'w') as f:
                json.dump(record, f, indent=2)
            logger.info(f"📝 Recorded outcome: {filepath}")
        except Exception as e:
            logger.error(f"Failed to record outcome: {e}")

class ObserverSystem:
    def __init__(self):
        self.redis = None
        self.docker_client = None
        self.running = False
        self.cognitive = CognitiveEngine()
        self.model = None
        if GOOGLE_API_KEY:
             self.model = genai.GenerativeModel(OBSERVER_MODEL) 
        self.failure_counts = {}
        self.state_path = os.path.join(TOOLBOX_PATH, "observer_state.json")
        self.compose_files = [
            "/app/docker-compose.local.yml",
            "/app/docker-compose.oci.yml",
            "/app/docker-compose.satellites.yml"
        ]
        self.load_state()

    def load_state(self):
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, 'r') as f:
                    self.state = json.load(f)
                    self.emergency_mode = self.state.get("mode") == "emergency"
                logger.info(f"💾 State Loaded: Mode={self.state.get('mode')}")
            else:
                self.state = {"mode": "emergency", "last_update": time.time()}
                self.emergency_mode = False
                self.save_state()
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            self.emergency_mode = False

    def save_state(self):
        try:
            self.state["mode"] = "emergency" if self.emergency_mode else "standard"
            self.state["last_update"] = time.time()
            with open(self.state_path, 'w') as f:
                json.dump(self.state, f, indent=2)
            logger.info(f"💾 State Saved: {self.state['mode']}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    async def start(self):
        logger.info(f"👁️ Observer Agent (Cognitive Reflex) Starting | Model: {OBSERVER_MODEL}")
        self.running = True
        
        # Start monitoring tasks immediately
        asyncio.create_task(self.monitor_alerts())
        asyncio.create_task(self.autonomous_health_checks())
        asyncio.create_task(self.monitor_docker_events())
        asyncio.create_task(self.monitor_geometry_state())
        
        # Establish background connections independently
        asyncio.create_task(self._connect_redis())
        asyncio.create_task(self._connect_docker())

    async def _connect_redis(self):
        # Resilient Redis Connection
        while self.running:
            try:
                self.redis = redis.from_url(REDIS_URL, decode_responses=True)
                await self.redis.ping()
                logger.info("✅ Connected to Redis")
                break
            except Exception as e:
                logger.warning(f"⏳ Waiting for Redis... ({e})")
                await asyncio.sleep(5)

    async def _connect_docker(self):
        # Resilient Docker Connection
        while self.running:
            try:
                self.docker_client = docker.from_env()
                self.docker_client.ping()
                logger.info("✅ Connected to Docker Socket")
                break
            except Exception as e:
                logger.warning(f"⏳ Waiting for Docker Socket... ({e})")
                await asyncio.sleep(5)

    async def monitor_docker_events(self):
        """Stream Docker events to detect container deaths instantly"""
        logger.info("🎧 Listening for Docker Events...")
        while self.running and not self.docker_client:
            await asyncio.sleep(1)
        if not self.docker_client: return
        await asyncio.to_thread(self._stream_docker_events)

    def _stream_docker_events(self):
        try:
            for event in self.docker_client.events(decode=True, filters={'type': 'container', 'event': 'die'}):
                attr = event.get('Actor', {}).get('Attributes', {})
                name = attr.get('name')
                exit_code = attr.get('exitCode')
                if exit_code != '0':
                    logger.error(f"💀 CRITICAL: Container {name} died (Exit: {exit_code})")
                    asyncio.run_coroutine_threadsafe(
                        self.handle_failure(f"{name}_crash", {"container": name, "exit_code": exit_code}), 
                        asyncio.get_event_loop()
                    )
        except Exception as e:
            logger.error(f"Event Stream Interrupted: {e}")

    async def autonomous_health_checks(self):
        while self.running and not self.docker_client:
            await asyncio.sleep(1)
        
        services_to_check = [
            # PHASE 1: Critical Infrastructure (Blocking)
            ("host_bridge", "http://host.docker.internal:8092/api/list_directory?path=."),
            ("redis", "tcp://redis:6379"),
            ("rabbitmq", "tcp://rabbitmq:5672"),
            ("postgres", "tcp://postgres:5432"),
            ("neo4j", "http://neo4j:7474"),
            
            # PHASE 2: Application Services (Dependent on Infra)
            ("mcp_server", "http://mcp_server:8086/health"), 
            ("llm_gateway", "http://llm_gateway:8080/health"), 
            ("user_interaction_agent", "http://user_interaction_agent:8084/health"),
            ("maintainer_agents", "http://maintainer_agents:8090/health"),
            
            # PHASE 3: Intelligence (Parallel / Non-Blocking)
            ("local_ops", "http://host.docker.internal:11435/health"),
            ("vulkan_secondary", "http://host.docker.internal:11436/health"),
            ("llama_cpp", "http://llama_cpp:8081/health"),

            # PHASE 4: OCI Services (Satellite Intelligence)
            ("neural_system", "http://neural_system:8085/health"),
            ("td_jepa", "http://td_jepa:8094/health"),
        ]
        while self.running:
            # PHASE 1 BOOTSTRAP: Must stabilize before checking others
            phase1_healthy = True
            for name, url in services_to_check[:5]: # host_bridge, redis, rabbitmq, postgres, neo4j
                try:
                    is_healthy = await self._check_service(name, url)
                    if not is_healthy:
                        phase1_healthy = False
                        logger.error(f"🚨 PHASE 1 (INFRA) DOWN: {name}")
                        await self.handle_failure(f"{name}_unresponsive", {"service": name, "phase": 1})
                except Exception as e:
                    logger.error(f"Bootstrap check error for {name}: {e}")
            
            if phase1_healthy:
                # PHASE 2 & 3: Application & Intelligence
                for name, url in services_to_check[5:]:
                    try:
                        is_healthy = await self._check_service(name, url)
                        if not is_healthy:
                            logger.error(f"🚨 Service DOWN: {name}")
                            await self.handle_failure(f"{name}_unresponsive", {"service": name, "phase": 2})
                    except Exception as e:
                        logger.error(f"Check error for {name}: {e}")
            else:
                if not self.emergency_mode:
                    self.emergency_mode = False
                    self.save_state()
                logger.warning("⏳ Phase 1 unstable. Emergency protocols active.")
                await asyncio.sleep(10)
            await asyncio.sleep(1.0)

    async def _check_service(self, name: str, url: str) -> bool:
        if url.startswith("http"):
             proc = await asyncio.create_subprocess_exec("curl", "-f", "-s", "-o", "/dev/null", "--max-time", "5", url)
             await proc.wait()
             return proc.returncode == 0
        elif url.startswith("tcp://"):
            try:
                host, port = url.replace("tcp://", "").split(":")
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, int(port)), timeout=2.0
                )
                writer.close()
                await writer.wait_closed()
                return True
            except Exception:
                return False
        return True

    async def monitor_geometry_state(self):
        while self.running:
            try:
                state_json = await self.redis.get(CH_GEOMETRY)
                if state_json:
                    state = json.loads(state_json)
                    if state.get("E_rot", 0) > 0.8:
                        await self.handle_failure("geometry_instability", {"state": state})
            except Exception: pass
            await asyncio.sleep(1.0)

    async def monitor_alerts(self):
        while self.running:
            try:
                if not self.redis:
                    await asyncio.sleep(1)
                    continue
                
                logger.info("🎧 Listening for Alerts...")
                pubsub = self.redis.pubsub()
                await pubsub.subscribe(CH_ALERTS)
                async for message in pubsub.listen():
                    if message['type'] == 'message':
                        await self.handle_failure("alert_received", {"message": message['data']})
            except Exception as e:
                logger.warning(f"⚠️ monitor_alerts interrupted: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

    async def handle_failure(self, failure_type: str, context: Dict[str, Any]):
        """Cognitive Response: 1. Deduce (Brain) -> 2. Reflex (Script/Docker) -> 3. Escalate"""
        
        # 1. Deduce Context (Independent of MCPServer)
        service = context.get("service") or context.get("container") or "unknown"
        rag_context = self.cognitive.retrieve_context(f"{failure_type} {service}")
        
        # 2. Consult Brain (Gemma via Google API)
        if self.model:
            try:
                prompt = (
                    f"CRITICAL SYSTEM ALERT: {failure_type}\n"
                    f"Context: {json.dumps(context)}\n"
                    f"Available Tools: {TOOLBOX_PATH}/scripts\n"
                    f"--- RELEVANT KNOWLEDGE ---\n{rag_context}\n"
                    f"--- GOAL ---\n"
                    f"Deduce root cause and recommend IMMEDIATE recovery action (script or restart).\n"
                    f"Format: JSON {{ 'root_cause': '...', 'recommended_action': 'restart_container' | 'run_script', 'script_name': '...'}}"
                )
                response = self.model.generate_content(prompt)
                logger.info(f"🧠 Observer Deduction: {response.text}")
            except Exception as e:
                 logger.error(f"Brain Deduction Failed: {e}")

        # 3. Execution (Reflex Priority with Persistence)
        max_retries = 3 # Reduced to prevent blocking
        for attempt in range(max_retries):
            logger.info(f"🔄 Recovery Attempt {attempt + 1} for {failure_type}")
            fixed = await self.attempt_reflex_recovery(failure_type, context)
            
            if fixed:
                logger.info(f"✅ Recovery Successful: {failure_type} (Attempt {attempt + 1})")
                # Write to Reasoning Bank
                self.cognitive.record_outcome(failure_type, "success", f"Reflex recovery on {service}", rag_context)
                self.failure_counts[service] = 0
                return
            
            logger.warning(f"❌ Recovery Attempt {attempt + 1} failed for {service}")
            await asyncio.sleep(10) # Wait before retry

        # Fallback to Escalation (Standard Mode only, and if Redis is up)
        if not self.emergency_mode and self.redis:
            try:
                logger.warning(f"⚠️ Escalating to Serena: {failure_type}")
                await self.redis.publish(CH_ESCALATION, json.dumps({
                    "source": "observer", 
                    "type": failure_type, 
                    "context": context,
                    "deduced_knowledge": rag_context,
                    "status": "escalated"
                }))
            except Exception as e:
                logger.error(f"Escalation failed: {e}")
        else:
            logger.warning(f"⚠️ In EMERGENCY MODE or Redis DOWN. Persistent re-bootstrap in progress for {service}.")

    async def attempt_reflex_recovery(self, failure_type: str, context: Dict[str, Any]) -> bool:
        service = context.get("service") or context.get("container")
        if not service: return False

        # State-Based Script Swapping (GRP-1: CORE=+ -> @ | CORE=- -> 1)
        mode_prefix = "emergency" if self.emergency_mode else "standard"
        TOOLKIT_SUBDIR = os.path.join(TOOLBOX_PATH, "scripts", mode_prefix)
        
        logger.info(f"🔍 Recovery in {mode_prefix.upper()} MODE for {service}")

        # Mapping services to specific recovery scripts (Mode Specific)
        script_mapping = {
            "local_ops": "restart_local_ops.sh",
            "vulkan_secondary": "restart_vulkan_ops.sh",
            "llama_cpp": "restart_llama_cpp.sh"
        }
        
        script_name = script_mapping.get(service)
        if not script_name:
            # Fallback to candidates in the current mode's folder
            candidates = [f"recover_{service}.sh", f"restart_{service}.sh", f"{service}_recovery.sh"]
            for s in candidates:
                script_path = os.path.join(TOOLKIT_SUBDIR, s)
                if os.path.exists(script_path):
                    script_name = s
                    break

        if script_name:
            script_path = os.path.join(TOOLKIT_SUBDIR, script_name)
            if os.path.exists(script_path):
                return await self._run_script(script_path)
            else:
                logger.warning(f"⚠️ Script {script_name} not found in {mode_prefix} toolkit")
        
        # Generic Docker Restart/UP as FINAL fallback
        if self.docker_client:
            try:
                container = self.docker_client.containers.get(service)
                container.restart()
                await asyncio.sleep(5)
                return True
            except docker.errors.NotFound:
                logger.info(f"🚀 Container {service} NOT FOUND. Searching across compose files...")
                try:
                    # Find which compose file has the service
                    target_compose = "/app/docker-compose.local.yml" # Default
                    for cf in self.compose_files:
                        if os.path.exists(cf):
                            try:
                                # Quick grep or check to see if service is in file
                                with open(cf, 'r') as f:
                                    if f"{service}:" in f.read():
                                        target_compose = cf
                                        logger.info(f"📍 Found {service} in {cf}")
                                        break
                            except: pass

                    # Using the Compose CLI installed in the container
                    docker_path = shutil.which("docker") or "/usr/bin/docker"
                    logger.info(f"Running: {docker_path} compose -f {target_compose} up -d {service}")
                    proc = await asyncio.create_subprocess_exec(
                        docker_path, "compose", "-f", target_compose, "up", "-d", service,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd="/app"
                    )
                    stdout, stderr = await proc.communicate()
                    
                    if proc.returncode == 0:
                        logger.info(f"✅ Successfully deployed {service} via {os.path.basename(target_compose)}")
                        return True
                    else:
                        logger.error(f"❌ Compose CLI failed for {service} (Code: {proc.returncode})")
                        logger.error(f"STDOUT: {stdout.decode()}")
                        logger.error(f"STDERR: {stderr.decode()}")
                except Exception as e:
                    logger.error(f"Failed to execute compose up: {e}")
            except Exception: pass
        return False

    async def _run_script(self, script_path) -> bool:
        # Check if we should route through host_bridge (Host-level recovery)
        # We assume scripts in the toolbox are intended for the host if not docker-specific
        try:
            # Calculate relative path for host_bridge (from project root)
            # Script path inside observer: /app/shared_storage/observer_toolbox/scripts/...
            # Host path expected: shared_storage/observer_toolbox/scripts/...
            if "/app/" in script_path:
                rel_path = script_path.split("/app/", 1)[1]
            else:
                rel_path = script_path

            logger.info(f"🌉 Routing execution via Host Bridge: {rel_path}")
            
            # Bridge is now running natively on host
            # Using requests (synchronous) for simplicity/stability as per requirements
            import requests # Lazy import to avoid global dependency issues
            resp = await asyncio.to_thread(
                requests.post,
                "http://host.docker.internal:8092/api/exec_script",
                json={"path": rel_path},
                timeout=60.0
            ) 
                
            if resp.status_code == 200:
                result = resp.json()
                if result.get("status") == "success":
                    logger.info(f"✅ Host Execution Success: {result.get('stdout')}")
                    return True
                else:
                    logger.error(f"❌ Host Execution Failed: {result.get('stderr')}")
                    return False
            else:
                logger.error(f"❌ Host Bridge Error: {resp.status_code} - {resp.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to execute via host_bridge: {e}")
            # Fallback to local (though unlikely to work for host services)
            try:
                proc = await asyncio.create_subprocess_exec("bash", script_path)
                await proc.wait()
                return proc.returncode == 0
            except:
                return False

@app.on_event("startup")
async def startup_event():
    system = ObserverSystem()
    asyncio.create_task(system.start()) 

@app.get("/health")
async def health():
    return {"status": "active", "role": "cognitive_observer"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8099)
