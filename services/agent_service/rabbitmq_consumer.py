import pika
import json
import logging
import os
import asyncio
import requests
from datetime import datetime
from typing import Dict, Any
from threading import Thread
from langgraph_agent import AgentWorkflowEngine
from state_schemas import GlobalState
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

class RabbitMQConsumer:
    def __init__(self, agent_system: AgentWorkflowEngine):
        self.agent_system = agent_system
        self.host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        self.port = int(os.getenv('RABBITMQ_PORT', 5672))
        self.user = os.getenv('RABBITMQ_USER', 'arca')
        self.password = os.getenv('RABBITMQ_PASSWORD', 'arca_password')
        self.vhost = os.getenv('RABBITMQ_VHOST', '/')
        if self.vhost == 'arca_vhost' and os.getenv('RABBITMQ_VHOST') is None:
             self.vhost = '/' # Force default if env var missing but code defaults to arca_vhost
        # Use unified exchange name
        self.exchange = os.getenv('RABBITMQ_EXCHANGE', 'arca.tier3')
        self.memory_system_url = os.getenv('MEMORY_SYSTEM_URL', 'http://arca-memory-system:8002')
        
        self.credentials = pika.PlainCredentials(self.user, self.password)
        self.parameters = pika.ConnectionParameters(
            self.host,
            self.port,
            self.vhost,
            self.credentials,
            heartbeat=600,  # 10 minutes - prevents "missed heartbeat" errors
            blocked_connection_timeout=300  # 5 minutes - allows long-running operations
        )
        self.connection = None
        self.channel = None
        self.preflight_passed = False

    def preflight_check(self) -> bool:
        """
        Perform preflight check to ensure all databases are accessible.
        Must pass before consuming any jobs.
        """
        try:
            logger.info("Performing preflight check...")
            response = requests.get(f"{self.memory_system_url}/preflight", timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get("all_systems_go", False):
                    logger.info(f"Preflight check PASSED: {json.dumps(result, indent=2)}")
                    self.preflight_passed = True
                    return True
                else:
                    logger.warning(f"Preflight check FAILED: {json.dumps(result, indent=2)}")
                    return False
            else:
                logger.error(f"Preflight check failed with status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Preflight check error: {e}")
            return False

    def connect(self):
        try:
            # Perform preflight check first
            if not self.preflight_check():
                logger.error("Preflight check failed - not starting consumer")
                # Retry after delay
                import time
                time.sleep(30)
                return self.connect()  # Retry
            
            self.connection = pika.BlockingConnection(self.parameters)
            self.channel = self.connection.channel()
            logger.info("Connected to RabbitMQ Consumer")
            
            # Declare exchanges (topic type for flexible routing)
            self.channel.exchange_declare(exchange=self.exchange, exchange_type='topic', durable=True)
            # Also declare arca.nexus for Tier 1 maintainer jobs
            self.channel.exchange_declare(exchange='arca.nexus', exchange_type='topic', durable=True)
            
            # Declare queues with aligned names
            # Tier 3: Architect (Genesis/Gnosis)
            self.channel.queue_declare(queue='tier3.architect', durable=True)
            self.channel.queue_bind(queue='tier3.architect', exchange=self.exchange, routing_key='tier3.architect.*')
            self.channel.queue_bind(queue='tier3.architect', exchange=self.exchange, routing_key='tier3.architect.genesis')
            self.channel.queue_bind(queue='tier3.architect', exchange=self.exchange, routing_key='tier3.architect.gnosis')
            
            # Tier 2: Planner
            self.channel.queue_declare(queue='tier2.planner', durable=True)
            self.channel.queue_bind(queue='tier2.planner', exchange=self.exchange, routing_key='tier2.planner.*')
            
            # Tier 1: Engineer, Reviewer (from tier3 exchange)
            self.channel.queue_declare(queue='tier1.engineer', durable=True)
            self.channel.queue_bind(queue='tier1.engineer', exchange=self.exchange, routing_key='tier1.engineer.*')
            
            self.channel.queue_declare(queue='tier1.reviewer', durable=True)
            self.channel.queue_bind(queue='tier1.reviewer', exchange=self.exchange, routing_key='tier1.reviewer.*')
            
            # Note: Tier 1 Maintainer jobs are handled via Serena -> MCP -> Ops agents
            # No separate queue consumer needed - Serena dispatches directly via MCP tools
            
            # Responses queue
            self.channel.queue_declare(queue='responses', durable=True)
            self.channel.queue_bind(queue='responses', exchange=self.exchange, routing_key='response.*')
            
            # Setup consumers
            self.channel.basic_consume(queue='tier3.architect', on_message_callback=self.handle_tier3, auto_ack=False)
            self.channel.basic_consume(queue='tier2.planner', on_message_callback=self.handle_tier2, auto_ack=False)
            self.channel.basic_consume(queue='tier1.engineer', on_message_callback=self.handle_tier1, auto_ack=False)
            self.channel.basic_consume(queue='tier1.reviewer', on_message_callback=self.handle_tier1, auto_ack=False)
            self.channel.basic_consume(queue='responses', on_message_callback=self.handle_responses, auto_ack=True)
            
            logger.info("Consumers registered for tier3.architect, tier2.planner, tier1.engineer, tier1.reviewer, responses")
            self.channel.start_consuming()
        except Exception as e:
            logger.error(f"RabbitMQ Consumer Error: {e}")
            if self.connection and not self.connection.is_closed:
                self.connection.close()

    def start(self):
        """Start the consumer in a background thread"""
        thread = Thread(target=self.connect, daemon=True)
        thread.start()

    def publish(self, routing_key: str, message: Dict[str, Any]):
        """Helper to publish messages"""
        try:
            # We need a separate connection for publishing if called from a different thread
            # Or use `connection.add_callback_threadsafe`
            # For simplicity in this prototype, we'll create a ephemeral connection or use a pool
            # But `basic_publish` is not thread safe on the same channel.
            # Let's use a fresh connection for publishing to be safe in async context
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(message)
            )
            connection.close()
        except Exception as e:
            logger.error(f"Failed to publish to {routing_key}: {e}")

    def _parse_body(self, body) -> Dict[str, Any]:
        """Parse message body, handling both direct payloads and file references."""
        try:
            data = json.loads(body)
            
            # Handle file_ref type messages (new routing pattern)
            if data.get("type") == "file_ref":
                return self._load_job_from_file(data)
            
            return data
        except Exception as e:
            logger.warning(f"Failed to parse JSON message body, returning as raw string: {e}")
            return {"content": body.decode('utf-8')}
    
    def _load_job_from_file(self, file_ref: Dict[str, Any]) -> Dict[str, Any]:
        """Load job payload from file reference.
        
        Args:
            file_ref: Dict with 'path' pointing to job JSON file
            
        Returns:
            Full job payload loaded from file
        """
        file_path = file_ref.get("path", "")
        job_id = file_ref.get("job_id", "unknown")
        
        logger.info(f"Loading job from file_ref: {file_path} (job_id: {job_id})")
        
        try:
            # Handle container vs host paths
            # In container: /app/shared_storage/jobs/...
            # On OCI host: /home/ubuntu/ARCA/shared_storage/jobs/...
            # On macOS host: /Users/danexall/Documents/VS Code Projects/ARCA/shared_storage/jobs/...
            container_path = file_path
            if file_path.startswith("/home/ubuntu/ARCA/"):
                container_path = file_path.replace("/home/ubuntu/ARCA/", "/app/")
            elif file_path.startswith("/Users/danexall/Documents/VS Code Projects/ARCA/"):
                container_path = file_path.replace("/Users/danexall/Documents/VS Code Projects/ARCA/", "/app/")
            elif file_path.startswith("/") and not file_path.startswith("/app/"):
                # For any other absolute path, try replacing the prefix with /app/
                parts = file_path.split("/")
                if "shared_storage" in parts:
                    idx = parts.index("shared_storage")
                    container_path = "/app/" + "/".join(parts[idx:])
            
            logger.debug(f"Path translation: {file_path} -> {container_path}")
            
            if not os.path.exists(container_path):
                logger.error(f"Job file not found: {container_path} (original: {file_path})")
                return {
                    "error": f"Job file not found: {file_path}",
                    "job_id": job_id,
                    "type": "file_ref_error"
                }
            
            with open(container_path, 'r') as f:
                job_payload = json.load(f)
            
            logger.info(f"Loaded job {job_id} from file: {job_payload.get('job_id', 'N/A')}")
            
            # Validate required fields
            if "tier" not in job_payload:
                logger.warning(f"Job missing 'tier' field: {job_id}")
            if "routing_key" not in job_payload:
                logger.warning(f"Job missing 'routing_key' field: {job_id}")
            
            # Add file_ref metadata
            job_payload["_file_ref"] = {
                "path": file_path,
                "container_path": container_path,
                "loaded_at": datetime.now().isoformat() if 'datetime' in dir() else None
            }
            
            return job_payload
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in job file {file_path}: {e}")
            return {
                "error": f"Invalid JSON in job file: {e}",
                "job_id": job_id,
                "type": "file_ref_error"
            }
        except Exception as e:
            logger.error(f"Error loading job file {file_path}: {e}")
            return {
                "error": str(e),
                "job_id": job_id,
                "type": "file_ref_error"
            }

    def handle_responses(self, ch, method, properties, body):
        """Response Consumer (Logger/UI Update + Persistence)"""
        logger.info(f"Received Response: {method.routing_key}")
        
        # Parse and persist response
        try:
            import os
            from datetime import datetime
            
            response_data = json.loads(body)
            
            # Create responses directory
            responses_dir = "/app/shared_storage/responses"
            os.makedirs(responses_dir, exist_ok=True)
            
            # Generate response filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            routing_parts = method.routing_key.split('.')
            response_type = '_'.join(routing_parts[-2:]) if len(routing_parts) >= 2 else 'unknown'
            request_id = response_data.get('request_id', 'unknown')
            
            response_file = f"{responses_dir}/response_{response_type}_{timestamp}_{request_id}.json"
            
            # Add metadata
            response_with_metadata = {
                "response_metadata": {
                    "routing_key": method.routing_key,
                    "timestamp": datetime.now().isoformat(),
                    "delivery_tag": method.delivery_tag
                },
                "response_data": response_data
            }
            
            # Write response to file
            with open(response_file, 'w') as f:
                json.dump(response_with_metadata, f, indent=2, default=str)
            
            logger.info(f"✅ Response saved to: {response_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to persist response: {e}")
            logger.info(f"Raw response body: {body}")

    def handle_tier3(self, ch, method, properties, body):
        """
        Tier 3 Consumer (Architect) - Genesis Chain Handler
        
        Phase 4 Execution Flow:
        1. Architect returns Schema and Scripts
        2. Robotics Check validates structure
        3. Engineer executes Cypher via mcp_neo4j_admin
        4. Engineer sets initial arca:state:global via mcp_blackboard_redis
        5. Planner awakens and reads Blackboard + queries Graph
        """
        logger.info(f"=== GENESIS TIER 3 TASK RECEIVED ===")
        logger.info(f"Routing Key: {method.routing_key}")
        
        payload = self._parse_body(body)
        request_id = payload.get("request_id", "unknown")
        target_agent = payload.get("target_agent", "architect")
        
        logger.info(f"Request ID: {request_id}, Target: {target_agent}")
        
        # Extract prompt content
        # Genesis payload structure: {"request_id": ..., "prompt": "...", "metadata": {...}}
        if "prompt" in payload:
            content = payload["prompt"]
            logger.info(f"Genesis prompt loaded ({len(content)} chars)")
        elif "content" in payload:
            content = payload["content"]
        else:
            content = json.dumps(payload)
        
        # Build state with Genesis context
        state = GlobalState(
            messages=[HumanMessage(content=content)],
            session_id=request_id,
            tier=3,
            active_agent="architect"
        )
        
        try:
            logger.info("Phase 1: Invoking Genesis Chain via AgentWorkflowEngine...")
            
            # Extract genesis prompt from payload - check multiple possible keys
            genesis_prompt = None
            if "genesis_prompt" in payload:
                genesis_prompt = payload["genesis_prompt"]
                logger.info(f"Using 'genesis_prompt' key from payload ({len(genesis_prompt)} chars)")
            elif "task_input" in payload:
                genesis_prompt = payload["task_input"]
                logger.info(f"Using 'task_input' key from payload ({len(genesis_prompt)} chars)")
            elif "prompt" in payload:
                genesis_prompt = payload["prompt"]
                logger.info(f"Using 'prompt' key from payload ({len(genesis_prompt)} chars)")
            elif "content" in payload:
                genesis_prompt = payload["content"]
                logger.info(f"Using 'content' key from payload ({len(genesis_prompt)} chars)")
            else:
                genesis_prompt = content
                logger.info(f"Using extracted content ({len(genesis_prompt)} chars)")
            
            if not genesis_prompt or not isinstance(genesis_prompt, str):
                raise ValueError(f"Invalid genesis_prompt: expected string, got {type(genesis_prompt)}")
            
            logger.info(f"Starting Genesis workflow with prompt ({len(genesis_prompt)} chars)...")
            
            # Invoke the async Genesis chain (run_genesis is async)
            # Note: run_genesis expects genesis_prompt (str) and optional session_id (str)
            result = asyncio.run(self.agent_system.run_genesis(
                genesis_prompt=genesis_prompt, 
                session_id=request_id
            ))
            
            logger.info(f"Genesis workflow complete. Status: {result.get('completion_status', 'unknown')}")
            logger.info(f"Architecture plan length: {len(str(result.get('architecture_plan', '')))} chars")
            
            # Extract responses from result
            architect_response = result.get("architecture_plan", "No architecture plan generated")
            execution_plan = result.get("execution_plan", "")
            action_history = result.get("action_history", [])
            
            logger.info(f"Architect Response (first 300 chars): {str(architect_response)[:300]}...")
            
            # Publish result based on completion status
            if result.get("completion_status") == "success":
                logger.info("✅ Genesis chain completed successfully")
                self.publish("response.genesis.complete", {
                    "request_id": request_id,
                    "source": "genesis_workflow",
                    "status": "COMPLETE",
                    "completion_status": "success",
                    "architecture_plan": architect_response,
                    "execution_plan": execution_plan,
                    "action_history": action_history,
                    "message": "Genesis workflow executed successfully"
                })
            else:
                error_details = result.get("error_state", {})
                logger.warning(f"❌ Genesis workflow failed: {error_details}")
                self.publish("response.genesis.error", {
                    "request_id": request_id,
                    "source": "genesis_workflow",
                    "status": "FAILED",
                    "completion_status": result.get("completion_status", "unknown"),
                    "error": str(error_details),
                    "message": "Genesis workflow execution failed"
                })
            
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"✅ Genesis task {request_id} acknowledged and processed")
            
        except Exception as e:
            logger.error(f"❌ Tier 3 Genesis Error: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Publish error response
            try:
                self.publish("response.genesis.error", {
                    "request_id": request_id,
                    "source": "genesis_workflow",
                    "status": "ERROR",
                    "error": f"{type(e).__name__}: {str(e)}",
                    "message": "Genesis workflow encountered an exception"
                })
            except Exception as pub_e:
                logger.error(f"Failed to publish error response: {pub_e}")
            
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def handle_tier2(self, ch, method, properties, body):
        """
        Tier 2 Consumer (Orchestrator) - Planner
        
        Genesis Awakening flow:
        1. Planner reads the Blackboard (arca:state:global)
        2. Planner queries the Graph (Neo4j)
        3. Output: "System Online. I perceive the Aether. The Alliance is active."
        """
        logger.info(f"Received Tier 2 Task: {method.routing_key}")
        payload = self._parse_body(body)
        task_type = payload.get("task_type", "planning")
        request_id = payload.get("request_id", "unknown")
        content = payload.get("content", "")
        
        state = GlobalState(
            messages=[HumanMessage(content=content)],
            session_id=request_id,
            tier=2,
            active_agent="planner"
        )
        
        try:
            if task_type == "awakening":
                logger.info(f"=== GENESIS AWAKENING (Planner) ===")
                logger.info(f"Request ID: {request_id}")
                
                # Planner awakens - reads Blackboard and queries Graph
                logger.info("Invoking Planner Node for Awakening...")
                result = asyncio.run(self.agent_system.planner_node(state))
                planner_response = result["messages"][-1].content
                
                logger.info(f"PLANNER AWAKENING RESPONSE: {planner_response}")
                
                # Publish Genesis complete response
                self.publish("response.genesis.complete", {
                    "request_id": request_id,
                    "source": "planner",
                    "status": "SYSTEM_ONLINE",
                    "content": planner_response,
                    "message": "Genesis Complete. The Alliance is active."
                })
                
            else:
                # Normal planning task
                result = asyncio.run(self.agent_system.planner_node(state))
                response = result["messages"][-1].content
                
                # Determine routing based on response content
                if "CODE" in response.upper() or "IMPLEMENT" in response.upper():
                    self.publish("tier1.engineer.task", {"content": response, "task_type": "code_gen"})
                elif "EXECUTE" in response.upper() or "RUN" in response.upper():
                    self.publish("tier1.engineer.task", {"content": response, "task_type": "execution"})
                else:
                    self.publish("response.tier2", {"content": response})
                
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Tier 2 Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def handle_tier1(self, ch, method, properties, body):
        """
        Tier 1 Consumer (Body) - Engineer, Reviewer, Local Executor
        
        Genesis execution flow:
        1. Engineer executes Cypher via mcp_neo4j_admin
        2. Engineer sets arca:state:global via mcp_blackboard_redis
        3. Routes to Planner for awakening
        """
        logger.info(f"Received Tier 1 Task: {method.routing_key}")
        payload = self._parse_body(body)
        task_type = payload.get("task_type", payload.get("type", "execution"))
        content = payload.get("content", "")
        request_id = payload.get("request_id", "unknown")
        
        state = GlobalState(
            messages=[HumanMessage(content=content)],
            session_id=request_id,
            tier=1
        )
        
        try:
            if task_type == "genesis_execution":
                logger.info(f"=== GENESIS EXECUTION (Engineer) ===")
                logger.info(f"Request ID: {request_id}")
                
                # Engineer executes the Architect's plan
                # This includes Cypher scripts and Blackboard initialization
                logger.info("Invoking Engineer Node for Genesis execution...")
                eng_result = asyncio.run(self.agent_system.engineer_node(state))
                engineer_output = eng_result["messages"][-1].content
                logger.info(f"Engineer output: {engineer_output[:500]}...")
                
                # After Engineer completes, awaken the Planner
                logger.info("Phase 4: Awakening Planner...")
                self.publish("tier2.planner.awakening", {
                    "request_id": request_id,
                    "source": "engineer",
                    "task_type": "awakening",
                    "content": "Genesis complete. Read the Blackboard and query the Graph. Report system status.",
                    "instructions": "Use read_blackboard to read arca:state:global. Query Neo4j for the Aether node. Confirm the Alliance is active."
                })
                
                self.publish("response.genesis.engineer", {
                    "request_id": request_id,
                    "content": engineer_output,
                    "status": "complete"
                })
                
            elif task_type == "code_gen":
                # Engineer -> Reviewer chain
                eng_result = asyncio.run(self.agent_system.engineer_node(state))
                state["messages"].extend(eng_result["messages"])
                rev_result = asyncio.run(self.agent_system.reviewer_node(state))
                
                final_output = rev_result["messages"][-1].content
                self.publish("response.tier1.code", {"content": final_output})
                
            elif task_type == "execution":
                # Local Executor
                exec_result = asyncio.run(self.agent_system.local_executor_node(state))
                final_output = exec_result["messages"][-1].content
                self.publish("response.tier1.exec", {"content": final_output})
            
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Tier 1 Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
