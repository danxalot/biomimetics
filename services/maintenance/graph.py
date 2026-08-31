import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pythia_integration import PYTHIA_TOOLS_LIST, PYTHIA_USAGE_PROMPT
from state import AgentState

logger = logging.getLogger("maintainer-agents-graph")


# --- SILENT LISTENER HELPER ---
async def log_agent_activity(
    activity_type: str, details: Dict[str, Any], severity: str = "INFO"
):
    """
    Fire-and-forget logging to the Silent Listener (Agent Service Audit Logger).
    """
    try:
        audit_url = os.getenv("AUDIT_LOGGER_URL", "http://agent_service:8088/audit")
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{audit_url}/log",
                json={
                    "service_name": "maintainer_agents",
                    "event_type": activity_type,
                    "details": details,
                    "severity": severity,
                    "timestamp": datetime.now().isoformat(),
                },
                timeout=2.0,
            )
    except Exception as e:
        logger.warning(f"Failed to push audit log: {e}")


# -----------------------------


class MaintainerGraph:
    def __init__(self, llm_client, mcp_client):
        self.llm = llm_client
        self.mcp = mcp_client
        self.workflow = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)

        # Add Nodes
        builder.add_node("planning", self.plan_node)
        builder.add_node("dream_node", self.dream_node)
        builder.add_node("execution", self.execute_node)
        builder.add_node("validation", self.validate_node)
        builder.add_node("escalation", self.escalate_node)
        builder.add_node("gordon_query", self.gordon_query_node)
        builder.add_node("mapping", self.mapping_node)  # New Auto-Mapping Node

        # Set Entry Point
        builder.add_edge(START, "planning")

        # Edges from Planning -> Dream Node -> Execution
        builder.add_conditional_edges(
            "planning",
            self.should_escalate,
            {"escalate": "escalation", "proceed": "dream_node"},
        )

        # Dream node routes: low stability -> replan, otherwise proceed to execution
        builder.add_conditional_edges(
            "dream_node",
            self.dream_node_routing,
            {"replan": "planning", "proceed": "execution"},
        )

        # Edges from Execution
        builder.add_conditional_edges(
            "execution",
            self.execution_routing,
            {
                "validate": "validation",
                "gordon": "gordon_query",
                "escalate": "escalation",
                "retry": "execution",
            },
        )

        # Edges from Gordon
        builder.add_edge("gordon_query", "execution")

        # Edges from Validation
        builder.add_conditional_edges(
            "validation",
            self.validation_routing,
            {
                "map": "mapping",  # Success path now leads to mapping
                "retry": "execution",
                "escalate": "escalation",
            },
        )

        # Edges from Mapping
        builder.add_edge("mapping", END)

        # Edges from Escalation
        builder.add_edge("escalation", END)

        return builder.compile()

    # --- Routing Logic ---

    def should_escalate(self, state: AgentState):
        if state.get("escalation_requested"):
            return "escalate"
        return "proceed"

    def execution_routing(self, state: AgentState):
        if state.get("escalation_requested"):
            return "escalate"
        # Check if Docker agent needs Gordon
        if state["agent_type"] == "docker" and "gordon" in (
            state["messages"][-1].content.lower()
        ):
            return "gordon"
        if not state.get("success") and state.get("retry_count", 0) < state.get(
            "max_retries", 3
        ):
            return "retry"
        return "validate"

    def validation_routing(self, state: AgentState):
        if state["success"]:
            return "map"  # Success -> Mapping -> End
        if state.get("retry_count", 0) < state.get("max_retries", 3):
            return "retry"
        return "escalate"

    # --- Node Implementations ---

    async def plan_node(self, state: AgentState):
        logger.info(f"[{state['task_id']}] 📋 Node: Planning ({state['agent_type']})")
        await log_agent_activity(
            "maintainer.planning.start",
            {
                "task_id": state["task_id"],
                "agent": state["agent_type"],
                "operation": state["operation"],
            },
        )

        try:
            sop = state["sop_content"]
            instructions = state.get("instructions") or state.get("params", {}).get(
                "instruct", ""
            )
            instruct_block = (
                f"\nADDITIONAL INSTRUCTIONS:\n{instructions}\n" if instructions else ""
            )

            prompt = f"""You are the {state["agent_type"]} agent.
            Your task is: {state["operation"]} with params {state["params"]}.
            {instruct_block}
            SOP:
            {sop}

            Create a detailed step-by-step plan to achieve this.
            If you believe this task is beyond your capability or requires architectural authorization,
            explicitly state "REQUEST_ESCALATION: <reason>".

            Plan format:
            Step 1: ...
            Step 2: ...

            PYTHIA INTEGRATION:
            You have access to Pythia geometric reasoning tools for novel tasks:
            - pythia_surprise: Assess if a task/concept is novel (use before unfamiliar tasks)
            - pythia_encode: Convert concepts to geometric vectors for memory storage
            - pythia_resonate: Search concept memory for related patterns
            - pythia_store_concept: Store learned concepts after completing novel tasks
            - pythia_predict: Get predictions from geometric reasoning

            Use Pythia when:
            1. Task involves unfamiliar patterns or concepts
            2. You need to assess novelty/complexity
            3. You want to store learnings for future retrieval
            4. You need geometric/semantic similarity matching
            """

            resp, model = await self.llm.generate(
                prompt,
                system="You are in the PLANNING phase. Skills-first approach. Use Pythia for novel tasks.",
                headers=state.get("headers"),
            )

            escalate = "REQUEST_ESCALATION" in resp
            reason = None
            if escalate:
                match = re.search(r"REQUEST_ESCALATION:\s*(.*)", resp)
                reason = match.group(1) if match else "Unknown"

            return {
                "plan": resp,
                "escalation_requested": escalate,
                "escalation_reason": reason,
                "messages": [AIMessage(content=resp)],
            }
        except Exception as e:
            logger.error(f"Planning Node Exception: {e}")
            return {
                "escalation_requested": True,
                "escalation_reason": f"Planning failure: {str(e)}",
                "messages": [AIMessage(content=f"Node Exception: {str(e)}")],
            }

    async def execute_node(self, state: AgentState):
        logger.info(
            f"[{state['task_id']}] 🛠️ Node: Execution ({state['agent_type']}) | Headers: {list(state.get('headers', {}).keys())}"
        )
        await log_agent_activity(
            "maintainer.execution.start",
            {
                "task_id": state["task_id"],
                "agent": state["agent_type"],
                "plan": state.get("plan"),
            },
        )

        try:
            plan = state["plan"]
            # Base tools for all agents
            tools = [
                "read_file",
                "write_file",
                "list_dir",
                "grep_search",  # Core FS
                "git_maintainer_operation",
                "mcp_code_crawler",  # Git/Search
                "docker_maintainer_operation",  # Docker
                "serena_chat",
                "serena_analyze_code",  # A2A Consultation
                "discover_infrastructure",
                "scan_workflows",
                "run_graph_linking",
                "get_universal_context",
            ]

            # Add Pythia geometric reasoning tools
            tools.extend(PYTHIA_TOOLS_LIST)

            if state["agent_type"] == "security":
                tools.append("mcp_security_ops")

            tools_str = ", ".join(tools)

            instructions = state.get("instructions") or state.get("params", {}).get(
                "instruct", ""
            )
            instruct_block = (
                f"\nADDITIONAL INSTRUCTIONS:\n{instructions}\n" if instructions else ""
            )

            prompt = f"""You are the {state["agent_type"]} agent EXECUTING the plan.
            PLAN:
            {plan}
            {instruct_block}
            AVAILABLE TOOLS:
            {tools_str}

            {PYTHIA_USAGE_PROMPT}

            SOP:
            {state["sop_content"]}

            Follow the plan. Call tools as needed using the following format:

            Action: tool_name
            Action Input: {{"arg1": "value1"}}

            CRITICAL: Stop after generating the Action Input. Do NOT generate "Observation:" or "Final Answer:" in the same turn. Wait for the system to provide the result.

            When you have completed the task, state:
            Final Answer: <summary of what was done>

            If you hit a blocker you cannot solve, state "REQUEST_ESCALATION: <reason>".
            If you need Gordon AI's help (Docker only), state "QUERY_GORDON: <your question>".
            """

            result = await self._internal_react_run(state, prompt)

            return {
                "execution_log": state.get("execution_log", []) + result["log"],
                "success": result["success"],
                "output": result["output"],
                "escalation_requested": result.get("escalate", False),
                "escalation_reason": result.get("escalate_reason"),
                "messages": [AIMessage(content=result["summary"])],
            }
        except Exception as e:
            logger.error(f"Execution Node Exception: {e}")
            return {
                "escalation_requested": True,
                "escalation_reason": f"Execution failure: {str(e)}",
                "messages": [AIMessage(content=f"Node Exception: {str(e)}")],
            }

    async def validate_node(self, state: AgentState):
        logger.info(f"[{state['task_id']}] ✅ Node: Validation ({state['agent_type']})")
        await log_agent_activity(
            "maintainer.validation.start",
            {"task_id": state["task_id"], "output": state.get("output", "No output")},
        )

        try:
            output = state["output"]
            operation = state["operation"]

            prompt = f"""Validate the outcome of the {state["agent_type"]} operation: {operation}.
            RESULT:
            {output}

            Does this satisfy the task requirements?
            If yes, state "VALIDATION_PASSED".
            If no, state "VALIDATION_FAILED: <reason>".
            """

            resp, _ = await self.llm.generate(prompt, headers=state.get("headers"))
            passed = "VALIDATION_PASSED" in resp

            # Write to Reasoning Bank on success/finish
            if passed or state.get("retry_count", 0) >= state.get("max_retries", 3):
                await self._write_to_reasoning_bank(state, passed)

            return {
                "validation_results": state.get("validation_results", []) + [resp],
                "success": passed,
                "error": None if passed else resp,
                "retry_count": state.get("retry_count", 0) + (0 if passed else 1),
            }
        except Exception as e:
            logger.error(f"Validation Node Exception: {e}")
            return {
                "escalation_requested": True,
                "escalation_reason": f"Validation failure: {str(e)}",
                "success": False,
                "messages": [AIMessage(content=f"Node Exception: {str(e)}")],
            }

    async def escalate_node(self, state: AgentState):
        logger.info(f"[{state['task_id']}] ⚠️ Node: Escalation to Serena")
        await log_agent_activity(
            "maintainer.escalation",
            {"task_id": state["task_id"], "reason": state.get("escalation_reason")},
            severity="WARNING",
        )
        reason = state.get("escalation_reason", "Task failure")

        # Call Serena via MCP or direct internal RPC if allowed
        # Here we use serena_chat tool as the escalation path
        serena_res = await self.mcp.call_tool(
            "serena_chat",
            {
                "message": f"ESCALATION from {state['agent_type']}. Reason: {reason}. State: {state['operation']} - {state['params']}"
            },
            headers=state.get("headers"),
        )

        # Write to Reasoning Bank on failure
        await self._write_to_reasoning_bank(state, success=False)

        return {
            "serena_feedback": serena_res.get("result", "Serena unavailable"),
            "success": False,
            "error": f"Escalated to Serena: {reason}",
        }

    async def gordon_query_node(self, state: AgentState):
        logger.info(f"[{state['task_id']}] 🤖 Node: Gordon AI Query")
        last_msg = state["messages"][-1].content
        match = re.search(r"QUERY_GORDON:\s*(.*)", last_msg)
        query = match.group(1) if match else "Check system health"

        # Call Gordon AI (placeholder for actual tool)
        gordon_res = await self.mcp.call_tool(
            "docker_maintainer_operation",
            {"operation": "query_gordon", "params": {"query": query}},
            headers=state.get("headers"),
        )

        return {
            "gordon_feedback": gordon_res.get("result", "Gordon unavailable"),
            "messages": [
                AIMessage(content=f"Gordon Response: {gordon_res.get('result')}")
            ],
        }

    async def mapping_node(self, state: AgentState):
        logger.info(
            f"[{state['task_id']}] 🗺️ Node: Auto-Mapping (Universal Skill Frame Update)"
        )
        await log_agent_activity(
            "maintainer.mapping",
            {"task_id": state["task_id"], "trigger": "post_success_update"},
        )

        updates = []
        try:
            # 1. Update Infrastructure (Fast)
            # await self.mcp.call_tool("discover_infrastructure", {})

            # 2. Update Code Graph (Scoped if possible, for now full crawl)
            # In future: Detect changed files from 'execution_log' and scope scan.
            crawl_res = await self.mcp.call_tool(
                "crawl_codebase", {"start_dir": "/app"}, headers=state.get("headers")
            )
            updates.append(f"Code: {crawl_res.get('result', 'OK')}")

            # 3. Update Workflows (Fast)
            scan_res = await self.mcp.call_tool(
                "scan_workflows", {}, headers=state.get("headers")
            )
            updates.append(f"Workflows: {scan_res.get('result', 'OK')}")

            # 4. Run Linker (Critical)
            link_res = await self.mcp.call_tool(
                "run_graph_linking", {}, headers=state.get("headers")
            )
            updates.append(f"Links: {link_res.get('result', 'OK')}")

            logger.info(f"[{state['task_id']}] ✅ Auto-Mapping Complete")

        except Exception as e:
            logger.warning(f"[{state['task_id']}] ⚠️ Auto-Mapping Partial/Failed: {e}")
            updates.append(f"Error: {e}")

        return {
            "mapping_report": updates,
            "messages": [
                AIMessage(content=f"Universal Skill Frame Updated: {updates}")
            ],
        }

    async def dream_node(self, state: AgentState):
        """Invoke the geometry kernel simulation for the proposed plan/change.

        This node calls the MCP `geometry_simulate` tool (proxying the kernel API)
        and records the simulation metrics on the state for routing.
        """
        logger.info(
            f"[{state['task_id']}] 🌙 Node: Dream (simulate) - preparing simulation"
        )
        await log_agent_activity(
            "maintainer.dream.start", {"task_id": state["task_id"]}
        )

        try:
            # Build a minimal simulate payload. Prefer explicit proposed_forces in state.
            forces = state.get("proposed_forces") or []
            payload = {
                "mode": "wake",
                "base_state_id": state.get("base_state_id"),
                "forces": forces,
                "attractor_proposals": [],
                "axis_emphasis": state.get("axis_emphasis", {}),
            }

            tool_res = await self.mcp.call_tool(
                "geometry_simulate", payload, headers=state.get("headers")
            )
            sim = tool_res.get("result") if isinstance(tool_res, dict) else tool_res

            # Defensive extraction of stability metric
            stability = None
            if isinstance(sim, dict):
                metrics = sim.get("metrics") or (
                    sim.get("predicted_state", {}).get("metrics")
                    if sim.get("predicted_state")
                    else None
                )
                if metrics and isinstance(metrics, dict):
                    stability = metrics.get("stability") or metrics.get(
                        "stability_index"
                    )
                # Some proxies return nested 'result'->SimulationResult-like dict
                if stability is None:
                    stability = (
                        sim.get("metrics", {}).get("stability")
                        if sim.get("metrics")
                        else None
                    )

            # Fallback checks
            stability = float(stability) if stability is not None else 0.0

            state["dream_simulation"] = sim
            state["dream_stability"] = stability

            await log_agent_activity(
                "maintainer.dream.result",
                {"task_id": state["task_id"], "stability": stability},
            )

            return {
                "simulation": sim,
                "dream_stability": stability,
                "messages": [
                    AIMessage(content=f"[DREAM] Stability index: {stability:.2f}")
                ],
            }

        except Exception as e:
            logger.error(f"Dream Node Exception: {e}")
            await log_agent_activity(
                "maintainer.dream.error",
                {"task_id": state["task_id"], "error": str(e)},
                severity="WARNING",
            )
            # Signal escalate
            return {
                "escalation_requested": True,
                "escalation_reason": f"Dream node failed: {e}",
                "messages": [AIMessage(content=f"Dream node error: {e}")],
            }

    def dream_node_routing(self, state: AgentState):
        """Routing helper for dream_node: replan if low stability, otherwise proceed."""
        stability = state.get("dream_stability", 0.0)
        logger.info(
            f"[{state.get('task_id')}] [DREAM] Routing on stability={stability}"
        )
        if stability < 0.4:
            return "replan"
        return "proceed"

    # --- Helpers ---

    def _get_tools_desc(self, agent_type: str) -> str:
        # Map tools from main.py's AGENT_TOOLS
        # In actual implementation, we'd import AGENT_TOOLS
        return "Toolbelt: Standard MCP tools for your agent role."

    async def _internal_react_run(self, state: AgentState, prompt: str):
        # Real ReAct Loop Implementation
        messages = [{"role": "system", "content": prompt}]
        max_steps = 10
        cur_step = 0
        execution_log = []

        while cur_step < max_steps:
            cur_step += 1

            # Generate LLM response
            # We construct a linear conversation for the LLM client
            conversation_text = ""
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    conversation_text += f"SYSTEM: {content}\n"
                elif role == "user":
                    conversation_text += f"USER: {content}\n"
                elif role == "assistant":
                    conversation_text += f"ASSISTANT: {content}\n"

            try:
                response, _ = await self.llm.generate(
                    conversation_text, headers=state.get("headers")
                )
            except Exception as e:
                logger.error(f"[{state['task_id']}] ❌ LLM Generation Error: {e}")
                if "500" in str(e) or "429" in str(e):
                    # Transient error, wait and retry once
                    await asyncio.sleep(2)
                    response, _ = await self.llm.generate(
                        conversation_text, headers=state.get("headers")
                    )
                else:
                    raise e

            # Clean up hallucinations (some models generate the Observation too)
            if "Observation:" in response:
                logger.warning(
                    f"[{state['task_id']}] ✂️ Stripping hallucinated Observation from response."
                )
                response = response.split("Observation:")[0].strip()

            logger.info(
                f"[{state['task_id']}] 💭 Step {cur_step} Thought: {response[:200]}..."
            )
            messages.append({"role": "assistant", "content": response})
            execution_log.append(f"Step {cur_step} Thought: {response}")

            # Parse for Action
            # Regex for "Action: tool_name" and "Action Input: {json}"
            action_match = re.search(r"Action:\s*(\w+)", response)
            input_match = re.search(
                r"Action Input:\s*(\{.*\}|\[.*\])", response, re.DOTALL
            )

            # Prioritize Action over Final Answer
            if action_match and input_match:
                tool_name = action_match.group(1).strip()
                try:
                    tool_args = json.loads(input_match.group(1).strip())

                    logger.info(
                        f"[{state['task_id']}] 🛠️ CALL: {tool_name}({tool_args})"
                    )

                    # Execute Tool via MCP
                    tool_res = await self.mcp.call_tool(
                        tool_name, tool_args, headers=state.get("headers")
                    )
                    result_str = str(
                        tool_res.get("result", tool_res.get("error", "Unknown Error"))
                    )

                    logger.info(
                        f"[{state['task_id']}] 📥 Observation: {result_str[:100]}..."
                    )
                    observation = f"Observation: {result_str}"
                    messages.append({"role": "user", "content": observation})
                    execution_log.append(
                        f"Step {cur_step} Result: {result_str[:200]}..."
                    )

                except json.JSONDecodeError:
                    messages.append(
                        {
                            "role": "user",
                            "content": "Observation: Invalid JSON in Action Input.",
                        }
                    )
                except Exception as e:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Observation: Tool execution failed: {e}",
                        }
                    )

            elif "Final Answer:" in response:
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"[{state['task_id']}] ✅ Final Answer reached.")
                return {
                    "success": True,
                    "output": final_answer,
                    "summary": f"Completed task in {cur_step} steps. Output: {final_answer[:100]}...",
                    "log": execution_log,
                }
            else:
                # If no action found but no final answer, prompt to convert thought to action
                if cur_step == max_steps:
                    return {
                        "success": False,
                        "output": "Max steps reached without Final Answer.",
                        "summary": "Agent timed out.",
                        "log": execution_log,
                    }
                # Implicit continuation or just thinking
                continue

        return {
            "success": False,
            "output": "ReAct loop limit reached.",
            "summary": "Failed to complete task.",
            "log": execution_log,
        }

    async def _write_to_reasoning_bank(self, state: AgentState, success: bool):
        """Write execution trace to Reasoning Bank (JSON)"""
        try:
            import datetime

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"maintainer_task_{state['task_id']}_{timestamp}.json"
            path = os.path.join("/app/shared_storage/reasoning_bank", filename)

            # Ensure directory exists (it should, volume mounted)
            os.makedirs(os.path.dirname(path), exist_ok=True)

            data = {
                "task_id": state["task_id"],
                "agent_type": state["agent_type"],
                "operation": state["operation"],
                "success": success,
                "execution_log": state.get("execution_log", []),
                "validation_results": state.get("validation_results", []),
                "escalation_reason": state.get("escalation_reason"),
                "timestamp": timestamp,
            }

            # If failure, add Nurture Hint
            if not success:
                data["nurture_recommendation"] = (
                    f"Refine SOP for {state['agent_type']} or check MCP skills."
                )

            with open(path, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"🧠 [REASONING] Wrote to {filename}")
        except Exception as e:
            logger.error(f"Failed to write to Reasoning Bank: {e}")
