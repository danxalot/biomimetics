import pytest
import httpx

@pytest.mark.asyncio
async def test_mcp_tool_execute_routing():
    url = "http://localhost:8090/api/mcp/tool/execute"
    payload = {
        "server_name": "copaw-omni",
        "tool_name": "get_secret",
        "args": {
            "secret_name": "test"
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            # Depending on if the tool actually exists or needs auth, we just verify routing here
            # e.g., 200 OK or 400 Bad Request, but not 404 Not Found
            assert response.status_code in [200, 400, 401, 403, 500]
            assert response.status_code != 404
    except httpx.ConnectError:
        pytest.skip("MCP server is not running on localhost:8090")
