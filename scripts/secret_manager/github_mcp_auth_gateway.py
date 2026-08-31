#!/usr/bin/env python3
"""
GitHub MCP Server - Authenticated SSE Gateway
Adds API key authentication to the GitHub MCP server on Koyeb

Usage:
    python3 github_mcp_auth_gateway.py
    
Environment Variables:
    API_KEY: Required API key for authentication
    PORT: Port to listen on (default: 8080)
    GITHUB_TOKEN: GitHub personal access token
"""

import os
import sys
import json
import asyncio
import httpx
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

try:
    from azure_secrets_provider import SecretsProvider
except ImportError:
    try:
        from secrets.azure_secrets_provider import SecretsProvider
    except ImportError:
        SecretsProvider = None

# Configuration
_api_key = None
_github_token = None

if SecretsProvider:
    try:
        _provider = SecretsProvider()
        _api_key = _provider.get("github-mcp-api-key")
        _github_token = _provider.get("github-token")
    except Exception as e:
        print(f"Warning: Failed to get secrets from SecretsProvider: {e}")

API_KEY = _api_key or os.environ.get("API_KEY", "")
PORT = int(os.environ.get("PORT", "8080"))
GITHUB_TOKEN = _github_token or os.environ.get("GITHUB_TOKEN", "")

# Upstream GitHub MCP server (local stdio via supergateway)
UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "http://127.0.0.1:8081")

# API Key security scheme
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# FastAPI app
app = FastAPI(
    title="GitHub MCP Auth Gateway",
    description="Authenticated gateway for GitHub MCP Server",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """Verify API key from X-API-Key header"""
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header."
        )
    
    if not API_KEY:
        # No API key configured - allow all (development mode)
        return api_key
    
    if api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return api_key


@app.get("/health")
async def health_check():
    """Health check endpoint (no auth required)"""
    return {
        "status": "healthy",
        "service": "github-mcp-auth-gateway",
        "port": PORT,
        "auth_enabled": bool(API_KEY),
        "github_token_configured": bool(GITHUB_TOKEN)
    }


@app.get("/sse")
async def sse_endpoint(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    SSE endpoint - proxies to upstream GitHub MCP server
    Requires valid X-API-Key header
    """
    async def generate_sse():
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "GET",
                    f"{UPSTREAM_URL}/sse",
                    headers={"X-API-Key": api_key} if api_key else {}
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n".encode()
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Auth-Status": "verified"
        }
    )


@app.post("/message")
async def post_message(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    POST message endpoint - proxies to upstream GitHub MCP server
    Requires valid X-API-Key header
    """
    try:
        body = await request.body()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{UPSTREAM_URL}/message",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": api_key if api_key else ""
                }
            )
            
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.get("/api-key/rotate")
async def rotate_api_key(current_api_key: str = Depends(verify_api_key)):
    """
    Rotate API key endpoint
    Returns new API key (should be secured further in production)
    """
    import secrets
    new_key = secrets.token_urlsafe(32)
    
    return {
        "api_key": new_key,
        "note": "Update your API_KEY environment variable with this value"
    }


@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    print(f"🚀 GitHub MCP Auth Gateway starting on port {PORT}")
    print(f"🔐 API Key Authentication: {'ENABLED' if API_KEY else 'DISABLED (dev mode)'}")
    print(f"📡 Upstream URL: {UPSTREAM_URL}")
    print(f"🔑 GitHub Token: {'CONFIGURED' if GITHUB_TOKEN else 'NOT CONFIGURED'}")


if __name__ == "__main__":
    uvicorn.run(
        "github_mcp_auth_gateway:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info"
    )
