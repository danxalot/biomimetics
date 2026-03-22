# Koyeb Deployment - Ready Status

**Date**: 2026-03-19  
**Status**: ✅ **READY TO DEPLOY** (awaiting login)

---

## Completed Setup

### 1. Koyeb CLI Installed ✅

```bash
brew tap koyeb/tap
brew install koyeb/tap/koyeb
```

**Version**: 5.10.1

### 2. Deployment Script Updated ✅

**File**: `scripts/migrate/deploy-to-koyeb.sh`

**New Features**:
- ✅ Koyeb login check before deployment
- ✅ Docker Hub authentication check
- ✅ Automatic app create or update
- ✅ Endpoint URL retrieval
- ✅ Health check test
- ✅ Configuration update instructions

### 3. Dockerfile Verified ✅

**Location**: `/Users/danexall/github-mcp-super-gateway/Dockerfile`

**Contents**:
```dockerfile
FROM node:20-alpine
RUN npm install -g @modelcontextprotocol/server-github supergateway
EXPOSE 8080
CMD ["npx", "-y", "supergateway", "--stdio", "npx -y @modelcontextprotocol/server-github", "--port", "8080", "--host", "0.0.0.0"]
```

---

## Next Steps (User Action Required)

### Step 1: Login to Koyeb

**Option A - Interactive Login**:
```bash
koyeb login
```
This will open a browser for authentication.

**Option B - API Token**:
1. Get token from: https://app.koyeb.com/settings/api
2. Run: `koyeb login --token YOUR_API_TOKEN`

### Step 2: Login to Docker Hub (if not already)

```bash
docker login
```

### Step 3: Run Deployment Script

```bash
cd ~/biomimetics
./scripts/migrate/deploy-to-koyeb.sh
```

**Expected Duration**: 5-10 minutes

**What it does**:
1. Builds Docker image from `/Users/danexall/github-mcp-super-gateway/`
2. Pushes to Docker Hub (`danxalot/github-mcp-server:latest`)
3. Creates/updates Koyeb app (`github-mcp-server`)
4. Deploys with free tier instance (512MB/0.1vCPU)
5. Retrieves endpoint URL
6. Tests endpoint health
7. Provides configuration update instructions

---

## Post-Deployment

### Update Client Configurations

The script will output the new endpoint URL. Update these files:

**1. Zed Editor** (`~/.zed/settings.json`):
```json
{
  "mcp_servers": {
    "github": {
      "url": "https://YOUR-APP.koyeb.app/sse",
      "transport": "sse"
    }
  }
}
```

**2. Antigravity** (`~/biomimetics/.antigravity/settings.json`):
```json
{
  "mcp_servers": {
    "github": {
      "url": "https://YOUR-APP.koyeb.app/sse",
      "transport": "sse"
    }
  }
}
```

**3. CoPaw** (`~/.copaw/config.json`):
```json
{
  "mcp_servers": {
    "github": {
      "url": "https://YOUR-APP.koyeb.app/sse",
      "transport": "sse"
    }
  }
}
```

### Azure Teardown

After confirming Koyeb deployment works:

```bash
cd ~/biomimetics
./scripts/migrate/azure-teardown.sh --yes
```

This will delete the Azure container and stop billing.

---

## Cost Comparison

| Service | Before | After |
|---------|--------|-------|
| Azure ACR | $5/month | $0 |
| Azure ACI | $0 (stopped) | $0 |
| Koyeb | $0 | $0 (free tier) |
| **Total** | **$60/year** | **$0** |

---

## Troubleshooting

### Koyeb Login Fails
```bash
# Clear any existing config
rm -f ~/.koyeb.yaml

# Try again
koyeb login
```

### Docker Push Fails
```bash
# Logout and login again
docker logout
docker login
```

### Deployment Fails
```bash
# Check Koyeb dashboard
open https://app.koyeb.com/apps

# Check logs
koyeb service logs github-mcp-server/main
```

---

**Ready to Deploy**: Run `./scripts/migrate/deploy-to-koyeb.sh` after login
