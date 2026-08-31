# Phase 2: Dual-Tier Memory Matrix - Quick Start

**Status**: Ready to Deploy  
**Architecture**: MemU (Deep Archive) + MuninnDB (Working Memory)

---

## 🚀 Quick Deployment (3 Steps)

### Step 1: Set Up Pub/Sub

```bash
cd /Users/danexall/Documents/VS Code Projects/ARCA
./services/memu/setup-pubsub.sh
```

This creates:
- Topic: `os-events` (already exists from Phase 1)
- Subscription: `memu-memory-events` (for MemU)
- Subscription: `muninn-global-events` (for MuninnDB)

---

### Step 2: Deploy MemU to Cloud Run

```bash
./services/memu/deploy-cloudrun.sh
```

This will:
1. Build Docker image with Gemini Embeddings + Gemma 3
2. Push to GCR
3. Deploy to Cloud Run (europe-west1)
4. Configure 2GB RAM, 2 CPU

**Output**: Cloud Run URL (save this!)

---

### Step 3: Deploy Local MuninnDB

```bash
docker-compose -f docker-compose.muninn-local.yml up -d
```

This starts Local MuninnDB on port 8098.

**Test**: http://localhost:8098/stats

---

## 📊 Architecture Overview

```
Notion Webhook (hooks.arca-vsa.tech)
         ↓
GCP Pub/Sub (os-events)
         ↓
    ┌────┴────┐
    ↓         ↓
MemU      MuninnDB Global
(Cloud    (GCP e2-micro)
Run)         ↓
 ↓           ↓
Qdrant   MuninnDB Local
Firebase   (Docker - Mac)
Gemini         ↓
Gemma 3    Copaw Integration
```

---

## 🔧 Configuration Summary

### MemU (Cloud Run)

| Setting | Value |
|---------|-------|
| **URL** | Deployed URL from Step 2 |
| **Embeddings** | Gemini text-embedding-004 (1024 dims) |
| **Agent** | Gemma 3 12B (gemma-3-12b-it) |
| **Vector Store** | Qdrant Cloud |
| **Structured Store** | Firebase Firestore |
| **MCP Port** | 8096 |

### MuninnDB Global (GCP e2-micro)

| Setting | Value |
|---------|-------|
| **Location** | GCP e2-micro VM |
| **Storage** | 30GB persistent disk |
| **MCP Port** | 8097 |
| **Learning** | Hebbian + ACT-R |
| **Pub/Sub** | muninn-global-events |

### MuninnDB Local (Docker)

| Setting | Value |
|---------|-------|
| **Location** | Local Mac (Docker) |
| **Port** | 8098 |
| **Storage** | ./data/muninn-local |
| **Mode** | Transient (dev scratchpad) |
| **Auto-flush** | Every hour |

---

## ✅ Verification Checklist

### MemU (Cloud Run)

- [ ] Deployed to Cloud Run
- [ ] Cloud Run URL saved
- [ ] Secrets configured (Google AI Studio, Qdrant, Firebase)
- [ ] Test endpoint: `https://<url>/health`
- [ ] Gemini embeddings working
- [ ] Gemma 3 agent responding
- [ ] Qdrant connection verified
- [ ] Firebase connection verified

### MuninnDB Global (GCP e2-micro)

- [ ] e2-micro VM created
- [ ] 30GB disk attached
- [ ] MuninnDB installed
- [ ] Systemd service running
- [ ] Pub/Sub subscription active
- [ ] MCP endpoint accessible (port 8097)
- [ ] Hebbian learning enabled
- [ ] ACT-R parameters configured

### MuninnDB Local (Docker)

- [ ] Docker container running
- [ ] Port 8098 accessible
- [ ] Test: http://localhost:8098/stats
- [ ] Serena integration enabled
- [ ] Transient tracking mode active

### Copaw Integration

- [ ] Muninn bridge configured
- [ ] Conversation turns logged
- [ ] Pub/Sub events logged
- [ ] Memory retrieval working
- [ ] Relevant artifacts surfaced

---

## 🧪 Testing

### Test MemU

```bash
# Health check
curl https://<memu-cloud-run-url>/health

# Test embedding
curl -X POST https://<memu-cloud-run-url>/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "Test memory"}'

# Test MCP
curl https://<memu-cloud-run-url>/mcp
```

### Test MuninnDB Local

```bash
# Stats
curl http://localhost:8098/stats

# Create engram
curl -X POST http://localhost:8098/engrams \
  -H "Content-Type: application/json" \
  -d '{
    "type": "test",
    "content": {"text": "Test engram"},
    "metadata": {}
  }'

# Search
curl "http://localhost:8098/engrams?limit=5"
```

### Test Pub/Sub Integration

```bash
# Publish test event
gcloud pubsub topics publish os-events \
  --message='{"event_type":"test","data":{"message":"Hello from Phase 2"}}'

# Check MemU logs
# Check MuninnDB engrams
curl http://localhost:8098/engrams
```

---

## 💰 Cost Estimate

| Service | Monthly Cost |
|---------|-------------|
| **MemU (Cloud Run)** | $0-5 (sleeps when idle) |
| **MuninnDB Global (e2-micro + 30GB)** | $10-15 |
| **MuninnDB Local** | $0 |
| **Qdrant Cloud** | $0-25 (free tier) |
| **Firebase** | $0 (free tier) |
| **GCP Pub/Sub** | $0 (free tier) |
| **Total** | **$10-45/mo** |

---

## 📁 Files Created

| File | Purpose |
|------|---------|
| `services/memu/Dockerfile` | MemU container |
| `services/memu/deploy-cloudrun.sh` | Cloud Run deployment |
| `services/memu/setup-pubsub.sh` | Pub/Sub setup |
| `services/muninn/muninn_server.py` | MuninnDB server |
| `services/muninn/copaw_integration.py` | Copaw bridge |
| `docker-compose.muninn-local.yml` | Local MuninnDB |
| `PHASE2_DEPLOYMENT.md` | Full deployment guide |

---

## 🎯 Success Criteria

Phase 2 is complete when:

1. ✅ MemU deployed and responding on Cloud Run
2. ✅ Gemini Embeddings generating 1024-dim vectors
3. ✅ Gemma 3 agent answering queries
4. ✅ MuninnDB Global running on e2-micro
5. ✅ Hebbian learning active
6. ✅ MuninnDB Local running in Docker
7. ✅ All Copaw conversations logged
8. ✅ All Pub/Sub events stored
9. ✅ Memories retrievable by relevance

---

## 🚀 Next Steps

After Phase 2 deployment:

1. **Test end-to-end flow**: Notion → Pub/Sub → MemU + MuninnDB
2. **Configure Copaw**: Enable conversation logging
3. **Test memory retrieval**: Ask Copaw about past conversations
4. **Monitor learning**: Watch Hebbian connections form
5. → **Proceed to Phase 3** (if applicable)

---

**Ready to deploy? Start with Step 1!** 🎯
