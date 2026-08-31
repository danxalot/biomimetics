# Phase 2: GCP Free Tier Only Configuration

**ALL resources deployed exclusively on GCP free tier**  
**NO local dependencies** (except Copaw conversation logging)  
**Same region as existing ARCA resources**

---

## 🆓 Free Tier Architecture

```
Notion Webhook (hooks.arca-vsa.tech)
         ↓
GCP Pub/Sub (os-events) - FREE: 10GB/month
         ↓
    ┌────┴────────────────┐
    ↓                     ↓
MemU (Cloud Run)    MuninnDB Global
- 512MB RAM         - e2-micro (1GB RAM)
- 1 CPU             - 20GB disk
- FREE: 2M req/mo   - FREE: 720 hrs/mo
- API calls only    - Same region as ARCA
  (Gemini/Gemma)
```

---

## 💰 Free Tier Limits

| Service | Free Tier Limit | Our Usage |
|---------|----------------|-----------|
| **Cloud Run** | 2M requests/month | ~100K estimated |
| **Cloud Run** | 360,000 GB-seconds/month | ~18,000 (512MB × 24/7) |
| **Cloud Run** | 180,000 vCPU-seconds/month | ~9,000 (1 vCPU × 24/7) |
| **Compute Engine** | 720 hours e2-micro/month | 720 hours (1 instance) |
| **Persistent Disk** | 30 GB-months/month | 20 GB |
| **Pub/Sub** | 10 GB/month | ~1 GB |
| **Pub/Sub** | 1M messages/month | ~100K |
| **Container Registry** | 1 GB storage | ~500 MB |
| **Monitoring** | 150MB ingest/month | ~10 MB |
| **Gemini API** | Pay-per-use | ~$0-5/month |

**Total Monthly Cost**: **$0-10** (mostly API calls)

---

## 🚀 Deployment (2 Scripts)

### Step 1: Deploy MemU to Cloud Run

```bash
cd /Users/danexall/Documents/VS Code Projects/ARCA
chmod +x services/memu/deploy-cloudrun-freetier.sh
./services/memu/deploy-cloudrun-freetier.sh
```

**Configuration**:
- Region: `europe-west1` (same as ARCA)
- Memory: 512MB
- CPU: 1
- Concurrency: 50
- Min instances: 0 (sleeps when idle)

---

### Step 2: Deploy MuninnDB Global to e2-micro

```bash
chmod +x services/muninn/setup-muninn-gcp-freetier.sh
./services/muninn/setup-muninn-gcp-freetier.sh
```

**Configuration**:
- Machine: e2-micro (1GB RAM, 0.25 vCPU)
- Disk: 20GB (alerts at 1.5GB usage)
- Region: `europe-west1`
- Zone: `europe-west1-b`
- Max engrams: 50,000
- Monthly requests: 100,000

---

## 📊 Quota Monitoring & Alerts

### Storage Alerts (MuninnDB)

- **75% threshold** (1.5GB / 2GB): Warning logged
- **90% threshold** (1.8GB / 2GB): Aggressive cleanup triggered
- **100% threshold**: Auto-delete lowest activation engrams

### Request Quota Alerts (MuninnDB)

- **75% threshold** (75,000 / 100,000): Alert sent to Cloud Monitoring
- **100% threshold**: Reject new engrams (read-only mode)

### Cloud Monitoring Integration

```bash
# View quota alerts
gcloud monitoring channels list

# View time series data
gcloud monitoring time-series list \
  --filter='metric.type="custom.googleapis.com/muninn/quota_usage"'
```

---

## 🔧 Copaw Integration (GCP-Only)

### Configuration

```python
from muninn_integration import CopawMuninnBridge, copaw_message_hook

# Initialize with GCP URL (NO localhost!)
muninn_bridge = CopawMuninnBridge(
    muninn_gcp_url="http://<EXTERNAL_IP>:8097",  # GCP MuninnDB
    session_id=session_id,
)

# Log every conversation turn
for message in conversation:
    await copaw_message_hook(message, muninn_bridge)
    
    # Retrieve relevant memories (from GCP)
    if message.get("role") == "user":
        memories = await muninn_bridge.retrieve_relevant_memories(
            query=message.get("content", ""),
            limit=3,
        )
```

### What Gets Logged

**Every Copaw conversation turn**:
- Role (user/assistant)
- Content (full text)
- Tools used (e.g., `["read_file", "shell"]`)
- Files accessed (e.g., `["/path/to/file.py"]`)
- Session ID
- Timestamp

**All Pub/Sub events**:
- Event type (e.g., `notion.task.created`)
- Source system
- Full payload
- Attributes

**NO local storage** - everything goes directly to GCP MuninnDB.

---

## 🧪 Testing

### Test MemU (Cloud Run)

```bash
# Get service URL
MEMU_URL=$(gcloud run services describe memu --region=europe-west1 --format='value(status.url)')

# Health check
curl ${MEMU_URL}/health

# Test embedding (Gemini)
curl -X POST ${MEMU_URL}/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "Test memory"}'
```

### Test MuninnDB (GCP e2-micro)

```bash
# Get external IP
MUNINN_IP=$(gcloud compute instances describe muninn-global --zone=europe-west1-b --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

# Stats endpoint
curl http://${MUNINN_IP}:8097/stats

# Create engram
curl -X POST http://${MUNINN_IP}:8097/engrams \
  -H "Content-Type: application/json" \
  -d '{"type":"test","content":{"text":"Test engram"}}'

# Check quota usage
curl http://${MUNINN_IP}:8097/stats | jq '.storage_usage_percent, .request_usage_percent'
```

---

## 📁 Files Created

| File | Purpose |
|------|---------|
| `services/memu/deploy-cloudrun-freetier.sh` | Cloud Run deployment (512MB) |
| `services/muninn/setup-muninn-gcp-freetier.sh` | e2-micro deployment (20GB) |
| `services/muninn/muninn_server.py` | MuninnDB with quota monitoring |
| `services/muninn/copaw_integration.py` | GCP-only Copaw bridge |
| `services/memu/Dockerfile` | MemU container |

---

## ✅ Verification Checklist

### MemU (Cloud Run)

- [ ] Deployed to `europe-west1`
- [ ] Memory: 512MB
- [ ] CPU: 1
- [ ] Health endpoint responds
- [ ] Gemini embeddings working
- [ ] Gemma 3 agent responding
- [ ] NO local dependencies

### MuninnDB Global (e2-micro)

- [ ] Instance running in `europe-west1-b`
- [ ] Disk: 20GB
- [ ] MCP port 8097 accessible
- [ ] Storage alerts at 75% (1.5GB)
- [ ] Request alerts at 75% (75K)
- [ ] Hebbian learning enabled
- [ ] ACT-R decay working
- [ ] Auto-cleanup at 90% storage

### Copaw Integration

- [ ] All conversation turns logged to GCP
- [ ] All Pub/Sub events captured
- [ ] Memory retrieval from GCP
- [ ] NO local storage
- [ ] Session tracking working

---

## 🎯 Success Criteria

Phase 2 is complete when:

1. ✅ MemU on Cloud Run (512MB, 1 CPU)
2. ✅ MuninnDB on e2-micro (20GB disk)
3. ✅ Both in `europe-west1` region
4. ✅ 75% quota alerts working
5. ✅ Storage auto-cleanup at 90%
6. ✅ All Copaw conversations logged to GCP
7. ✅ All Pub/Sub events stored in GCP
8. ✅ NO local dependencies (except Copaw client)
9. ✅ Total cost: $0-10/month

---

## 🚀 Deploy Now

```bash
# 1. Deploy MemU
./services/memu/deploy-cloudrun-freetier.sh

# 2. Deploy MuninnDB
./services/muninn/setup-muninn-gcp-freetier.sh

# 3. Test endpoints
curl $(gcloud run services describe memu --region=europe-west1 --format='value(status.url)')/health

MUNINN_IP=$(gcloud compute instances describe muninn-global --zone=europe-west1-b --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
curl http://${MUNINN_IP}:8097/stats
```

---

**100% GCP Free Tier - Ready to Deploy!** 🎯
