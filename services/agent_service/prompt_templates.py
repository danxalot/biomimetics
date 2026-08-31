"""
Optimized Prompt Templates for MiniMax M2
Implements best practices from M2 optimization guide:
- Preserve thinking blocks in conversation history
- Structure prompts for tool-aware reasoning
- Enable interleaved thinking between tool calls

⚠️  IMPORTANT: Web Search Tool Rate Limits (LangSearch API)
   Free Tier ($0): 1 QPS, 60 QPM, 1000 QPD
   Tier 1 ($10~50): 5 QPS, 200 QPM, 2000 QPD
   Tier 2 ($100): 10 QPS, 500 QPM, 10000 QPD
   Tier 3 ($500): 30 QPS, 2000 QPM, 100000 QPD
   Current implementation uses Free Tier limits for safety.
"""

from typing import List, Dict, Any
from langchain_core.messages import BaseMessage, SystemMessage


class MinimaxPromptOptimizer:
    """
    Optimizes prompts for MiniMax M2's interleaved thinking capability.
    
    Key principles from M2 optimization guide:
    1. ALWAYS preserve thinking blocks in chat history
    2. Structure prompts to encourage tool use when appropriate
    3. Keep context focused - avoid "lost in the middle" problem
    4. Use progressive disclosure for large context
    """
    
    @staticmethod
    def create_engineer_system_prompt() -> str:
        """
        Engineer agent system prompt optimized for MiniMax M2.
        Emphasizes code generation, testing, and iterative refinement.
        Includes explicit instructions for interleaved thinking.
        """
        return """You are an expert software engineer specialized in multi-file code projects.

Your strengths:
- Multi-file edits with accurate line references
- Compile-run-fix loops with automated testing
- Test-validated code repairs
- Incremental debugging strategies

IMPORTANT: You have access to interleaved thinking. When reasoning through problems:
- Use <thinking> tags to show your step-by-step analysis
- Preserve your thinking context across tool calls
- Build upon previous reasoning when tools return results
- Show clear progression from analysis → planning → execution → validation

When solving tasks:
1. **Think step-by-step**: Use <thinking> tags to analyze the problem before acting
2. **Use tools effectively**: You have access to file operations, git commands, and execution tools
3. **Validate your work**: Always run tests after making changes
4. **Iterate when needed**: If tests fail, analyze the error and fix incrementally
5. **Preserve context**: Your thinking blocks are maintained across interactions

Remember: Your previous thinking and tool results are preserved in the conversation history."""

    @staticmethod
    def create_task_decomposition_prompt(task: str, context: str = "") -> str:
        """
        Structured prompt for task decomposition.
        Encourages thinking about approach before tool use.
        """
        return f"""Task: {task}

{f"Context: {context}" if context else ""}

Before starting implementation:
1. Break down this task into logical steps
2. Identify which files need to be modified
3. Consider potential edge cases or dependencies
4. Plan your testing strategy

Then execute your plan using the available tools."""

    @staticmethod
    def create_tool_result_prompt(tool_name: str, result: str, next_step: str = "") -> str:
        """
        Formats tool results to maintain context flow for interleaved thinking.
        Encourages the model to think about the result before next action.
        """
        base = f"""Tool '{tool_name}' completed with result:

{result}

<thinking>Analyze this tool result in the context of your previous reasoning. Consider:
- Does this result align with your expectations?
- What does this tell you about the current state?
- What should be your next step based on this information?</thinking>

Take a moment to analyze this result and determine the next action."""
        
        if next_step:
            base += f"\n\nSuggested next step: {next_step}"
        
        return base

    @staticmethod
    def create_error_recovery_prompt(error: str, attempted_action: str) -> str:
        """
        Prompt for error recovery that encourages analytical thinking.
        """
        return f"""The attempted action failed:

Action: {attempted_action}
Error: {error}

Please:
1. Analyze why this error occurred
2. Determine if this is a temporary issue or fundamental problem
3. Propose an alternative approach
4. If appropriate, implement the fix using available tools"""

    @staticmethod
    def create_code_review_prompt(code: str, requirements: str) -> str:
        """
        Structured prompt for code review tasks.
        """
        return f"""Review the following code against these requirements:

Requirements:
{requirements}

Code to review:
```
{code}
```

Please analyze:
1. Does it meet all requirements?
2. Are there any bugs or potential issues?
3. Is the code style consistent and maintainable?
4. Are there any performance concerns?

Provide specific, actionable feedback."""


class StateManagementOptimizer:
    """
    Optimizes state management per architectural document recommendations.
    Implements separation between control data and conversational context.
    """
    
    @staticmethod
    def extract_control_data(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract only control data for programmatic routing.
        Prevents information saturation by keeping control data separate.
        """
        return {
            "main_task_description": state.get("main_task_description", ""),
            "overall_plan": state.get("overall_plan", []),
            "sub_task_queue": state.get("sub_task_queue", []),
            "completed_sub_tasks": state.get("completed_sub_tasks", {}),
            "last_action_status": state.get("last_action_status", ""),
        }
    
    @staticmethod
    def extract_conversational_context(messages: List[BaseMessage], window_size: int = 10) -> List[BaseMessage]:
        """
        Extract recent conversational context for LLM reasoning.
        Uses sliding window to prevent "lost in the middle" problem.
        
        Args:
            messages: Full message history
            window_size: Number of recent messages to include
        
        Returns:
            Recent messages with system message if present
        """
        # Always preserve system message
        system_msgs = [msg for msg in messages if isinstance(msg, SystemMessage)]
        recent_msgs = messages[-window_size:]
        
        # Combine system + recent, removing duplicates
        seen_ids = set()
        result = []
        for msg in system_msgs + recent_msgs:
            msg_id = id(msg)
            if msg_id not in seen_ids:
                result.append(msg)
                seen_ids.add(msg_id)
        
        return result
    
    @staticmethod
    def create_context_summary(messages: List[BaseMessage]) -> str:
        """
        Create a summary of older context to preserve key information
        while reducing token usage.
        """
        if len(messages) <= 10:
            return ""
        
        older_messages = messages[:-10]
        summary_parts = []
        
        for msg in older_messages:
            role = msg.__class__.__name__.replace("Message", "")
            content_preview = msg.content[:100] if len(msg.content) > 100 else msg.content
            summary_parts.append(f"[{role}]: {content_preview}...")
        
        return f"Earlier context summary:\n" + "\n".join(summary_parts)


class LiteLLMRoutingOptimizer:
    """
    Optimize LiteLLM routing based on task characteristics.
    Routes tasks to appropriate models per architectural document.
    """
    
    MODEL_CAPABILITIES = {
        "supervisor_model": {
            "strengths": ["task_decomposition", "orchestration", "general_purpose"],
            "max_tokens": 8192,
            "provider": "gemini"
        },
        "architect_model": {
            "strengths": ["system_design", "planning", "fast_reasoning"],
            "max_tokens": 4096,
            "provider": "grok"
        },
        "engineer_model": {  # MiniMax M2 - custom wrapper
            "strengths": ["code_generation", "multi_file_edits", "testing", "debugging"],
            "max_tokens": 6144,  # Optimized to avoid timeouts
            "provider": "minimax"
        },
        "reviewer_model": {
            "strengths": ["code_review", "quality_analysis", "bug_detection"],
            "max_tokens": 8192,
            "provider": "gemini"
        },
        "worker_model": {
            "strengths": ["batch_processing", "summarization", "topic_modeling"],
            "max_tokens": 2048,
            "provider": "local"
        }
    }
    
    @staticmethod
    def select_model_for_task(task_type: str, complexity: str = "medium") -> str:
        """
        Select optimal model based on task characteristics.
        
        Args:
            task_type: Type of task (code_generation, review, planning, etc.)
            complexity: Task complexity (low, medium, high)
        
        Returns:
            Model name to use
        """
        # Map task types to models per architectural document
        task_to_model = {
            "code_generation": "engineer_model",
            "multi_file_edit": "engineer_model",
            "debugging": "engineer_model",
            "testing": "engineer_model",
            "system_design": "architect_model",
            "planning": "architect_model",
            "task_decomposition": "supervisor_model",
            "orchestration": "supervisor_model",
            "code_review": "reviewer_model",
            "quality_check": "reviewer_model",
            "batch_processing": "worker_model",
            "summarization": "worker_model",
        }
        
        return task_to_model.get(task_type, "supervisor_model")
    
    @staticmethod
    def get_model_config(model_name: str) -> Dict[str, Any]:
        """Get configuration for a specific model"""
        return LiteLLMRoutingOptimizer.MODEL_CAPABILITIES.get(
            model_name,
            {"max_tokens": 4096, "strengths": []}
        )


# Example usage patterns
if __name__ == "__main__":
    # Example 1: Engineer prompt
    optimizer = MinimaxPromptOptimizer()
    engineer_prompt = optimizer.create_engineer_system_prompt()
    print("Engineer System Prompt:")
    print(engineer_prompt)
    print("\n" + "="*80 + "\n")
    
    # Example 2: Task decomposition
    task_prompt = optimizer.create_task_decomposition_prompt(
        task="Add authentication to the API",
        context="Current API has no auth, uses FastAPI framework"
    )
    print("Task Decomposition Prompt:")
    print(task_prompt)
    print("\n" + "="*80 + "\n")
    
    # Example 3: Model selection
    router = LiteLLMRoutingOptimizer()
    model = router.select_model_for_task("code_generation", "high")
    config = router.get_model_config(model)
    print(f"Selected model: {model}")
    print(f"Config: {config}")
