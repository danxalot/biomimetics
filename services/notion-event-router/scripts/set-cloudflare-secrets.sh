#!/bin/bash
# Set Cloudflare Secrets for Notion Event Router
# Uses credentials from .secrets/cloudflare

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR/.."
SECRETS_DIR="/Users/danexall/Documents/VS Code Projects/ARCA/.secrets"

echo "=================================="
echo "Setting Cloudflare Secrets"
echo "=================================="
echo ""

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "Error: wrangler is not installed"
    echo "Run: npm install -g wrangler"
    exit 1
fi

# Check if logged in
if ! wrangler whoami &> /dev/null; then
    echo "Not logged in to Cloudflare. Logging in..."
    wrangler login
fi

echo "✓ Logged in to Cloudflare"
echo ""

# Set Cloudflare API Token (for custom domain management)
echo "Setting CLOUDFLARE_API_TOKEN..."
CLOUDFLARE_TOKEN=$(cat "$SECRETS_DIR/cloudflare" | tr -d '\n')
echo "$CLOUDFLARE_TOKEN" | wrangler secret put CLOUDFLARE_API_TOKEN
echo "✓ CLOUDFLARE_API_TOKEN set"
echo ""

# Set GitHub PAT
echo "Setting GITHUB_PAT..."
GITHUB_PAT=$(cat "$SECRETS_DIR/github_token" | tr -d '\n')
echo "$GITHUB_PAT" | wrangler secret put GITHUB_PAT
echo "✓ GITHUB_PAT set"
echo ""

# Set GCP Service Account JSON
echo "Setting GCP_SERVICE_ACCOUNT_JSON..."
wrangler secret put GCP_SERVICE_ACCOUNT_JSON < "$SECRETS_DIR/gcp_credentials.json"
echo "✓ GCP_SERVICE_ACCOUNT_JSON set"
echo ""

# Generate and set Notion Webhook Secret
echo "Setting NOTION_WEBHOOK_SECRET..."
NOTION_SECRET=$(openssl rand -hex 32)
echo "$NOTION_SECRET" | wrangler secret put NOTION_WEBHOOK_SECRET
echo "✓ NOTION_WEBHOOK_SECRET set"
echo ""

echo "=================================="
echo "All secrets configured!"
echo "=================================="
echo ""
echo "Custom Domain: notion.arca-vsa.tech"
echo ""
echo "Next steps:"
echo "  1. Ensure arca-vsa.tech is added to your Cloudflare account"
echo "  2. Run: npm run deploy:prod"
echo "  3. In Cloudflare Dashboard, map the custom domain"
echo ""
echo "Your Notion Webhook Secret (save this for Notion configuration):"
echo "  $NOTION_SECRET"
echo ""
