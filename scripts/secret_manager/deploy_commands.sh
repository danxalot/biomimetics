#!/bin/bash
# Deployment commands for GitHub MCP Auth Gateway

IMAGE_NAME="danxalot/github-mcp-server"
TAG="auth-20260322144719"
API_KEY="40489880280b34e1436636197236b04a079604ab4c656763bc19e340ea85dcf7"
GITHUB_TOKEN="ghp_TITE8x..."
APP_NAME="github-mcp-server"

echo "Pushing to Docker Hub..."
docker push $IMAGE_NAME:$TAG
docker push $IMAGE_NAME:auth

echo "Deploying to Koyeb..."
koyeb app update $APP_NAME     --docker $IMAGE_NAME:auth     --env API_KEY="40489880280b34e1436636197236b04a079604ab4c656763bc19e340ea85dcf7"     --env GITHUB_TOKEN="REPLACED_WITH_SECRET_FETCHER"     --env PORT="8080"     --ports 8080:http     --instance-type nano     --regions fra

echo "Done!"
