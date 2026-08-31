#!/usr/bin/env python3
"""
Persistent Task Runner for System & Development Files Review
Analyzes current codebase and generates comprehensive documentation
"""

import requests
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'/home/ubuntu/mcp_storage/ARCA/logs/system_review_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
AGENT_URL = "http://localhost:8000/invoke"
CHECKPOINT_DIR = Path("/home/ubuntu/mcp_storage/ARCA/checkpoints")
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# Task definition with correct geographic locations
SUBTASKS = [
    {
        "name": "infrastructure_inventory",
        "prompt": """Perform a comprehensive infrastructure inventory of the ARCA system:

**IMPORTANT - Correct Geographic Locations:**
- GCP Region: us-central1 (Iowa, USA)
- OCI Region: uk-south-1 (London, UK)

Please create: /home/ubuntu/mcp_storage/ARCA/system_review/01_INFRASTRUCTURE_INVENTORY.md

Document the following:

1. **Multi-Cloud Infrastructure**
   - GCP us-central1 resources and services
   - OCI uk-south-1 (London) resources and services
   - Network connectivity between regions
   - Cross-cloud communication patterns

2. **Compute Resources**
   - All Docker containers (docker ps -a output)
   - Running services and their ports
   - Resource allocation (CPU, memory, storage)
   - Container orchestration setup

3. **Storage Systems**
   - Oracle 23ai Free database configuration
   - Vector database (40GB allocated)
   - File storage locations
   - Backup configurations

4. **Network Architecture**
   - Docker networks and IP assignments
   - Port mappings and exposed services
   - Inter-service communication
   - External access points

Use file_read to examine docker-compose files and file_list to inventory services."""
    },
    {
        "name": "service_architecture",
        "prompt": """Analyze the service architecture and create: /home/ubuntu/mcp_storage/ARCA/system_review/02_SERVICE_ARCHITECTURE.md

Review these key services:

1. **Agent Service** (/home/ubuntu/ARCA/services/agent_service/)
   - langgraph_agent.py implementation
   - Persistent task runner architecture
   - MiniMax M2 integration with max_tokens=8192
   - Tool calling and response handling

2. **MCP Server** (/home/ubuntu/ARCA/services/mcp_server/)
   - Available tools and their purposes
   - Authentication mechanism
   - File operations and security

3. **User Interaction Agent** 
   - Public vs private instances
   - API endpoints and interfaces

4. **Supporting Services**
   - Resource monitor
   - Sync service
   - Docker helper

Use file_read to examine key Python files and document the architecture patterns."""
    },
    {
        "name": "data_flow_analysis",
        "prompt": """Create a data flow analysis document: /home/ubuntu/mcp_storage/ARCA/system_review/03_DATA_FLOW_ANALYSIS.md

Map out:

1. **Memory System Architecture**
   - 3-tier memory (episodic, semantic, procedural)
   - Oracle 23ai vector database usage
   - Storage locations and data structures

2. **Agent Communication Patterns**
   - LangGraph state management
   - Message passing between agents
   - Tool execution workflow

3. **External Integrations**
   - MiniMax M2 API calls (us-central1 → MiniMax)
   - OCI uk-south-1 data processing
   - Cross-region data flows

4. **Checkpoint and Persistence**
   - Checkpoint save/load mechanism
   - State recovery procedures
   - Data consistency patterns

Read relevant configuration files and analyze the implementation."""
    },
    {
        "name": "development_workflow",
        "prompt": """Document the development workflow: /home/ubuntu/mcp_storage/ARCA/system_review/04_DEVELOPMENT_WORKFLOW.md

Cover:

1. **Code Organization**
   - Directory structure and purpose
   - Service separation and boundaries
   - Configuration management

2. **Build and Deployment**
   - Docker build process
   - docker-compose configurations
   - Deployment scripts (deploy.sh)
   - Environment variables and secrets

3. **Development Tools**
   - Available scripts (/home/ubuntu/ARCA/scripts/)
   - CLI tools (arca_cli.py, oi.sh)
   - Monitoring and debugging utilities

4. **Version Control**
   - Git repository structure
   - Branch strategy (a1-sync-2025-10-24)
   - Documentation organization (Gemini/)

Use file_list to inventory scripts and file_read to examine key configuration files."""
    },
    {
        "name": "llm_integration_status",
        "prompt": """Analyze LLM integrations: /home/ubuntu/mcp_storage/ARCA/system_review/05_LLM_INTEGRATION_STATUS.md

Document:

1. **MiniMax M2 Integration**
   - Current configuration (max_tokens=8192)
   - Native Anthropic tool calling
   - Thinking block support
   - Performance characteristics

2. **Local Models**
   - Models in /home/ubuntu/ARCA/models/
   - Model specifications and use cases
   - Qwen server setup

3. **Provider Architecture**
   - MinimaxAnthropicWrapper implementation
   - LangChain integration
   - Fallback and error handling

4. **Future Integration Plans**
   - Puter.js roadmap (400+ free models)
   - Multi-provider strategy
   - Cost optimization approaches

Read the models directory and examine agent service implementation."""
    },
    {
        "name": "security_audit",
        "prompt": """Perform security audit: /home/ubuntu/mcp_storage/ARCA/system_review/06_SECURITY_AUDIT.md

Analyze:

1. **Authentication & Authorization**
   - MCP Server API key authentication
   - Service-to-service security
   - Credential management (test_credentials.sh)

2. **Network Security**
   - Docker network isolation
   - Port exposure and firewall rules
   - Cross-region security (GCP us-central1 ↔ OCI uk-south-1)

3. **Data Security**
   - Database access controls
   - File system permissions
   - Sensitive data handling

4. **Secrets Management**
   - Environment variable usage
   - Configuration file security
   - API key storage

Review configuration files and security-related documentation."""
    },
    {
        "name": "performance_optimization",
        "prompt": """Create performance optimization guide: /home/ubuntu/mcp_storage/ARCA/system_review/07_PERFORMANCE_OPTIMIZATION.md

Cover:

1. **Current Performance Metrics**
   - Agent response times
   - Tool execution performance
   - Database query performance
   - Cross-region latency (us-central1 ↔ uk-south-1)

2. **Resource Utilization**
   - CPU and memory usage patterns
   - Storage efficiency
   - Network bandwidth utilization

3. **Optimization Opportunities**
   - Caching strategies
   - Query optimization
   - Connection pooling
   - Model selection for tasks

4. **Scaling Strategies**
   - Horizontal scaling approaches
   - Load balancing considerations
   - Multi-region deployment optimization

Examine performance scripts and resource monitor configurations."""
    },
    {
        "name": "operational_runbook",
        "prompt": """Create operational runbook: /home/ubuntu/mcp_storage/ARCA/system_review/08_OPERATIONAL_RUNBOOK.md

Document:

1. **Service Management**
   - Starting/stopping services
   - Health checks and monitoring
   - Log locations and analysis

2. **Troubleshooting Procedures**
   - Common issues and solutions
   - Debug workflows
   - Error recovery procedures

3. **Maintenance Tasks**
   - Database maintenance
   - Log rotation
   - Backup procedures
   - System updates

4. **Monitoring and Alerts**
   - Resource monitor usage
   - Performance tracking
   - Alert configurations

Use file_read on operational scripts and systemd configurations."""
    },
    {
        "name": "master_index",
        "prompt": """Create master index: /home/ubuntu/mcp_storage/ARCA/system_review/00_MASTER_INDEX.md

Generate a comprehensive table of contents for all system review documents:

1. Overview of the system review documentation
2. Links to all 8 documents
3. Quick reference guide
4. Key findings summary
5. Priority action items

Structure as a navigation aid for the entire system review."""
    }
]

class SystemReviewRunner:
    def __init__(self, task_id: str = "system_review"):
        self.task_id = task_id
        self.checkpoint_path = CHECKPOINT_DIR / f"{task_id}.json"
        self.state = self.load_checkpoint()
        
    def load_checkpoint(self) -> Dict[str, Any]:
        """Load checkpoint if exists, otherwise create new state"""
        if self.checkpoint_path.exists():
            logger.info(f"Loading checkpoint from {self.checkpoint_path}")
            with open(self.checkpoint_path, 'r') as f:
                return json.load(f)
        
        logger.info("Creating new task state")
        return {
            'task_id': self.task_id,
            'timestamp': datetime.now().isoformat(),
            'state': {
                'completed_subtasks': [],
                'current_subtask': None,
                'failed_subtasks': []
            }
        }
    
    def save_checkpoint(self):
        """Save current state to checkpoint"""
        self.state['timestamp'] = datetime.now().isoformat()
        with open(self.checkpoint_path, 'w') as f:
            json.dump(self.state, f, indent=2)
        logger.info(f"Checkpoint saved to {self.checkpoint_path}")
    
    def call_agent(self, prompt: str, session_id: str) -> Dict[str, Any]:
        """Call the agent service with a prompt"""
        payload = {
            "user_input": prompt,
            "session_id": session_id,
            "user_id": "system_review"
        }
        
        try:
            response = requests.post(AGENT_URL, json=payload, timeout=300)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Agent call failed: {e}")
            raise
    
    def execute_subtask(self, subtask: Dict[str, str]) -> bool:
        """Execute a single subtask with retry logic"""
        name = subtask['name']
        prompt = subtask['prompt']
        
        # Check if already completed
        completed_names = [s['name'] for s in self.state['state']['completed_subtasks']]
        if name in completed_names:
            logger.info(f"Subtask {name} already completed, skipping")
            return True
        
        logger.info(f"Executing subtask: {name}")
        self.state['state']['current_subtask'] = name
        self.save_checkpoint()
        
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Attempt {attempt}/{max_retries} for {name}")
                
                result = self.call_agent(prompt, self.task_id)
                
                # Record completion
                self.state['state']['completed_subtasks'].append({
                    'name': name,
                    'completed_at': datetime.now().isoformat(),
                    'result': result
                })
                self.state['state']['current_subtask'] = None
                self.save_checkpoint()
                
                logger.info(f"✓ Subtask {name} completed successfully")
                return True
                
            except Exception as e:
                logger.error(f"✗ Attempt {attempt} failed for {name}: {e}")
                if attempt == max_retries:
                    logger.error(f"All retries exhausted for {name}")
                    self.state['state']['failed_subtasks'].append({
                        'name': name,
                        'error': str(e),
                        'failed_at': datetime.now().isoformat()
                    })
                    self.save_checkpoint()
                    return False
                time.sleep(10 * attempt)  # Exponential backoff
        
        return False
    
    def run(self):
        """Execute all subtasks"""
        logger.info(f"Starting system review with {len(SUBTASKS)} subtasks")
        logger.info(f"Task ID: {self.task_id}")
        
        start_time = time.time()
        
        for i, subtask in enumerate(SUBTASKS, 1):
            logger.info(f"[{i}/{len(SUBTASKS)}] Processing: {subtask['name']}")
            success = self.execute_subtask(subtask)
            
            if not success:
                logger.error(f"Subtask {subtask['name']} failed, continuing with next task")
        
        # Mark as complete
        duration = time.time() - start_time
        logger.info(f"System review completed in {duration:.1f} seconds")
        logger.info(f"Completed: {len(self.state['state']['completed_subtasks'])}/{len(SUBTASKS)}")
        logger.info(f"Failed: {len(self.state['state']['failed_subtasks'])}")
        
        self.save_checkpoint()
        
        return self.state

if __name__ == '__main__':
    runner = SystemReviewRunner()
    final_state = runner.run()
    
    print("\n" + "="*60)
    print("SYSTEM REVIEW COMPLETED")
    print("="*60)
    print(f"Completed subtasks: {len(final_state['state']['completed_subtasks'])}")
    print(f"Failed subtasks: {len(final_state['state']['failed_subtasks'])}")
    print(f"\nCheckpoint: {runner.checkpoint_path}")
    print(f"Output directory: /home/ubuntu/mcp_storage/ARCA/system_review/")
    print("="*60)
