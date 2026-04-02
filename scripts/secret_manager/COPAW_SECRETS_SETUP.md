# CoPaw Secrets Configuration

## Overview

All secrets for CoPaw are now fetched dynamically from the **Azure Credentials Server** (port 8089).
No secrets are hardcoded in configuration files.

## Architecture

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   CoPaw     │────▶│  Credentials Server  │────▶│  Azure Key      │
│   Scripts   │     │  (port 8089)         │     │  Vault          │
└─────────────┘     └──────────────────────┘     └─────────────────┘
       │                       │
       │                       │
       ▼                       ▼
┌─────────────┐     ┌──────────────────────┐
│ ~/.copaw/   │     │ API Key Auth         │
│ .secrets/   │     │ X-API-Key header     │
└─────────────┘     └──────────────────────┘
```

## Components

### 1. Azure Credentials Server (`credentials_server.py`)

- **Port**: 8089
- **API Key**: Stored in launch agent environment
- **Endpoints**:
  - `GET /secrets/{name}` - Fetch a single secret
  - `GET /secrets` - List all secret names
  - `POST /secrets/batch` - Fetch multiple secrets
  - `GET /health` - Health check

### 2. CoPaw Secrets Wrapper (`copaw-secrets-wrapper.py`)

- Fetches secrets on CoPaw startup
- Creates secret files in `~/.copaw/.secrets/`
- Updates `providers.json` with correct paths

### 3. Secret Fetcher Utility (`copaw_secret_fetcher.py`)

Python utility for copaw scripts:

```python
from copaw_secret_fetcher import get_secret_or_env

# Fetch from credentials server, fallback to environment
api_key = get_secret_or_env("notion_api_key", "NOTION_API_KEY")
```

## Available Secrets

| Secret Name | Azure Key Vault Name | Used By |
|-------------|---------------------|---------|
| `google_ai_studio` | `google-api-key` | Google AI Studio / Gemini |
| `github_models_token` | `github-models-token` | GitHub Models (Azure) |
| `notion_api_key` | `notion-api-key` | Notion MCP integration |
| `openai_api_key` | `openai-api-key` | OpenAI API |
| `anthropic_api_key` | `anthropic-api-key` | Anthropic Claude |
| `tavily_api_key` | `tavily-api-key` | Tavily Search MCP |
| `groq_api_key` | `groq-api-key` | Groq inference |
| `cohere_api_key` | `cohere-api-key` | Cohere models |
| `huggingface_token` | `huggingface-token` | Hugging Face |
| `opencode_api_key` | `opencode-api-key` | Opencode Zen |
| `openrouter_api_key` | `openrouter-api-key` | OpenRouter |
| `minimax_api_key` | `minimax-api-key` | MiniMax models |
| `gemini_api_key` | `gemini-api-key` | Gemini API |

## Configuration Files

### Launch Agent: `com.bios.credentials-server.plist`

Location: `~/Library/LaunchAgents/`

Environment variables:
- `CREDENTIALS_API_KEY` - API key for authentication
- `CREDENTIALS_PORT` - Server port (8089)
- `AZURE_KEY_VAULT_NAME` - Key vault name
- `AZURE_TENANT_ID` - Azure AD tenant
- `AZURE_CLIENT_ID` - Service principal ID

### CoPaw Wrapper: `~/.copaw/bin/copaw`

Updated to call `copaw-secrets-wrapper.py` before starting CoPaw.

## Usage

### Starting CoPaw

```bash
# Secrets are fetched automatically
copaw
```

### Manual Secret Fetch

```bash
# Test secret fetch
python3 /Users/danexall/biomimetics/scripts/secret_manager/copaw_secret_fetcher.py google-api-key
```

### Credentials Server Health

```bash
curl http://127.0.0.1:8089/health
```

## Security Notes

1. **No hardcoded secrets** in config files
2. Secret files in `~/.copaw/.secrets/` have `0600` permissions
3. API key authentication required for credentials server
4. Secrets are cached for 5 minutes to reduce API calls

## Troubleshooting

### Check credentials server status

```bash
launchctl print gui/501/com.bios.credentials-server
```

### View credentials server logs

```bash
tail -f ~/biomimetics/logs/credentials_server.log
```

### Test secret fetch

```bash
curl -H "X-API-Key: YOUR_API_KEY" http://127.0.0.1:8089/secrets/google-api-key
```

### Restart credentials server

```bash
launchctl unload ~/Library/LaunchAgents/com.bios.credentials-server.plist
launchctl load ~/Library/LaunchAgents/com.bios.credentials-server.plist
```
