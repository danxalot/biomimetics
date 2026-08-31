#!/bin/bash
# setup-pubsub.sh - Create Pub/Sub subscriptions for MemU and MuninnDB

set -e

PROJECT_ID="arca-471022"
TOPIC_ID="os-events"

echo "=================================="
echo "Setting up Pub/Sub Subscriptions"
echo "=================================="
echo ""

# Set project
gcloud config set project ${PROJECT_ID}

# Create topic if not exists
echo "Checking topic: ${TOPIC_ID}..."
if ! gcloud pubsub topics describe ${TOPIC_ID} &> /dev/null; then
    echo "Creating topic: ${TOPIC_ID}..."
    gcloud pubsub topics create ${TOPIC_ID}
else
    echo "✅ Topic exists"
fi

# Create subscription for MemU
MEMU_SUBSCRIPTION="memu-memory-events"
echo ""
echo "Creating MemU subscription: ${MEMU_SUBSCRIPTION}..."
if ! gcloud pubsub subscriptions describe ${MEMU_SUBSCRIPTION} &> /dev/null; then
    gcloud pubsub subscriptions create ${MEMU_SUBSCRIPTION} \
        --topic=${TOPIC_ID} \
        --message-retention-duration=604800s \
        --ack-deadline=30s
    echo "✅ Created ${MEMU_SUBSCRIPTION}"
else
    echo "✅ Subscription exists"
fi

# Create subscription for Global MuninnDB
MUNINN_SUBSCRIPTION="muninn-global-events"
echo ""
echo "Creating MuninnDB subscription: ${MUNINN_SUBSCRIPTION}..."
if ! gcloud pubsub subscriptions describe ${MUNINN_SUBSCRIPTION} &> /dev/null; then
    gcloud pubsub subscriptions create ${MUNINN_SUBSCRIPTION} \
        --topic=${TOPIC_ID} \
        --message-retention-duration=604800s \
        --ack-deadline=30s
    echo "✅ Created ${MUNINN_SUBSCRIPTION}"
else
    echo "✅ Subscription exists"
fi

echo ""
echo "=================================="
echo "✅ Pub/Sub Setup Complete!"
echo "=================================="
echo ""
echo "Subscriptions:"
echo "  - ${MEMU_SUBSCRIPTION} (MemU)"
echo "  - ${MUNINN_SUBSCRIPTION} (MuninnDB)"
echo ""
echo "To test publishing:"
echo "  gcloud pubsub topics publish ${TOPIC_ID} --message='Test event'"
echo ""
