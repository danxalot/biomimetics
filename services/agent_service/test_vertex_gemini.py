#!/usr/bin/env python3
"""Test Gemini via Vertex AI with service account"""
import asyncio
from google.oauth2 import service_account
from vertexai.generative_models import GenerativeModel
import vertexai

async def test_vertex_gemini():
    print("=" * 60)
    print("Testing Gemini via Vertex AI (Enterprise Trial)")
    print("=" * 60)
    
    try:
        # Load service account credentials
        print("\n1. Loading service account credentials...")
        credentials = service_account.Credentials.from_service_account_file(
            '/home/ubuntu/ARCA/.secrets/gemini-reviewer-agent-credentials.json',
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        print(f"✓ Service account: {credentials.service_account_email}")
        
        # Initialize Vertex AI
        print("\n2. Initializing Vertex AI...")
        vertexai.init(
            project="arca-471022",
            location="us-central1",
            credentials=credentials
        )
        print("✓ Vertex AI initialized")
        
        # Create model
        print("\n3. Creating Gemini model...")
        model = GenerativeModel('gemini-1.5-pro')
        print("✓ Model: gemini-1.5-pro")
        
        # Test message
        print("\n4. Sending test message...")
        chat = model.start_chat()
        response = chat.send_message("Say 'Hello from Vertex AI Gemini!' in exactly 6 words.")
        print(f"✓ Response: {response.text}")
        
        print("\n" + "=" * 60)
        print("✓ Gemini via Vertex AI is working!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_vertex_gemini())
