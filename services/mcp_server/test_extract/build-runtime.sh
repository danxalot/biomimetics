#!/bin/bash
# ARCA MCP Server Build Script
# Builds runtime artifacts on MacBook and exports as tar for OCI deployment

set -e

# Configuration
IMAGE_NAME="arca-mcp-server"
OUTPUT_DIR="./arm64-runtime-artifact"
GHCR_REPO="ghcr.io/danxalot/arca-mcp-server"
CACHE_TAG="build-cache"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting ARCA MCP Server Runtime Build${NC}"

# Ensure QEMU handlers are installed for cross-compilation
echo -e "${YELLOW}📋 Ensuring QEMU handlers for ARM64 cross-compilation...${NC}"
docker run --privileged --rm tonistiigi/binfmt --install all || true

# Read GitHub token from secrets file
GITHUB_TOKEN_FILE="/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/github_token"
if [ -f "$GITHUB_TOKEN_FILE" ]; then
    # Extract token value from the GITHUB_TOKEN line
    GHCR_TOKEN=$(grep "^GITHUB_TOKEN=" "$GITHUB_TOKEN_FILE" | cut -d'=' -f2- | tr -d '\n')
    if [ -n "$GHCR_TOKEN" ]; then
        export GHCR_TOKEN
        echo -e "${GREEN}🔑 GitHub token extracted from secrets file${NC}"
    else
        echo -e "${YELLOW}⚠️  Could not extract GitHub token from secrets file${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  GitHub token file not found at $GITHUB_TOKEN_FILE${NC}"
fi

# Login to GHCR for caching (if token available)
if [ -n "$GHCR_TOKEN" ]; then
    echo -e "${YELLOW}🔐 Logging into GitHub Container Registry...${NC}"
    # Try login with token as password and username as token owner
    echo "$GHCR_TOKEN" | docker login ghcr.io -u danxalot --password-stdin || {
        echo -e "${YELLOW}⚠️  GHCR login failed, proceeding without caching${NC}"
        unset GHCR_TOKEN
    }
fi

# Build and export runtime artifacts
echo -e "${YELLOW}🏗️  Building runtime artifacts for linux/arm64...${NC}"
if [ -n "$GHCR_TOKEN" ]; then
    # Use buildx with caching but export locally
    docker buildx build \
        --platform linux/arm64 \
        --target runtime \
        --output type=docker,dest="${OUTPUT_DIR}/runtime.tar" \
        --cache-from type=registry,ref="${GHCR_REPO}:${CACHE_TAG}" \
        --cache-to type=registry,ref="${GHCR_REPO}:${CACHE_TAG}",mode=max \
        --load \
        -t "${GHCR_REPO}:latest" \
        .
    
    # Extract only the /app directory from the container
    mkdir -p /tmp/extract
    docker create --name temp-container "${GHCR_REPO}:latest"
    docker export temp-container | tar -xf - -C /tmp/extract
    tar czf "${OUTPUT_DIR}/runtime.tar" -C /tmp/extract/app .
    docker rm temp-container
    rm -rf /tmp/extract
else
    echo -e "${YELLOW}⚠️  No GHCR token found, building without caching...${NC}"
    # Use regular docker build with multi-stage and export
    # First build the full image
    docker build --target runtime -t arca-runtime-temp .
    # Then export the container filesystem as tar
    docker run --rm arca-runtime-temp tar czf - -C /app . > "${OUTPUT_DIR}/runtime.tar"
    # Clean up temp image
    docker rmi arca-runtime-temp
fi

# Build deployable image for GHCR (only if authenticated)
if [ -n "$GHCR_TOKEN" ]; then
    echo -e "${YELLOW}📦 Building deployable image for GHCR...${NC}"
    docker buildx build \
        --platform linux/arm64 \
        --target runtime \
        --cache-from type=registry,ref="${GHCR_REPO}:${CACHE_TAG}" \
        --load \
        -t "${GHCR_REPO}:latest" \
        .
else
    echo -e "${YELLOW}⚠️  Skipping GHCR image build (no token)${NC}"
fi

# Compress the artifact
echo -e "${YELLOW}📦 Compressing runtime artifact...${NC}"
gzip -f "${OUTPUT_DIR}/runtime.tar"

ARTIFACT_PATH="${OUTPUT_DIR}/runtime.tar.gz"
ARTIFACT_SIZE=$(du -h "$ARTIFACT_PATH" | cut -f1)

echo -e "${GREEN}✅ Build complete!${NC}"
echo -e "${GREEN}📁 Artifact: ${ARTIFACT_PATH}${NC}"
echo -e "${GREEN}📊 Size: ${ARTIFACT_SIZE}${NC}"
echo -e "${GREEN}🚀 Ready for OCI deployment${NC}"

# Instructions for deployment
echo -e "\n${YELLOW}📋 Deployment Instructions:${NC}"
echo -e "1. Transfer artifact to OCI: ${YELLOW}scp ${ARTIFACT_PATH} ubuntu@100.124.13.62:/tmp/${NC}"
echo -e "2. Deploy on OCI: ${YELLOW}ssh ubuntu@100.124.13.62 'cd /home/ubuntu/ARCA && ./scripts/deploy-mcp-runtime.sh'${NC}"