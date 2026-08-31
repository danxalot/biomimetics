import os
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any

class LangSearchClient:
    """Client for LangSearch API operations"""
    
    def __init__(self, api_key: Optional[str] = None):
        # Try env vars first, then file
        self.api_key = api_key or os.getenv("LANGSEARCH_API_KEY") or os.getenv("LANGSEARCH_API")
        
        if not self.api_key:
            try:
                # Try reading from mounted secrets
                # Container mount: /app/arca -> Host: /home/ubuntu/ARCA
                secret_file = Path("/app/arca/.secrets/LANGSEARCH_API")
                if secret_file.exists():
                    content = secret_file.read_text().strip()
                    if content.startswith("LANGSEARCH_API="):
                        self.api_key = content.split("=", 1)[1].strip()
                    else:
                        self.api_key = content
            except Exception:
                pass
                
        self.base_url = "https://api.langsearch.com/v1"
        
    def web_search(self, query: str, count: int = 10, freshness: str = "noLimit", summary: bool = True) -> str:
        """
        Perform web search using LangSearch Web Search API.
        
        Args:
            query: Search keywords or question
            count: Number of results to return (max 10)
            freshness: Time filter - "oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit"
            summary: Whether to include detailed content summaries
            
        Returns:
            Formatted search results string
        """
        if not self.api_key:
            return "Error: LANGSEARCH_API_KEY environment variable not set"

        # Validate inputs
        valid_freshness = ["oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit"]
        if freshness not in valid_freshness:
            return f"Error: Invalid freshness value. Must be one of: {', '.join(valid_freshness)}"

        if not isinstance(count, int) or count < 1 or count > 10:
            return "Error: Count must be an integer between 1 and 10"

        url = f"{self.base_url}/web-search"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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

    def semantic_rerank(self, query: str, documents: List[str], top_n: Optional[int] = None) -> str:
        """
        Perform semantic reranking of documents using LangSearch API.
        
        Args:
            query: The search query for relevance comparison
            documents: List of document texts to rerank
            top_n: Optional limit on number of results to return
            
        Returns:
            Formatted rerank results string
        """
        if not self.api_key:
            return "Error: LANGSEARCH_API_KEY environment variable not set"

        if not documents or len(documents) == 0:
            return "Error: Documents list cannot be empty"

        if len(documents) > 50:  # API limit
            return "Error: Maximum 50 documents allowed for reranking"

        url = f"{self.base_url}/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
