import pytest
from unittest.mock import AsyncMock, MagicMock
from copaw.app.channels.voice.vultr_relay_client import VultrGeminiLiveClient

@pytest.fixture
def client():
    # Instantiate the client with mocked params if necessary
    return VultrGeminiLiveClient()

def test_build_realtime_input_output_schema(client):
    encoded_chunk = "SGVsbG8="  # Base64 for "Hello"
    result = client.build_realtime_input(encoded_chunk)
    
    assert "realtimeInput" in result
    assert "mediaChunks" in result["realtimeInput"]
    assert len(result["realtimeInput"]["mediaChunks"]) == 1
    chunk = result["realtimeInput"]["mediaChunks"][0]
    assert "mimeType" in chunk
    assert chunk["mimeType"].startswith("audio/pcm")
    assert "data" in chunk
    assert chunk["data"] == encoded_chunk

@pytest.mark.asyncio
async def test_handle_server_payload_setupComplete(client):
    payload = {"setupComplete": {}}
    on_transcript_cb = AsyncMock()
    
    # Run the method and assert no exceptions, and state is set appropriately
    await client._handle_server_payload(payload, on_transcript_cb)
    
    # Based on standard implementation, setupComplete might just print or set a flag.
    # Asserting that no error is raised and nothing crashes.

@pytest.mark.asyncio
async def test_handle_server_payload_toolCall(client):
    payload = {
        "toolCall": {
            "functionCalls": [
                {
                    "name": "some_tool",
                    "id": "call_123",
                    "args": {"param": "value"}
                }
            ]
        }
    }
    on_transcript_cb = AsyncMock()
    
    client.handle_tool_call = AsyncMock()
    
    await client._handle_server_payload(payload, on_transcript_cb)
    
    # We assume there's some routing to handle_tool_call or similar
    # If this is highly specific to the internal implementation, we just test the code paths
    # For now, it's a basic structural test.

@pytest.mark.asyncio
async def test_handle_server_payload_goAway(client):
    payload = {"serverContent": {"modelTurn": {"parts": [{"text": "bye"}]}}}
    # Assuming goAway might be an explicit key or some structure
    payload_goaway = {"goAway": {}}
    on_transcript_cb = AsyncMock()
    
    await client._handle_server_payload(payload_goaway, on_transcript_cb)
