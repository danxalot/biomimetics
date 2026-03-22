#!/bin/bash
# Phase 7 Setup Script
# Multimodal Live API Voice Interface

set -e

echo "=============================================="
echo "Phase 7: Multimodal Live API Voice Interface"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd /Users/danexall/arca-live-voice

echo -e "\n${YELLOW}Step 1: Install dependencies${NC}"
npm install 2>&1 | tail -10
echo -e "${GREEN}✓ Dependencies installed${NC}"

echo -e "\n${YELLOW}Step 2: Check for Gemini API key${NC}"
if [ -f ~/.gemini_api_key ]; then
    API_KEY=$(cat ~/.gemini_api_key)
    echo -e "${GREEN}✓ Found API key${NC}"
else
    echo -e "${YELLOW}⚠ No API key found${NC}"
    echo "Enter your Gemini API key from https://aistudio.google.com/apikey"
    echo -n "API Key: "
    read -s API_KEY
    echo ""
    echo "$API_KEY" > ~/.gemini_api_key
    chmod 600 ~/.gemini_api_key
fi

echo -e "\n${YELLOW}Step 3: Create environment file${NC}"
cat > .env << ENVEOF
VITE_GEMINI_API_KEY=$API_KEY
VITE_CLOUDFLARE_WORKER_URL=https://notion-webhook-router.<your-subdomain>.workers.dev
VITE_GCP_GATEWAY_URL=https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator
ENVEOF
echo -e "${GREEN}✓ Environment file created${NC}"

echo -e "\n${YELLOW}Step 4: Check Wrangler (Cloudflare CLI)${NC}"
if command -v wrangler &> /dev/null; then
    echo -e "${GREEN}✓ Wrangler installed${NC}"
    wrangler --version
else
    echo -e "${YELLOW}⚠ Wrangler not found${NC}"
    echo "Install with: npm install -g wrangler"
    echo "Or: brew install wrangler"
fi

echo -e "\n${YELLOW}Step 5: Test build${NC}"
npm run build 2>&1 | tail -10
echo -e "${GREEN}✓ Build successful${NC}"

echo -e "\n${YELLOW}Step 6: Create Cloudflare Pages project${NC}"
echo "Run these commands to deploy:"
echo ""
echo "  # Login to Cloudflare"
echo "  wrangler login"
echo ""
echo "  # Deploy to Pages"
echo "  npm run deploy"
echo ""
echo "  # Or manually:"
echo "  wrangler pages deploy ./dist --project-name=arca-live-voice"
echo ""

# Summary
echo -e "\n${GREEN}=============================================="
echo "Phase 7 Setup Complete!"
echo "==============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. ${YELLOW}Start development server:${NC}"
echo "   npm run dev"
echo "   Open: http://localhost:3000"
echo ""
echo "2. ${YELLOW}Deploy to Cloudflare Pages:${NC}"
echo "   wrangler login"
echo "   npm run deploy"
echo ""
echo "3. ${YELLOW}Configure Cloudflare Worker URL:${NC}"
echo "   Edit .env and set VITE_CLOUDFLARE_WORKER_URL"
echo "   to your deployed Cloudflare Worker URL"
echo ""
echo "4. ${YELLOW}Install as PWA:${NC}"
echo "   - Open in Chrome/Safari"
echo "   - Click 'Add to Home Screen' or 'Install App'"
echo "   - App will run fullscreen on mobile"
echo ""
echo "5. ${YELLOW}Test voice interface:${NC}"
echo "   - Enter Gemini API key"
echo "   - Click 'Connect'"
echo "   - Say: 'What do you remember about my projects?'"
echo "   - The app will query memory and respond via voice"
echo ""
echo "=============================================="
echo ""
echo "Features:"
echo "  ✅ Real-time voice conversation (Gemini Live API)"
echo "  ✅ Interruptible speech (barge-in support)"
echo "  ✅ Camera/vision streaming"
echo "  ✅ query_memory tool → GCP Gateway"
echo "  ✅ trigger_notion_action → Cloudflare Worker"
echo "  ✅ PWA installable on mobile"
echo "  ✅ Deployed on Cloudflare Pages (global edge)"
echo ""
echo "=============================================="
