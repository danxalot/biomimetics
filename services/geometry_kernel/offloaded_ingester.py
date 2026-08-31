
import os
import sys
import time
import subprocess
import requests
import json
import logging
from threading import Thread
from flask import Flask, request, jsonify

# Configuration
MODAL_USER = "dan-exall"
# These MUST match the URLs from 'modal deploy' output
INFERENCE_URL = "https://dan-exall--arca-geometry-heavy-lifter-heavygeometryinges-9adcec.modal.run"
EMBEDDING_URL = "https://dan-exall--arca-geometry-heavy-lifter-heavygeometryinges-e75c3a.modal.run"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OffloadedIngester")

# 1. Start the Bridge Layer (Flask)
bridge_app = Flask(__name__)

@bridge_app.route("/v1/chat/completions", methods=["POST"])
def chat_proxy():
    data = request.json
    messages = data.get("messages", [])
    prompt = messages[-1]["content"] if messages else ""
    
    logger.info("📡 Forwarding Reasoning to Modal...")
    try:
        resp = requests.post(INFERENCE_URL, json={"prompt": prompt}, timeout=150.0)
        resp.raise_for_status()
        content = resp.json().get("content", "{}")
        return jsonify({"choices": [{"message": {"role": "assistant", "content": content}}]})
    except Exception as e:
        logger.error(f"Reasoning proxy failed: {e}")
        return jsonify({"error": str(e)}), 500

@bridge_app.route("/embed", methods=["POST"])
def embed_proxy():
    data = request.json
    texts = data.get("texts", [])
    if not texts: return jsonify({"embeddings": []})
    
    logger.info(f"📡 Forwarding {len(texts)} texts to Modal for embedding (Batched Proxy)...")
    
    all_embeddings = []
    LOCAL_BATCH_SIZE = 100
    
    try:
        for i in range(0, len(texts), LOCAL_BATCH_SIZE):
            batch = texts[i : i + LOCAL_BATCH_SIZE]
            logger.info(f"   📤 Sending batch {i//LOCAL_BATCH_SIZE + 1}/{(len(texts)-1)//LOCAL_BATCH_SIZE + 1} ({len(batch)} texts)")
            
            resp = requests.post(EMBEDDING_URL, json={"texts": batch}, timeout=120.0)
            resp.raise_for_status()
            
            batch_embeddings = resp.json().get("embeddings", [])
            all_embeddings.extend(batch_embeddings)
            
        logger.info(f"✅ Successfully embedded {len(all_embeddings)}/{len(texts)} texts")
        return jsonify({"embeddings": all_embeddings})
    except Exception as e:
        logger.error(f"Batched embedding proxy failed: {e}")
        return jsonify({"error": str(e)}), 500

@bridge_app.route("/health", methods=["GET"])
def health(): return jsonify({"status": "ok"})

def run_bridge(port):
    bridge_app.run(host="127.0.0.1", port=port, threaded=True)

# 2. Main Execution
if __name__ == "__main__":
    # Ports for geometry_kernel
    INSTRUCT_PORT = 8080
    EMBED_PORT = 8005
    
    # Start bridges in background threads
    Thread(target=run_bridge, args=(INSTRUCT_PORT,), daemon=True).start()
    Thread(target=run_bridge, args=(EMBED_PORT,), daemon=True).start()
    
    time.sleep(2) # Give Flask time to breathe
    
    # Set Environment Variables to point geometry_kernel here
    os.environ["ARCA_ENV"] = "local"
    os.environ["GPU_ROUTER_HOST"] = "127.0.0.1"
    os.environ["GPU_ROUTER_PORT"] = str(INSTRUCT_PORT)
    os.environ["EMBEDDING_SERVICE_URL"] = f"http://127.0.0.1:{EMBED_PORT}/embed"
    
    # Imports MUST be after env vars are set
    from services.geometry_kernel.model_engine import CognitiveScheduler
    from services.geometry_kernel.recursive_ingestion import RecursiveIngestion
    
    target_file = "/Users/danexall/Documents/VS Code Projects/ARCA/shared_storage/jobs/Gemini Training Chat.txt"
    # Fallback to relative if absolute mount missing locally
    if not os.path.exists(target_file):
        target_file = "shared_storage/jobs/Gemini Training Chat.txt"

    objective = "Extract all geometric trajectories and conceptual JEPA shifts from the Gemini Training Chat"
    
    logger.info(f"🚀 Starting Offloaded Ingestion for: {target_file}")
    
    scheduler = CognitiveScheduler()
    ingester = RecursiveIngestion(scheduler)
    
    try:
        result = ingester.ingest_content(
            file_path=target_file,
            objective=objective,
            content_type="NARRATIVE",
            verbosity="low",
            use_semantic_chunking=True
        )
        
        logger.info("✅ Ingestion Complete!")
        print(f"Summary: Found {len(result.get('objects', []))} objects.")
        
        # Save output
        output_path = "ingestion_result_modal_offloaded.json"
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"💾 Results saved to {output_path}")
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        sys.exit(1)
