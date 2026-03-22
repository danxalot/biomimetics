#!/bin/bash
# Phase 3 Setup Script
# Configures Copaw Memory Interceptor and Notion webhook routing

set -e

echo "=============================================="
echo "Phase 3: Life OS Router Setup"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Create directories
echo -e "\n${YELLOW}Creating directories...${NC}"
mkdir -p ~/.copaw
mkdir -p ~/.copaw/skills
mkdir -p ~/.arca

# Copy Memory Interceptor to Copaw hooks directory
echo -e "\n${YELLOW}Installing Memory Interceptor hook...${NC}"
cp /Users/danexall/copaw-memory-interceptor.py ~/.copaw/memory_interceptor.py

# Create Copaw configuration for memory interceptor
echo -e "\n${YELLOW}Creating Copaw configuration...${NC}"
cat > ~/.copaw/config.json << 'CONFIGEOF'
{
  "memory_interceptor": {
    "enabled": true,
    "gateway_url": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
    "max_tokens": 2000,
    "min_confidence": 0.3,
    "timeout": 10.0
  },
  "notion_integration": {
    "enabled": true,
    "webhook_path": "/notion",
    "skills": {
      "analyze_notion_page": {
        "enabled": true,
        "auto_execute": true
      },
      "process_notion_comment": {
        "enabled": true,
        "auto_execute": true
      },
      "plan_feature": {
        "enabled": true,
        "auto_execute": false,
        "requires_confirmation": true
      },
      "review_code": {
        "enabled": true,
        "auto_execute": false,
        "requires_confirmation": true
      },
      "summarize_meeting": {
        "enabled": true,
        "auto_execute": true
      }
    }
  }
}
CONFIGEOF

echo -e "${GREEN}✓ Copaw configuration created${NC}"

# Create example Copaw skill for Notion actions
echo -e "\n${YELLOW}Creating example Copaw skills...${NC}"
cat > ~/.copaw/skills/analyze_notion_page.py << 'SKILLEOF'
#!/usr/bin/env python3
"""
Copaw Skill: Analyze Notion Page
Extracts action items and key information from Notion pages.
"""

import json
from typing import Dict, Any

async def execute(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze a Notion page and extract action items."""
    
    page_id = input_data.get("page_id", "")
    title = input_data.get("title", "")
    properties = input_data.get("properties", {})
    
    # Extract relevant information
    result = {
        "page_id": page_id,
        "title": title,
        "extracted_actions": [],
        "key_info": {},
        "summary": f"Analyzed page: {title}"
    }
    
    # In production, this would:
    # 1. Fetch full page content from Notion API
    # 2. Use LLM to extract action items
    # 3. Store in memory via Gateway
    
    return result

if __name__ == "__main__":
    import asyncio
    result = asyncio.run(execute({
        "page_id": "test-123",
        "title": "Test Page",
        "properties": {}
    }))
    print(json.dumps(result, indent=2))
SKILLEOF

chmod +x ~/.copaw/skills/analyze_notion_page.py
echo -e "${GREEN}✓ Example skill created${NC}"

# Check for wrangler (Cloudflare Workers CLI)
echo -e "\n${YELLOW}Checking Cloudflare Workers CLI...${NC}"
if command -v wrangler &> /dev/null; then
    echo -e "${GREEN}✓ wrangler installed${NC}"
    wrangler --version
else
    echo -e "${YELLOW}⚠ wrangler not found${NC}"
    echo "Install with: npm install -g wrangler"
    echo "Or: brew install wrangler"
fi

# Check for existing Cloudflare Worker
echo -e "\n${YELLOW}Checking Cloudflare Worker configuration...${NC}"
if [ -f /Users/danexall/wrangler.toml ]; then
    echo -e "${GREEN}✓ wrangler.toml exists${NC}"
    echo ""
    echo "To deploy the Notion webhook worker:"
    echo "  1. wrangler login"
    echo "  2. wrangler secret put NOTION_WEBHOOK_SECRET"
    echo "  3. wrangler secret put COPAW_TUNNEL_URL"
    echo "  4. wrangler deploy"
else
    echo -e "${YELLOW}⚠ wrangler.toml not found${NC}"
fi

# Update webhook receiver configuration
echo -e "\n${YELLOW}Updating webhook receiver...${NC}"

# Add Notion endpoint to launchd plist if it exists
PLIST_PATH=~/Library/LaunchAgents/com.arca.copaw-webhook.plist
if [ -f "$PLIST_PATH" ]; then
    echo -e "${GREEN}✓ Webhook receiver plist exists${NC}"
    echo "Restart with: launchctl unload $PLIST_PATH && launchctl load $PLIST_PATH"
else
    echo -e "${YELLOW}⚠ Webhook receiver not configured${NC}"
    echo "Run Phase 2 setup first: ./phase2-setup.sh"
fi

# Summary
echo -e "\n${GREEN}=============================================="
echo "Phase 3 Setup Complete!"
echo "==============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. ${YELLOW}Configure Copaw to use Memory Interceptor:${NC}"
echo "   Add to your Copaw agent initialization:"
echo ""
echo "   from copaw.memory_interceptor import MemoryInterceptorHook"
echo "   memory_hook = MemoryInterceptorHook()"
echo "   agent.register_instance_hook('pre_reasoning', 'memory', memory_hook)"
echo ""
echo "2. ${YELLOW}Deploy Cloudflare Worker:${NC}"
echo "   cd /Users/danexall"
echo "   wrangler login"
echo "   wrangler secret put NOTION_WEBHOOK_SECRET"
echo "   wrangler secret put COPAW_TUNNEL_URL"
echo "   wrangler deploy"
echo ""
echo "3. ${YELLOW}Configure Notion webhook:${NC}"
echo "   - Go to Notion developer portal"
echo "   - Add webhook URL: https://notion-webhook-router.<your-subdomain>.workers.dev"
echo "   - Set HMAC secret: (generate secure random string)"
echo "   - Select events: Pages, Comments, Database items"
echo ""
echo "4. ${YELLOW}Test the integration:${NC}"
echo "   - Update a page in your connected Notion database"
echo "   - Check webhook receiver logs: tail -f ~/.arca/copaw-webhook.log"
echo "   - Verify memory injection in Copaw responses"
echo ""
echo "=============================================="
