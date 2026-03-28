"""
Memory Orchestrator Cloud Function - Token Budgeted Gateway
Routes queries to MuninnDB (working memory) and MemU (archive memory)
Implements token budgeting to stay within API limits
"""

import os
import json
import urllib.request
import urllib.error
import functions_framework

# Configuration
# NOTE: Using GCP Internal IP 10.128.0.3 (requires Serverless VPC Access).
MUNINN_VM_URL = os.environ.get("MUNINN_VM_URL", "http://10.128.0.3:8097")
MEMU_URL = os.environ.get("MEMU_URL", "https://memu-757330161781.us-central1.run.app")

# Token budgeting configuration
MAX_TOTAL_TOKENS = int(os.environ.get("MAX_TOTAL_TOKENS", "2000"))
MUNINN_TOKEN_BUDGET = int(os.environ.get("MUNINN_TOKEN_BUDGET", "1500"))
MEMU_TOKEN_BUDGET = int(os.environ.get("MEMU_TOKEN_BUDGET", "500"))
MIN_CONFIDENCE_THRESHOLD = float(os.environ.get("MIN_CONFIDENCE", "0.3"))


def estimate_tokens(text: str) -> int:
    """Simple token estimation (4 chars ≈ 1 token for English)"""
    if not text:
        return 0
    return len(text) // 4


def truncate_to_token_budget(text: str, budget: int) -> str:
    """Truncate text to fit within token budget"""
    if estimate_tokens(text) <= budget:
        return text
    # Truncate to fit budget (4 chars per token estimate)
    max_chars = budget * 4
    return text[:max_chars] + "..."


def call_endpoint(url: str, payload: dict, timeout: int = 30) -> dict:
    """Make HTTP POST request to endpoint"""
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "results": []}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {str(e)}", "results": []}
    except Exception as e:
        return {"error": str(e), "results": []}


def apply_token_budget(results: list, budget: int, source: str) -> list:
    """
    Apply token budgeting to results based on ACT-R confidence scores.
    Returns results sorted by confidence, truncated to fit budget.
    """
    if not results:
        return []
    
    # Sort by confidence (highest first) - ACT-R retrieval principle
    sorted_results = sorted(
        results,
        key=lambda x: x.get('confidence', x.get('relevance', 0)),
        reverse=True
    )
    
    budgeted_results = []
    tokens_used = 0
    
    for result in sorted_results:
        content = result.get('content', '')
        content_tokens = estimate_tokens(content)
        
        # Check if adding this result would exceed budget
        if tokens_used + content_tokens > budget:
            # Truncate this result to fit remaining budget
            remaining = budget - tokens_used
            if remaining > 10:  # At least 10 tokens worth
                truncated = truncate_to_token_budget(content, remaining)
                result['content'] = truncated
                result['truncated'] = True
                budgeted_results.append(result)
            break
        
        budgeted_results.append(result)
        tokens_used += content_tokens
        
        # Stop if we've used 90% of budget (safety margin)
        if tokens_used >= budget * 0.9:
            break
    
    return budgeted_results


@functions_framework.http
def process_memory_request(request):
    """
    HTTP Cloud Function - Token Budgeted Memory Gateway
    
    Receives from:
    - Cloudflare Worker (Notion updates)
    - Copaw (direct queries)
    
    Routes to:
    - MuninnDB: Working memory (ACT-R, Hebbian learning)
    - MemU: Archive memory (Gemini embeddings, Qdrant)
    
    Returns unified results within token budget.
    """
    # Parse incoming JSON
    request_json = request.get_json(silent=True)
    
    if not request_json:
        return (json.dumps({
            "status": "error",
            "error": "Invalid JSON payload"
        }), 400, {'Content-Type': 'application/json'})
    
    # Determine operation type
    operation = request_json.get("operation", "search")
    
    if operation == "search" or "query" in request_json:
        return handle_search(request_json)
    elif operation == "memorize" or "content" in request_json:
        return handle_memorize(request_json)
    else:
        return (json.dumps({
            "status": "error",
            "error": f"Unknown operation: {operation}"
        }), 400, {'Content-Type': 'application/json'})


def handle_search(payload: dict) -> tuple:
    """
    Handle search query with token budgeting.
    Queries both MuninnDB (working) and MemU (archive).
    """
    query = payload.get("query", "")
    user_id = payload.get("user_id", "default")
    
    # Token budget allocation
    muninn_budget = MUNINN_TOKEN_BUDGET
    memu_budget = MEMU_TOKEN_BUDGET
    
    # Query MuninnDB (working memory)
    muninn_payload = {
        "query": query,
        "user_id": user_id,
        "limit": 20,  # Get more, filter by token budget later
        "min_confidence": MIN_CONFIDENCE_THRESHOLD
    }
    muninn_results = call_endpoint(f"{MUNINN_VM_URL}/Activate", muninn_payload)
    
    # Fallback to /search if /Activate doesn't exist
    if "error" in muninn_results or not muninn_results.get("results"):
        muninn_results = call_endpoint(f"{MUNINN_VM_URL}/search", {
            "query": query,
            "limit": 20
        })
    
    # Apply token budgeting to MuninnDB results
    muninn_budgeted = apply_token_budget(
        muninn_results.get("results", []),
        muninn_budget,
        "muninn_working"
    )
    
    # Query MemU (archive memory)
    memu_payload = {
        "query": query,
        "user_id": user_id,
        "limit": 10,
        "min_confidence": MIN_CONFIDENCE_THRESHOLD
    }
    memu_results = call_endpoint(f"{MEMU_URL}/search", memu_payload)
    
    # Apply token budgeting to MemU results
    memu_budgeted = apply_token_budget(
        memu_results.get("results", []),
        memu_budget,
        "memu_archive"
    )
    
    # Combine results (working memory has priority - ACT-R principle)
    all_results = muninn_budgeted + memu_budgeted
    
    # Calculate total tokens
    total_tokens = sum(
        estimate_tokens(r.get('content', ''))
        for r in all_results
    )
    
    # Build response
    response = {
        "status": "success",
        "source": "unified",
        "query": query,
        "user_id": user_id,
        "results": all_results,
        "token_usage": {
            "total": total_tokens,
            "budget": MAX_TOTAL_TOKENS,
            "muninn_working": sum(estimate_tokens(r.get('content', '')) for r in muninn_budgeted),
            "memu_archive": sum(estimate_tokens(r.get('content', '')) for r in memu_budgeted)
        },
        "sources": {
            "working": len(muninn_budgeted),
            "archive": len(memu_budgeted)
        },
        "errors": []
    }
    
    # Collect any errors
    if "error" in muninn_results:
        response["errors"].append(f"MuninnDB: {muninn_results['error']}")
    if "error" in memu_results:
        response["errors"].append(f"MemU: {memu_results['error']}")
    
    return (json.dumps(response), 200, {'Content-Type': 'application/json'})


def handle_memorize(payload: dict) -> tuple:
    """
    Handle memory storage request.
    Stores in MuninnDB (working memory) primarily.
    """
    content = payload.get("content", "")
    metadata = payload.get("metadata", {})
    user_id = payload.get("user_id", "default")
    
    # Check token limit for single memory
    content_tokens = estimate_tokens(content)
    if content_tokens > MAX_TOTAL_TOKENS:
        content = truncate_to_token_budget(content, MAX_TOTAL_TOKENS)
    
    # Store in MuninnDB (working memory)
    muninn_payload = {
        "content": content,
        "metadata": metadata,
        "user_id": user_id
    }
    muninn_result = call_endpoint(f"{MUNINN_VM_URL}/memorize", muninn_payload)
    
    # Build response
    response = {
        "status": "success" if "error" not in muninn_result else "partial",
        "source": "muninndb",
        "memory_id": muninn_result.get("id", muninn_result.get("memory_id")),
        "token_usage": {
            "content": estimate_tokens(content),
            "budget": MAX_TOTAL_TOKENS
        },
        "errors": []
    }
    
    if "error" in muninn_result:
        response["errors"].append(f"MuninnDB: {muninn_result['error']}")
    
    return (json.dumps(response), 200, {'Content-Type': 'application/json'})
