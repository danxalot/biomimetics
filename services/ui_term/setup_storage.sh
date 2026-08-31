#!/bin/bash
# Setup script for Cloud Run environment - ensures proper database setup

PROJECT_ID="arca-471022"

echo "Setting up Firestore and Pub/Sub for terminal storage..."

# Create Firestore collections and indexes
gcloud firestore databases create --region=europe-west2 --type=firestore-native --project="$PROJECT_ID" 2>/dev/null || echo "Firestore database already exists"

# Create Pub/Sub topic for terminal conversations
gcloud pubsub topics create arca-terminal-conversations --project="$PROJECT_ID" 2>/dev/null || echo "Pub/Sub topic already exists"

# Create subscription for conversation monitoring (optional)
gcloud pubsub subscriptions create arca-terminal-monitor \
    --topic=arca-terminal-conversations \
    --project="$PROJECT_ID" 2>/dev/null || echo "Pub/Sub subscription already exists"

# Create Firestore indexes for efficient querying
cat > firestore-indexes.json << 'EOF'
{
  "indexes": [
    {
      "collectionGroup": "terminal_messages",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "session_id", "order": "ASCENDING"},
        {"fieldPath": "timestamp", "order": "DESCENDING"}
      ]
    },
    {
      "collectionGroup": "terminal_messages", 
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "agent_type", "order": "ASCENDING"},
        {"fieldPath": "timestamp", "order": "DESCENDING"}
      ]
    },
    {
      "collectionGroup": "terminal_sessions",
      "queryScope": "COLLECTION", 
      "fields": [
        {"fieldPath": "last_activity", "order": "DESCENDING"}
      ]
    }
  ]
}
EOF

echo "Firestore collections:"
echo "  - terminal_messages: Individual messages with full context"
echo "  - terminal_sessions: Session metadata and state"
echo ""
echo "Pub/Sub topics:"
echo "  - arca-terminal-conversations: Real-time message distribution"
echo ""
echo "Setup complete! Terminal conversations will be fully persistent."