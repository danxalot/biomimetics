
import json
import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Config - Set these to your Modal deployment URLs after 'modal deploy'
# Format: https://<username>--arca-geometry-heavy-lifter-heavygeometryingester-<endpoint>.modal.run
MODAL_USER = os.environ.get("MODAL_USER", "dan-exall")
BASE_URL = f"https://{MODAL_USER}--arca-geometry-heavy-lifter-heavygeometryingester"

INFERENCE_URL = f"{BASE_URL}-inference.modal.run"
EMBEDDING_URL = f"{BASE_URL}-embedding.modal.run"

print(f"🚀 Modal Bridge Active")
print(f"🔗 Instruct: {INFERENCE_URL}")
print(f"🔗 Embed:    {EMBEDDING_URL}")

@app.route("/v1/chat/completions", methods=["POST"])
def chat_proxy():
    """Simulate OpenAI/llama.cpp chat endpoint for geometry_kernel."""
    data = request.json
    messages = data.get("messages", [])
    
    # Extract prompt from messages (simple mapping)
    prompt = ""
    context = ""
    for msg in messages:
        if msg["role"] == "user":
            prompt = msg["content"]
        elif msg["role"] == "system":
            # Some systems might pass context in system prompt
            pass

    print(f"📡 Forwarding Inference to Modal...")
    try:
        resp = requests.post(INFERENCE_URL, json={"prompt": prompt, "context": context}, timeout=120.0)
        resp.raise_for_status()
        content = resp.json().get("content", "{}")
        
        # Return OpenAI compatible format
        return jsonify({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content
                }
            }]
        })
    except Exception as e:
        print(f"❌ Inference bridge error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/embed", methods=["POST"])
@app.route("/embedding", methods=["POST"])
def embed_proxy():
    """Simulate embedding endpoint."""
    data = request.json
    texts = data.get("texts", [])
    if not texts and "content" in data:
        texts = [data["content"]]

    print(f"📡 Forwarding Embedding to Modal...")
    try:
        resp = requests.post(EMBEDDING_URL, json={"texts": texts}, timeout=60.0)
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
        
        # Return standard format
        return jsonify({"embeddings": embeddings, "data": [{"embedding": e} for e in embeddings]})
    except Exception as e:
        print(f"❌ Embedding bridge error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # Internal ports matching geometry_kernel expectations
    # 8080 for GPU Router (Instruct)
    # 8005 for Embedding Service
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    app.run(host="0.0.0.0", port=port)
