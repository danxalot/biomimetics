#!/bin/bash
# deploy-memu-cloudrun.sh - Deploy MemU to GCP Cloud Run (FREE TIER)
# All resources stay within GCP free tier limits

set -e

PROJECT_ID="arca-471022"
REGION="us-central1"  # Existing ARCA project region
SERVICE_NAME="memu"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

echo "=================================="
echo "Deploying MemU to Cloud Run"
echo "FREE TIER CONFIGURATION"
echo "=================================="
echo ""

# Navigate to project root
cd "/Users/danexall/Documents/VS Code Projects/ARCA"

# Build Docker image
echo "Building Docker image..."
docker build -t ${IMAGE_NAME} -f services/memu/Dockerfile .

# Push to Container Registry (free tier: 1GB/month)
echo "Pushing to GCR..."
docker push ${IMAGE_NAME}

# Deploy to Cloud Run (free tier: 2M requests/month)
echo "Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --concurrency 50 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},REGION=${REGION}" \
  --add-cloudsql-instances="" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=10 \
  --cpu-boost

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format='value(status.url)')

echo ""
echo "=================================="
echo "✅ Deployment Complete!"
echo "=================================="
echo ""
echo "Service URL: ${SERVICE_URL}"
echo "Region: ${REGION}"
echo ""
echo "FREE TIER LIMITS:"
echo "  - Cloud Run: 2M requests/month"
echo "  - Cloud Run: 360,000 GB-seconds/month"
echo "  - Container Registry: 1GB storage"
echo "  - Current memory: 512Mi"
echo "  - Current CPU: 1"
echo ""
echo "QUOTA MONITORING:"
echo "  - 75% threshold alerts enabled"
echo "  - Check: gcloud monitoring channels list"
echo ""
