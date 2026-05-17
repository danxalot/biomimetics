#!/usr/bin/env python3
"""
Standalone CLI script to trigger manifold backup from outside the container.
Usage: python trigger_backup.py [TARGET_IP]
"""
import sys
import os
import requests
import json

def trigger_snapshot(target_ip: str = None) -> dict:
    """
    Trigger manifold snapshot via HTTP POST to the neural system API.
    
    Args:
        target_ip: IP address of the target container. If None, uses environment variable or defaults to localhost.
        
    Returns:
        dict: Response from the API
    """
    # Determine target IP
    if target_ip is None:
        target_ip = os.environ.get('TARGET_IP', 'localhost')
    
    # Construct URL
    port = os.environ.get('PORT', '8086')
    url = f"http://{target_ip}:{port}/system/snapshot"
    
    print(f"Triggering manifold snapshot at {url}")
    
    try:
        # Make POST request
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        
        # Parse and return response
        result = response.json() if response.content else {"status": "success"}
        print(f"Snapshot triggered successfully: {result}")
        return result
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to trigger snapshot: {e}"
        print(error_msg, file=sys.stderr)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        print(error_msg, file=sys.stderr)
        return {"error": error_msg}

def main():
    """Main entry point for CLI usage."""
    # Get target IP from command line argument or environment
    target_ip = sys.argv[1] if len(sys.argv) > 1 else None
    
    result = trigger_snapshot(target_ip)
    
    # Print result as JSON for easy parsing
    print(json.dumps(result, indent=2))
    
    # Exit with appropriate code
    if "error" in result:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()