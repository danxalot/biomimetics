#!/usr/bin/env python3
import json
import os
import sys
import subprocess
from google_auth_oauthlib.flow import InstalledAppFlow

# ============================================================================
# BIOS 1.5.2 ZERO-TOUCH GDRIVE OAUTH INITIALIZATION
# ============================================================================

def run_oauth_flow():
    print("\n" + "=" * 70)
    print("  BiOS Zero-Touch GDrive OAuth Initialization")
    print("=" * 70 + "\n")

    # Hardcoded BiOS OAuth Credentials from detected ARCA environment
    client_config = {
        "installed": {
            "client_id": os.getenv("GDRIVE_CLIENT_ID", "757330161781-bost17tu1u4kuhuf6f8rjt6dm40u5ogp.apps.googleusercontent.com"),
            "client_secret": os.getenv("GDRIVE_CLIENT_SECRET", "PLACEHOLDER"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"]
        }
    }
    
    print("📡 Detected BiOS OAuth Identity: 757330161781...apps.googleusercontent.com")
    
    try:
        # Launching browser for authorization...
        scopes = ['https://www.googleapis.com/auth/drive']
        flow = InstalledAppFlow.from_client_config(client_config, scopes)
        
        # We use run_local_server to ensure we get a refresh_token
        creds = flow.run_local_server(port=0, prompt='consent', access_type='offline')
        
        # Serialize credentials to JSON string (this is our token.json)
        token_json = creds.to_json()
        
        print("\n✅ Authorization successful!")
        
        print("\n[STEP 3] Pushing token to Azure Key Vault (arca-mcp-kv-dae)...")
        # SECURITY: Push directly to Azure CLI, no local file saving.
        az_cmd = [
            "/usr/local/bin/az", "keyvault", "secret", "set",
            "--vault-name", "arca-mcp-kv-dae",
            "--name", "gdrive-oauth-token",
            "--value", token_json
        ]
        
        # Serialize credentials to JSON string (this is our token.json)
        token_json = creds.to_json()
        
        print("\n✅ Authorization successful!")
        
        print("\n[STEP 3] Pushing token to Azure Key Vault (arca-mcp-kv-dae)...")
        # SECURITY: Push directly to Azure CLI, no local file saving.
        az_cmd = [
            "/usr/local/bin/az", "keyvault", "secret", "set",
            "--vault-name", "arca-mcp-kv-dae",
            "--name", "gdrive-oauth-token",
            "--value", token_json
        ]
        
        result = subprocess.run(az_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Token securely pushed to Azure Key Vault.")
            print("   Secret Name: gdrive-oauth-token")
        else:
            print(f"❌ Azure CLI Error: {result.stderr}")
            print("\nManually push the following token string if needed:")
            print("-" * 70)
            print(token_json)
            print("-" * 70)

    except Exception as e:
        print(f"❌ OAuth Flow Failed: {e}")

if __name__ == "__main__":
    run_oauth_flow()
