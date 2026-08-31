#!/bin/bash
# Test Notion Event Router deployment

WORKER_URL="https://hooks.arca-vsa.tech"
WEBHOOK_SECRET=""

# Test payload
PAYLOAD='{
  "event": {
    "id": "test-123",
    "created_time": "2024-01-01T00:00:00.000Z",
    "last_edited_time": "2024-01-01T00:00:00.000Z",
    "properties": {
      "title": [{"plain_text": "Test ARCA Task"}],
      "Tags": {"multi_select": [{"name": "ARCA"}, {"name": "urgent"}]},
      "Description": {"rich_text": [{"plain_text": "Testing Phase 1 deployment"}]}
    },
    "parent": {
      "type": "database_id",
      "database_id": "test-db-123"
    }
  }
}'

# Generate signature (HMAC SHA256)
SIGNATURE="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')"

echo "Testing Notion Event Router..."
echo "URL: $WORKER_URL"
echo "Payload: $PAYLOAD"
echo "Signature: $SIGNATURE"
echo ""

# Send request
curl -X POST "$WORKER_URL" \
  -H "Content-Type: application/json" \
  -H "X-Notion-Signature: $SIGNATURE" \
  -d "$PAYLOAD" \
  -w "\n\nHTTP Status: %{http_code}\n"

echo ""
echo "Check GitHub for new issue: https://github.com/danxalot/ARCA/issues"
echo "Check Pub/Sub: gcloud pubsub subscriptions pull os-events-sub --auto-ack"
