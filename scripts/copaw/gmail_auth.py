#!/usr/bin/env python3
"""
Gmail OAuth2 Setup Script for CoPaw

This script guides you through setting up Gmail API credentials
and authorizing the CoPaw webhook receiver to access your Gmail.

Setup Instructions:
1. Go to https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Enable Gmail API
4. Create OAuth2 credentials (Desktop app)
5. Download credentials.json
6. Place at ~/.copaw/gmail/credentials.json
7. Run this script to complete authorization
"""

import os
import sys
import json
from pathlib import Path

# Gmail directories
GMAIL_DIR = Path.home() / ".copaw" / "gmail"
CREDENTIALS_PATH = GMAIL_DIR / "credentials.json"
TOKEN_PATH = GMAIL_DIR / "token.json"

# Required scopes for Gmail access
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]


def check_dependencies():
    """Check if required packages are installed"""
    missing = []
    
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        missing.append("google-auth")
    
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        missing.append("google-auth-oauthlib")
    
    try:
        from googleapiclient.discovery import build
    except ImportError:
        missing.append("google-api-python-client")
    
    if missing:
        print("❌ Missing dependencies. Install with:")
        print(f"   pip3 install {' '.join(missing)}")
        return False
    
    print("✅ All dependencies installed")
    return True


def setup_directory():
    """Create the Gmail config directory"""
    GMAIL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ Created directory: {GMAIL_DIR}")


def check_credentials_file():
    """Check if credentials.json exists"""
    if CREDENTIALS_PATH.exists():
        print(f"✅ Found credentials: {CREDENTIALS_PATH}")
        return True
    else:
        print(f"❌ Credentials not found: {CREDENTIALS_PATH}")
        print("\n📋 Setup Instructions:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create/select a project")
        print("3. Enable 'Gmail API' in APIs & Services > Library")
        print("4. Go to APIs & Services > Credentials")
        print("5. Click 'Create Credentials' > 'OAuth client ID'")
        print("6. Application type: 'Desktop app'")
        print("7. Download credentials.json")
        print(f"8. Move to: {CREDENTIALS_PATH}")
        return False


def run_oauth_flow():
    """Run OAuth2 authorization flow"""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    
    creds = None
    
    # Load existing token
    if TOKEN_PATH.exists():
        print(f"📄 Loading existing token: {TOKEN_PATH}")
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("\n🔐 Starting OAuth authorization flow...")
            print("   A browser window will open for you to authorize access")
            print("   Select your Google account and grant permissions")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
    
    # Save the credentials for the next run
    TOKEN_PATH.write_text(creds.to_json())
    print(f"✅ Token saved to: {TOKEN_PATH}")
    
    # Test the connection
    try:
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        print(f"\n✅ Successfully connected to Gmail!")
        print(f"   Logged in as: {profile['emailAddress']}")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to Gmail: {e}")
        return False


def main():
    """Main setup routine"""
    print("=" * 60)
    print("  CoPaw Gmail OAuth2 Setup")
    print("=" * 60)
    print()
    
    # Step 1: Check dependencies
    print("Step 1: Checking dependencies...")
    if not check_dependencies():
        sys.exit(1)
    print()
    
    # Step 2: Setup directory
    print("Step 2: Setting up directory...")
    setup_directory()
    print()
    
    # Step 3: Check credentials
    print("Step 3: Checking credentials file...")
    if not check_credentials_file():
        print("\n⚠️  Please download credentials.json and place it at:")
        print(f"   {CREDENTIALS_PATH}")
        print("\nThen run this script again.")
        sys.exit(1)
    print()
    
    # Step 4: Run OAuth flow
    print("Step 4: Running OAuth authorization...")
    if run_oauth_flow():
        print("\n" + "=" * 60)
        print("  ✅ Gmail setup complete!")
        print("=" * 60)
        print("\nYou can now use Gmail commands with Jarvis:")
        print("  - 'Search my emails from [person]'")
        print("  - 'Summarize my latest email'")
        print("  - 'Draft an email to [person] about [topic]'")
    else:
        print("\n❌ Setup failed. Please try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
