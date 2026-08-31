#!/usr/bin/env python3
"""
LangChain Tools Integration Example
Demonstrates how to integrate LangSearch tools directly into LangGraph agents
"""

import os
import asyncio
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

# Import our custom tools
from langchain_tools import langsearch_web_search, langsearch_semantic_rerank, LANGCHAIN_TOOLS
# Import existing agent components
from langgraph_agent import MinimaxAnthropicWrapper
from mcp_client import MCPClient


class LangChainToolAgent:
    """
    Example agent that integrates LangChain tools directly with LangGraph
    This shows the alternative to using MCP server for tool calls
    """

    def __init__(self, model_name: str = "minimax"):
        """Initialize agent with specified model"""
        self.model_name = model_name
        self.tools = LANGCHAIN_TOOLS
        self.tool_map = {tool.name: tool for tool in self.tools}

        # Initialize LLM based on model choice
        if model_name == "minimax":
            # Use existing MiniMax wrapper
            self.llm = MinimaxAnthropicWrapper(
                base_url="https://api.minimax.chat/v1",
                api_key=os.getenv("MINIMAX_API_KEY", ""),
                model="MiniMax-Text-01"
            )
        elif model_name == "openai":
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        elif model_name == "anthropic":
            self.llm = ChatAnthropic(
                model="claude-3-sonnet-20240229",
                temperature=0,
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        else:
            raise ValueError(f"Unsupported model: {model_name}")

        # Initialize MCP client for comparison
        self.mcp_client = MCPClient("http://localhost:8085")

    def _format_tools_for_llm(self) -> str:
        """Format tool descriptions for the LLM"""
        tool_descriptions = []
        for tool in self.tools:
            desc = f"- {tool.name}: {tool.description}"
            tool_descriptions.append(desc)
        return "\n".join(tool_descriptions)

    async def _call_tools_directly(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tools directly (LangChain approach)"""
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})

            if tool_name in self.tool_map:
                try:
                    # Call tool directly
                    tool = self.tool_map[tool_name]
                    result = await tool.arun(**tool_args) if hasattr(tool, 'arun') else tool.run(**tool_args)
                    results.append({
                        "tool_call_id": tool_call.get("id"),
                        "role": "tool",
                        "name": tool_name,
                        "content": result
                    })
                except Exception as e:
                    results.append({
                        "tool_call_id": tool_call.get("id"),
                        "role": "tool",
                        "name": tool_name,
                        "content": f"Error executing tool: {str(e)}"
                    })
            else:
                results.append({
                    "tool_call_id": tool_call.get("id"),
                    "role": "tool",
                    "name": tool_name,
                    "content": f"Unknown tool: {tool_name}"
                })

        return results

    async def _call_tools_via_mcp(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tools via MCP server (existing approach)"""
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})

            try:
                # Map tool names to MCP method names
                mcp_method_map = {
                    "langsearch_web_search": "web_search",
                    "langsearch_semantic_rerank": "semantic_rerank"
                }

                mcp_method = mcp_method_map.get(tool_name, tool_name)

                # Call via MCP
                mcp_result = self.mcp_client._call_mcp(mcp_method, tool_args)
                results.append({
                    "tool_call_id": tool_call.get("id"),
                    "role": "tool",
                    "name": tool_name,
                    "content": mcp_result.get("result", "MCP call failed")
                })

            except Exception as e:
                results.append({
                    "tool_call_id": tool_call.get("id"),
                    "role": "tool",
                    "name": tool_name,
                    "content": f"MCP error: {str(e)}"
                })

        return results

    async def run_with_tools(self, query: str, use_mcp: bool = False) -> Dict[str, Any]:
        """
        Run agent with tool calling capabilities

        Args:
            query: User question
            use_mcp: If True, use MCP server; if False, call tools directly

        Returns:
            Agent response with tool usage information
        """
        system_prompt = f"""You are a helpful AI assistant with access to web search tools.

Available tools:
{self._format_tools_for_llm()}

When you need current information or to search the web, use the langsearch_web_search tool.
For document ranking tasks, use the langsearch_semantic_rerank tool.

Always use tools when the user asks questions that require current information or web search."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        # First call to LLM to see if tools are needed
        llm_response = await self.llm.ainvoke(messages)

        # Check if LLM wants to use tools
        tool_calls = []
        if hasattr(llm_response, 'tool_calls') and llm_response.tool_calls:
            tool_calls = llm_response.tool_calls
        elif hasattr(llm_response, 'additional_kwargs') and 'tool_calls' in llm_response.additional_kwargs:
            tool_calls = llm_response.additional_kwargs['tool_calls']

        if not tool_calls:
            # No tools needed, return direct response
            return {
                "response": llm_response.content if hasattr(llm_response, 'content') else str(llm_response),
                "tools_used": [],
                "method": "direct" if not use_mcp else "mcp"
            }

        # Execute tools
        if use_mcp:
            tool_results = await self._call_tools_via_mcp(tool_calls)
            method = "mcp"
        else:
            tool_results = await self._call_tools_directly(tool_calls)
            method = "direct"

        # Add tool results to conversation
        messages.extend(tool_results)

        # Get final response from LLM
        final_response = await self.llm.ainvoke(messages)

        return {
            "response": final_response.content if hasattr(final_response, 'content') else str(final_response),
            "tools_used": [call.get("name") for call in tool_calls],
            "method": method,
            "tool_results": tool_results
        }


async def main():
    """Example usage comparing direct LangChain tools vs MCP approach"""

    # Initialize agent
    agent = LangChainToolAgent(model_name="minimax")

    query = "Why is the sky blue? Please search for a scientific explanation."

    print("🔍 Testing LangChain Tools Integration")
    print("=" * 50)
    print(f"Query: {query}")
    print()

    # Test direct LangChain tool calls
    print("🛠️  Method 1: Direct LangChain Tool Calls")
    print("-" * 40)
    try:
        result_direct = await agent.run_with_tools(query, use_mcp=False)
        print(f"Response: {result_direct['response'][:200]}...")
        print(f"Tools used: {result_direct['tools_used']}")
        print(f"Method: {result_direct['method']}")
    except Exception as e:
        print(f"❌ Direct method failed: {e}")
    print()

    # Test MCP server approach
    print("🌐 Method 2: Via MCP Server")
    print("-" * 40)
    try:
        result_mcp = await agent.run_with_tools(query, use_mcp=True)
        print(f"Response: {result_mcp['response'][:200]}...")
        print(f"Tools used: {result_mcp['tools_used']}")
        print(f"Method: {result_mcp['method']}")
    except Exception as e:
        print(f"❌ MCP method failed: {e}")
    print()

    print("📊 Comparison:")
    print("- Direct LangChain: Faster, simpler, direct API calls")
    print("- MCP Server: Centralized tool management, better for complex workflows")


if __name__ == "__main__":
    asyncio.run(main())