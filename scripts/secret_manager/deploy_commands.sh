#!/bin/bash
# Deployment commands for GitHub MCP Auth Gateway

IMAGE_NAME="danxalot/github-mcp-server"
TAG="auth-20260322144719"
APP_NAME="github-mcp-server"
CRED_KEY_FILE="${CRED_KEY_FILE:-/Users/danexall/biomimetics/secrets/credentials_api_key}"
CREDENTIALS_API_KEY="$(cat "$CRED_KEY_FILE")"
fetch_secret() {
  curl -sf -H "X-API-Key: " "http://127.0.0.1:8089/secrets/$1" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('value',''))"
}
API_KEY="$(fetch_secret github-mcp-api-key)"
GITHUB_TOKEN="$(fetch_secret github-token)"
if [ -z "$API_KEY" ] || [ -z "$GITHUB_TOKEN" ]; then
  echo "❌ missing github-mcp-api-key or github-token from credentials server"
  exit 1
fi

echo "Pushing to Docker Hub..."
docker push $IMAGE_NAME:$TAG
docker push $IMAGE_NAME:auth

echo "Deploying to Koyeb..."
koyeb app update $APP_NAME     --docker $IMAGE_NAME:auth     --env API_KEY="$API_KEY"     --env GITHUB_TOKEN="$GITHUB_TOKEN"     --env PORT="8080"     --ports 8080:http     --instance-type nano     --regions fra

echo "Done!"
