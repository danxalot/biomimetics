import logging
import numpy as np
from typing import Dict, Any, Optional, List
import asyncio
import time
from prometheus_api_client import PrometheusConnect


logger = logging.getLogger("HDCOpsAgent")

# NumPy-based Hyperdimensional Computing Operations (replacing torchhd)
class HDCOps:
    """NumPy-based HDC operations for bipolar {-1, +1} vectors."""
    
    @staticmethod
    def random(dim: int = 10000, seed: Optional[int] = None) -> np.ndarray:
        """Generate a random bipolar hypervector."""
        if seed is not None:
            rng = np.random.RandomState(seed)
            return rng.choice([-1, 1], size=dim)
        return np.random.choice([-1, 1], size=dim)
    
    @staticmethod
    def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Bind two hypervectors (element-wise multiplication for bipolar)."""
        return a * b
    
    @staticmethod
    def bundle(vectors: List[np.ndarray]) -> np.ndarray:
        """Bundle hypervectors using element-wise sum and threshold."""
        if not vectors:
            return np.zeros(10000, dtype=np.float32)
        
        stacked = np.vstack(vectors)
        bundled = np.sum(stacked, axis=0)
        
        # Threshold to bipolar: positive -> +1, negative -> -1, zero -> random
        bundled = np.sign(bundled)
        zeros = (bundled == 0)
        if np.any(zeros):
            bundled[zeros] = np.random.choice([-1, 1], size=np.sum(zeros))
        
        return bundled.astype(np.float32)
    
    @staticmethod
    def permute(hv: np.ndarray, n: int = 1) -> np.ndarray:
        """Circular shift (permutation) for sequence encoding."""
        return np.roll(hv, shift=n)
    
    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between hypervectors."""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        # Avoid division by zero
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return dot_product / (norm_a * norm_b)

# Global HDC operations instance
_hdc_ops = HDCOps()

class HDCOpsAgent:
    """
    Local ops agent that receives HDC intent vectors alongside text commands.
    """

    def __init__(self, agent_type: str, encoder=None, dragonfly_client=None, hv_dim: int = 10000, prom_url: str = "http://prometheus:9090"):
        self.agent_type = agent_type
        self.encoder = encoder
        self.kv = dragonfly_client
        self.hv_dim = hv_dim
        
        # Telemetry Connection
        try:
            self.prom = PrometheusConnect(url=prom_url, disable_ssl=True)
            self._prom_available = True
        except:
            self._prom_available = False
            logger.warning("Prometheus not available - Proprioception will be simulated.")

        # Agent's capability vector (what this agent can do)
        self.capability_hv = self._load_capability_vector()

    def _load_capability_vector(self) -> np.ndarray:
        # Placeholder: Generate random capability vector for now
        # In a real system, this would be an aggregation of tool embeddings
        return _hdc_ops.random(1, self.hv_dim)[0]

    def _suggest_agent(self, command_hv: np.ndarray) -> str:
        # Placeholder logic
        return "human"

    async def _capture_state(self) -> dict:
        """
        Capture the Proprioceptive State of the System (ConceptMonad Lite).
        """
        metrics = {}
        if self._prom_available:
            try:
                # 1. Fetch Key Metrics (Proprioception)
                # "Heartbeat" (Up)
                metrics['up'] = self._fetch_metric('up{job="user_interaction_agent"}', 0)
                # "Energy" (CPU Usage)
                metrics['cpu'] = self._fetch_metric('rate(container_cpu_usage_seconds_total[1m])', 0.1)
                # "Mass" (Memory Usage)
                metrics['memory'] = self._fetch_metric('container_memory_usage_bytes', 100 * 1024 * 1024)
            except Exception as e:
                logger.error(f"Telemetry fetch failed: {e}")
        
        # 2. Encode into HDC (System State Vector)
        # Create a foundational basis for system components if not exists
        # In real impl, fetch from Dragonfly. Here we generate deterministic basis.
        
        # Encode "Health" (1.0 = good, 0.0 = bad)
        health_val = metrics.get('up', 1.0)
        energy_val = min(metrics.get('cpu', 0.0) * 10, 1.0) # Normalize 0.1 core to 1.0
        
        # Generate State Matrix Product (Simplified as scaled binding)
        # State = (Health * ID_HEALTH) + (Energy * ID_ENERGY)
        # For now, we simple rotate a random vector by the 'metric' amount
        
        base_hv = _hdc_ops.random(1, self.hv_dim)[0]
        
        # Apply "Stress" rotation based on CPU load (Energy)
        # Higher energy = Faster rotation (Frequency)
        # We simulate this by returning a vector that 'drifts' based on load
        
        return {
            'hv': base_hv, 
            'phase': (time.time() % 6.28), # Simulated Phase (0-2pi)
            'frequency': 1.0 + energy_val, # Frequency shifts with Load (Proprioception)
            'metrics': metrics,
            'timestamp': time.time()
        }

    def _fetch_metric(self, query: str, default: float) -> float:
        """Helper to fetch single scalar from Prometheus"""
        try:
            result = self.prom.custom_query(query=query)
            if result and len(result) > 0:
                val = result[0]['value'][1]
                return float(val)
        except:
            pass
        return default

    async def _execute_command(self, command: str) -> str:
        # Placeholder execution logic
        logger.info(f"Executing: {command}")
        return "Command Executed Successfully"

    async def execute(self, command: str,
                      intent_hv: np.ndarray,
                      expected_outcome_hv: np.ndarray) -> dict:
        """
        Execute a command with HDC validation.
        """
        # Validate command matches intent
        if self.encoder:
            # Assuming encoder handles text to hv directly
            command_hv = self.encoder.encode_text(command)
        else:
             # Fallback
             command_hv = _hdc_ops.random(1, self.hv_dim)[0]

        intent_alignment = _hdc_ops.cosine_similarity(command_hv, intent_hv)

        # Relaxed threshold for dev
        if intent_alignment < 0.3:
            return {
                'status': 'rejected',
                'reason': f'Command does not match intent (alignment: {intent_alignment:.2f})',
                'suggestion': 'Verify command matches the planned action'
            }

        # Validate this agent can handle the command
        capability_match = _hdc_ops.cosine_similarity(command_hv, self.capability_hv)

        if capability_match < 0.2:
            return {
                'status': 'rejected',
                'reason': f'Command outside agent capabilities (match: {capability_match:.2f})',
                'suggestion': f'Route to appropriate agent for {self._suggest_agent(command_hv)}'
            }

        # Execute
        pre_state = await self._capture_state()

        try:
            result = await self._execute_command(command)
            post_state = await self._capture_state()

            # Encode state change -> Bind(Pre, Post)
            # Use 'hv' from the Monad structure
            state_change_hv = _hdc_ops.bind(pre_state['hv'], post_state['hv'])

            # Validate outcome matches expectation
            outcome_match = _hdc_ops.cosine_similarity(post_state['hv'], expected_outcome_hv)

            return {
                'status': 'success' if outcome_match > 0.5 else 'partial_success',
                'result': result,
                'pre_state_hv': pre_state['hv'],
                'post_state_hv': post_state['hv'],
                'state_change_hv': state_change_hv,
                'outcome_match': outcome_match,
                'outcome_warning': None if outcome_match > 0.5 else \
                    f'Outcome differs from prediction (match: {outcome_match:.2f})',
                'proprioception': {
                    'pre_metrics': pre_state.get('metrics', {}),
                    'post_metrics': post_state.get('metrics', {})
                }
            }

        except Exception as e:
            # post_state might fail if system crashed, try capture again
            try:
                post_state_hv = (await self._capture_state())['hv']
            except:
                post_state_hv = np.zeros(self.hv_dim, dtype=np.float32)
                
            return {
                'status': 'error',
                'error': str(e),
                'pre_state_hv': pre_state['hv'],
                'post_state_hv': post_state_hv
            }
