# Quick Start: Testing ARCA Puter AI Prototype

## Option 1: Local Testing (No Login Required)

**Best for**: Quick testing, development

```bash
# 1. Ensure MCP server is running
docker-compose up -d mcp_server

# 2. Start test server
cd services/user_interaction_agent/static
./test-puter-ai.sh

# 3. Open browser
open http://localhost:8080/puter-ai-prototype.html
```

**Note**: Uses Mock AI (no real inference), but shows the UI and tool call structure.

---

## Option 2: Deploy to Puter.js (Real AI)

**Best for**: Production use with real AI (Gemini, Claude, GPT-4)

### Step 1: Create Puter Account
```bash
# Visit puter.com and sign up
open https://puter.com/signup

# Or use GitHub login
```

### Step 2: Install Puter CLI
```bash
npm install -g @puter/cli
```

### Step 3: Login to Puter
```bash
puter login
# Follow prompts to authenticate
```

### Step 4: Deploy ARCA
```bash
cd services/user_interaction_agent/static

# Create puter app
puter deploy

# Your app URL will be shown:
# https://arca-terminal-[your-username].puter.com
```

### Step 5: Configure Backend URL
After deployment, you need to expose your MCP server:

**Option A: Use ngrok (quick)**
```bash
ngrok http 8086
# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
```

**Option B: Deploy MCP server to cloud**
```bash
# Deploy to your cloud provider
# Update ChatPanelPuterAI.js:
this.mcpApiUrl = 'https://your-mcp-server.com'
```

---

## Quick Test (Local)

Run this right now to see the UI:

```bash
cd /Users/danexall/Documents/VS\ Code\ Projects/ARCA/services/user_interaction_agent/static
python3 -m http.server 8080
```

Then visit: http://localhost:8080/puter-ai-prototype.html

**You'll see**:
- ARCA chat interface
- Mock AI responses (since Puter.js not available locally)
- Tool call structure demonstrated

---

## Troubleshooting

**Q: "Puter.js not detected"**
A: Normal for local testing. Deploy to puter.com for real AI.

**Q: "MCP server connection failed"**
A: Ensure `docker-compose up mcp_server` is running.

**Q: "How do I get a Puter API key?"**
A: Not needed! Puter handles auth automatically when deployed.

---

## Next: Zero-Trust Auth

Once deployed, add authentication:
```javascript
// In ChatPanelPuterAI.js
this.apiToken = await puter.auth.getToken();
```

Then protect your MCP server with JWT verification.
