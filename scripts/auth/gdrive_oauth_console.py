#!/usr/bin/env python3
import json
import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

# ============================================================================
# BIOS 1.5.2 MANUAL GDRIVE OAUTH ORCHESTRATOR
# ============================================================================

def run_manual_flow():
    print("\n" + "=" * 70)
    print("  BiOS Manual GDrive OAuth Orchestrator")
    print("=" * 70 + "\n")

    client_config = {
        "installed": {
            "client_id": os.getenv("GDRIVE_CLIENT_ID", "757330161781-bost17tu1u4kuhuf6f8rjt6dm40u5ogp.apps.googleusercontent.com"),
            "client_secret": os.getenv("GDRIVE_CLIENT_SECRET", "PLACEHOLDER"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }
    }
    
    scopes = ['https://www.googleapis.com/auth/drive']
    # Use the OOB (Out-of-band) flow which is more robust when localhost is failing
    REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
    
    flow = InstalledAppFlow.from_client_config(
        client_config, 
        scopes,
        redirect_uri=REDIRECT_URI
    )
    
    # Generate the authorization URL
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    print("🚨 ACTION REQUIRED: Please authorize BiOS by clicking the link below:")
    print("-" * 70)
    print(auth_url)
    print("-" * 70)
    print("\nAfter authorizing, COPY the code provided by Google and paste it here.")
    
    try:
        code = input("\nEnter the authorization code: ").strip()
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        # Serialize to JSON
        token_json = creds.to_json()
        
        # Save locally to .local_gdrive_token.json
        TOKEN_PATH = "/Users/danexall/biomimetics/.local_gdrive_token.json"
        with open(TOKEN_PATH, "w") as f:
            f.write(token_json)
        
        print(f"\n✅ Token successfully generated and saved to {TOKEN_PATH}")

    except Exception as e:
        print(f"❌ OAuth Flow Failed: {e}")

if __name__ == "__main__":
    run_manual_flow()
