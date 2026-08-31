#!/usr/bin/env python3
"""Test the GeminiCloudAICompanionWrapper"""
import sys
import asyncio
sys.path.insert(0, '/home/ubuntu/ARCA/services/agent_service')

from langgraph_agent import GeminiCloudAICompanionWrapper
from langchain_core.messages import HumanMessage, SystemMessage

async def test_gemini():
    print("=" * 60)
    print("Testing Gemini Cloud AI Companion Wrapper")
    print("=" * 60)
    
    try:
        # Initialize the wrapper
        print("\n1. Initializing Gemini wrapper...")
        wrapper = GeminiCloudAICompanionWrapper(
            project_id="arca-471022",
            credentials_path="/home/ubuntu/ARCA/.secrets/gemini-reviewer-agent-credentials.json",
            model="gemini-1.5-pro"
        )
        print("✓ Wrapper initialized")
        
        # Test a simple message
        print("\n2. Sending test message...")
        messages = [
            SystemMessage(content="You are a helpful AI assistant."),
            HumanMessage(content="Say 'Hello from Gemini Cloud AI Companion!' in exactly 6 words.")
        ]
        
        response = await wrapper.ainvoke(messages)
        print(f"✓ Response received: {response.content}")
        
        print("\n" + "=" * 60)
        print("✓ Gemini Cloud AI Companion wrapper is working!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gemini())
