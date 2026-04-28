---
tags: [bios/architecture, bios/security, bios/swarm, source/legacy]
status: active
---

# Phase 5: Desktop & Vision Actuator Integration

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  CoPaw Agent    │────▶│  Vision Router      │────▶│  Local Qwen-VL   │
│  (LLM)          │     │  (Token Saver)      │     │  (11435)         │
└────────┬────────┘     └─────────────────────┘     └──────────────────┘
         │
         │ Screen Control Tools
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Computer Use MCP Server                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ take_       │ │ move_       │ │ click       │ │ type_       │   │
│  │ screenshot  │ │ mouse       │ │             │ │ text        │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                   │
│  │ get_screen  │ │ press_      │ │ scroll      │                   │
│  │ info        │ │ key         │ │             │                   │
│  └─────────────┘ └─────────────┘ └─────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ Browser Automation
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Puppeteer MCP Server                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ navigate    │ │ screenshot  │ │ click       │ │ type        │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                   │
│  │ select      │ │ evaluate    │ │ get_content │                   │
│  └─────────────┘ └─────────────┘ └─────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Token Savings Strategy

### Before (Cloud-Only)
```
Screenshot → Base64 → Minimax API → 5000 tokens → $0.50
```

### After (Local Vision)
```
Screenshot → Base64 → Local Qwen-VL → 0 cloud tokens → $0.00
                          ↓
                    Only text reasoning to cloud
```

**Estimated Savings: 80-90% on vision tasks**

---

## Configuration

### Copaw Config (~/.copaw/config.json)

```json
{
  "mcp_servers": {
    "computer_use": {
      "command": "python3",
      "args": ["/Users/danexall/computer-use-mcp.py"],
      "transport": "stdio",
      "restricted_tools": [
        "take_screenshot",
        "move_mouse",
        "click",
        "type_text"
      ],
      "require_approval_for": ["click", "type_text"],
      "vision_routing": {
        "enabled": true,
        "local_url": "http://localhost:11435/v1/chat/completions",
        "local_model": "qwen2.5-vl-7b-instruct",
        "auto_analyze_screenshots": true
      }
    },
    "puppeteer": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
      "transport": "stdio",
      "restricted_tools": [
        "puppeteer_navigate",
        "puppeteer_screenshot",
        "puppeteer_click"
      ]
    }
  },
  "vision_routing": {
    "enabled": true,
    "local_vision_url": "http://localhost:11435/v1/chat/completions",
    "local_vision_model": "qwen2.5-vl-7b-instruct",
    "auto_route_screenshots": true
  }
}
```

---

## Usage Examples

### Take Screenshot with Auto-Analysis

```python
# CoPaw automatically analyzes with local Qwen-VL
result = await copaw.call_tool("take_screenshot")

# Result includes vision analysis:
{
  "status": "success",
  "image_base64": "...",
  "vision_analysis": {
    "model": "local_qwen_vl",
    "content": "I see a login form with username field at [100, 200]...",
    "tokens_saved": 500
  }
}
```

### UI Element Detection

```python
from vision_router import vision_router

result = vision_router.detect_ui_elements(image_base64)

# Returns:
{
  "status": "success",
  "ui_elements": [
    {
      "type": "button",
      "label": "Submit",
      "bbox": [100, 200, 200, 250],
      "click_point": [150, 225]
    }
  ]
}
```

### Click Sequence Planning

```python
result = vision_router.sequence_click_actions(
    image_base64,
    goal="Log in with username 'test' and password 'secret'"
)

# Returns action plan:
{
  "actions": [
    {"type": "click", "x": 150, "y": 225, "description": "Click username field"},
    {"type": "type", "text": "test", "description": "Enter username"},
    {"type": "click", "x": 150, "y": 275, "description": "Click password field"},
    {"type": "type", "text": "secret", "description": "Enter password"},
    {"type": "click", "x": 150, "y": 325, "description": "Click Submit button"}
  ]
}
```

### Browser Automation

```python
# Navigate to URL
await copaw.call_tool("puppeteer_navigate", {
    "url": "https://example.com"
})

# Take screenshot
screenshot = await copaw.call_tool("puppeteer_screenshot")

# Click element
await copaw.call_tool("puppeteer_click", {
    "selector": "#submit-button"
})

# Extract content
content = await copaw.call_tool("puppeteer_get_content")
```

---

## Ollama Setup for Qwen-VL

### Install Ollama

```bash
# macOS
brew install ollama

# Start Ollama
ollama serve

# Pull Qwen-VL model
ollama pull qwen2.5-vl:7b
```

### Test Vision Model

```bash
# Test with ollama CLI
ollama run qwen2.5-vl:7b "What do you see?" --image /path/to/image.png

# Test via API
curl http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-vl:7b",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
        {"type": "text", "text": "What is in this image?"}
      ]
    }]
  }'
```

---

## Tool Guard Integration

High-risk tools require approval:

| Tool | Approval Required |
|------|-------------------|
| `click` | ✅ Yes |
| `type_text` | ✅ Yes |
| `press_key` | ✅ Yes |
| `puppeteer_click` | ✅ Yes |
| `puppeteer_type` | ✅ Yes |
| `take_screenshot` | ❌ No (safe) |
| `get_screen_info` | ❌ No (safe) |
| `puppeteer_navigate` | ❌ No (safe) |

---

## Files Created

| File | Purpose |
|------|---------|
| `computer-use-mcp.py` | Local Computer Use MCP server |
| `vision-router.py` | Vision model routing (token saver) |
| `phase5-setup.sh` | Complete Phase 5 setup script |
| `start-ollama-vision.sh` | Ollama + Qwen-VL startup |
| `~/.copaw/config-phase5.json` | Phase 5 Copaw configuration |
| `~/Library/LaunchAgents/com.arca.computer-use-mcp.plist` | Computer Use MCP service |

---

## Testing

### 1. Test Computer Use MCP

```bash
# Start MCP server
python3 /Users/danexall/computer-use-mcp.py

# In another terminal, test via MCP client
mcp-client connect stdio://python3:/Users/danexall/computer-use-mcp.py
```

### 2. Test Vision Router

```bash
# Test connection to Ollama
python3 /Users/danexall/vision-router.py --test

# Expected output:
# ✅ Local vision model is working!
#    Tokens saved: 500
```

### 3. Test Full Workflow

```bash
# Start Ollama
/Users/danexall/start-ollama-vision.sh

# Start Computer Use MCP
launchctl load ~/Library/LaunchAgents/com.arca.computer-use-mcp.plist

# In CoPaw:
# 1. Ask: "Take a screenshot and tell me what buttons you see"
# 2. CoPaw calls take_screenshot
# 3. Vision router analyzes with local Qwen-VL
# 4. Response includes UI element coordinates
```

---

## Troubleshooting

### Ollama Not Responding

```bash
# Check if running
ps aux | grep ollama

# Restart
ollama serve

# Check logs
tail -f ~/.ollama/logs/server.log
```

### Permission Denied (Screen Capture)

```bash
# macOS: Grant screen recording permission
# System Preferences → Security & Privacy → Privacy → Screen Recording
# Add Terminal or your IDE
```

### PyAutoGUI Failsafe

```python
# Move mouse to corner (0, 0) to abort
# Or disable failsafe (not recommended)
pyautogui.FAILSAFE = False
```

---

## Token Savings Calculation

```
Before (per screenshot):
- Image analysis: 5000 tokens @ $0.0001/token = $0.50
- 100 screenshots/day = $50/day = $1500/month

After (local Qwen-VL):
- Image analysis: $0 (local)
- Only text reasoning: 500 tokens @ $0.0001/token = $0.05
- 100 screenshots/day = $5/day = $150/month

Monthly Savings: $1350 (90%)
```
