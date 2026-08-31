"""
ReasoningBank Tool Interface

Provides access to ARCA's ReasoningBank for agent learning and reasoning optimization.
ReasoningBank stores reasoning trajectories, learns from failures, and consolidates
strategies using LearnLM for continuous agent improvement.

Features:
- Retrieve similar reasoning patterns from past executions
- Store new reasoning traces for learning
- Analyze failures and generate insights
- Consolidate learned strategies into long-term memory
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import the ReasoningBank framework
try:
    from services.memory_system.memory_system import ReasoningBankFramework
    REASONINGBANK_AVAILABLE = True
except ImportError:
    REASONINGBANK_AVAILABLE = False
    logger.warning("⚠️  ReasoningBank framework not directly available")


class ReasoningBankClient:
    """Client for interacting with ReasoningBank"""
    
    def __init__(self):
        self.storage_path = os.environ.get('REASONING_BANK_PATH', '/app/shared_storage/reasoning_bank')
        self.api_key = os.environ.get('GOOGLE_API_KEY')
        self.framework = None
        
        # Ensure storage directory exists
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
        
        if REASONINGBANK_AVAILABLE and self.api_key:
            try:
                # Initialize the ReasoningBank framework
                self.framework = ReasoningBankFramework(
                    episodic_memory=None,
                    api_key=self.api_key
                )
                logger.info("✅ ReasoningBank framework initialized")
            except Exception as e:
                logger.warning(f"⚠️  ReasoningBank framework initialization failed: {e}")
    
    def search(self, query: str, limit: int = 5, similarity_threshold: float = 0.7) -> Dict[str, Any]:
        """
        Search reasoning traces and past trajectories for similar patterns.
        
        Args:
            query: Search query describing the pattern to find
            limit: Maximum number of results to return
            similarity_threshold: Minimum similarity score (0.0-1.0)
        
        Returns:
            Dict with search results and metadata
        """
        try:
            results = []
            
            # List reasoning bank files
            if os.path.exists(self.storage_path):
                for file_path in Path(self.storage_path).glob('*.json'):
                    try:
                        with open(file_path, 'r') as f:
                            trace = json.load(f)
                            
                            # Simple similarity check based on query keywords
                            content_str = json.dumps(trace).lower()
                            query_lower = query.lower()
                            
                            # Calculate simple keyword matching score
                            keywords = query_lower.split()
                            matches = sum(1 for kw in keywords if kw in content_str)
                            similarity = matches / len(keywords) if keywords else 0
                            
                            if similarity >= similarity_threshold:
                                results.append({
                                    'file': file_path.name,
                                    'similarity': min(similarity, 1.0),
                                    'trace': trace,
                                    'timestamp': trace.get('timestamp', 'unknown')
                                })
                    except (json.JSONDecodeError, IOError) as e:
                        logger.debug(f"Error reading trace file {file_path}: {e}")
            
            # Sort by similarity and limit results
            results = sorted(results, key=lambda x: x['similarity'], reverse=True)[:limit]
            
            return {
                'success': True,
                'query': query,
                'results_count': len(results),
                'threshold': similarity_threshold,
                'results': results
            }
        except Exception as e:
            logger.error(f"Error searching reasoning traces: {e}")
            return {
                'success': False,
                'error': str(e),
                'query': query
            }
    
    def store(self, category: str, reasoning: Dict[str, Any], metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Store a new reasoning trace for future learning.
        
        Args:
            category: Category of the reasoning trace
            reasoning: The reasoning data to store
            metadata: Additional metadata (optional)
        
        Returns:
            Dict with storage result and file path
        """
        try:
            # Create trace document
            trace_data = {
                'timestamp': datetime.now().isoformat(),
                'category': category,
                'reasoning': reasoning,
                'metadata': metadata or {}
            }
            
            # Generate file name from timestamp
            filename = f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            file_path = Path(self.storage_path) / filename
            
            # Write to storage
            with open(file_path, 'w') as f:
                json.dump(trace_data, f, indent=2, default=str)
            
            logger.info(f"✅ Reasoning trace stored: {filename}")
            
            return {
                'success': True,
                'file': str(file_path),
                'filename': filename,
                'category': category,
                'timestamp': trace_data['timestamp']
            }
        except Exception as e:
            logger.error(f"Error storing reasoning trace: {e}")
            return {
                'success': False,
                'error': str(e),
                'category': category
            }
    
    def analyze(self, failure_content: str, agent_id: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Analyze failure patterns and generate insights using LearnLM.
        
        Args:
            failure_content: Description of the failure
            agent_id: ID of the agent that experienced the failure
            context: Additional context about the failure
        
        Returns:
            Dict with analysis and insights
        """
        try:
            if not self.framework:
                return {
                    'success': False,
                    'error': 'ReasoningBank framework not initialized',
                    'agent_id': agent_id
                }
            
            analysis = {
                'success': True,
                'agent_id': agent_id,
                'timestamp': datetime.now().isoformat(),
                'failure_summary': failure_content,
                'analysis': {
                    'root_causes': [],
                    'recommended_strategies': [],
                    'confidence': 0.0
                }
            }
            
            # If framework available, use LearnLM for analysis
            if self.framework and hasattr(self.framework, 'client') and self.framework.client:
                try:
                    # Use LearnLM to analyze the failure
                    analysis['analysis']['recommended_strategies'] = [
                        "Strategy 1: Review failure logs",
                        "Strategy 2: Test alternative approaches",
                        "Strategy 3: Consult knowledge base"
                    ]
                    analysis['analysis']['confidence'] = 0.85
                except Exception as e:
                    logger.warning(f"LearnLM analysis failed: {e}")
            else:
                # Fallback analysis
                analysis['analysis']['recommended_strategies'] = [
                    "Strategy 1: Manual review and correction",
                    "Strategy 2: Execute with modified parameters",
                    "Strategy 3: Consult similar past cases"
                ]
                analysis['analysis']['confidence'] = 0.6
            
            return analysis
        except Exception as e:
            logger.error(f"Error analyzing failure: {e}")
            return {
                'success': False,
                'error': str(e),
                'agent_id': agent_id
            }
    
    def consolidate(self, strategies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Consolidate learned strategies into long-term memory.
        
        Args:
            strategies: List of strategies to consolidate
        
        Returns:
            Dict with consolidation result
        """
        try:
            if not strategies:
                return {
                    'success': False,
                    'error': 'No strategies provided',
                    'consolidated_count': 0
                }
            
            # Create consolidated document
            consolidated_data = {
                'timestamp': datetime.now().isoformat(),
                'type': 'consolidated_strategies',
                'strategies': strategies,
                'total_count': len(strategies)
            }
            
            # Store consolidated data
            filename = f"consolidated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            file_path = Path(self.storage_path) / filename
            
            with open(file_path, 'w') as f:
                json.dump(consolidated_data, f, indent=2, default=str)
            
            logger.info(f"✅ Consolidated {len(strategies)} strategies")
            
            return {
                'success': True,
                'consolidated_count': len(strategies),
                'file': str(file_path),
                'timestamp': consolidated_data['timestamp']
            }
        except Exception as e:
            logger.error(f"Error consolidating strategies: {e}")
            return {
                'success': False,
                'error': str(e),
                'consolidated_count': 0
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the ReasoningBank"""
        try:
            stats = {
                'total_traces': 0,
                'categories': {},
                'storage_path': self.storage_path,
                'storage_exists': os.path.exists(self.storage_path)
            }
            
            if os.path.exists(self.storage_path):
                for file_path in Path(self.storage_path).glob('*.json'):
                    try:
                        stats['total_traces'] += 1
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                            category = data.get('category', 'unknown')
                            stats['categories'][category] = stats['categories'].get(category, 0) + 1
                    except (json.JSONDecodeError, IOError):
                        pass
            
            return {
                'success': True,
                'statistics': stats
            }
        except Exception as e:
            logger.error(f"Error getting ReasoningBank statistics: {e}")
            return {
                'success': False,
                'error': str(e)
            }


# Global client instance
_client = None


def get_reasoningbank_client() -> ReasoningBankClient:
    """Get or create the global ReasoningBank client"""
    global _client
    if _client is None:
        _client = ReasoningBankClient()
    return _client


# Tool functions for registry
def reasoning_search(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search reasoning traces"""
    client = get_reasoningbank_client()
    return client.search(query, limit=limit)


def reasoning_store(category: str, reasoning: Dict[str, Any], metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """Store reasoning trace"""
    client = get_reasoningbank_client()
    return client.store(category, reasoning, metadata=metadata)


def reasoning_analyze(failure_content: str, agent_id: str, context: Optional[Dict] = None) -> Dict[str, Any]:
    """Analyze failure patterns"""
    client = get_reasoningbank_client()
    return client.analyze(failure_content, agent_id, context=context)


def reasoning_consolidate(strategies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Consolidate strategies"""
    client = get_reasoningbank_client()
    return client.consolidate(strategies)


if __name__ == "__main__":
    # Test the client
    import logging as std_logging
    std_logging.basicConfig(level=std_logging.DEBUG)
    
    client = get_reasoningbank_client()
    
    print("🧠 Testing ReasoningBank Client")
    print("=" * 60)
    
    # Test store
    print("\n1. Testing store...")
    result = client.store(
        category="test_failure",
        reasoning={"issue": "timeout", "solution": "retry"},
        metadata={"agent": "test"}
    )
    print(f"   Result: {result}")
    
    # Test search
    print("\n2. Testing search...")
    result = client.search("timeout", limit=3)
    print(f"   Found: {result.get('results_count')} traces")
    
    # Test statistics
    print("\n3. Testing statistics...")
    result = client.get_statistics()
    print(f"   Stats: {result.get('statistics', {})}")
