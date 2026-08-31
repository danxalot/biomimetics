#!/usr/bin/env python3
"""
Re-embedding Script for memU Memory System
============================================
Re-generates embeddings for all existing memories using Gemini Embeddings API.

Usage:
    python reembed_memories.py [--batch-size N] [--dry-run]

Requirements:
    - memu container must be running with Gemini Embeddings enabled
    - Google API key with embeddings permissions
    - Qdrant access credentials
"""

import os
import sys
import asyncio
import aiohttp
import json
from typing import List, Dict, Any
from datetime import datetime

# Configuration from environment (same as memu service)
MEMU_URL = os.getenv("MEMU_URL", "http://localhost:8096")
QDRANT_URL = os.getenv("QDRANT_URL", "https://bfc3f711-81d4-43c6-b7bb-f58c99684d70.eu-west-2-0.aws.cloud.qdrant.io")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "arca_memory")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "1024"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5"))

# Load API key from file if provided
def load_api_key_from_file(file_path: str) -> str:
    """Load API key from file, handling KEY=VALUE format"""
    if not os.path.exists(file_path):
        return ""
    
    with open(file_path, "r") as f:
        val = f.read().strip()
    
    # Handle "KEY=VALUE" format
    if "=" in val and "\n" not in val:
        val = val.split("=", 1)[1].strip()
    elif ":" in val and "\n" not in val and not val.startswith("{"):
        parts = val.split(":", 1)
        if len(parts[0]) < 20:
            val = parts[1].strip()
    
    return val


async def get_all_memories_from_qdrant() -> List[Dict[str, Any]]:
    """Fetch all memory points from Qdrant"""
    import math
    
    url = f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/scroll"
    headers = {"api-key": QDRANT_API_KEY, "Content-Type": "application/json"}
    
    all_points = []
    offset = None
    
    async with aiohttp.ClientSession() as session:
        while True:
            payload = {"limit": 100}
            if offset:
                payload["offset"] = offset
            
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_body = await resp.text()
                    raise Exception(f"Qdrant error {resp.status}: {error_body}")
                
                data = await resp.json()
                points = data.get("result", {}).get("points", [])
                
                if not points:
                    break
                
                all_points.extend(points)
                
                if len(points) < 100:
                    break
                
                offset = points[-1]["id"]
    
    return all_points


async def generate_gemini_embedding(session: aiohttp.ClientSession, text: str) -> List[float]:
    """Generate embedding using Gemini Embeddings API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_EMBEDDING_MODEL}:embedContent?key={GEMINI_API_KEY}"
    
    payload = {
        "content": {"parts": [{"text": text}]},
        "model": f"models/{GEMINI_EMBEDDING_MODEL}",
    }
    
    async with session.post(url, json=payload) as resp:
        if resp.status != 200:
            error_body = await resp.text()
            raise Exception(f"Gemini API error {resp.status}: {error_body}")
        
        data = await resp.json()
        embedding = data.get("embedding", {}).get("values", [])
        
        if not embedding:
            raise Exception("No embedding returned from Gemini API")
        
        # Normalize
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding


async def update_memory_embedding(
    session: aiohttp.ClientSession,
    point_id: str,
    new_embedding: List[float],
) -> bool:
    """Update a single memory point's embedding in Qdrant"""
    url = f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points"
    headers = {"api-key": QDRANT_API_KEY, "Content-Type": "application/json"}
    
    payload = {
        "points": [{
            "id": point_id,
            "vector": new_embedding,
        }]
    }
    
    async with session.put(url, json=payload, headers=headers) as resp:
        if resp.status != 200:
            error_body = await resp.text()
            print(f"  ❌ Update failed for {point_id}: {error_body}")
            return False
        
        return True


async def reembed_all_memories(dry_run: bool = False, batch_size: int = 5):
    """Main re-embedding function"""
    print(f"🔍 Connecting to Qdrant at {QDRANT_URL}")
    print(f"📦 Collection: {QDRANT_COLLECTION}")
    print(f"🤖 Using Gemini Embeddings: {GEMINI_EMBEDDING_MODEL} @ {EMBEDDING_DIMS} dims")
    print(f"📊 Batch size: {batch_size}")
    print()
    
    if dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made")
        print()
    
    async with aiohttp.ClientSession() as session:
        # Fetch all memories
        print("📥 Fetching existing memories from Qdrant...")
        points = await get_all_memories_from_qdrant()
        print(f"✅ Found {len(points)} memories")
        print()
        
        if not points:
            print("No memories to re-embed.")
            return
        
        # Re-embed each memory
        reembedded_count = 0
        failed_count = 0
        skipped_count = 0
        
        for i, point in enumerate(points, 1):
            point_id = point.get("id")
            payload = point.get("payload", {})
            content = payload.get("content")
            
            if not content:
                print(f"[{i}/{len(points)}] ⚠️  Skipping {point_id}: No content")
                skipped_count += 1
                continue
            
            print(f"[{i}/{len(points)}] 🔄 Re-embedding {point_id[:8]}... ", end="")
            
            if dry_run:
                print("(dry run - skipped)")
                reembedded_count += 1
                continue
            
            try:
                # Generate new embedding
                embedding = await generate_gemini_embedding(session, content)
                
                if len(embedding) != EMBEDDING_DIMS:
                    print(f"❌ Wrong dimension: {len(embedding)} (expected {EMBEDDING_DIMS})")
                    failed_count += 1
                    continue
                
                # Update in Qdrant
                success = await update_memory_embedding(session, point_id, embedding)
                
                if success:
                    print("✅")
                    reembedded_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                print(f"❌ {str(e)[:50]}")
                failed_count += 1
            
            # Rate limiting - be nice to the API
            if i % batch_size == 0:
                await asyncio.sleep(0.5)
        
        print()
        print("=" * 50)
        print("📊 Re-embedding Complete!")
        print(f"   ✅ Re-embedded: {reembedded_count}")
        print(f"   ❌ Failed:      {failed_count}")
        print(f"   ⚠️  Skipped:     {skipped_count}")
        print(f"   📦 Total:       {len(points)}")
        print("=" * 50)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Re-embed memories with Gemini Embeddings")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Batch size for API calls")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()
    
    # Load API keys
    global QDRANT_API_KEY, GEMINI_API_KEY
    
    # Try to load from environment first
    if not QDRANT_API_KEY:
        qdrant_key_file = os.getenv("QDRANT_API_KEY_FILE")
        if qdrant_key_file:
            QDRANT_API_KEY = load_api_key_from_file(qdrant_key_file)
    
    if not GEMINI_API_KEY:
        gemini_key_file = os.getenv("GEMINI_API_KEY_FILE", "/app/.secrets/google_ai_studio")
        GEMINI_API_KEY = load_api_key_from_file(gemini_key_file)
    
    if not QDRANT_API_KEY:
        print("❌ Error: QDRANT_API_KEY not set and no key file found")
        sys.exit(1)
    
    if not GEMINI_API_KEY:
        print("❌ Error: GEMINI_API_KEY not set and no key file found")
        sys.exit(1)
    
    print("🔑 API keys loaded successfully")
    print()
    
    # Run re-embedding
    asyncio.run(reembed_all_memories(dry_run=args.dry_run, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
