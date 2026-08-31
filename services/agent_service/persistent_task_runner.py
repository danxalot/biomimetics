#!/usr/bin/env python3
"""
Persistent Task Runner for Long-Running Agent Tasks

This script enables autonomous, overnight execution of complex tasks by:
1. Breaking tasks into checkpointed subtasks
2. Resuming from last checkpoint on failure
3. Continuously polling until task completion
4. Handling API rate limits and timeouts gracefully
"""

import requests
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PersistentTaskRunner:
    """Manages long-running agent tasks with checkpoint/resume capability"""
    
    def __init__(
        self, 
        agent_url: str = "http://localhost:8000",
        checkpoint_dir: str = "/home/ubuntu/mcp_storage/ARCA/checkpoints"
    ):
        self.agent_url = agent_url
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
    def save_checkpoint(self, task_id: str, state: Dict) -> None:
        """Save task state to disk"""
        checkpoint_file = self.checkpoint_dir / f"{task_id}.json"
        with open(checkpoint_file, 'w') as f:
            json.dump({
                'task_id': task_id,
                'timestamp': datetime.now().isoformat(),
                'state': state
            }, f, indent=2)
        logger.info(f"Checkpoint saved: {checkpoint_file}")
    
    def load_checkpoint(self, task_id: str) -> Optional[Dict]:
        """Load task state from disk"""
        checkpoint_file = self.checkpoint_dir / f"{task_id}.json"
        if checkpoint_file.exists():
            with open(checkpoint_file, 'r') as f:
                data = json.load(f)
                logger.info(f"Checkpoint loaded: {checkpoint_file}")
                return data['state']
        return None
    
    def execute_subtask(self, prompt: str, session_id: str, max_retries: int = 3) -> Dict:
        """Execute a single subtask with retries"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Executing subtask (attempt {attempt + 1}/{max_retries})")
                
                response = requests.post(
                    f"{self.agent_url}/invoke",
                    json={
                        "user_input": prompt,
                        "session_id": session_id
                    },
                    timeout=300  # 5 minute timeout per subtask
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Subtask completed: {result.get('status')}")
                    return result
                else:
                    logger.error(f"HTTP {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(30)  # Wait 30s before retry
            except Exception as e:
                logger.error(f"Error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(30)
        
        return {"status": "failure", "error": "Max retries exceeded"}
    
    def run_comprehensive_analysis(
        self,
        task_id: str = None,
        resume: bool = True
    ) -> Dict:
        """
        Run comprehensive ARCA analysis with automatic checkpointing
        
        Breaks the task into 8 sequential subtasks:
        1. Read reference materials
        2. Scan documentation repository
        3. Generate 01_CURRENT_STATE_ASSESSMENT.md
        4. Generate 02_DESIGN_EVOLUTION_HISTORY.md
        5. Generate 03_TECHNICAL_SPECIFICATIONS.md
        6. Generate 04_INTEGRATION_ROADMAP.md
        7. Generate 05-06-07 remaining documents
        8. Generate 00_INDEX.md
        """
        
        if task_id is None:
            task_id = f"comprehensive_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Load checkpoint if resuming
        state = self.load_checkpoint(task_id) if resume else None
        if state is None:
            state = {
                'completed_subtasks': [],
                'current_subtask': 0,
                'session_id': task_id,
                'start_time': datetime.now().isoformat()
            }
        
        # Define subtasks
        subtasks = [
            {
                'name': 'read_references',
                'prompt': """Read these three reference documents and summarize key findings:
1. `/home/ubuntu/ARCA/Gemini/An Architectural Analysis of a Multi-Cloud, Agentic AI System with Advanced Memory and Knowledge Discovery (1).txt`
2. `/home/ubuntu/ARCA/Gemini/A Sovereign Multi-Cloud Architecture for a Self-Evolving, Multi-Agent Development Crew.txt`
3. `/home/ubuntu/ARCA/SYSTEM_STATUS.md`

Use file_read tool for each. Provide a 500-word summary of the current ARCA architecture."""
            },
            {
                'name': 'scan_documentation',
                'prompt': """Scan the documentation repository at `/home/ubuntu/mcp_storage/ARCA/` using file_list tool.
Identify all markdown files and categorize them by topic (architecture, deployment, guides, etc.).
Provide a structured inventory."""
            },
            {
                'name': 'generate_01_current_state',
                'prompt': """Generate `/home/ubuntu/mcp_storage/ARCA/gemini_final/01_CURRENT_STATE_ASSESSMENT.md`

Include:
- Infrastructure topology (OCI A1, E2, Oracle 26ai, GCP)
- Service inventory (Docker containers, ports, health status)
- Authentication matrix
- Data flow diagrams (Mermaid)
- LLM integration status
- Oracle 26ai vector database details

Use file_write tool to create the document. Minimum 2000 words."""
            },
            {
                'name': 'generate_02_evolution',
                'prompt': """Generate `/home/ubuntu/mcp_storage/ARCA/gemini_final/02_DESIGN_EVOLUTION_HISTORY.md`

Include:
- CrewAI → LangGraph migration timeline
- Multi-agent architecture emergence
- Memory system evolution (3-tier)
- LLM provider journey
- Key architectural decisions

Use file_write tool. Minimum 1500 words."""
            },
            {
                'name': 'generate_03_technical_specs',
                'prompt': """Generate `/home/ubuntu/mcp_storage/ARCA/gemini_final/03_TECHNICAL_SPECIFICATIONS.md`

Include:
- LangGraph workflow architecture
- MinimaxAnthropicWrapper implementation
- MCP Server API specification
- Oracle 26ai vector DB schemas
- Docker Compose configurations
- Network topology diagrams (Mermaid)

Use file_write tool. Minimum 2500 words with code examples."""
            },
            {
                'name': 'generate_04_roadmap',
                'prompt': """Generate `/home/ubuntu/mcp_storage/ARCA/gemini_final/04_INTEGRATION_ROADMAP.md`

Include all 7 phases:
- Phase 1: Multi-Agent Workflow
- Phase 2: E2 Telemetry
- Phase 3: Azure AD IDAM
- Phase 4: Neo4j Deployment
- Phase 5: GCP Pub/Sub
- Phase 6: Puter.js Integration (HIGH PRIORITY)
- Phase 7: Grok LLM

Use file_write tool. Minimum 2000 words with implementation steps."""
            },
            {
                'name': 'generate_05_06_07',
                'prompt': """Generate remaining documents:
1. `/home/ubuntu/mcp_storage/ARCA/gemini_final/05_OPERATIONAL_PROCEDURES.md` (SOPs, backup, monitoring)
2. `/home/ubuntu/mcp_storage/ARCA/gemini_final/06_RESOURCE_OPTIMIZATION_STRATEGY.md` (Free tier strategies)
3. `/home/ubuntu/mcp_storage/ARCA/gemini_final/07_CREATIVE_RECOMMENDATIONS.md` (Puter.js, innovative proposals)

Use file_write tool for each. Minimum 1500 words each."""
            },
            {
                'name': 'generate_00_index',
                'prompt': """Generate `/home/ubuntu/mcp_storage/ARCA/gemini_final/00_INDEX.md`

Create comprehensive index with:
- Table of contents linking all documents
- Quick navigation section
- Executive summary
- Document dependency graph

Use file_write tool."""
            }
        ]
        
        # Execute subtasks sequentially
        start_idx = state['current_subtask']
        for idx in range(start_idx, len(subtasks)):
            subtask = subtasks[idx]
            logger.info(f"\n{'='*60}")
            logger.info(f"Starting subtask {idx + 1}/{len(subtasks)}: {subtask['name']}")
            logger.info(f"{'='*60}\n")
            
            result = self.execute_subtask(
                prompt=subtask['prompt'],
                session_id=state['session_id']
            )
            
            if result.get('status') == 'success':
                state['completed_subtasks'].append({
                    'name': subtask['name'],
                    'completed_at': datetime.now().isoformat(),
                    'result': result
                })
                state['current_subtask'] = idx + 1
                self.save_checkpoint(task_id, state)
                
                logger.info(f"✅ Subtask completed: {subtask['name']}")
                time.sleep(5)  # Brief pause between subtasks
            else:
                logger.error(f"❌ Subtask failed: {subtask['name']}")
                state['last_error'] = {
                    'subtask': subtask['name'],
                    'error': result.get('error'),
                    'timestamp': datetime.now().isoformat()
                }
                self.save_checkpoint(task_id, state)
                return {
                    'status': 'partial_completion',
                    'completed': state['completed_subtasks'],
                    'failed_at': subtask['name'],
                    'checkpoint': task_id
                }
        
        # All subtasks completed
        state['completed_at'] = datetime.now().isoformat()
        state['status'] = 'completed'
        self.save_checkpoint(task_id, state)
        
        logger.info(f"\n{'='*60}")
        logger.info("🎉 COMPREHENSIVE ANALYSIS COMPLETED!")
        logger.info(f"Total subtasks: {len(subtasks)}")
        logger.info(f"Output directory: /home/ubuntu/mcp_storage/ARCA/gemini_final/")
        logger.info(f"{'='*60}\n")
        
        return {
            'status': 'completed',
            'completed_subtasks': state['completed_subtasks'],
            'total_time': state['completed_at']
        }


def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Persistent Task Runner for ARCA Agent')
    parser.add_argument('--resume', action='store_true', help='Resume from last checkpoint')
    parser.add_argument('--task-id', type=str, help='Task ID for resume')
    parser.add_argument('--agent-url', type=str, default='http://localhost:8000', help='Agent service URL')
    
    args = parser.parse_args()
    
    runner = PersistentTaskRunner(agent_url=args.agent_url)
    
    try:
        result = runner.run_comprehensive_analysis(
            task_id=args.task_id,
            resume=args.resume
        )
        
        print("\n" + "="*60)
        print("FINAL RESULT:")
        print(json.dumps(result, indent=2))
        print("="*60)
        
        exit(0 if result['status'] == 'completed' else 1)
        
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user. Progress saved to checkpoint.")
        exit(2)
    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)
        exit(3)


if __name__ == "__main__":
    main()
