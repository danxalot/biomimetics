#!/usr/bin/env python3
"""
Proton Bridge STARTTLS Proof-of-Concept
Verifies Python can negotiate STARTTLS and authenticate with local Proton Mail Bridge.
"""

import imaplib
import ssl
import httpx
import sys
from pathlib import Path

# Configuration
CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_FILE = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
PROTON_HOST = "127.0.0.1"
PROTON_PORT = 1143
TEST_EMAIL = "dan@arca-vsa.tech"


def get_credentials_api_key() -> str:
    """Load Credentials API key from secure file."""
    if CREDENTIALS_FILE.exists():
        return CREDENTIALS_FILE.read_text().strip()
    raise FileNotFoundError(f"Credentials API key not found: {CREDENTIALS_FILE}")


def fetch_proton_password(api_key: str) -> str:
    """Fetch proton-bridge-password from Credentials Server."""
    response = httpx.get(
        f"{CREDENTIALS_SERVER_URL}/secrets/proton-bridge-password",
        headers={"X-API-Key": api_key},
        timeout=10
    )
    if response.status_code == 200:
        return response.json().get("value")
    raise Exception(f"Failed to fetch password: HTTP {response.status_code}")


def test_proton_bridge():
    """Test STARTTLS connection to Proton Bridge."""
    print("=" * 70)
    print("  Proton Bridge STARTTLS Proof-of-Concept")
    print("=" * 70)
    print()

    try:
        # Step 1: Load credentials
        print("📋 Step 1: Loading credentials...")
        api_key = get_credentials_api_key()
        print(f"   ✅ Credentials API key loaded")

        password = fetch_proton_password(api_key)
        print(f"   ✅ Proton Bridge password fetched from Credentials Server")
        print()

        # Step 2: Create SSL context (bypass hostname check for localhost)
        print("📋 Step 2: Creating SSL context...")
        ctx = ssl._create_unverified_context()
        print(f"   ✅ SSL context created (hostname verification disabled)")
        print()

        # Step 3: Connect via standard IMAP (unencrypted initially)
        print(f"📋 Step 3: Connecting to {PROTON_HOST}:{PROTON_PORT}...")
        mail = imaplib.IMAP4(PROTON_HOST, PROTON_PORT)
        print(f"   ✅ Connected to Proton Bridge")
        print()

        # Step 4: Upgrade to TLS
        print("📋 Step 4: Upgrading to STARTTLS...")
        mail.starttls(ssl_context=ctx)
        print(f"   ✅ STARTTLS negotiation successful")
        print()

        # Step 5: Authenticate
        print(f"📋 Step 5: Authenticating as {TEST_EMAIL}...")
        mail.login(TEST_EMAIL, password)
        print(f"   ✅ Authentication successful")
        print()

        # Step 6: Select INBOX and get count
        print("📋 Step 6: Selecting INBOX...")
        mail.select("INBOX")
        print(f"   ✅ INBOX selected")
        print()

        # Step 7: Get email count
        print("📋 Step 7: Counting emails...")
        status, messages = mail.search(None, "ALL")
        if status == "OK":
            email_count = len(messages[0].split())
            print(f"   ✅ INBOX contains {email_count} emails")
        else:
            print(f"   ❌ Search failed: {status}")
        print()

        # Cleanup
        mail.close()
        mail.logout()

        print("=" * 70)
        print("  ✅ STARTTLS PROOF-OF-CONCEPT SUCCESSFUL")
        print("=" * 70)
        print()
        print("  Summary:")
        print(f"   - Email: {TEST_EMAIL}")
        print(f"   - Host: {PROTON_HOST}:{PROTON_PORT}")
        print(f"   - Connection: IMAP4 → STARTTLS upgrade")
        print(f"   - Authentication: Successful")
        print(f"   - INBOX Count: {email_count} emails")
        print()
        print("  Ready for MCP server integration.")
        print()

        return True

    except Exception as e:
        print()
        print("=" * 70)
        print("  ❌ STARTTLS PROOF-OF-CONCEPT FAILED")
        print("=" * 70)
        print()
        print(f"  Error: {e}")
        print()
        print("  Stack trace:")
        import traceback
        traceback.print_exc()
        print()
        return False


if __name__ == "__main__":
    success = test_proton_bridge()
    sys.exit(0 if success else 1)
