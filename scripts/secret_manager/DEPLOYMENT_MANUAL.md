# GitHub MCP Auth Deployment - Manual Steps

**Date:** 2026-03-22  
**Status:** ⚠️ **REQUIRES MANUAL DOCKER HUB SETUP**

---

## Issue

Docker Hub push failed because the repository `danxalot/github-mcp-server` doesn't exist or you don't have write access.

---

## Solution Options

### Option 1: Create Docker Hub Repository (Recommended)

1. **Go to Docker Hub:** https://hub.docker.com/repos/create

2. **Create repository:**
   - Name: `github-mcp-server`
   - Visibility: Public (free tier)
   - Description: "GitHub MCP Server with API Authentication"

3. **Then run the deployment script:**
   ```bash
   cd ~/biomimetics/scripts/secrets
   ./deploy_commands.sh
   ```

### Option 2: Use Koyeb Dashboard (No Docker Hub)

1. **Build image locally:**
   ```bash
   cd ~/biomimetics/scripts/secrets
   docker build -f Dockerfile.github-mcp-auth -t github-mcp-auth:latest .
   ```

2. **Export image to tar:**
   ```bash
   docker save github-mcp-auth:latest > github-mcp-auth.tar
   ```

3. **Upload to Koyeb via dashboard:**
   - Go to https://app.koyeb.com/apps/github-mcp-server
   - Services → github-mcp-server → Deployment
   - Choose "Deploy from Docker image"
   - Upload the tar file or use Koyeb's build from Dockerfile

4. **Add environment variables:**
   - `API_KEY`: (from `github_mcp_api_key` file)
   - `GITHUB_TOKEN`: (already set)

### Option 3: Use Alternative Registry

Use GitHub Container Registry (ghcr.io) instead:

```bash
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u danxalot --password-stdin

# Tag and push
docker tag github-mcp-auth:latest ghcr.io/danxalot/github-mcp-server:auth
docker push ghcr.io/danxalot/github-mcp-server:auth

# Deploy to Koyeb
koyeb services update github-mcp-server/github-mcp-server \
  --docker ghcr.io/danxalot/github-mcp-server:auth \
  --env API_KEY="$(cat github_mcp_api_key)"
```

---

## Current Status

### ✅ Completed:
- Auth gateway code written (`github_mcp_auth_gateway.py`)
- Dockerfile created (`Dockerfile.github-mcp-auth`)
- API key generated: `40489880...`
- GitHub token configured
- Docker image built locally

### ⏳ Pending:
- Push image to container registry (Docker Hub or GHCR)
- Update Koyeb deployment
- Update Zed config with API key

---

## Files Ready for Deployment

| File | Location |
|------|----------|
| Auth Gateway | `scripts/secrets/github_mcp_auth_gateway.py` |
| Dockerfile | `scripts/secrets/Dockerfile.github-mcp-auth` |
| Deploy Script | `scripts/secrets/deploy_commands.sh` |
| API Key | `scripts/secrets/github_mcp_api_key` |
| Zed Config | `scripts/secrets/github_mcp_zed_config.json` |

---

## Quick Deploy (After Creating Docker Hub Repo)

```bash
cd ~/biomimetics/scripts/secrets
./deploy_commands.sh
```

This will:
1. Push to Docker Hub
2. Update Koyeb app
3. Configure authentication

---

## Test Authentication

After deployment:

```bash
# Without API key (should fail)
curl -I https://github-mcp-server-arca-vsa-3c648978.koyeb.app/sse
# Expected: HTTP 401

# With API key (should succeed)
curl -H "X-API-Key: $(cat github_mcp_api_key)" -I https://github-mcp-server-arca-vsa-3c648978.koyeb.app/sse
# Expected: HTTP 200
```

---

**Next Step:** Create Docker Hub repository or use GHCR, then run `./deploy_commands.sh`
