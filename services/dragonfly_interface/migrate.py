
import os
import json
import asyncio
import argparse
import requests
from tqdm import tqdm
from client import DragonflyClient
import sys

# Qwen Embedding Endpoint (OCI HDEmbedding)
EMBEDDING_URL = "http://100.70.0.13:8081/v1/embeddings" 

def get_embedding(text: str):
    """Get embedding from Qwen/SigLIP via Embedding Service."""
    try:
        payload = {
            "input": text,
            "model": "qwen3-embedding" 
        }
        res = requests.post(EMBEDDING_URL, json=payload)
        res.raise_for_status()
        return res.json()["data"][0]["embedding"]
    except Exception as e:
        print(f"Embedding failed: {e}")
        return None

def migrate(concept_dir: str, redis_host: str, redis_port: int, dimension: int):
    print(f"Connecting to Dragonfly at {redis_host}:{redis_port}...")
    client = DragonflyClient(host=redis_host, port=redis_port)
    
    # Create Index
    client.create_index(dimension)
    
    if not os.path.exists(concept_dir):
        print(f"Error: Concept directory {concept_dir} not found.")
        return

    files = [f for f in os.listdir(concept_dir) if f.endswith(".json")]
    print(f"Found {len(files)} concept files.")
    
    for filename in tqdm(files):
        path = os.path.join(concept_dir, filename)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                
            # Content is the key
            content = data.get("content", "")
            if not content:
                continue

            # Generate ID if missing
            concept_id = filename.replace(".json", "")
            
            # GENERATE EMBEDDING (The "Lifting")
            hv_sig = get_embedding(content)
            
            if hv_sig:
                if len(hv_sig) != dimension:
                   # Pad or truncate if dimension mismatch (temporary fix for valid storage)
                   # Real fix: Ensure Embedding Service returns correct dim
                   if len(hv_sig) < dimension:
                       hv_sig += [0.0] * (dimension - len(hv_sig))
                   else:
                       hv_sig = hv_sig[:dimension]

                client.add_concept(concept_id, hv_sig, data)
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    print("Migration complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="./shared_storage/reasoning_bank", help="Path to concept JSONs")
    parser.add_argument("--host", default="localhost", help="Dragonfly host")
    parser.add_argument("--port", type=int, default=6379, help="Dragonfly port")
    parser.add_argument("--dim", type=int, default=2048, help="Vector dimension") # Qwen 2B OCI
    args = parser.parse_args()
    
    migrate(args.dir, args.host, args.port, args.dim)
