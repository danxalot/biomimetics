#!/usr/bin/env python3
"""
Test script for LangChain tools integration
"""

import os
import sys
import asyncio

# Add current directory and MCP server to path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, '/home/ubuntu/ARCA/services/mcp_server')

from langchain_tools import langsearch_web_search, langsearch_semantic_rerank
from mcp_server import load_api_keys_from_secrets


async def test_langchain_tools():
    """Test the LangChain tool implementations"""

    print("🧪 Testing LangChain Tools")
    print("=" * 40)

    # Test 1: Web Search Tool
    print("\n🔍 Testing Web Search Tool...")
    try:
        result = await langsearch_web_search.ainvoke({
            "query": "test query",
            "count": 2,
            "freshness": "noLimit"
        })
        if "Error:" in result:
            print(f"❌ Web search failed: {result}")
        else:
            print("✅ Web search successful")
            print(f"   Preview: {result[:100]}...")
    except Exception as e:
        print(f"❌ Web search error: {e}")

    # Test 2: Semantic Rerank Tool
    print("\n🔄 Testing Semantic Rerank Tool...")
    try:
        docs = [
            "Artificial intelligence is transforming technology",
            "The weather today is sunny",
            "Machine learning is a subset of AI"
        ]
        result = await langsearch_semantic_rerank.ainvoke({
            "query": "artificial intelligence",
            "documents": docs,
            "top_n": 2
        })
        if "Error:" in result:
            print(f"❌ Rerank failed: {result}")
        else:
            print("✅ Semantic rerank successful")
            print(f"   Preview: {result[:100]}...")
    except Exception as e:
        print(f"❌ Rerank error: {e}")

    print("\n" + "=" * 40)
    print("✅ LangChain tools test completed")


if __name__ == "__main__":
    # Load environment variables from secrets
    load_api_keys_from_secrets()

    asyncio.run(test_langchain_tools())