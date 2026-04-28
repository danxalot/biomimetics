#!/bin/bash
# BiOS ACR Purge Tool
# Staged for failed MCP container cleanup.
# 
# Usage: ./acr_purge.sh <REGISTRY_NAME>

REGISTRY_NAME=$1

if [ -z "$REGISTRY_NAME" ]; then
    echo "Usage: $0 <REGISTRY_NAME>"
    exit 1
fi

echo "--- ACR REPOSITORY LIST for $REGISTRY_NAME ---"
REPOS=$(az acr repository list --name "$REGISTRY_NAME" --output tsv)

if [ -z "$REPOS" ]; then
    echo "No repositories found in registry $REGISTRY_NAME."
    exit 0
fi

for repo in $REPOS; do
    read -p "Delete repository '$repo' in $REGISTRY_NAME? (y/N): " confirm
    if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
        echo "Purging $repo..."
        az acr repository delete --name "$REGISTRY_NAME" --repository "$repo" --yes
    else
        echo "Skipping $repo."
    fi
done

echo "Purge process complete."
