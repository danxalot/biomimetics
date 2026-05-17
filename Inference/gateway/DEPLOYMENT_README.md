# ARCA LLM Gateway Deployment Setup

## Overview
The LLM Gateway has been successfully containerized and tested locally. To complete the deployment pipeline to the workhorse server, follow these steps:

## Required Repository Secrets

Add the following secret to your GitHub repository (Settings → Secrets and variables → Actions):

### `ARCA_OCI_SSH_KEY`
- **Value**: The private SSH key content from `.secrets/arca_oci_key`
- **Usage**: Allows GitHub Actions to SSH into the workhorse server (100.124.13.62) for deployment

To add the secret:
```bash
# Copy the private key content
cat .secrets/arca_oci_key

# Add as repository secret: ARCA_OCI_SSH_KEY
```

## Deployment Process

Once the secret is configured, the deployment will happen automatically on pushes to the `main` branch:

1. **Build**: GitHub Actions builds the LLM Gateway container
2. **Security Scan**: Trivy scans for vulnerabilities
3. **Push to GHCR**: Container pushed to GitHub Container Registry
4. **Deploy to Workhorse**: SSH deployment to OCI instance
   - Stops existing container
   - Pulls new image
   - Starts container with proper configuration
   - Health check validation

## Workhorse Configuration

The deployment assumes:
- **Host**: `100.124.13.62` (Tailscale IP)
- **User**: `ubuntu`
- **Docker**: Installed and running
- **Redis**: Available at `redis://localhost:6379`
- **Port**: `8000` exposed for the LLM Gateway

## Testing Deployment

After deployment, verify the service is running:

```bash
# SSH to workhorse
ssh -i .secrets/arca_oci_key ubuntu@100.124.13.62

# Check container status
docker ps | grep llm-gateway

# Test health endpoint
curl http://localhost:8000/health

# Test models endpoint
curl http://localhost:8000/models
```

## Environment Variables

The deployed container uses these environment variables:
- `REDIS_URL=redis://localhost:6379` - Redis connection for caching/rate limiting
- `LITELLM_VERBOSE=false` - Disable verbose logging in production
- `DEBUG=false` - Production mode

## API Keys

For the LLM Gateway to function with external providers, set these environment variables on the workhorse:

```bash
# On workhorse server
export OPENAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
export GOOGLE_API_KEY="your-key"
export COHERE_API_KEY="your-key"
export OPENROUTER_API_KEY="your-key"
```

## Next Steps

1. Add the `ARCA_OCI_SSH_KEY` repository secret
2. Push to main branch to trigger deployment
3. Verify deployment on workhorse
4. Configure API keys for LLM providers
5. Test end-to-end functionality</content>
<parameter name="filePath">/Users/danexall/Documents/VS Code Projects/ARCA/services/llm_gateway/DEPLOYMENT_README.md