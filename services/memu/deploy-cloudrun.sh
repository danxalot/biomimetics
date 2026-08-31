#!/bin/bash
# deploy-memu-cloudrun.sh - Deploy MemU to GCP Cloud Run

set -e

PROJECT_ID="arca-471022"
REGION="europe-west1"
SERVICE_NAME="memu"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

echo "=================================="
echo "Deploying MemU to Cloud Run"
echo "=================================="
echo ""

# Navigate to project root
cd "/Users/danexall/Documents/VS Code Projects/ARCA"

# Build Docker image
echo "Building Docker image..."
docker build -t ${IMAGE_NAME} -f services/memu/Dockerfile .

# Push to Container Registry
echo "Pushing to GCR..."
docker push ${IMAGE_NAME}

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --concurrency 10 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID}" \
  --add-cloudsql-instances="" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=10

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format='value(status.url)')

echo ""
echo "=================================="
echo "✅ Deployment Complete!"
echo "=================================="
echo ""
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "Next steps:"
echo "  1. Set up secrets in Secret Manager"
echo "  2. Configure environment variables"
echo "  3. Test MCP endpoint"
echo ""
