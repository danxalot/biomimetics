#!/bin/bash
# Deploy Notion Event Router to Cloudflare Workers

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=================================="
echo "Deploying Notion Event Router"
echo "=================================="
echo ""

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "❌ wrangler is not installed"
    echo "   Run: npm install -g wrangler"
    exit 1
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "❌ Dependencies not installed"
    echo "   Run: npm install"
    exit 1
fi

# Check if logged in
if ! wrangler whoami &> /dev/null; then
    echo "Not logged in to Cloudflare. Logging in..."
    wrangler login
fi

echo "✓ Logged in to Cloudflare"
echo ""

# Validate configuration
echo "Validating configuration..."
if [ ! -f "wrangler.toml" ]; then
    echo "❌ wrangler.toml not found"
    exit 1
fi

# Check secrets are set
echo "Checking secrets..."
SECRETS_CHECK=$(wrangler secret list 2>&1 | grep -E "(GITHUB_PAT|GCP_SERVICE_ACCOUNT_JSON|NOTION_WEBHOOK_SECRET)" | wc -l)
if [ "$SECRETS_CHECK" -lt 3 ]; then
    echo "❌ Not all secrets are set"
    echo "   Run: ./scripts/set-cloudflare-secrets.sh"
    exit 1
fi
echo "✓ All secrets configured"
echo ""

# Deploy to production
echo "Deploying to Cloudflare Workers (Production)..."
echo "Custom Domain: notion.arca-vsa.tech"
echo ""
wrangler deploy --env production

echo ""
echo "=================================="
echo "✓ Deployment Complete!"
echo "=================================="
echo ""
echo "Your Worker is now available at:"
echo "  https://notion.arca-vsa.tech"
echo ""
echo "In Cloudflare Dashboard:"
echo "  1. Go to Workers & Pages"
echo "  2. Select 'notion-event-router'"
echo "  3. Go to 'Custom Domains' tab"
echo "  4. Add 'notion.arca-vsa.tech' if not already mapped"
echo ""
echo "Test with:"
echo "  curl -X POST https://notion.arca-vsa.tech \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -H 'X-Notion-Signature: sha256=test' \\"
echo "    -d '{\"event\":{\"id\":\"test\",\"properties\":{\"title\":[{\"plain_text\":\"Test\"}]}}}'"
echo ""
echo "View logs:"
echo "  wrangler tail --env production"
echo ""
