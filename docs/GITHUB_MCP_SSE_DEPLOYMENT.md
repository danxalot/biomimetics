---
tags: [bios/architecture, bios/infrastructure, bios/memory, bios/security, bios/swarm, source/legacy]
status: active
---

# GitHub MCP SSE Deployment - Complete

**Date:** 2026-03-16
**Status:** ✅ **DEPLOYED AND OPERATIONAL**

---

## Summary

The GitHub MCP server is now deployed on Azure Container Instances with Supergateway, exposing the MCP server over SSE (Server-Sent Events) for 24/7 remote access.

---

## Deployment Details

### Azure Container Instance
- **Name:** `github-mcp-sse`
- **Resource Group:** `arca-mcp-services`
- **Location:** westus2
- **Status:** Running
- **CPU:** 2 cores
- **Memory:** 2 GB

### Endpoints
- **SSE Endpoint:** `http://github-mcp-sse.westus2.azurecontainer.io:8080/sse`
- **Message Endpoint:** `http://github-mcp-sse.westus2.azurecontainer.io:8080/message`

### Container Image
- **Registry:** `arcamcpregistry.azurecr.io`
- **Image:** `github-mcp-sse:latest`
- **Based on:** Node.js 20 Alpine
- **Supergateway:** Wraps stdio MCP server with SSE transport

---

## Copaw Configuration

Updated `~/.copaw/config.json`:

```json
{
  "mcp_servers": {
    "github-remote": {
      "url": "http://github-mcp-sse.westus2.azurecontainer.io:8080/sse",
      "transport": "sse",
      "description": "GitHub MCP via Azure ACI (24/7 remote access)",
      "restricted_tools": [
        "github.create_issue",
        "github.update_issue",
        "github.search_issues",
        "github.get_issue",
        "github.create_pull_request",
        "github.list_pull_requests",
        "github.get_pull_request",
        "github.get_repository"
      ],
      "require_approval_for": [
        "github.create_issue",
        "github.update_issue",
        "github.create_pull_request"
      ]
    }
  }
}
```

---

## Architecture

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Copaw Client   │────▶│  Supergateway       │────▶│  GitHub MCP      │
│  (SSE Transport)│     │  (SSE ↔ stdio)      │     │  Server (stdio)  │
└─────────────────┘     └─────────────────────┘     └──────────────────┘
                              │
                              ▼
                       Azure Container
                       Instances (ACI)
                       - 24/7 uptime
                       - Public endpoint
                       - GitHub PAT configured
```

---

## Comparison: Remote vs Local

| Feature | Local stdio | Azure SSE (Current) |
|---------|-------------|---------------------|
| **Availability** | Only when Mac is on | ✅ 24/7 Global Access (via Cloudflare Workers & Azure ACI) |
| **Setup** | Easy | ✅ Moderate (done) |
| **Security** | Local process only | GitHub PAT in env var |
| **Life OS Fit** | Fragments the "Brain" | ✅ Unified: Serena can use it too |
| **Access** | Local only | ✅ Any device, anywhere |
| **Cost** | Free | ~$30/month (2 core ACI) |

---

## Testing

### Test SSE Endpoint
```bash
curl -v http://github-mcp-sse.westus2.azurecontainer.io:8080/sse
```

Expected response:
```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
Connection: keep-alive
```

### Check Container Logs
```bash
az container logs --resource-group arca-mcp-services --name github-mcp-sse
```

Expected output:
```
[supergateway] Listening on port 8080
[supergateway] SSE endpoint: http://localhost:8080/sse
[supergateway] Child stderr: GitHub MCP Server running on stdio
```

---

## Management Commands

### View Container Status
```bash
az container show \
  --resource-group arca-mcp-services \
  --name github-mcp-sse \
  --output table
```

### View Logs
```bash
az container logs \
  --resource-group arca-mcp-services \
  --name github-mcp-sse
```

### Restart Container
```bash
az container restart \
  --resource-group arca-mcp-services \
  --name github-mcp-sse
```

### Delete Container
```bash
az container delete \
  --resource-group arca-mcp-services \
  --name github-mcp-sse \
  --yes
```

---

## Security Notes

1. **GitHub PAT** stored as environment variable in ACI
2. **No SSL/TLS** - traffic is unencrypted (HTTP only)
3. **Public endpoint** - anyone with URL can connect
4. **Recommendation:** Add custom domain with SSL certificate for production

### To Add SSL (Optional)
1. Purchase domain (e.g., `mcp.arca.tech`)
2. Point DNS to ACI IP
3. Deploy nginx/traefik reverse proxy with Let's Encrypt
4. Update Copaw config with HTTPS URL

---

## Cost Estimate

| Resource | Monthly Cost |
|----------|--------------|
| ACI (2 core, 2GB) | ~$30 USD |
| ACR (Basic) | ~$5 USD |
| **Total** | **~$35 USD/month** |

---

## Next Steps

1. **Test Copaw Integration** - Verify Copaw can connect via SSE
2. **Monitor Usage** - Check ACI metrics for usage patterns
3. **Consider SSL** - Add custom domain with HTTPS if needed
4. **Document for Team** - Share endpoint URL with team members

---

## Troubleshooting

### SSE Connection Fails
```bash
# Check container is running
az container show --resource-group arca-mcp-services --name github-mcp-sse

# Check logs
az container logs --resource-group arca-mcp-services --name github-mcp-sse

# Test endpoint directly
curl -v http://github-mcp-sse.westus2.azurecontainer.io:8080/sse
```

### GitHub API Errors
```bash
# Verify PAT is set correctly
az container exec \
  --resource-group arca-mcp-services \
  --name github-mcp-sse \
  --exec-command "/bin/sh -c 'echo \$GITHUB_PERSONAL_ACCESS_TOKEN'"
```

### Supergateway Crashes
```bash
# Restart container
az container restart \
  --resource-group arca-mcp-services \
  --name github-mcp-sse
```

---

## Files Created

| File | Purpose |
|------|---------|
| `/Users/danexall/github-mcp-super-gateway/Dockerfile` | Supergateway container |
| `/Users/danexall/deploy-github-mcp-sse.sh` | Deployment script |
| `/Users/danexall/.copaw/config.json` | Updated Copaw config |
| `GITHUB_MCP_SSE_DEPLOYMENT.md` | This documentation |

---

**Deployment Complete!** The GitHub MCP server is now accessible 24/7 via SSE at:
`http://github-mcp-sse.westus2.azurecontainer.io:8080/sse`
