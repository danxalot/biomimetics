"""
LangChain Tools Integration
Provides direct LangChain tool implementations for various APIs
"""

import os
import requests
from typing import Optional, Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class LangSearchWebSearchInput(BaseModel):
    """Input schema for LangSearch web search tool"""
    query: str = Field(description="Search query string")
    count: Optional[int] = Field(default=10, description="Number of results to return (1-10)")
    freshness: Optional[str] = Field(
        default="noLimit",
        description="Time range filter: oneDay, oneWeek, oneMonth, oneYear, noLimit"
    )
    summary: Optional[bool] = Field(default=True, description="Include detailed summaries")


@tool("langsearch_web_search", args_schema=LangSearchWebSearchInput)
def langsearch_web_search(
    query: str,
    count: int = 10,
    freshness: str = "noLimit",
    summary: bool = True
) -> str:
    """
    Perform web search using LangSearch Web Search API.

    This tool searches the internet for current information and returns
    formatted results including titles, URLs, and content summaries.

    Args:
        query: Search keywords or question
        count: Number of results to return (max 10)
        freshness: Time filter - "oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit"
        summary: Whether to include detailed content summaries

    Returns:
        Formatted search results with citations, titles, URLs, and content
    """
    api_key = os.getenv("LANGSEARCH_API_KEY")
    if not api_key:
        return "Error: LANGSEARCH_API_KEY environment variable not set"

    # Validate inputs
    valid_freshness = ["oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit"]
    if freshness not in valid_freshness:
        return f"Error: Invalid freshness value. Must be one of: {', '.join(valid_freshness)}"

    if not isinstance(count, int) or count < 1 or count > 10:
        return "Error: Count must be an integer between 1 and 10"

    url = "https://api.langsearch.com/v1/web-search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "query": query,
        "freshness": freshness,
        "summary": summary,
        "count": count
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)

        if response.status_code == 200:
            json_response = response.json()

            # Check API response code
            if json_response.get("code") != 200:
                error_msg = json_response.get("msg", "Unknown API error")
                return f"Search API request failed: {error_msg}"

            data_section = json_response.get("data", {})
            web_pages = data_section.get("webPages", {}).get("value", [])

            if not web_pages:
                return f"No search results found for query: '{query}'"

            # Format results
            formatted_results = []
            formatted_results.append(f"🔍 Web Search Results for: '{query}'")
            formatted_results.append("=" * 60)

            for idx, page in enumerate(web_pages, start=1):
                title = page.get('name', 'No title')
                url = page.get('url', 'No URL')
                content = page.get('summary', 'No summary available')

                formatted_results.append(f"Citation {idx}:")
                formatted_results.append(f"Title: {title}")
                formatted_results.append(f"URL: {url}")
                if summary and content:
                    # Truncate long summaries for readability
                    if len(content) > 500:
                        content = content[:500] + "..."
                    formatted_results.append(f"Summary: {content}")
                formatted_results.append("")

            return "\n".join(formatted_results).strip()

        elif response.status_code == 401:
            return "Error: Invalid LangSearch API key"
        elif response.status_code == 429:
            return "Error: Rate limit exceeded. Please try again later."
        else:
            return f"Search API request failed with status {response.status_code}: {response.text}"

    except requests.exceptions.Timeout:
        return "Error: Search request timed out"
    except requests.exceptions.RequestException as e:
        return f"Error: Network request failed: {str(e)}"
    except Exception as e:
        return f"Error: Unexpected error during search: {str(e)}"


class LangSearchRerankInput(BaseModel):
    """Input schema for LangSearch semantic rerank tool"""
    query: str = Field(description="Search query for relevance ranking")
    documents: list[str] = Field(description="List of documents to rerank")
    top_n: Optional[int] = Field(default=None, description="Number of top results to return")


@tool("langsearch_semantic_rerank", args_schema=LangSearchRerankInput)
def langsearch_semantic_rerank(
    query: str,
    documents: list[str],
    top_n: Optional[int] = None
) -> str:
    """
    Perform semantic reranking of documents using LangSearch API.

    This tool ranks documents by semantic relevance to a query,
    useful for improving search result quality or document filtering.

    Args:
        query: The search query for relevance comparison
        documents: List of document texts to rerank
        top_n: Optional limit on number of results to return

    Returns:
        Reranked documents with relevance scores
    """
    api_key = os.getenv("LANGSEARCH_API_KEY")
    if not api_key:
        return "Error: LANGSEARCH_API_KEY environment variable not set"

    if not documents or len(documents) == 0:
        return "Error: Documents list cannot be empty"

    if len(documents) > 50:  # API limit
        return "Error: Maximum 50 documents allowed for reranking"

    url = "https://api.langsearch.com/v1/rerank"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "query": query,
        "documents": documents,
        "model": "langsearch-reranker-v1",
        "top_n": top_n
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)

        if response.status_code == 200:
            json_response = response.json()

            if json_response.get("code") != 200:
                error_msg = json_response.get("msg", "Unknown API error")
                return f"Rerank API request failed: {error_msg}"

            results = json_response.get("results", [])

            if not results:
                return "No reranking results returned"

            # Format results
            formatted_results = []
            formatted_results.append(f"🔄 Semantic Rerank Results for: '{query}'")
            formatted_results.append(f"Model: {json_response.get('model', 'unknown')}")
            formatted_results.append(f"Total documents: {len(documents)}")
            formatted_results.append("=" * 60)

            for idx, result in enumerate(results, 1):
                doc_index = result.get("index", "N/A")
                score = result.get("relevance_score", 0)

                formatted_results.append(f"Rank {idx}:")
                formatted_results.append(f"  Original Position: {doc_index}")
                formatted_results.append(f"  Relevance Score: {score:.4f}")

                # Show document preview
                if 0 <= doc_index < len(documents):
                    doc_text = documents[doc_index]
                    preview = doc_text[:200] + "..." if len(doc_text) > 200 else doc_text
                    formatted_results.append(f"  Document: {preview}")

                formatted_results.append("")

            return "\n".join(formatted_results).strip()

        elif response.status_code == 401:
            return "Error: Invalid LangSearch API key"
        elif response.status_code == 429:
            return "Error: Rate limit exceeded. Please try again later."
        else:
            return f"Rerank API request failed with status {response.status_code}: {response.text}"

    except requests.exceptions.Timeout:
        return "Error: Rerank request timed out"
    except requests.exceptions.RequestException as e:
        return f"Error: Network request failed: {str(e)}"
    except Exception as e:
        return f"Error: Unexpected error during reranking: {str(e)}"


# Export available tools
LANGCHAIN_TOOLS = [
    langsearch_web_search,
    langsearch_semantic_rerank
]

__all__ = [
    "langsearch_web_search",
    "langsearch_semantic_rerank",
    "LANGCHAIN_TOOLS"
]