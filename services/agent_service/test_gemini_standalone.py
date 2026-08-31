#!/usr/bin/env python3
"""Standalone test for Gemini Cloud AI Companion with service account"""
import asyncio
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import google.generativeai as genai

async def test_gemini():
    print("=" * 60)
    print("Testing Gemini Cloud AI Companion with Service Account")
    print("=" * 60)
    
    try:
        # Load service account credentials
        print("\n1. Loading service account credentials...")
        credentials = service_account.Credentials.from_service_account_file(
            '/home/ubuntu/ARCA/.secrets/gemini-reviewer-agent-credentials.json',
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        print(f"✓ Service account: {credentials.service_account_email}")
        
        # Refresh to get access token
        print("\n2. Getting OAuth access token...")
        credentials.refresh(Request())
        print(f"✓ Token obtained (expires: {credentials.expiry})")
        
        # Configure genai with the access token
        print("\n3. Configuring Gemini API...")
        genai.configure(api_key=credentials.token)
        
        # Create model
        model = genai.GenerativeModel('gemini-1.5-pro')
        print("✓ Model initialized: gemini-1.5-pro")
        
        # Test message
        print("\n4. Sending test message...")
        response = model.generate_content("Say 'Hello from Gemini!' in exactly 4 words.")
        print(f"✓ Response: {response.text}")
        
        print("\n" + "=" * 60)
        print("✓ Gemini Cloud AI Companion is working!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gemini())
