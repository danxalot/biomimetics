# 🎙️ ARCA Live Voice Interface

**Gemini Live API Implementation for Biomimetics Project**

A real-time multimodal voice and vision interface powered by Google's Gemini Live API. Features tool calling for memory queries and Notion action triggers.

---

## ✨ Features

- 🎤 **Real-time Voice Interaction** - Speak naturally with Gemini AI
- 📹 **Vision Support** - Share your camera for visual context
- 🧠 **Memory Integration** - Query GCP Memory Gateway (MuninnDB + MemU)
- 📊 **Notion Actions** - Trigger workflows, create tasks, update pages
- 🔧 **Tool Calling** - Extensible framework for custom tools
- 📱 **PWA Support** - Install as a progressive web app
- ☁️ **Cloudflare Deployment** - Serverless deployment via Pages

---

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Browser   │─────▶│  Gemini Live │─────▶│  Audio/Vision│
│   (React)   │◀─────│     API      │◀─────│   I/O        │
└─────────────┘      └──────────────┘      └─────────────┘
       │
       │ Tool Calls
       │
       ├──────────────┬──────────────┐
       │              │              │
       ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ query_memory│ │trigger_notion│ │Future Tools │
│   (GCP)     │ │ (Cloudflare)│ │             │
└─────────────┘ └─────────────┘ └─────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Node.js 18+
- npm
- Gemini API Key (get from [Google AI Studio](https://aistudio.google.com/apikey))

### Installation

```bash
# Navigate to project
cd ~/biomimetics/gemini-live-voice

# Install dependencies
npm install

# Start development server
npm run dev
```

Open `http://localhost:3000` in your browser.

### Build & Deploy

```bash
# Build for production
npm run build

# Deploy to Cloudflare Pages
npm run deploy
```

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
VITE_CLOUDFLARE_WORKER_URL=https://arca-github-notion-sync.dan-exall.workers.dev
```

### Wrangler Configuration

See `wrangler.toml` for Cloudflare Pages configuration.

```toml
name = "arca-live-voice"
compatibility_date = "2024-01-01"
pages_build_output_dir = "./dist"

[vars]
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
```

---

## 🛠️ Tool Implementation

### query_memory

Query the unified memory system (MuninnDB working memory + MemU archive).

**Parameters**:
```json
{
  "query": "What do you remember about my last project?",
  "user_id": "voice_user"  // optional, defaults to "voice_user"
}
```

**Response**:
```json
{
  "status": "success",
  "results": [
    {
      "content": "Memory content...",
      "source": "muninn",
      "confidence": 0.95
    }
  ],
  "token_usage": { "total": 1024 }
}
```

---

### trigger_notion_action

Trigger Notion actions via Cloudflare Worker.

**Supported Actions**:
- `create_task` - Create a new task in Notion
- `update_page` - Update an existing page
- `plan_feature` - Plan a new feature
- `review_code` - Request code review
- `summarize_meeting` - Summarize a meeting
- `create_github_issue` - Create GitHub issue from Notion

**Parameters**:
```json
{
  "action": "create_task",
  "data": {
    "title": "Review the code changes",
    "description": "Please review the latest PR",
    "priority": "high"
  }
}
```

---

## 📱 PWA Installation

The app supports Progressive Web App installation:

1. Open in Chrome/Safari
2. Click "Install" or "Add to Home Screen"
3. Use as a native app

---

## 🎯 Notion Integration

### Required Databases

The following Notion databases should be created:

1. **Voice Session Logs** - Track all voice interactions
2. **Voice Tool Registry** - Document available tools
3. **Voice Interface Tasks** - Development task tracking
4. **Voice API Configuration** - Store configuration references

See `~/biomimetics/docs/GEMINI_LIVE_VOICE_PROJECT.md` for detailed schema.

---

## 🔐 Security

### API Key Handling

- API keys are stored in browser localStorage (client-side only)
- Never sent to any server except Google's Gemini API
- Users can bring their own API key

### Best Practices

- Use Cloudflare Workers for server-side tool implementations
- Never expose secrets in client-side code
- Implement rate limiting for tool calls
- Add user authentication for production use

---

## 📊 Monitoring

### Key Metrics

- Session success rate
- Average response time
- Tool call accuracy
- API cost per session

### Logging

Tool calls are logged to:
- Browser console (development)
- Cloudflare Logs (production)
- Notion Session Logs (if enabled)

---

## 🐛 Troubleshooting

### Common Issues

**"Failed to connect"**
- Check your Gemini API key
- Verify internet connection
- Check browser console for errors

**"Microphone access denied"**
- Grant microphone permissions in browser
- Check system microphone settings

**"Tool call failed"**
- Verify GCP Gateway URL is correct
- Check Cloudflare Worker is deployed
- Review tool parameters match schema

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

## 📚 Documentation

| Document | Location |
|----------|----------|
| Project Knowledge Graph | `~/biomimetics/docs/GEMINI_LIVE_VOICE_PROJECT.md` |
| System Architecture | `~/biomimetics/docs/SYSTEM_ARCHITECTURE.md` |
| MCP Integration | `~/biomimetics/docs/MCP_INTEGRATION.md` |

---

## 📄 License

Private - Biomimetics Project

---

## 👥 Contact

- **Project**: Biomimetics
- **Repository**: https://github.com/danxalot/biomimetics
- **Identity**: Claws <claws@arca-vsa.tech>

---

**Last Updated**: 2026-03-18
**Version**: 1.0.0
