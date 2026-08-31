"""
Serena Integration for ARCA User Interaction Agent

Serena is the Noetic Code Agent - a semantic code analyzer and repair orchestrator.
Refactored to use LangGraph for structured reasoning and Serial Queue for backpressure management.

Architecture:
    Input Sources (RabbitMQ / Redis Alerts) → Serial Queue → LangGraph Workflow
    
    LangGraph Nodes:
    [Diagnose] → [Plan] → [Execute] → [Verify] → [Learn]
"""

import os
import json
import logging
import asyncio
import threading
from typing import Dict, List, Any, Optional, Callable, TypedDict, Literal
from datetime import datetime
from pathlib import Path

# LangGraph Imports
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# Import model config
try:
    from shared.model_config import serena_model
except ImportError:
    def serena_model(): return "qwen3-4b-thinking"

# Skills and Reasoning Bank Directories
def _get_skills_dir():
    direct = Path("/app/mcp_skills")
    shared = Path(os.environ.get("SHARED_STORAGE_PATH", "/app/shared_storage")) / "mcp_skills"
    if direct.exists() and any(direct.glob("*.md")):
        return direct
    return shared

REASONING_BANK_DIR = Path(os.environ.get("SHARED_STORAGE_PATH", "/app/shared_storage")) / "reasoning_bank"


# --- Dependencies (SkillsBank, ReasoningBank, HealthMonitor, SkillCapture) ---
# Kept largely same as original but streamlined

class SkillsBank:
    def __init__(self, skills_dir: Path = None):
        self.skills_dir = skills_dir if skills_dir else _get_skills_dir()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills_cache: Dict[str, Dict] = {}
        self._load_skills()
    
    def _load_skills(self):
        self._skills_cache = {}
        for skill_file in self.skills_dir.glob("*.md"):
            skill_name = skill_file.stem
            try:
                with open(skill_file, 'r') as f:
                    content = f.read()
                self._skills_cache[skill_name] = {
                    "name": skill_name,
                    "content": content,
                    "loaded_at": datetime.now().isoformat()
                }
            except Exception as e:
                logger.warning(f"Failed to load skill {skill_name}: {e}")
    
    def search_skills(self, query: str) -> List[Dict]:
        query_lower = query.lower()
        matches = []
        for name, skill in self._skills_cache.items():
            if query_lower in skill["content"].lower() or query_lower in name.lower():
                matches.append(skill)
        return matches

    def get_skill(self, name: str):
        return self._skills_cache.get(name)

class ReasoningBank:
    def __init__(self, reasoning_dir: Path = REASONING_BANK_DIR):
        self.reasoning_dir = reasoning_dir
        self.reasoning_dir.mkdir(parents=True, exist_ok=True)
    
    def store_reasoning(self, category: str, reasoning: Dict[str, Any]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{category}_{timestamp}.json"
        filepath = self.reasoning_dir / filename
        reasoning["stored_at"] = datetime.now().isoformat()
        with open(filepath, 'w') as f:
            json.dump(reasoning, f, indent=2)
        return str(filepath)

class HealthMonitor:
    HEALTH_CHANNEL = "arca:health:alerts"
    
    def __init__(self, redis_client, on_health_alert: Callable = None):
        self.redis = redis_client
        self.on_health_alert = on_health_alert
        self._running = False
        self.pubsub = None
    
    def start_monitoring(self):
        if self._running: return
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(self.HEALTH_CHANNEL)
        self._running = True
        threading.Thread(target=self._listen, daemon=True).start()
        logger.info("Health monitor started")
    
    def stop_monitoring(self):
        self._running = False
        if self.pubsub: self.pubsub.close()
    
    def _listen(self):
        while self._running:
            try:
                msg = self.pubsub.get_message(timeout=1.0)
                if msg and msg['type'] == 'message':
                    alert = json.loads(msg['data'])
                    if self.on_health_alert: self.on_health_alert(alert)
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

class SkillCapture:
    def __init__(self, skills_dir: Path = None):
        self.skills_dir = skills_dir if skills_dir else _get_skills_dir()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
    
    def capture_skill(self, skill_name, category, description, problem, solution_steps, verification, mcp_tools_used, related_services):
        content = f"# {skill_name}\n\nCategory: {category}\n\n## Purpose\n{description}\n\n## Problem\n{problem}\n\n## Solution\n"
        for i, step in enumerate(solution_steps, 1): content += f"{i}. {step}\n"
        content += f"\n## Verification\n{verification}\n\n## Tools\n{mcp_tools_used}"
        
        filepath = self.skills_dir / f"{skill_name}.md"
        with open(filepath, 'w') as f: f.write(content)
        logger.info(f"Captured skill: {filepath}")
        return str(filepath)


# --- LangGraph State Definition ---

class SerenaState(TypedDict):
    """State definition for Serena's repair workflow."""
    service: str
    status: str
    details: Dict[str, Any]
    
    # Reasoning Trace
    trace_id: str
    diagnostics: Dict[str, Any]
    relevant_skills: List[Dict[str, Any]]
    
    # Plan
    selected_strategy: Optional[str] # 'skill', 'default', 'fallback', 'escalate'
    selected_skill: Optional[str]
    plan_steps: List[str]
    
    # Execution
    execution_log: List[str]
    tools_used: List[str]
    
    # Outcome
    repair_success: bool
    final_output: str


# --- Main Agent Class ---

class SerenaCodeAgent:
    """
    Serena - The Noetic Code Agent (Graph-Based + Serial Queue).
    """
    
    def __init__(self, mcp_client, redis_client, llm_gateway_client=None, loop=None):
        self.mcp_client = mcp_client
        self.redis_client = redis_client
        self.llm_gateway_client = llm_gateway_client
        self.loop = loop  # Main event loop for async operations
        
        # Components
        self.skills_bank = SkillsBank()
        self.reasoning_bank = ReasoningBank()
        self.skill_capture = SkillCapture()
        self.health_monitor = HealthMonitor(redis_client, on_health_alert=self._handle_health_alert)
        
        # Serial Task Queue (Backpressure management)
        # Using a thread-safe Queue wrapper or asyncio Queue depending on context
        # Since we mix threads (RabbitMQ) and Async, we need to be careful.
        self._repair_queue = asyncio.Queue(maxsize=20)
        self._worker_task = None
        
        # RabbitMQ Config
        self.rabbitmq_url = os.environ.get("RABBITMQ_URL")
        if not self.rabbitmq_url:
            user = os.environ.get("RABBITMQ_USER", "arca")
            pwd = os.environ.get("RABBITMQ_PASS", "arca_password")
            host = os.environ.get("RABBITMQ_HOST", "rabbitmq")
            port = os.environ.get("RABBITMQ_PORT", "5672")
            vhost = os.environ.get("RABBITMQ_VHOST", "arca_vhost")
            if vhost == "/": vhost = "" # pika URL format for default vhost
            self.rabbitmq_url = f"amqp://{user}:{pwd}@{host}:{port}/{vhost}"
        self._supervisor_thread = None
        self._supervisor_running = False
        
        # Initialize the LangGraph
        self.workflow = self._build_workflow()
        
        logger.info(f"Serena Code Agent initialized (Queue Mode)")

    def _build_workflow(self) -> StateGraph:
        """Construct the LangGraph workflow for system repair."""
        workflow = StateGraph(SerenaState)
        
        # Add Nodes
        workflow.add_node("diagnose", self.diagnose_node)
        workflow.add_node("plan", self.plan_node)
        workflow.add_node("execute", self.execute_node)
        workflow.add_node("verify", self.verify_node)
        workflow.add_node("learn", self.learn_node)
        
        # Add Edges
        workflow.set_entry_point("diagnose")
        workflow.add_edge("diagnose", "plan")
        workflow.add_edge("plan", "execute")
        workflow.add_edge("execute", "verify")
        
        # Conditional Edge after verify
        def check_success(state: SerenaState) -> Literal["learn", "end"]:
            if state.get("repair_success"):
                return "learn"
            return "end"
            
        workflow.add_conditional_edges("verify", check_success, {
            "learn": "learn",
            "end": END
        })
        
        workflow.add_edge("learn", END)
        
        return workflow.compile()

    # --- Worker & Queue Management ---

    def start(self):
        """Start Serena's components."""
        self.health_monitor.start_monitoring()
        self._start_supervisor_listener()
        
        # Start the serial worker loop
        if self.loop:
            self._worker_task = self.loop.create_task(self._serial_worker_loop())
            logger.info("✅ Serena Serial Worker Started")
        else:
            logger.error("❌ Cannot start Serena Worker: No event loop provided")

    def stop(self):
        self.health_monitor.stop_monitoring()
        self._supervisor_running = False
        if self._worker_task:
            self._worker_task.cancel()

    async def _serial_worker_loop(self):
        """Daemon that processes one repair task at a time."""
        logger.info("🔧 Serena Worker Loop Active - Waiting for tasks...")
        while True:
            try:
                # Wait for next task
                task_payload = await self._repair_queue.get()
                
                service = task_payload.get("service")
                logger.info(f"🦾 Serena picked up task for: {service}")
                
                # Execute via Graph
                await self._run_repair_graph(task_payload)
                
                # Mark done
                self._repair_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Serena Worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in Serena Worker Loop: {e}")
                # Don't crash the loop
                await asyncio.sleep(1)

    async def _run_repair_graph(self, task_payload: Dict):
        """Execute the LangGraph workflow for a single task."""
        try:
            # Initialize State
            initial_state = SerenaState(
                service=task_payload.get("service", "unknown"),
                status=task_payload.get("status", "unknown"),
                details=task_payload.get("details", {}),
                trace_id=task_payload.get("trace_id", "unknown"),
                diagnostics={},
                relevant_skills=[],
                selected_strategy=None,
                selected_skill=None,
                plan_steps=[],
                execution_log=[],
                tools_used=[],
                repair_success=False,
                final_output=""
            )
            
            # Invoke Graph
            # Since invoke is sync in some versions, but we are async:
            # We use ainvoke if available, else invoke in executor
            result = await self.workflow.ainvoke(initial_state)
            
            logger.info(f"GRAPH COMPLETE for {initial_state['service']}. Success: {result.get('repair_success')}")
            
        except Exception as e:
            logger.error(f"Graph Execution Failed: {e}", exc_info=True)

    # --- Graph Nodes ---

    async def diagnose_node(self, state: SerenaState) -> Dict:
        """Diagnose the issue using Skills and LLM."""
        logger.info(f"🔎 [Diagnose] Analyzing {state['service']}...")
        service = state['service']
        
        # 1. Search Skills
        relevant_skills = self.skills_bank.search_skills(service)
        state['relevant_skills'] = relevant_skills
        
        # 2. LLM Analysis (Stub for brevity - assume context provided)
        diagnosis_text = f"Service {service} reported {state['status']}. Found {len(relevant_skills)} relevant skills."
        
        state['diagnostics'] = {
            "summary": diagnosis_text,
            "skill_count": len(relevant_skills)
        }
        return state

    async def plan_node(self, state: SerenaState) -> Dict:
        """Decide valid repair strategy."""
        logger.info(f"🧠 [Plan] Planning repair for {state['service']}...")
        
        if state['relevant_skills']:
            state['selected_strategy'] = 'skill'
            state['selected_skill'] = state['relevant_skills'][0]['name']
            state['plan_steps'] = ["Execute skill instructions"]
        else:
            state['selected_strategy'] = 'default'
            state['plan_steps'] = ["Check Status", "Restart Service", "Verify"]
            
        return state

    async def execute_node(self, state: SerenaState) -> Dict:
        """Execute the planned actions via MCP."""
        logger.info(f"⚡ [Execute] Executing {state['selected_strategy']} strategy...")
        service = state['service']
        
        # Simple execution logic (mapping to original _default_repair_strategy)
        try:
            if state['selected_strategy'] == 'default':
                # Restart
                await self.mcp_client.call_tool("docker_maintainer_operation", {
                    "operation": "restart", "service_name": service
                })
                state['execution_log'].append("Triggered Docker Restart")
                state['tools_used'].append("docker_maintainer_operation")
                await asyncio.sleep(5) # Wait for startup
                
            elif state['selected_strategy'] == 'skill':
                # Simplified skill execution
                await self.mcp_client.call_tool("docker_maintainer_operation", {
                    "operation": "restart", "service_name": service
                })
                state['execution_log'].append("Executed Skill (Restart)")
        except Exception as e:
            state['execution_log'].append(f"Execution Error: {e}")
            
        return state

    async def verify_node(self, state: SerenaState) -> Dict:
        """Verify if the repair worked."""
        logger.info(f"✅ [Verify] Checking health of {state['service']}...")
        
        try:
            status = await self.mcp_client.call_tool("get_container_status", {"container": state['service']})
            if status and "running" in str(status).lower():
                state['repair_success'] = True
                state['final_output'] = "Service recovered successfully."
            else:
                state['repair_success'] = False
                state['final_output'] = f"Service still unhealthy: {status}"
        except Exception as e:
            state['repair_success'] = False
            state['final_output'] = f"Verification failed: {e}"
            
        return state

    async def learn_node(self, state: SerenaState) -> Dict:
        """Capture successful repair as a new skill."""
        logger.info(f"📚 [Learn] Capturing success for {state['service']}...")
        
        self.skill_capture.capture_skill(
            skill_name=f"AUTO_{state['service'].upper()}_REPAIR_{datetime.now().strftime('%H%M')}",
            category="auto-generated",
            description=f"Auto repair for {state['service']}",
            problem=state['status'],
            solution_steps=state['execution_log'],
            verification=state['final_output'],
            mcp_tools_used=state['tools_used'],
            related_services=[state['service']]
        )
        return state

    # --- Public Inputs (Feed the Queue) ---

    def _handle_health_alert(self, alert: Dict):
        """Callback from Redis PubSub - non-blocking push to queue."""
        if not self.loop: return
        
        task = {
            "service": alert.get("service"),
            "status": alert.get("status"),
            "details": alert.get("details", {}),
            "trace_id": f"health_{datetime.now().timestamp()}"
        }
        
        try:
            self.loop.call_soon_threadsafe(self._repair_queue.put_nowait, task)
            logger.info(f"📥 Enqueued Health Alert for {task['service']}")
        except Exception as e:
            logger.error(f"Failed to enqueue alert: {e}")

    def _handle_supervised_task(self, payload: Dict):
        """Callback from RabbitMQ Listener - threadsafe push to queue."""
        if not self.loop: return
        
        task = {
            "service": payload.get("details", {}).get("service", "unknown"),
            "status": "supervised",
            "details": payload.get("details", {}),
            "trace_id": payload.get("task_id")
        }
        
        # This runs in a thread, so we must use call_soon_threadsafe
        try:
            self.loop.call_soon_threadsafe(self._repair_queue.put_nowait, task)
            logger.info(f"📥 Enqueued Supervisor Task {task['trace_id']}")
        except Exception as e:
            logger.error(f"Failed to enqueue supervisor task: {e}")

    # --- Supervisor Listener (RabbitMQ) ---

    def _start_supervisor_listener(self):
        self._supervisor_running = True
        self._supervisor_thread = threading.Thread(target=self._listen_supervisor_queue, daemon=True)
        self._supervisor_thread.start()

    def _listen_supervisor_queue(self):
        """Standard RabbitMQ listener loop."""
        import pika
        logger.info(f"🐰 Serena Supervisor Listener starting on {self.rabbitmq_url}")
        while self._supervisor_running:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
                channel = connection.channel()
                channel.queue_declare(queue='serena_supervisor_queue', durable=True)
                
                for method, props, body in channel.consume('serena_supervisor_queue', inactivity_timeout=1):
                    if not self._supervisor_running: break
                    if method:
                        try:
                            payload = json.loads(body)
                            channel.basic_ack(method.delivery_tag)
                            self._handle_supervised_task(payload)
                        except Exception as e:
                            logger.error(f"Msg Error: {e}")
                            channel.basic_nack(method.delivery_tag, requeue=False)
                connection.close()
            except Exception as e:
                logger.error(f"RabbitMQ Error: {e}")
                import time; time.sleep(5)

# Factory function needed by main.py
def create_serena_agent(mcp_client, redis_client, llm_gateway_client=None):
    # We need to capture the running loop for the worker
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        
    system = SerenaCodeAgent(mcp_client, redis_client, llm_gateway_client, loop=loop)
    system.start()
    return system
