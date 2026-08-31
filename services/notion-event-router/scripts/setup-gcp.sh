#!/bin/bash
# GCP Infrastructure Setup for Notion Event Router
# Run this script to create required GCP resources

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
SERVICE_ACCOUNT_NAME="notion-event-router"
TOPIC_NAME="os-events"
SUBSCRIPTION_NAME="os-events-sub"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}==================================${NC}"
echo -e "${GREEN}GCP Infrastructure Setup${NC}"
echo -e "${GREEN}==================================${NC}"
echo ""

# Check if PROJECT_ID is set
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: GCP_PROJECT_ID environment variable not set${NC}"
    echo "Please run: export GCP_PROJECT_ID=your-project-id"
    exit 1
fi

echo -e "${YELLOW}Using GCP Project: ${PROJECT_ID}${NC}"
echo ""

# Set project
echo -e "${YELLOW}Step 1: Setting GCP project...${NC}"
gcloud config set project $PROJECT_ID
echo -e "${GREEN}✓ Project set${NC}"
echo ""

# Enable required APIs
echo -e "${YELLOW}Step 2: Enabling required APIs...${NC}"
gcloud services enable pubsub.googleapis.com
echo -e "${GREEN}✓ Pub/Sub API enabled${NC}"
echo ""

# Create Service Account
echo -e "${YELLOW}Step 3: Creating Service Account...${NC}"
if gcloud iam service-accounts describe ${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com &> /dev/null; then
    echo -e "${GREEN}✓ Service Account already exists${NC}"
else
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="Notion Event Router Service Account" \
        --project=$PROJECT_ID
    echo -e "${GREEN}✓ Service Account created${NC}"
fi
echo ""

# Grant Pub/Sub Publisher role
echo -e "${YELLOW}Step 4: Granting Pub/Sub Publisher role...${NC}"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/pubsub.publisher" \
    --condition-none
echo -e "${GREEN}✓ Pub/Sub Publisher role granted${NC}"
echo ""

# Create Pub/Sub Topic
echo -e "${YELLOW}Step 5: Creating Pub/Sub Topic...${NC}"
if gcloud pubsub topics describe $TOPIC_NAME &> /dev/null; then
    echo -e "${GREEN}✓ Topic already exists${NC}"
else
    gcloud pubsub topics create $TOPIC_NAME
    echo -e "${GREEN}✓ Topic created: $TOPIC_NAME${NC}"
fi
echo ""

# Create Pub/Sub Subscription (for testing)
echo -e "${YELLOW}Step 6: Creating Pub/Sub Subscription...${NC}"
if gcloud pubsub subscriptions describe $SUBSCRIPTION_NAME &> /dev/null; then
    echo -e "${GREEN}✓ Subscription already exists${NC}"
else
    gcloud pubsub subscriptions create $SUBSCRIPTION_NAME \
        --topic=$TOPIC_NAME \
        --message-retention-duration=604800s
    echo -e "${GREEN}✓ Subscription created: $SUBSCRIPTION_NAME${NC}"
fi
echo ""

# Generate Service Account Key
echo -e "${YELLOW}Step 7: Generating Service Account Key...${NC}"
KEY_FILE="service-account.json"
if [ -f "$KEY_FILE" ]; then
    echo -e "${RED}Warning: $KEY_FILE already exists!${NC}"
    echo "Delete it first if you want to generate a new key:"
    echo "  rm $KEY_FILE"
else
    gcloud iam service-accounts keys create $KEY_FILE \
        --iam-account=${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com
    echo -e "${GREEN}✓ Service Account Key generated: $KEY_FILE${NC}"
    echo ""
    echo -e "${RED}⚠️  IMPORTANT: Keep this file secure!${NC}"
    echo "   Never commit it to git."
    echo "   You'll need its content for Cloudflare Secrets."
fi
echo ""

# Get Service Account email
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Output summary
echo -e "${GREEN}==================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}==================================${NC}"
echo ""
echo "Summary:"
echo "  Project ID: $PROJECT_ID"
echo "  Service Account: $SERVICE_ACCOUNT_EMAIL"
echo "  Pub/Sub Topic: $TOPIC_NAME"
echo "  Pub/Sub Subscription: $SUBSCRIPTION_NAME"
echo "  Key File: $KEY_FILE"
echo ""
echo "Next steps:"
echo "  1. Copy the content of $KEY_FILE"
echo "  2. Run: wrangler secret put GCP_SERVICE_ACCOUNT_JSON"
echo "  3. Paste the JSON content when prompted"
echo ""
echo "To test Pub/Sub:"
echo "  gcloud pubsub topics publish $TOPIC_NAME --message='Test message'"
echo "  gcloud pubsub subscriptions pull $SUBSCRIPTION_NAME --auto-ack"
echo ""
