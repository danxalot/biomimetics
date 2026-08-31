# ARCA MCP Infrastructure

## Overview

The ARCA Model Context Protocol (MCP) infrastructure implements a self-improving AI network across 4 OCI instances using the Anthropic Skills Framework. The data-hub serves as the central reasoning hub with Gordon AI integration, while other instances act as specialized clients with skills-aware capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARCA MCP Network                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │   Data-Hub      │◄──►│   Workhorse     │                    │
│  │  MCP Server     │    │   MCP Client    │                    │
│  │  Gordon AI      │    │   Skills-Aware  │                    │
│  │  Skills Hub     │    │   Execution     │                    │
│  │  Port: 8086     │    │   Port: 8092    │                    │
│  └─────────────────┘    └─────────────────┘                    │
│           │                       │                            │
│           ▼                       ▼                            │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ Knowledge-Proc  │    │    Gateway      │                    │
│  │   MCP Client    │    │   MCP Client    │                    │
│  │   Skills-Aware  │    │   Skills-Aware  │                    │
│  │   Analysis      │    │   Coordination  │                    │
│  │   Port: 8092    │    │   Port: 8092    │                    │
│  └─────────────────┘    └─────────────────┘                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### MCP Server (Data-Hub)
- **Location**: OCI instance `data-hub` (10.0.0.10)
- **Port**: 8086
- **Purpose**: Central reasoning hub with skills management
- **Features**:
  - Anthropic Skills Framework implementation
  - Gordon AI integration for enhanced reasoning
  - Skills performance tracking and improvement
  - Learning events logging
  - Cross-instance skill recommendations

### MCP Clients (Worker Instances)
- **Locations**: 
  - Workhorse (10.0.0.11:8092)
  - Knowledge-Processor (10.0.0.12:8092)
  - Gateway (10.0.0.13:8092)
- **Purpose**: Skills-aware task execution
- **Features**:
  - Automatic skills tracking for all operations
  - Enhanced reasoning via Gordon AI queries
  - Performance feedback to central hub
  - Adaptive strategy selection

### Gordon AI Services
- **Port**: 8091 on all instances
- **Purpose**: Distributed AI reasoning enhancement
- **Integration**: Docker-based deployment with MCP tool wrappers

## Skills Framework

The system implements the Anthropic Skills Framework with the following categories:

### Core Skills
- **Reasoning**: logical_analysis, critical_thinking, problem_decomposition, causal_reasoning
- **Technical**: code_generation, infrastructure_management, system_architecture, debugging
- **Creative**: innovative_problem_solving, alternative_approaches, synthesis
- **Meta**: self_reflection, learning_optimization, skill_assessment, adaptation
- **Communication**: clear_explanation, context_awareness, user_intent_understanding

### Skill Tracking
- Success/failure rates for each skill
- Weakness identification and improvement suggestions
- Performance trends over time
- Context-aware skill recommendations

## Deployment

### Prerequisites
```bash
# Ensure SSH access to all OCI instances
ssh-keygen -t rsa -b 4096 -C "arca-mcp"
# Copy key to all instances

# Verify instance connectivity
ping 10.0.0.10  # data-hub
ping 10.0.0.11  # workhorse  
ping 10.0.0.12  # knowledge-processor
ping 10.0.0.13  # gateway
```

### Quick Deployment
```bash
# Deploy entire MCP infrastructure
./scripts/deploy_mcp_infrastructure.sh

# Check deployment status
./scripts/deploy_mcp_infrastructure.sh status

# View logs from specific instance
./scripts/deploy_mcp_infrastructure.sh logs data-hub
```

### Manual Deployment

#### 1. Deploy MCP Server (Data-Hub)
```bash
# Copy server files
scp -r services/mcp_server/ ubuntu@10.0.0.10:~/ARCA/services/

# Install dependencies and start service  
ssh ubuntu@10.0.0.10
cd ~/ARCA/services/mcp_server
pip3 install -r requirements.txt
python3 macbook_mcp_integration_server.py
```

#### 2. Deploy MCP Clients (Worker Instances)
```bash
# For each worker instance
for ip in 10.0.0.11 10.0.0.12 10.0.0.13; do
    scp services/mcp_server/mcp_client.py ubuntu@$ip:~/ARCA/services/mcp_server/
    scp services/mcp_server/requirements.txt ubuntu@$ip:~/ARCA/services/mcp_server/
    
    ssh ubuntu@$ip "cd ~/ARCA/services/mcp_server && pip3 install -r requirements.txt"
done

Optional: If `mcp_client` is containerized and published to GHCR, you can pull and run it instead of copying Python files:

```bash
# example pulling and running the client container
docker pull ghcr.io/<owner>/<repo>/mcp_client:latest
docker run -d --name arca-mcp-client --restart unless-stopped \
    -e MCP_SERVER_URL=http://10.0.0.10:8086 \
    ghcr.io/<owner>/<repo>/mcp_client:latest
```

To register the container with systemd or restart it on updates, create a small systemd service unit that starts the container (or update your configuration management to handle it).
```

## Usage

### Skills-Enhanced Sync Agent
```bash
# Use enhanced sync with skills tracking
python3 services/sync_service/enhanced_sync_agent.py sync gcs_upload /local/path gs://bucket/path

# Get performance insights
python3 services/sync_service/enhanced_sync_agent.py performance-insights

# Intelligent conflict resolution
python3 services/sync_service/enhanced_sync_agent.py resolve-conflict conflict.json

# Test skills system
python3 services/sync_service/enhanced_sync_agent.py test-skills
```

### Direct MCP API Usage
```bash
# Query skills recommendations
curl -X POST http://10.0.0.10:8086/mcp/tools/get_skill_recommendations \
  -H "Content-Type: application/json" \
  -d '{"context": "debugging network connectivity issues"}'

# Record learning event
curl -X POST http://10.0.0.10:8086/mcp/tools/record_learning_event \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "debugging", "success": true, "context": "Fixed network issue"}'

# Get skills dashboard
curl http://10.0.0.10:8086/skills/dashboard
```

### Enhanced Reasoning with Gordon AI
```python
from services.mcp_server.mcp_client import SkillsAwareAgent

async def example_usage():
    agent = SkillsAwareAgent("workhorse", "http://10.0.0.10:8086")
    
    # Enhanced reasoning for complex problems
    result = await agent.enhanced_reasoning(
        "How should I optimize this large file transfer?",
        {"file_size": "10GB", "network": "limited_bandwidth"}
    )
    print(result)
    
    # Execute task with automatic skills tracking
    await agent.execute_with_skills_tracking(
        "Deploy service to production",
        deploy_function,
        service_config
    )
```

## Monitoring

### Network Status Dashboard
```bash
# Start monitoring dashboard
python3 services/mcp_server/monitoring_dashboard.py

# View at http://localhost:8080
```

### Service Health Checks
```bash
# Check all services
for ip in 10.0.0.10 10.0.0.11 10.0.0.12 10.0.0.13; do
    curl -s http://$ip:8086/health 2>/dev/null || curl -s http://$ip:8092/health
done

# Check Gordon AI services
for ip in 10.0.0.10 10.0.0.11 10.0.0.12 10.0.0.13; do
    curl -s http://$ip:8091/health
done
```

### Systemd Service Management
```bash
# On data-hub
sudo systemctl status arca-mcp-server
sudo journalctl -u arca-mcp-server -f

# On worker instances  
sudo systemctl status arca-mcp-client
sudo journalctl -u arca-mcp-client -f

# Restart all services
./scripts/deploy_mcp_infrastructure.sh restart
```

## Skills Data and Learning

### Skills Registry
- **Location**: `{ARCA_ROOT}/data/skills/skills_registry.json`
- **Content**: Complete skills database with performance metrics
- **Access**: Via MCP resource `skills://registry`

### Learning Events Log
- **Location**: `{ARCA_ROOT}/data/skills/learning_events.json`
- **Content**: Chronological log of all learning events
- **Retention**: Last 1000 events
- **Access**: Via MCP resource `skills://learning-events`

### Performance Dashboard
- **Access**: Via MCP resource `skills://performance-dashboard`
- **Metrics**:
  - Overall success rates by skill category
  - Skills needing improvement
  - Performance trends
  - Instance-specific insights

## Integration Examples

### Integrate with Existing Services
```python
# In your existing service
import sys
sys.path.append('/path/to/ARCA/services/mcp_server')
from mcp_client import SkillsAwareAgent

class YourService:
    def __init__(self):
        self.skills_agent = SkillsAwareAgent("your-instance", "http://10.0.0.10:8086")
    
    async def your_method(self):
        # Wrap your operations with skills tracking
        await self.skills_agent.execute_with_skills_tracking(
            "Your operation description",
            self._your_actual_operation
        )
```

### ARCA Controller Integration
```python
# In arca.py
from services.mcp_server.mcp_client import MCPClient

async def enhanced_mode_execution(mode_name):
    async with MCPClient("http://10.0.0.10:8086", "controller") as mcp:
        # Get skill recommendations for the mode
        skills = await mcp.get_skill_recommendations(f"Execute {mode_name} mode")
        
        # Execute mode with tracking
        # ... your mode execution logic ...
        
        # Record results
        await mcp.record_learning_event("mode_execution", success, mode_name, details)
```

## Troubleshooting

### Common Issues

#### Connection Failures
```bash
# Check network connectivity
ping 10.0.0.10

# Check service status
curl http://10.0.0.10:8086/health

# Check firewall rules
sudo iptables -L | grep 8086
```

#### Service Start Failures
```bash
# Check logs
sudo journalctl -u arca-mcp-server -n 50

# Check Python dependencies
python3 -c "import fastapi, uvicorn, aiohttp"

# Check port availability
netstat -tulpn | grep 8086
```

#### Skills Data Issues
```bash
# Verify skills data directory
ls -la ~/ARCA/data/skills/

# Reset skills registry (if needed)
rm ~/ARCA/data/skills/skills_registry.json
# Service will recreate with defaults on restart
```

### Log Locations
- **MCP Server**: `journalctl -u arca-mcp-server`
- **MCP Clients**: `journalctl -u arca-mcp-client`
- **Gordon AI**: `journalctl -u gordon-ai`
- **Enhanced Sync**: `/tmp/arca-enhanced-sync.log`

## Development

### Adding New Skills
```python
# In macbook_mcp_integration_server.py
new_skill = Skill(
    name="your_new_skill",
    category=SkillCategory.TECHNICAL,
    level=SkillLevel.INTERMEDIATE
)
skills_manager.skills["your_new_skill"] = new_skill
```

### Creating Custom MCP Tools
```python
# Add to _setup_mcp_handlers in macbook_mcp_integration_server.py
Tool(
    name="your_custom_tool",
    description="Description of your tool",
    inputSchema={
        "type": "object",
        "properties": {
            "param": {"type": "string"}
        }
    }
)
```

### Extending Gordon AI Integration
```python
# In gordon_ai_manager.py
async def custom_gordon_query(self, specialized_prompt: str):
    # Add custom Gordon AI interaction logic
    pass
```

## Performance Optimization

### Skills Framework Optimization
- Skills registry is cached in memory for fast access
- Learning events are batched and written asynchronously
- Performance metrics are computed on-demand

### Network Optimization
- HTTP/2 used for MCP communication where available
- Connection pooling for frequent client-server interactions
- Compression enabled for large skill data transfers

### Resource Management
- Skills data cleanup (old events pruned automatically)
- Memory usage monitoring for large skill registries
- Disk space management for learning logs

## Security Considerations

- **Network Security**: All MCP traffic over private Tailscale network
- **Authentication**: Instance-based authentication using instance IDs
- **Data Privacy**: Skills data remains within OCI infrastructure
- **Access Control**: Service-to-service communication only

## Future Enhancements

1. **Advanced AI Integration**: Full Gordon AI Docker deployment
2. **Enhanced Learning**: Machine learning models for skill improvement prediction
3. **Cross-Instance Collaboration**: Distributed task execution with skill-aware load balancing
4. **Real-time Analytics**: Live skills performance dashboards
5. **Integration APIs**: REST and GraphQL APIs for external system integration

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review service logs using systemd journalctl
3. Test network connectivity between instances
4. Verify MCP client-server communication

The MCP infrastructure provides a foundation for self-improving AI operations across the ARCA network, enabling continuous learning and performance optimization through the Anthropic Skills Framework.

## Images, GHCR, and Verification ✅

### Which services get pushed to GHCR
- The repository's main GitOps pipeline (`.github/workflows/gitops-pipeline.yml`) builds and pushes the following services to GitHub Container Registry (GHCR):
    - mcp_server
    - agent_runner
    - otel_collector
    - qwen_server
    - resource_monitor
    - user_interaction_agent
    - sync_service
    - agent_service

    Some services use a repository-scoped image name (e.g., `ghcr.io/<owner>/<repo>/<service>` used by the GitOps matrix), while other workflows set explicit image names or owner-scoped names. Example mappings from the workflows:

    - `gitops-pipeline.yml` -> `ghcr.io/<owner>/<repo>/mcp_server`
    - `user-interaction-agent-build.yml` -> `ghcr.io/<owner>/arca-user-interaction-agent`
    - `resource-monitor-build.yml` -> `ghcr.io/<owner>/arca-resource-monitor`
    - `docker-helper-build.yml` -> `ghcr.io/<owner>/<repo>/docker_helper`

    When verifying images, check the image path used by the corresponding workflow for the exact image name.

- Additional services have dedicated workflows that publish to GHCR (e.g., `resource-monitor-build.yml`, `user-interaction-agent-build.yml`, `docker-helper-build.yml`). These workflows are configured to push to `ghcr.io` using `docker/build-push-action` and `docker/metadata-action`.

### Where those images are stored on GHCR
- The image path used by the pipelines is: `ghcr.io/<OWNER>/<REPOSITORY>/<service>` by convention. Example:
    - `ghcr.io/<owner>/<repo>/mcp_server:latest`

### How to verify images have been pushed (local commands)
Note: these commands require you to be authenticated with `gh` and/or `docker` to access GHCR packages.

- Authenticate with GitHub and GHCR using `gh` (recommended) or `docker login`:
    - gh CLI: `gh auth login`
    - Docker CLI: `echo $GITHUB_TOKEN | docker login ghcr.io -u <GH_USER> --password-stdin`

- List container packages for the repository (requires `gh`):
    ```bash
    # List container packages for the repo (owner/repo)
    gh api repos/:OWNER/:REPO/packages --jq '.[].name'
    ```

- Pull an image from GHCR to verify it exists:
    ```bash
    docker pull ghcr.io/<owner>/<repo>/mcp_server:latest
    # or specific tag
    docker pull ghcr.io/<owner>/<repo>/mcp_server:<tag>
    ```

- Inspect image manifest (skopeo or docker):
    ```bash
    # Using docker:
    docker manifest inspect ghcr.io/<owner>/<repo>/mcp_server:latest

    # Using skopeo (recommended for multi-arch inspection):
    skopeo inspect docker://ghcr.io/<owner>/<repo>/mcp_server:latest
    ```

You can also use the included helper script to run a quick verification of the image list (requires `gh` and `docker`):

```bash
# Example usage from repo root (requires gh and docker configured):
./scripts/check_ghcr_images.sh <owner> <repo>
```

### Check GitHub Actions workflows and logs
- Confirm the `gitops-pipeline.yml` (or the service-specific workflow) ran successfully and pushed the image by checking the workflow run logs:
    ```bash
    # List workflow runs (requires gh CLI and repo access)
    gh run list --workflow gitops-pipeline.yml

    # View logs for a specific run (use the run id from the previous command)
    gh run view <run_id> --log
    ```

### Deploying the image from GHCR
- To run a container locally from GHCR:
    ```bash
    docker run --rm -it ghcr.io/<owner>/<repo>/mcp_server:latest /bin/bash
    ```

### About the local MacBook MCP client
- The `mcp_client` is currently deployed as a standalone Python script (`services/mcp_server/mcp_client.py`), not a container image by default. It is commonly copied to target hosts and managed via systemd (see the Systemd Service Management section).
- If you would like the client published as a dedicated GHCR image (recommended for container-based deployments), follow the optional steps below.

### Optional: Packaging `mcp_client` as a container and publishing to GHCR
If you prefer a containerized `mcp_client`, you can add the `services/mcp_client/Dockerfile`, update the pipeline to build and push it, and use the image during deployments.

Example `Dockerfile` (`services/mcp_client/Dockerfile`):
```Dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY services/mcp_server/mcp_client.py ./
COPY services/mcp_server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "mcp_client.py"]
```

Add the `mcp_client` to the build pipeline's matrix or create a service-specific workflow similar to existing ones (e.g., `docker-helper-build.yml`) with `docker/build-push-action@v5` to publish to GHCR as `ghcr.io/<owner>/<repo>/mcp_client`.

If you'd like, I can implement the `Dockerfile` and a small workflow that builds and publishes the `mcp_client` to GHCR for you.

### Local Build & Deploy (Free-tier / Local Runner) ⚙️
If you are constrained by GitHub Actions free-tier quotas, you can use your local machine as the build environment (e.g., `dans-macbook-pro` at Tailscale IP `100.124.13.62`) and perform builds locally.

Steps to build & push locally (macOS / Linux):
```bash
# Authenticate to GH and GHCR
gh auth login --with-token < /Users/danexall/Documents/VS\ Code\ Projects/ARCA/.secrets/github_token
echo "$(cat /Users/danexall/Documents/VS\ Code\ Projects/ARCA/.secrets/github_token)" | docker login ghcr.io -u danxalot --password-stdin

# Build locally and optionally push (push=false avoids GHCR writes; set push=true to push image)
./scripts/local_build.sh "mcp_server,mcp_client" false danxalot arca

# Push to GHCR (optional)
./scripts/local_build.sh "mcp_server,mcp_client" true danxalot arca
```

Steps to deploy to remote host from local machine (via ssh):
```bash
# Example to deploy mcp_server to workhorse
./scripts/local_deploy.sh 100.124.13.62 mcp_server danxalot arca

Note: the `MCP_API_KEY` used by the `mcp_client` can be loaded from `./.secrets/arca_oci_key` when running locally or set in your environment as `MCP_API_KEY`. For example:

```bash
export MCP_API_KEY="$(cat ./.secrets/arca_oci_key)"
./scripts/local_deploy.sh 100.124.13.62 mcp_server danxalot arca
```

Also ensure the workhorse host's MCP server is started and listening on port 8090 (0.0.0.0 or your tailscale interface) if you want the client to reach it from outside the OCI private subnet.
```

Notes:
- `./scripts/local_build.sh` uses Buildx to build multi-arch images; if running on Apple Silicon it still creates multi-arch images using QEMU support.
- When pushing to GHCR, ensure the token used has `packages:write` or `write:packages` permission.
- The `LOCAL_BUILD` repository secret can be set to 'true' to prevent heavy CI operations and keep the repository in the GitHub Actions free tier.

### Configure local MCP Client to point to the workhorse/OCI server
If you want to run the `mcp_client` locally on the Macbook and connect to the workhorse MCP server for testing:
```bash
export DATA_HUB_MCP_URL=http://<workhorse-host>:8086
export INSTANCE_ID=dans-macbook-pro
python3 services/mcp_server/mcp_client.py
```
Or if you containerized `mcp_client` and prefer to run that container locally, use:
```bash
docker run --rm -it -e DATA_HUB_MCP_URL=http://<workhorse-host>:8086 -e INSTANCE_ID=dans-macbook-pro ghcr.io/danxalot/arca-mcp-client:latest
```

This sets up the local client to connect to the remote MCP server (`workhorse` or `data-hub`), enabling you to test tool invocations and skill recording without running GitHub Actions.