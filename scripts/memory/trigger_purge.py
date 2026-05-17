#!/usr/bin/env python3
"""
Emergency Memory Purge Trigger
Sends a purge request to the GCP Memory Orchestrator to remove rogue staging memories.
"""

import json
import urllib.request
import os

GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"

def trigger_purge():
    print("="*60)
    print("  BiOS Emergency Memory Purge Trigger")
    print("="*60)
    
    payload = {
        "operation": "purge",
        "source_filter": "staging",
        "timeframe": "48h"
    }
    
    print(f"📡 Sending purge request to: {GCP_GATEWAY_URL}")
    print(f"📋 Payload: {json.dumps(payload, indent=2)}")
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        GCP_GATEWAY_URL,
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        # Note: SSL verification is disabled as per previous pipeline stabilization
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
            result = json.loads(response.read().decode('utf-8'))
            print("-" * 60)
            print(f"✅ Response: {json.dumps(result, indent=2)}")
            print("-" * 60)
            print(f"Total Deleted: {result.get('deleted_counts', {}).get('total', 0)}")
    except Exception as e:
        print(f"❌ Failed to trigger purge: {e}")

if __name__ == "__main__":
    # Explicit safety check: This script should only be run when authorized.
    confirm = input("Are you sure you want to trigger a memory purge? (y/N): ")
    if confirm.lower() == 'y':
        trigger_purge()
    else:
        print("Purge aborted.")
