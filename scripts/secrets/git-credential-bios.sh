#!/usr/bin/env bash

# BiOS Git Credential Helper
# Dynamically fetches the GitHub PAT from the local credentials server (Port 8089).

API_KEY_FILE="/Users/danexall/biomimetics/secrets/credentials_api_key"
API_URL="http://127.0.0.1:8089/secrets/github-token"

# Only respond to 'get' command
if [ "$1" != "get" ]; then
    exit 0
fi

# 1. Read API Key
if [ ! -f "$API_KEY_FILE" ]; then
    exit 1
fi
API_KEY=$(cat "$API_KEY_FILE" | tr -d '\n')

# 2. Fetch Secret from local server
RAW_RESPONSE=$(curl -s -H "X-API-Key: $API_KEY" "$API_URL")

# 3. Defensive Parsing (extract value from {"value": "github-token=ghp_..."})
# format: value = github-token=ghp_...
TOKEN_VALUE=$(echo "$RAW_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); val=data.get('value', ''); print(val.split('=', 1)[1]) if '=' in val else print(val)")

# 4. Output to Git
if [ -n "$TOKEN_VALUE" ]; then
    echo "username=danxalot"
    echo "password=$TOKEN_VALUE"
fi
