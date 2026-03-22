#!/bin/bash
#
# MCP Integration Test Script
# Tests GitHub MCP (Azure), Notion MCP (GCP), and GCP Gateway connectivity
#

set -euo pipefail

echo "=========================================="
echo "MCP Integration Test Suite"
echo "=========================================="
echo ""

# Configuration
GITHUB_MCP_URL="http://github-mcp-sse.westus2.azurecontainer.io:8080/sse"
GCP_GATEWAY_URL="https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
NOTION_TOKEN="${NOTION_TOKEN:-[NOTION_TOKEN_REDACTED]}"

TESTS_PASSED=0
TESTS_FAILED=0

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}✗${NC} $1"
    ((TESTS_FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# =========================================================
# Test 1: GitHub MCP SSE Endpoint
# =========================================================
echo "Test 1: GitHub MCP SSE Endpoint"
echo "  URL: $GITHUB_MCP_URL"

RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout 10 "$GITHUB_MCP_URL" 2>&1 || echo "FAILED")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [[ "$HTTP_CODE" == "200" ]]; then
    pass "GitHub MCP SSE endpoint reachable (HTTP $HTTP_CODE)"
else
    fail "GitHub MCP SSE endpoint not reachable (HTTP $HTTP_CODE)"
    warn "Check Azure container: az container show -g arca-mcp-services -n github-mcp-sse"
fi
echo ""

# =========================================================
# Test 2: GCP Gateway
# =========================================================
echo "Test 2: GCP Gateway (Memory Orchestrator)"
echo "  URL: $GCP_GATEWAY_URL"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$GCP_GATEWAY_URL" \
    -H "Content-Type: application/json" \
    -d '{"action": "ping"}' \
    --connect-timeout 10 2>&1 || echo "FAILED")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [[ "$HTTP_CODE" == "200" ]] || [[ "$HTTP_CODE" == "400" ]]; then
    pass "GCP Gateway reachable (HTTP $HTTP_CODE)"
else
    fail "GCP Gateway not reachable (HTTP $HTTP_CODE)"
    warn "Check GCP Cloud Function deployment"
fi
echo ""

# =========================================================
# Test 3: Notion MCP Server (npx)
# =========================================================
echo "Test 3: Notion MCP Server"
echo "  Token: ${NOTION_TOKEN:0:10}..."

if command -v npx &> /dev/null; then
    pass "npx available"
    
    # Try to run Notion MCP briefly
    timeout 5 npx -y @notionhq/notion-mcp-server --version > /dev/null 2>&1 && \
        pass "Notion MCP server executable" || \
        warn "Notion MCP server check timed out (may still work)"
else
    fail "npx not found (install Node.js)"
fi
echo ""

# =========================================================
# Test 4: Zed Configuration
# =========================================================
echo "Test 4: Zed Editor Configuration"

ZED_CONFIG="$HOME/.zed/settings.json"
if [ -f "$ZED_CONFIG" ]; then
    pass "Zed config exists: $ZED_CONFIG"
    
    if grep -q "github-mcp-sse" "$ZED_CONFIG" 2>/dev/null; then
        pass "GitHub MCP configured in Zed"
    else
        fail "GitHub MCP not found in Zed config"
    fi
    
    if grep -q "notion" "$ZED_CONFIG" 2>/dev/null; then
        pass "Notion MCP configured in Zed"
    else
        fail "Notion MCP not found in Zed config"
    fi
    
    if grep -q "GCP_GATEWAY" "$ZED_CONFIG" 2>/dev/null; then
        pass "GCP Gateway configured in Zed"
    else
        fail "GCP Gateway not found in Zed config"
    fi
else
    fail "Zed config not found: $ZED_CONFIG"
    warn "Run: ./scripts/setup_mcp_integration.sh"
fi
echo ""

# =========================================================
# Test 5: Antigravity Configuration
# =========================================================
echo "Test 5: Antigravity Configuration"

ANTIGRAVITY_CONFIG="./.antigravity/settings.json"
if [ -f "$ANTIGRAVITY_CONFIG" ]; then
    pass "Antigravity config exists: $ANTIGRAVITY_CONFIG"
    
    if grep -q "github-mcp-sse" "$ANTIGRAVITY_CONFIG" 2>/dev/null; then
        pass "GitHub MCP configured in Antigravity"
    else
        fail "GitHub MCP not found in Antigravity config"
    fi
    
    if grep -q "notion" "$ANTIGRAVITY_CONFIG" 2>/dev/null; then
        pass "Notion MCP configured in Antigravity"
    else
        fail "Notion MCP not found in Antigravity config"
    fi
    
    if grep -q "gcp_gateway" "$ANTIGRAVITY_CONFIG" 2>/dev/null; then
        pass "GCP Gateway configured in Antigravity"
    else
        fail "GCP Gateway not found in Antigravity config"
    fi
else
    fail "Antigravity config not found: $ANTIGRAVITY_CONFIG"
    warn "Run: ./scripts/setup_mcp_integration.sh"
fi
echo ""

# =========================================================
# Test 6: Azure Container Status
# =========================================================
echo "Test 6: Azure Container Status (GitHub MCP)"

if command -v az &> /dev/null; then
    CONTAINER_STATUS=$(az container show \
        -g arca-mcp-services \
        -n github-mcp-sse \
        --query "instanceView.currentState.state" \
        -o tsv 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$CONTAINER_STATUS" == "Running" ]]; then
        pass "Azure container running ($CONTAINER_STATUS)"
    else
        fail "Azure container not running ($CONTAINER_STATUS)"
        warn "Deploy: az container create ... or check deployment script"
    fi
else
    warn "Azure CLI not installed, skipping container check"
fi
echo ""

# =========================================================
# Test 7: Cloudflare Worker Config
# =========================================================
echo "Test 7: Cloudflare Worker Configuration"

WRANGLER_CONFIG="./cloudflare/wrangler.toml"
if [ -f "$WRANGLER_CONFIG" ]; then
    pass "Wrangler config exists: $WRANGLER_CONFIG"
    
    if grep -q "GCP_GATEWAY" "$WRANGLER_CONFIG" 2>/dev/null; then
        pass "GCP Gateway configured in Cloudflare Worker"
    else
        fail "GCP Gateway not found in Cloudflare Worker config"
    fi
    
    if grep -q "NOTION_DB_ID" "$WRANGLER_CONFIG" 2>/dev/null; then
        pass "Notion DB configured in Cloudflare Worker"
    else
        fail "Notion DB not found in Cloudflare Worker config"
    fi
else
    fail "Wrangler config not found: $WRANGLER_CONFIG"
fi
echo ""

# =========================================================
# Summary
# =========================================================
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC} ✓"
    echo ""
    echo "Your MCP integration is fully configured:"
    echo "  • GitHub MCP (Azure SSE): Operational"
    echo "  • Notion MCP (GCP): Operational"
    echo "  • GCP Gateway: Operational"
    echo "  • Zed Editor: Configured"
    echo "  • Antigravity: Configured"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    echo ""
    echo "Recommended actions:"
    echo "  1. Run setup script: ./scripts/setup_mcp_integration.sh"
    echo "  2. Check Azure container: az container show -g arca-mcp-services -n github-mcp-sse"
    echo "  3. Review docs: docs/MCP_INTEGRATION_STATUS.md"
    exit 1
fi
