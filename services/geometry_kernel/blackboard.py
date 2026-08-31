"""
Geometry Blackboard - Redis-based geometry state sharing between agents.

Enables cross-agent communication via geometric models:
- Agents publish geometry states to shared channels
- Other agents subscribe to geometry updates
- Force proposals can be shared and aggregated

This implements the "Neuro-Symbolic" communication layer where
agents reason about shared geometric models rather than raw text.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from .core import KernelState, ConceptNode, Attractor, Vector3D, Force, ForceSource

logger = logging.getLogger(__name__)


# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Geometry channels
GEOMETRY_STATE_CHANNEL = "arca:geometry:state"
GEOMETRY_FORCE_CHANNEL = "arca:geometry:force"
GEOMETRY_ANOMALY_CHANNEL = "arca:geometry:anomaly"

# State keys
GEOMETRY_STATE_KEY = "arca:geometry:current_state"
GEOMETRY_HISTORY_KEY = "arca:geometry:state_history"


@dataclass
class GeometryMessage:
    """Message format for geometry state sharing."""
    message_type: str  # "state", "force", "anomaly"
    agent_id: str
    timestamp: str
    payload: Dict[str, Any]
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @staticmethod
    def from_json(data: str) -> 'GeometryMessage':
        d = json.loads(data)
        return GeometryMessage(**d)


class GeometryBlackboard:
    """
    Redis-based blackboard for sharing geometric states between agents.
    
    Implements pub/sub for real-time updates and key-value storage
    for persistent state access.
    
    Example:
        blackboard = GeometryBlackboard()
        
        # Publish state
        blackboard.publish_state(kernel.current_state, agent_id="architect")
        
        # Subscribe to force proposals
        blackboard.subscribe_forces(on_force_received)
        
        # Get current shared state
        state = blackboard.get_current_state()
    """
    
    def __init__(self, host: str = None, port: int = None):
        """Initialize the geometry blackboard."""
        self.host = host or REDIS_HOST
        self.port = port or REDIS_PORT
        self.client = None
        self.pubsub = None
        self._subscribers: Dict[str, Callable] = {}
        
        if REDIS_AVAILABLE:
            try:
                self.client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    decode_responses=True
                )
                self.client.ping()
                logger.info(f"Geometry Blackboard connected to Redis at {self.host}:{self.port}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self.client = None
        else:
            logger.warning("Redis not available - Geometry Blackboard running in local mode")
    
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        if not self.client:
            return False
        try:
            self.client.ping()
            return True
        except:
            return False
    
    # ========================================================================
    # State Publishing
    # ========================================================================
    
    def publish_state(
        self,
        state: KernelState,
        agent_id: str = "unknown"
    ) -> bool:
        """
        Publish a geometry state to the blackboard.
        
        Other agents can subscribe to state updates or retrieve
        the current state at any time.
        """
        if not self.client:
            logger.debug("Redis not available, skipping state publish")
            return False
        
        try:
            # Store current state
            state_dict = state.to_dict()
            self.client.set(GEOMETRY_STATE_KEY, json.dumps(state_dict))
            
            # Push to history (keep last 100)
            self.client.lpush(GEOMETRY_HISTORY_KEY, json.dumps({
                "state_id": state.id,
                "timestamp": datetime.utcnow().isoformat(),
                "agent_id": agent_id
            }))
            self.client.ltrim(GEOMETRY_HISTORY_KEY, 0, 99)
            
            # Publish update notification
            message = GeometryMessage(
                message_type="state",
                agent_id=agent_id,
                timestamp=datetime.utcnow().isoformat(),
                payload={
                    "state_id": state.id,
                    "nodes_count": len(state.nodes),
                    "attractors_count": len(state.attractors),
                    "stability": state.health_metrics.get("stability_index", 1.0)
                }
            )
            self.client.publish(GEOMETRY_STATE_CHANNEL, message.to_json())
            
            logger.debug(f"Published geometry state: {state.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish geometry state: {e}")
            return False
    
    def get_current_state(self) -> Optional[KernelState]:
        """Retrieve the current shared geometry state."""
        if not self.client:
            return None
        
        try:
            data = self.client.get(GEOMETRY_STATE_KEY)
            if data:
                return KernelState.from_dict(json.loads(data))
            return None
        except Exception as e:
            logger.error(f"Failed to get geometry state: {e}")
            return None
    
    def get_state_history(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent state change history."""
        if not self.client:
            return []
        
        try:
            history = self.client.lrange(GEOMETRY_HISTORY_KEY, 0, count - 1)
            return [json.loads(h) for h in history]
        except Exception as e:
            logger.error(f"Failed to get state history: {e}")
            return []
    
    # ========================================================================
    # Force Publishing
    # ========================================================================
    
    def publish_force(
        self,
        force: Force,
        agent_id: str = "unknown"
    ) -> bool:
        """
        Publish a force proposal to the blackboard.
        
        Other agents can subscribe to force proposals to observe
        or aggregate them before application.
        """
        if not self.client:
            return False
        
        try:
            message = GeometryMessage(
                message_type="force",
                agent_id=agent_id,
                timestamp=datetime.utcnow().isoformat(),
                payload={
                    "target_id": force.target_id,
                    "vector": force.vector.to_list(),
                    "magnitude": force.magnitude,
                    "source": force.source.value,
                    "rationale": force.rationale
                }
            )
            self.client.publish(GEOMETRY_FORCE_CHANNEL, message.to_json())
            
            logger.debug(f"Published force proposal: {force.target_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish force: {e}")
            return False
    
    def publish_anomaly(
        self,
        anomaly: Dict[str, Any],
        agent_id: str = "unknown"
    ) -> bool:
        """Publish an anomaly detection to the blackboard."""
        if not self.client:
            return False
        
        try:
            message = GeometryMessage(
                message_type="anomaly",
                agent_id=agent_id,
                timestamp=datetime.utcnow().isoformat(),
                payload=anomaly
            )
            self.client.publish(GEOMETRY_ANOMALY_CHANNEL, message.to_json())
            
            logger.debug(f"Published anomaly: {anomaly.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish anomaly: {e}")
            return False
    
    # ========================================================================
    # Subscriptions
    # ========================================================================
    
    def subscribe_states(self, callback: Callable[[GeometryMessage], None]):
        """Subscribe to geometry state updates."""
        self._subscribe(GEOMETRY_STATE_CHANNEL, callback)
    
    def subscribe_forces(self, callback: Callable[[GeometryMessage], None]):
        """Subscribe to force proposals."""
        self._subscribe(GEOMETRY_FORCE_CHANNEL, callback)
    
    def subscribe_anomalies(self, callback: Callable[[GeometryMessage], None]):
        """Subscribe to anomaly detections."""
        self._subscribe(GEOMETRY_ANOMALY_CHANNEL, callback)
    
    def _subscribe(self, channel: str, callback: Callable):
        """Internal subscribe helper."""
        if not self.client:
            logger.warning(f"Cannot subscribe to {channel}: Redis not available")
            return
        
        self._subscribers[channel] = callback
        
        if not self.pubsub:
            self.pubsub = self.client.pubsub()
        
        def message_handler(message):
            if message["type"] == "message":
                try:
                    geo_msg = GeometryMessage.from_json(message["data"])
                    callback(geo_msg)
                except Exception as e:
                    logger.error(f"Error handling geometry message: {e}")
        
        self.pubsub.subscribe(**{channel: message_handler})
        logger.info(f"Subscribed to geometry channel: {channel}")
    
    def start_listening(self):
        """Start listening for subscribed messages (blocking)."""
        if self.pubsub:
            for message in self.pubsub.listen():
                pass  # Handlers called automatically
    
    def start_listening_async(self):
        """Start listening in a background thread."""
        import threading
        thread = threading.Thread(target=self.start_listening, daemon=True)
        thread.start()
        return thread
    
    # ========================================================================
    # Agent Coordination
    # ========================================================================
    
    def register_agent(self, agent_id: str, agent_role: str) -> bool:
        """Register an agent on the blackboard."""
        if not self.client:
            return False
        
        try:
            self.client.hset("arca:geometry:agents", agent_id, json.dumps({
                "role": agent_role,
                "registered_at": datetime.utcnow().isoformat(),
                "last_seen": datetime.utcnow().isoformat()
            }))
            return True
        except:
            return False
    
    def get_active_agents(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered agents."""
        if not self.client:
            return {}
        
        try:
            agents = self.client.hgetall("arca:geometry:agents")
            return {k: json.loads(v) for k, v in agents.items()}
        except:
            return {}
    
    def heartbeat(self, agent_id: str):
        """Update agent's last seen timestamp."""
        if not self.client:
            return
        
        try:
            data = self.client.hget("arca:geometry:agents", agent_id)
            if data:
                agent = json.loads(data)
                agent["last_seen"] = datetime.utcnow().isoformat()
                self.client.hset("arca:geometry:agents", agent_id, json.dumps(agent))
        except:
            pass


# Singleton instance for global access
_blackboard: Optional[GeometryBlackboard] = None


def get_blackboard() -> GeometryBlackboard:
    """Get the global geometry blackboard instance."""
    global _blackboard
    if _blackboard is None:
        _blackboard = GeometryBlackboard()
    return _blackboard


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== Geometry Blackboard Test ===")
    
    blackboard = get_blackboard()
    print(f"Connected: {blackboard.is_connected()}")
    
    if blackboard.is_connected():
        # Test state publish
        from .core import GeometryKernel
        from datetime import datetime
        
        kernel = GeometryKernel()
        nodes = [
            ConceptNode(
                id="test_node",
                position=Vector3D(0, 0, 0),
                velocity=Vector3D(0, 0, 0),
                mass=1.0,
                energy=0.1,
                stability=0.9,
                confidence=0.8,
                last_updated=datetime.utcnow()
            )
        ]
        state = kernel.initialize_state(nodes, [])
        
        blackboard.register_agent("test_agent", "architect")
        blackboard.publish_state(state, "test_agent")
        
        retrieved = blackboard.get_current_state()
        if retrieved:
            print(f"✅ State retrieved: {retrieved.id}")
        
        agents = blackboard.get_active_agents()
        print(f"Active agents: {list(agents.keys())}")
    else:
        print("⚠️ Running in local mode (no Redis)")
    
    print("=== Test Complete ===")
