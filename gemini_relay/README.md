# Gemini Live WebSocket Relay

Lightweight, asynchronous WebSocket proxy for bridging clients to the Gemini Live API.
Designed for micro VPS deployments (0.1 vCPU / 512MB RAM).

## Features

- ✅ **Bidirectional Message Piping** - Client ↔ Gemini relay via `asyncio.gather`
- ✅ **Azure Key Vault Integration** - Secure API key retrieval on startup
- ✅ **Background Memory Spooler** - Extracts transcripts and POSTs to Muninn (non-blocking)
- ✅ **Minimal Footprint** - No audio transcoding, lightweight dependencies
- ✅ **Production Ready** - systemd services, Cloudflare Tunnel integration

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Client    │────▶│  WebSocket Relay │────▶│  Gemini Live    │
│   (Browser) │     │ (149.248.32.53)  │     │  API            │
└─────────────┘     └──────────────────┘     └─────────────────┘
                           │
                           │ (background)
                           ▼
                    ┌──────────────────┐
                    │  Muninn Endpoint │
                    │  (Memory Store)  │
                    └──────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
cd /opt/gemini_relay
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
sudo cp scripts/gemini_relay.env /etc/gemini_relay.env
sudo nano /etc/gemini_relay.env
```

Set at minimum:
```bash
GEMINI_API_KEY=your_api_key_here
```

Or use Azure Key Vault:
```bash
AZURE_TENANT_ID=your_tenant_id
AZURE_CLIENT_ID=your_client_id
AZURE_CLIENT_SECRET=your_client_secret
```

### 3. Run the Relay

```bash
python3 main.py
```

### 4. Test Connection

```bash
# Health check
curl http://localhost:8765/health

# WebSocket test (requires wscat)
wscat -c ws://localhost:8765/ws/live
```

## Deployment

### VPS Provisioning (Ubuntu)

```bash
# Run provisioning script
chmod +x scripts/setup_vps.sh
sudo ./scripts/setup_vps.sh
```

This will:
- Install Python 3.12+
- Install cloudflared daemon
- Create systemd services
- Create gemini user

### Cloudflare Tunnel Setup

```bash
# Login to Cloudflare
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create gemini-relay

# Route DNS
cloudflared tunnel route dns gemini-relay gemini.your-domain.com

# Start tunnel
sudo systemctl start cloudflared-tunnel
```

### Start Services

```bash
# Start relay
sudo systemctl start gemini-relay

# Enable auto-start
sudo systemctl enable gemini-relay
sudo systemctl enable cloudflared-tunnel

# Check status
sudo systemctl status gemini-relay
sudo systemctl status cloudflared-tunnel

# View logs
sudo journalctl -u gemini-relay -f
```

## API Reference

### WebSocket Endpoint

```
ws://localhost:8765/ws/live
```

Connect and send Gemini Live API messages. The relay will:
1. Forward messages to Gemini Live API
2. Return responses to client
3. Extract transcript chunks for memory spooling

### HTTP Endpoints

#### GET /health

```bash
curl http://localhost:8765/health
```

Response:
```json
{
  "status": "healthy",
  "service": "gemini_relay",
  "timestamp": "2024-01-15T10:30:00",
  "api_key_configured": true
}
```

#### GET /metrics

```bash
curl http://localhost:8765/metrics
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | - | Direct API key (optional if using Azure KV) |
| `AZURE_KEY_VAULT_NAME` | `arca-mcp-kv-dae` | Azure Key Vault name |
| `AZURE_TENANT_ID` | - | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | - | Service principal client ID |
| `AZURE_CLIENT_SECRET` | - | Service principal client secret |
| `GEMINI_SECRET_NAME` | `gemini-api-key` | Secret name in Azure KV |
| `MUNINN_URL` | - | Muninn endpoint for memory spooler |
| `RELAY_HOST` | `0.0.0.0` | Host to bind |
| `RELAY_PORT` | `8765` | Port to bind |

### Memory Spooler

The memory spooler automatically:
1. Extracts transcript chunks from Gemini responses
2. Aggregates them when the WebSocket connection closes
3. POSTs to `MUNINN_URL` as a background task (non-blocking)

Payload format:
```json
{
  "session_id": "session_20240115_103000_123456",
  "type": "gemini_live_transcript",
  "content": "Full aggregated transcript...",
  "metadata": {
    "source": "gemini_relay",
    "start_time": "2024-01-15T10:30:00",
    "end_time": "2024-01-15T10:35:00",
    "chunk_count": 42,
    "character_count": 1234
  }
}
```

## Resource Usage

Designed for micro VPS:

| Resource | Limit | Typical Usage |
|----------|-------|---------------|
| CPU | 0.1 vCPU | 5-15% |
| Memory | 256MB (hard limit) | 50-100MB |
| Disk | - | ~100MB |

### systemd Resource Limits

```ini
MemoryLimit=256M
CPUQuota=50%
```

## Troubleshooting

### Check Service Status

```bash
sudo systemctl status gemini-relay
sudo journalctl -u gemini-relay -f
```

### Common Issues

**"API key not configured"**
- Set `GEMINI_API_KEY` in `/etc/gemini_relay.env`
- Or configure Azure Key Vault credentials

**"Failed to connect to Gemini"**
- Check API key is valid
- Verify network connectivity to `generativelanguage.googleapis.com`

**"Memory limit exceeded"**
- Check for memory leaks in logs
- Reduce concurrent connections
- Consider upgrading VPS

### Restart Services

```bash
sudo systemctl restart gemini-relay
sudo systemctl restart cloudflared-tunnel
```

## File Structure

```
/opt/gemini_relay/
├── main.py                 # Main relay application
├── requirements.txt        # Python dependencies
├── scripts/
│   ├── setup_vps.sh       # VPS provisioning script
│   ├── gemini_relay.env   # Environment template
│   └── config.yml         # Cloudflare Tunnel config
└── systemd/
    ├── gemini-relay.service
    └── cloudflared-tunnel.service
```

## Security

- ✅ API keys stored in Azure Key Vault (recommended)
- ✅ systemd security hardening (`NoNewPrivileges`, `ProtectSystem`)
- ✅ Resource limits prevent runaway memory usage
- ✅ User isolation (runs as `gemini` user)

## License

MIT

## Related

- [Gemini Live API Docs](https://ai.google.dev/docs/gemini_live_api)
- [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Azure Key Vault Docs](https://docs.microsoft.com/en-us/azure/key-vault/)
