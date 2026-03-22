#!/usr/bin/env python3
"""
Legacy CLAWS Data Migration Script
===================================
Migrates memory data from the old "claws" agent to the new omnimodal MemU system.

What it does:
1. Queries Firebase Firestore for all documents where user_id = "claws"
2. Extracts raw text content from each document
3. Generates 1536-dimension embeddings using gemini-embedding-2-preview
4. Upserts into new Qdrant collection (memu_archive_1536) with user_id = "copaw"

Requirements:
    pip install firebase-admin qdrant-client google-generativeai

Usage:
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcp-service-account.json
    export GEMINI_API_KEY="your-api-key"
    python migrate_claws_data.py
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional

# Configuration
FIREBASE_PROJECT = "arca-471022"
QDRANT_URL = "https://bfc3f711-81d4-43c6-b7bb-f58c99684d70.eu-west-2-0.aws.cloud.qdrant.io"
QDRANT_COLLECTION = "memu_archive_1536"
QDRANT_DIMENSION = 1536
LEGACY_USER_ID = "claws"
NEW_USER_ID = "copaw"
BATCH_SIZE = 50  # Process in batches to avoid rate limits


def get_gemini_api_key() -> str:
    """Get Gemini API key from environment or secret file"""
    # Try environment variable first
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]

    # Get ARCA secrets directory from environment or use default
    arca_secrets_dir = os.environ.get(
        "ARCA_SECRETS_DIR",
        "/Users/danexall/Documents/VS Code Projects/ARCA/.secrets"
    )

    # Try secret file
    secret_paths = [
        f"{arca_secrets_dir}/google_ai_studio",
        "/Users/danexall/.secrets/google_ai_studio",
        "./google_ai_studio",
    ]

    for path in secret_paths:
        if os.path.exists(path):
            with open(path) as f:
                content = f.read().strip()
                # Handle KEY=VALUE format
                if "=" in content and "\n" not in content:
                    return content.split("=", 1)[1].strip()
                return content

    raise RuntimeError("Gemini API key not found. Set GEMINI_API_KEY env var or create secret file.")


def init_firestore() -> Any:
    """Initialize Firebase Admin SDK"""
    import firebase_admin
    from firebase_admin import credentials, firestore

    # Check if already initialized
    try:
        apps = firebase_admin.get_app()
        if apps:
            return firestore.client()
    except ValueError:
        pass

    # Get ARCA secrets directory from environment or use default
    arca_secrets_dir = os.environ.get(
        "ARCA_SECRETS_DIR",
        "/Users/danexall/Documents/VS Code Projects/ARCA/.secrets"
    )

    # Try to find credentials
    cred_paths = [
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        f"{arca_secrets_dir}/gcp_credentials.json",
        "/Users/danexall/.secrets/gcp_credentials.json",
        "./gcp_credentials.json",
    ]

    cred_path = None
    for path in cred_paths:
        if path and os.path.exists(path):
            cred_path = path
            break

    if not cred_path:
        # Use application default credentials
        print("Using application default credentials...")
        firebase_admin.initialize_app()
    else:
        print(f"Using credentials from: {cred_path}")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    return firestore.client()


def init_qdrant() -> Any:
    """Initialize Qdrant client and create collection if needed"""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")

    # Get ARCA secrets directory from environment or use default
    arca_secrets_dir = os.environ.get(
        "ARCA_SECRETS_DIR",
        "/Users/danexall/Documents/VS Code Projects/ARCA/.secrets"
    )

    # Try to read from secret file
    secret_paths = [
        f"{arca_secrets_dir}/qdrant_api_key",
        "/Users/danexall/.secrets/qdrant_api_key",
    ]
    for path in secret_paths:
        if os.path.exists(path):
            with open(path) as f:
                qdrant_api_key = f.read().strip()
            break

    client = QdrantClient(url=QDRANT_URL, api_key=qdrant_api_key)
    
    # Check if collection exists
    collections = [c.name for c in client.get_collections().collections]
    
    if QDRANT_COLLECTION not in collections:
        print(f"Creating new collection: {QDRANT_COLLECTION} (1536 dims)...")
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=QDRANT_DIMENSION, distance=Distance.COSINE),
        )
        print(f"✅ Collection created: {QDRANT_COLLECTION}")
    else:
        print(f"✅ Collection exists: {QDRANT_COLLECTION}")
    
    return client


def generate_embedding(text: str, api_key: str) -> List[float]:
    """Generate 1536-dim embedding using gemini-embedding-2-preview"""
    try:
        import requests
        import certifi
    except ImportError:
        print("Please install: pip install requests certifi")
        return []
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2-preview:embedContent?key={api_key}"
    
    payload = {
        "content": {
            "parts": [{"text": text}]
        },
        "model": "models/gemini-embedding-2-preview",
        "outputDimensionality": 1536,  # Truncate to 1536 dims
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=30, verify=certifi.where())
        resp.raise_for_status()
        result = resp.json()
        return result.get("embedding", {}).get("values", [])
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error {e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:
        print(f"Embedding API error: {e}")
        return []


def fetch_legacy_memories(db: Any) -> List[Dict[str, Any]]:
    """Fetch all legacy memories from Firestore where user_id = 'claws'"""
    print(f"Querying Firestore for legacy '{LEGACY_USER_ID}' memories...")
    
    memories = []
    
    try:
        # Query the memories collection (adjust collection name as needed)
        collections = db.collections()
        
        for collection in collections:
            print(f"  Checking collection: {collection.id}")
            
            # Try different query patterns
            try:
                # Pattern 1: Direct user_id field
                docs = collection.where("user_id", "==", LEGACY_USER_ID).stream()
                for doc in docs:
                    data = doc.to_dict()
                    data['_doc_id'] = doc.id
                    data['_collection'] = collection.id
                    memories.append(data)
            except Exception:
                pass
            
            try:
                # Pattern 2: metadata.user_id
                docs = collection.where("metadata.user_id", "==", LEGACY_USER_ID).stream()
                for doc in docs:
                    data = doc.to_dict()
                    data['_doc_id'] = doc.id
                    data['_collection'] = collection.id
                    memories.append(data)
            except Exception:
                pass
            
            # Also check for documents with 'claws' in content (fallback)
            try:
                docs = collection.limit(1000).stream()
                for doc in docs:
                    data = doc.to_dict()
                    content = data.get("content", "") or data.get("text", "") or ""
                    if LEGACY_USER_ID.lower() in str(data).lower():
                        data['_doc_id'] = doc.id
                        data['_collection'] = collection.id
                        memories.append(data)
            except Exception:
                pass
    
    except Exception as e:
        print(f"⚠️  Firestore query error: {e}")
    
    print(f"Found {len(memories)} legacy documents")
    return memories


def extract_content(doc: Dict[str, Any]) -> Optional[str]:
    """Extract text content from a legacy document"""
    # Try common field names
    for field in ["content", "text", "body", "memory", "data"]:
        if doc.get(field):
            return str(doc[field])
    
    # Try nested content
    if "metadata" in doc and isinstance(doc["metadata"], dict):
        for field in ["content", "text", "body"]:
            if doc["metadata"].get(field):
                return str(doc["metadata"][field])
    
    return None


def migrate_memories(
    db: Any,
    qdrant: Any,
    gemini_api_key: str,
    dry_run: bool = False
) -> Dict[str, int]:
    """Main migration function"""
    
    stats = {
        "fetched": 0,
        "processed": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
    }
    
    # Fetch legacy memories
    memories = fetch_legacy_memories(db)
    stats["fetched"] = len(memories)
    
    if not memories:
        print("No legacy memories found to migrate.")
        return stats
    
    print(f"\nStarting migration of {len(memories)} documents...")
    print(f"  From: {LEGACY_USER_ID}")
    print(f"  To:   {NEW_USER_ID}")
    print(f"  Collection: {QDRANT_COLLECTION}")
    print(f"  Dimensions: {QDRANT_DIMENSION}")
    
    if dry_run:
        print("\n🔍 DRY RUN MODE - No data will be written")
    
    points = []
    
    for i, doc in enumerate(memories):
        try:
            # Extract content
            content = extract_content(doc)
            
            if not content or len(content.strip()) < 10:
                stats["skipped"] += 1
                continue
            
            # Generate embedding
            embedding = generate_embedding(content, gemini_api_key)
            
            if not embedding or len(embedding) != QDRANT_DIMENSION:
                print(f"  ⚠️  Invalid embedding for doc {i}")
                stats["errors"] += 1
                continue
            
            # Create Qdrant point
            doc_id = doc.get("_doc_id", hashlib.md5(content.encode()).hexdigest()[:16])
            
            # Prepare metadata
            metadata = {
                "original_user_id": LEGACY_USER_ID,
                "migrated_user_id": NEW_USER_ID,
                "original_collection": doc.get("_collection", "unknown"),
                "migrated_at": datetime.now().isoformat(),
                "content_length": len(content),
            }
            
            # Preserve original metadata
            if "metadata" in doc and isinstance(doc["metadata"], dict):
                metadata.update({k: str(v) for k, v in doc["metadata"].items() if k not in ["embedding", "vector"]})
            
            point = {
                "id": doc_id,
                "vector": embedding,
                "payload": {
                    "content": content,
                    "user_id": NEW_USER_ID,  # Reassign to copaw
                    "source": "claws_migration",
                    **metadata
                }
            }
            
            points.append(point)
            stats["processed"] += 1
            
            # Batch upsert
            if len(points) >= BATCH_SIZE:
                if not dry_run:
                    qdrant.upsert(
                        collection_name=QDRANT_COLLECTION,
                        points=points
                    )
                print(f"  ✓ Batch of {len(points)} uploaded")
                points = []
            
        except Exception as e:
            print(f"  ✗ Error processing doc {i}: {e}")
            stats["errors"] += 1
    
    # Upload remaining points
    if points:
        if not dry_run:
            qdrant.upsert(
                collection_name=QDRANT_COLLECTION,
                points=points
            )
        print(f"  ✓ Final batch of {len(points)} uploaded")
    
    stats["migrated"] = len(memories) - stats["skipped"] - stats["errors"]
    
    return stats


def print_stats(stats: Dict[str, int]):
    """Print migration statistics"""
    print("\n" + "=" * 50)
    print("MIGRATION COMPLETE")
    print("=" * 50)
    print(f"  Total fetched:    {stats['fetched']}")
    print(f"  Processed:        {stats['processed']}")
    print(f"  Successfully migrated: {stats['migrated']}")
    print(f"  Skipped (empty):  {stats['skipped']}")
    print(f"  Errors:           {stats['errors']}")
    print("=" * 50)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate CLAWS legacy data to MemU omnimodal")
    parser.add_argument("--dry-run", action="store_true", help="Preview migration without writing")
    parser.add_argument("--verify", action="store_true", help="Verify migration after completion")
    args = parser.parse_args()
    
    print("=" * 50)
    print("CLAWS → MemU Omnimodal Migration")
    print("=" * 50)
    print(f"  Qdrant Collection: {QDRANT_COLLECTION}")
    print(f"  Dimensions:        {QDRANT_DIMENSION}")
    print(f"  Legacy User:       {LEGACY_USER_ID}")
    print(f"  New User:          {NEW_USER_ID}")
    print("=" * 50)
    
    # Get API key
    try:
        gemini_api_key = get_gemini_api_key()
        print(f"✅ Gemini API key loaded")
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Initialize clients
    print("\nInitializing clients...")
    db = init_firestore()
    print("✅ Firestore connected")
    
    qdrant = init_qdrant()
    print("✅ Qdrant connected")
    
    # Run migration
    print()
    stats = migrate_memories(db, qdrant, gemini_api_key, dry_run=args.dry_run)
    print_stats(stats)
    
    # Verify migration
    if args.verify and not args.dry_run:
        print("\nVerifying migration...")
        try:
            result = qdrant.count(
                collection_name=QDRANT_COLLECTION,
                count_filter={
                    "must": [
                        {"key": "user_id", "match": {"value": NEW_USER_ID}},
                        {"key": "source", "match": {"value": "claws_migration"}}
                    ]
                }
            )
            print(f"✅ Verified: {result.count} migrated documents in Qdrant")
        except Exception as e:
            print(f"⚠️  Verification error: {e}")
    
    print("\n✨ Migration complete!")


if __name__ == "__main__":
    main()
