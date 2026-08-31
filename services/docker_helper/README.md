# ARCA Docker Helper Service

A lightweight REST API service that provides safe access to Docker daemon operations for the ARCA autonomous agent system.

## Overview

The Docker Helper service acts as a secure intermediary between ARCA agents and the Docker daemon, providing REST endpoints for common Docker operations like listing containers, viewing stats, and retrieving logs.

## Features

- **Container Management**: List running and stopped containers
- **Resource Monitoring**: Get real-time container statistics
- **Log Access**: Retrieve container logs with configurable tail length
- **Security**: Read-only access to Docker socket
- **Health Checks**: Built-in health monitoring

## API Endpoints

### GET /containers
List all containers (running and stopped by default).

**Query Parameters:**
- `all` (boolean): Include stopped containers (default: true)

**Response:** JSON array of container objects

### GET /containers/{container_id}/stats
Get real-time statistics for a specific container.

**Response:** JSON object with CPU, memory, network, and I/O statistics

### GET /containers/{container_id}/logs
Get logs from a specific container.

**Query Parameters:**
- `tail` (integer): Number of log lines to return (default: 200)

**Response:** Plain text log output

## Usage

### Local Development
```bash
cd services/docker_helper
docker-compose up -d
```

### Testing the API
```bash
# List all containers
curl http://localhost:8082/containers

# Get container stats
curl http://localhost:8082/containers/{container_id}/stats

# Get container logs
curl http://localhost:8082/containers/{container_id}/logs
```

## Security Considerations

- The service mounts the Docker socket as read-only
- No container creation, deletion, or modification operations are exposed
- All operations are read-only and safe for agent consumption

## Integration with ARCA

This service is designed to be used by ARCA agents for:
- Monitoring container health and performance
- Troubleshooting container issues through log access
- Resource usage analysis for optimization decisions

## Deployment

The service is deployed via GitOps pipeline and can run in multiple environments:

- **Local**: For development and testing
- **Workhorse**: Production deployment on OCI instance
- **Data Hub**: Additional deployment locations as needed

## Health Checks

The service includes health checks that verify:
- FastAPI application is responding
- Docker socket is accessible
- Container listing functionality works

## Dependencies

- FastAPI: Web framework
- Docker socket access: For daemon communication
- curl: For health check testing
