# Phase 7: Multimodal Live API Voice Interface

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  User Voice     │────▶│  Gemini Live API    │────▶│  Tool Calls      │
│  (Browser PWA)  │     │  (WebSocket)        │     │  (Client-side)   │
└─────────────────┘     └──────────┬──────────┘     └────────┬─────────┘
                                   │                         │
                                   │ Audio/Text              │
                                   │ Response                │
                                   ▼                         ▼
                          ┌─────────────────┐     ┌──────────────────┐
                          │  Audio Output   │     │  GCP Gateway     │
                          │  (Speaker)      │     │  (Memory)        │
                          └─────────────────┘     └──────────────────┘
                                                        │
                                                        │
                                                        ▼
                                               ┌──────────────────┐
                                               │  Cloudflare      │
                                               │  Worker          │
                                               │  (Notion)        │
                                               └──────────────────┘
```

---

## Tool Definitions

### Tool 1: `query_memory`

Queries the unified memory system (MuninnDB + MemU) via GCP Cloud Function Gateway.

**Parameters:**
```typescript
{
  query: string,      // Search query
  user_id?: string    // User identifier (default: "voice_user")
}
```

**Response:**
```json
{
  "results": [
    {
      "content": "Memory content...",
      "source": "muninn_working",
      "confidence": 0.85
    }
  ],
  "summary": "Found 3 relevant memories (150 tokens)"
}
```

**Handler Implementation:**
```typescript
const executeQueryMemory = async (args: { query: string; user_id?: string }) => {
  const response = await fetch(GCP_GATEWAY_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: args.query, user_id: args.user_id })
  });
  return JSON.stringify(await response.json());
};
```

---

### Tool 2: `trigger_notion_action`

Triggers Notion workflows via Cloudflare Worker webhook router.

**Parameters:**
```typescript
{
  action: 'create_task' | 'update_page' | 'plan_feature' | 'review_code' | 'summarize_meeting' | 'create_github_issue',
  data: {
    title?: string,
    description?: string,
    page_id?: string,
    database_id?: string
  }
}
```

**Response:**
```json
{
  "status": "success",
  "action": "create_task",
  "message": "Action triggered successfully"
}
```

**Handler Implementation:**
```typescript
const executeTriggerNotionAction = async (args: { action: string; data: any }) => {
  const response = await fetch(CLOUDFLARE_WORKER_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source: 'voice_interface',
      action: args.action,
      data: args.data
    })
  });
  return JSON.stringify(await response.json());
};
```

---

## Live API Configuration

```typescript
const LIVE_CONFIG: LiveConnectConfig = {
  model: 'gemini-2.5-flash',
  tools: [
    {
      name: 'query_memory',
      description: 'Query unified memory system...',
      parameters: { ... }
    },
    {
      name: 'trigger_notion_action',
      description: 'Trigger Notion action...',
      parameters: { ... }
    }
  ],
  responseModalities: ['AUDIO', 'TEXT'],
  speechConfig: {
    voiceConfig: {
      prebuiltVoiceConfig: { voiceName: 'Aoede' }
    }
  },
  systemInstruction: {
    parts: [{
      text: `You are ARCA Voice, a multimodal assistant with:
1. Unified Memory access via query_memory
2. Notion integration via trigger_notion_action
3. Screen/vision analysis via camera stream`
    }]
  }
};
```

---

## PWA Configuration

### manifest.json
```json
{
  "name": "ARCA Live Voice Interface",
  "short_name": "ARCA Voice",
  "start_url": "/",
  "display": "standalone",
  "theme_color": "#4285f4",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192" },
    { "src": "/icon-512.png", "sizes": "512x512" }
  ],
  "shortcuts": [
    {
      "name": "Query Memory",
      "url": "/?action=query_memory"
    },
    {
      "name": "Create Task",
      "url": "/?action=create_task"
    }
  ]
}
```

### Service Worker (via vite-plugin-pwa)
- Auto-updates on new version
- Caches static assets
- Offline support for app shell

---

## Cloudflare Pages Deployment

### wrangler.toml
```toml
name = "arca-live-voice"
compatibility_date = "2024-01-01"
pages_build_output_dir = "./dist"

[vars]
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"

[build]
command = "npm run build"
```

### Deploy Commands
```bash
# Login to Cloudflare
wrangler login

# Deploy to Pages
npm run deploy

# Or manually
wrangler pages deploy ./dist --project-name=arca-live-voice
```

### Environment Variables (set via dashboard)
```
GEMINI_API_KEY=AIzaSy...  # From Google AI Studio
CLOUDFLARE_WORKER_URL=https://...workers.dev
```

---

## Usage Examples

### Voice Query Memory
```
User: "What do you remember about my last project?"

→ Live API triggers query_memory tool
→ GCP Gateway returns unified context
→ Gemini responds with voice + text
```

### Voice Create Task
```
User: "Create a task to review the code changes"

→ Live API triggers trigger_notion_action
→ Cloudflare Worker routes to Notion
→ Task created in database
→ Voice confirmation
```

### Vision Analysis
```
User: "What do you see on my screen?"
+ Camera enabled

→ Live API receives video frames
→ Gemini analyzes with vision model
→ Describes UI elements verbally
```

---

## Files Created

| File | Purpose |
|------|---------|
| `arca-live-voice/package.json` | Dependencies |
| `arca-live-voice/src/App.tsx` | Main React component |
| `arca-live-voice/src/index.css` | Styles |
| `arca-live-voice/public/manifest.json` | PWA manifest |
| `arca-live-voice/vite.config.ts` | Vite + PWA config |
| `arca-live-voice/wrangler.toml` | Cloudflare Pages config |
| `phase7-setup.sh` | Setup script |

---

## Testing

### 1. Development
```bash
cd /Users/danexall/arca-live-voice
npm run dev
# Open http://localhost:3000
```

### 2. Production Build
```bash
npm run build
npm run preview
```

### 3. Deploy
```bash
wrangler login
npm run deploy
```

### 4. PWA Install
- Open deployed URL in Chrome/Safari
- Click "Add to Home Screen" (iOS) or "Install" (Android)
- App runs fullscreen

---

## Voice Commands

| Command | Tool Triggered |
|---------|----------------|
| "What do you remember about..." | `query_memory` |
| "Search my memories for..." | `query_memory` |
| "Create a task to..." | `trigger_notion_action` |
| "Add to my Notion..." | `trigger_notion_action` |
| "Plan the feature for..." | `trigger_notion_action` (plan_feature) |
| "Review the code in..." | `trigger_notion_action` (review_code) |
| "What do you see?" | Vision analysis (camera) |

---

## Troubleshooting

### Microphone Not Working
```
- Check browser permissions
- Ensure HTTPS (required for getUserMedia)
- Test in Chrome/Safari (best support)
```

### API Connection Failed
```
- Verify Gemini API key is valid
- Check network connectivity
- Ensure WebSocket is not blocked by firewall
```

### Tool Calls Not Executing
```
- Check GCP_GATEWAY_URL and CLOUDFLARE_WORKER_URL
- Verify CORS headers on endpoints
- Check browser console for errors
```

### PWA Not Installing
```
- Must be served over HTTPS
- manifest.json must be valid
- Service worker must be registered
```

---

## Token Savings

With local voice processing via Live API:
- No transcription API calls (built-in)
- Direct tool execution (no intermediate)
- Streaming responses (lower latency)

**Estimated savings: 40-60% vs traditional request/response**
