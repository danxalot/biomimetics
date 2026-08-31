"""
Geometry Kernel API Service

Flask-based HTTP API for the geometry kernel.

This is the narrow waist through which all state changes flow.
Everything funnels through these endpoints.
Nothing bypasses the geometry kernel.

Endpoints:
  POST /geometry/simulate      - Predict next state (no mutation)
  POST /geometry/validate      - Check if simulation is safe
  POST /geometry/apply         - Apply validated simulation to state
  GET  /geometry/render        - Get visualization data
  GET  /geometry/health        - Service health check
"""

from flask import Flask, request, jsonify
from dataclasses import asdict
from typing import Dict, Any, List, Optional, Tuple
import json
import uuid
from datetime import datetime
import logging
import os
import sys
import threading
import time
import requests
import redis
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import (
    GeometryKernel,
    KernelState,
    ConceptNode,
    Attractor,
    Force,
    ForceSource,
    Mode,
    Vector3D,
    EvaluationOutcome,
    EvaluationOutcome,
    SimulationResult,
)
from model_engine import CognitiveScheduler
from audit_service import LocalAuditor
from recursive_ingestion import RecursiveIngestion

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.json.sort_keys = False

# Global kernel instance
kernel: Optional[GeometryKernel] = None
# Global scheduler instance
scheduler: Optional[CognitiveScheduler] = None
# Global auditor instance
auditor: Optional[LocalAuditor] = None
# Redis client
redis_client: Optional[redis.Redis] = None
# HSE Polling thread
hse_thread: Optional[threading.Thread] = None


# ============================================================================
# Initialization
# ============================================================================

def init_kernel():
    """Initialize the geometry kernel with default state."""
    global kernel
    kernel = GeometryKernel(
        v_max=0.5,
        curvature_cap=0.2,
        inertia_friction=0.1,
        time_step=1.0,
    )
    
    # Initialize Scheduler
    global scheduler, auditor
    scheduler = CognitiveScheduler()
    auditor = LocalAuditor(scheduler)
    logger.info("Cognitive Scheduler and Auditor initialized")

    # Connect to Redis
    global redis_client
    try:
        redis_host = os.environ.get("REDIS_HOST", "redis")
        redis_client = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)
        redis_client.ping()
        logger.info(f"Connected to Redis at {redis_host}")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        redis_client = None

    # Start HSE polling thread
    start_hse_polling()
    
    # Start cognitive tick thread (0.3s heartbeat)
    start_cognitive_tick()

    # Create initial concepts
    initial_nodes = [
        ConceptNode(
            id="concept:system_coherence",
            position=Vector3D(0.0, 0.0, 0.0),
            velocity=Vector3D(0.0, 0.0, 0.0),
            mass=2.0,
            energy=0.0,
            stability=1.0,
            confidence=0.95,
            last_updated=datetime.utcnow(),
        ),
        ConceptNode(
            id="concept:agent_reliability",
            position=Vector3D(1.0, 0.0, 0.0),
            velocity=Vector3D(0.0, 0.0, 0.0),
            mass=1.0,
            energy=0.0,
            stability=0.9,
            confidence=0.9,
            last_updated=datetime.utcnow(),
        ),
        ConceptNode(
            id="concept:semantic_coherence",
            position=Vector3D(0.5, 1.0, 0.0),
            velocity=Vector3D(0.0, 0.0, 0.0),
            mass=1.5,
            energy=0.0,
            stability=0.85,
            confidence=0.85,
            last_updated=datetime.utcnow(),
        ),
        ConceptNode(
            id="concept:error_rate",
            position=Vector3D(-1.0, -1.0, 0.0),
            velocity=Vector3D(0.0, 0.0, 0.0),
            mass=0.8,
            energy=0.0,
            stability=0.8,
            confidence=0.8,
            last_updated=datetime.utcnow(),
        ),
    ]

    initial_attractors = [
        Attractor(
            id="attractor:stable_operation",
            center=Vector3D(0.5, 0.2, 0.0),
            radius=0.5,
            depth=0.8,
            confidence=0.95,
            created_by=Mode.WAKE,
            created_at=datetime.utcnow(),
        ),
        Attractor(
            id="attractor:learning_mode",
            center=Vector3D(0.0, 0.5, 0.5),
            radius=0.4,
            depth=0.6,
            confidence=0.7,
            created_by=Mode.DREAM,
            created_at=datetime.utcnow(),
        ),
    ]

    kernel.initialize_state(initial_nodes, initial_attractors)
    logger.info("Geometry Kernel initialized with default state")


def start_hse_polling():
    """Start background thread to poll HSE state."""
    global hse_thread
    if hse_thread is None or not hse_thread.is_alive():
        hse_thread = threading.Thread(target=_poll_hse_loop, daemon=True)
        hse_thread.start()
        logger.info("Started HSE polling thread")


def _poll_hse_loop():
    """Poll Redis/Service for HSE updates."""
    # Try polling Redis first (lower latency)
    # Fallback to HTTP if needed
    while True:
        try:
            if kernel and redis_client:
                # 1. Try Redis for raw vector push
                data_str = redis_client.get("arca:hse:state_vector")
                if data_str:
                    data = json.loads(data_str)
                    # Convert hex string back to vector if needed, or pass as is if Logic expects it
                    # core.py expects: vector, velocity, anomaly_score
                    kernel.ingest_hse_state(data)
                
            time.sleep(5.0) # 5 seconds poll
        except Exception as e:
            logger.error(f"HSE poll error: {e}")
            time.sleep(10.0)


# Cognitive Tick Thread
cognitive_tick_thread: Optional[threading.Thread] = None

def start_cognitive_tick():
    """Start background thread for cognitive tick (0.3s heartbeat)."""
    global cognitive_tick_thread
    if cognitive_tick_thread is None or not cognitive_tick_thread.is_alive():
        cognitive_tick_thread = threading.Thread(target=_cognitive_tick_loop, daemon=True)
        cognitive_tick_thread.start()
        logger.info("Started Cognitive Tick thread (0.3s interval)")


def _cognitive_tick_loop():
    """
    Cognitive Tick: 0.3s heartbeat for geometry kernel.
    
    Each tick:
    1. Runs simulation step (applies decay, momentum, attractors)
    2. Publishes state summary to Redis
    """
    tick_count = 0
    while True:
        try:
            if kernel and kernel.current_state:
                tick_count += 1
                
                # Every tick: run simulation with no external forces (just internal physics)
                # This applies decay, attractor pull, and momentum
                try:
                    kernel.simulate([])  # Empty force list = physics only
                except Exception as sim_err:
                    logger.debug(f"Tick simulation: {sim_err}")
                
                # Every 10 ticks (~3s): publish summary to Redis
                if tick_count % 10 == 0 and redis_client:
                    health = kernel.current_state.health_metrics or {}
                    summary = {
                        "tick": tick_count,
                        "node_count": len(kernel.current_state.nodes),
                        "stability_index": health.get("stability_index", 1.0),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    redis_client.set("arca:geometry:tick_summary", json.dumps(summary))
                    
            time.sleep(0.3)  # 300ms cognitive tick
        except Exception as e:
            logger.error(f"Cognitive tick error: {e}")
            time.sleep(1.0)  # Back off on error


# ============================================================================
# Request/Response Serialization Helpers
# ============================================================================

def serialize_kernel_state(state: KernelState) -> Dict[str, Any]:
    """Convert KernelState to JSON-serializable dict."""
    return {
        "id": state.id,
        "timestamp": state.timestamp.isoformat(),
        "nodes": {
            nid: {
                "id": node.id,
                "position": node.position.to_list(),
                "velocity": node.velocity.to_list(),
                "mass": node.mass,
                "energy": node.energy,
                "stability": node.stability,
                "confidence": node.confidence,
                "last_updated": node.last_updated.isoformat(),
            }
            for nid, node in state.nodes.items()
        },
        "attractors": {
            aid: {
                "id": attr.id,
                "center": attr.center.to_list(),
                "radius": attr.radius,
                "depth": attr.depth,
                "confidence": attr.confidence,
                "created_by": attr.created_by.value,
                "created_at": attr.created_at.isoformat(),
            }
            for aid, attr in state.attractors.items()
        },
        "health_metrics": state.health_metrics,
        "axes_weights": state.axes_weights,
        "hse_state": state.hse_state.to_dict() if state.hse_state else None,
    }


def serialize_simulation_result(result: SimulationResult) -> Dict[str, Any]:
    """Convert SimulationResult to JSON-serializable dict."""
    return {
        "simulation_id": result.simulation_id,
        "predicted_state": serialize_kernel_state(result.predicted_state),
        "metrics": result.metrics,
    }


def parse_vector3d(lst: List[float]) -> Vector3D:
    """Parse [x, y, z] to Vector3D."""
    return Vector3D(lst[0], lst[1], lst[2])


# ============================================================================
# API Endpoints
# ============================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """Service health check."""
    return jsonify({
        "status": "healthy",
        "service": "geometry_kernel",
        "kernel_initialized": kernel is not None,
    }), 200


@app.route("/state", methods=["GET"])
def get_current_state():
    """
    GET /geometry/state
    Returns current kernel state.
    """
    if kernel is None or kernel.current_state is None:
        return jsonify({"error": "Kernel not initialized"}), 503

    return jsonify({
        "current_state": serialize_kernel_state(kernel.current_state),
    }), 200


@app.route("/simulate", methods=["POST"])
def simulate():
    """
    POST /geometry/simulate

    Simulate forces without mutating state.

    Request body:
    {
      "mode": "dream" | "wake",
      "base_state_id": "uuid",
      "forces": [
        {
          "target_id": "concept:x",
          "vector": [x, y, z],
          "magnitude": 0.1,
          "source": "evidence" | "contradiction" | "decay" | "dream" | "otel",
          "rationale": "short explanation"
        }
      ],
      "attractor_proposals": [
        {
          "id": "attractor:new_concept",
          "center": [x, y, z],
          "radius": 0.3,
          "depth": 0.8,
          "confidence": 0.75
        }
      ],
      "axis_emphasis": {
        "semantic_coherence": +0.1
      }
    }

    Returns:
    {
      "simulation_id": "uuid",
      "predicted_state": {...},
      "metrics": {
        "stability": 0.75,
        "energy_delta": -0.1,
        "divergence": 0.05
      }
    }
    """
    try:
        data = request.get_json()

        # Parse input
        mode_str = data.get("mode", "wake")
        mode = Mode(mode_str)
        base_state_id = data.get("base_state_id")
        forces_data = data.get("forces", [])
        attractors_data = data.get("attractor_proposals", [])
        axis_emphasis = data.get("axis_emphasis", {})

        # Build Force objects
        forces = []
        for f in forces_data:
            force = Force(
                target_id=f["target_id"],
                vector=parse_vector3d(f["vector"]),
                magnitude=f.get("magnitude", 0.1),
                source=ForceSource(f.get("source", "evidence")),
                rationale=f.get("rationale", ""),
            )
            forces.append(force)

        # Build Attractor proposals
        attractors = []
        for a in attractors_data:
            attractor = Attractor(
                id=a.get("id", f"attractor:{uuid.uuid4()}"),
                center=parse_vector3d(a["center"]),
                radius=a.get("radius", 0.3),
                depth=a.get("depth", 0.6),
                confidence=a.get("confidence", 0.7),
                created_by=mode,
                created_at=datetime.utcnow(),
            )
            attractors.append(attractor)

        # Run simulation
        result = kernel.simulate(
            base_state_id=base_state_id or kernel.current_state.id,
            forces=forces,
            attractor_proposals=attractors,
            axis_emphasis=axis_emphasis,
            mode=mode,
        )

        return jsonify(serialize_simulation_result(result)), 200

    except ValueError as e:
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Simulation error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/validate", methods=["POST"])
def validate():
    """
    POST /geometry/validate

    Validate a simulation before applying it.

    Request body:
    {
      "simulation_id": "uuid",
      "health_metrics": {
        "stability_index": 0.9,
        "error_rate": 0.02,
        "entropy_level": 0.1
      }
    }

    Returns:
    {
      "decision": "accept" | "softened" | "reject",
      "reason": "symbolic reason",
      "notes": "optional details"
    }

    Note: This is a minimal internal gate. External gates (robotics, guardian)
    are called by the orchestrator separately.
    """
    try:
        data = request.get_json()
        simulation_id = data.get("simulation_id")
        health_metrics = data.get("health_metrics", {})

        # Run validation
        decision, reason = kernel.validate(simulation_id, health_metrics)

        return jsonify({
            "simulation_id": simulation_id,
            "decision": decision.value,
            "reason": reason,
        }), 200

    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/apply", methods=["POST"])
def apply():
    """
    POST /geometry/apply

    Apply a validated simulation to persistent state.

    RESTRICTED: Only callable by orchestrator after full validation pipeline.

    Request body:
    {
      "simulation_id": "uuid",
      "approved_by": ["guardian", "robotics", "reviewer"]
    }

    Returns:
    {
      "state_id": "uuid",
      "timestamp": "2025-01-XX...",
      "status": "applied"
    }
    """
    try:
        data = request.get_json()
        simulation_id = data.get("simulation_id")
        approved_by = data.get("approved_by", [])

        if not approved_by:
            return jsonify({"error": "No approvers specified"}), 400

        # Apply (in production, this mutates kernel.current_state)
        # For now, placeholder
        new_state_id = str(uuid.uuid4())
        return jsonify({
            "state_id": new_state_id,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "applied",
            "approved_by": approved_by,
        }), 200

    except Exception as e:
        logger.error(f"Apply error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/ingest", methods=["POST"])
def ingest_data():
    """
    POST /geometry/ingest
    Ingest a document or data chunk to become a ConceptNode.
    Expected payload:
    {
        "title": "...",
        "content_snippet": "...",
        "vector": [x, y, z...], # or None
        "source": "...",
        "mode": "store"
    }
    """
    try:
        data = request.get_json()
        title = data.get("title", "Untitled")
        vector_data = data.get("vector", [])
        
        # Convert n-dim embedding to 3D position if needed, or store high-dim else-where?
        # The Kernel uses Vector3D for position.
        # Simple projection for now: First 3 dims, or 0,0,0
        if vector_data and len(vector_data) >= 3:
            pos = Vector3D(vector_data[0], vector_data[1], vector_data[2])
        else:
            pos = Vector3D(0.0, 0.0, 0.0)
            
        new_id = f"concept:{uuid.uuid4()}"
        confidence = 0.8
        
        node = ConceptNode(
            id=new_id,
            position=pos,
            velocity=Vector3D(0.0, 0.0, 0.0),
            mass=1.0,
            energy=0.5, # Initial energy punch
            stability=0.5,
            confidence=confidence,
            last_updated=datetime.utcnow()
        )
        
        if kernel and kernel.current_state:
            kernel.current_state.nodes[new_id] = node
            logger.info(f"Ingested concept {new_id} ('{title}')")
            
        return jsonify({
            "status": "ingested", 
            "id": new_id,
            "mapped_position": pos.to_list()
        }), 200
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/ingest_recursive", methods=["POST"])
def ingest_recursive():
    """
    POST /geometry/ingest_recursive
    Uses Recursive Logic (RLM) to walk a file and return a full Solar System abstraction.
    """
    try:
        data = request.get_json()
        file_path = data.get("file_path")
        objective = data.get("objective")
        content_type = data.get("content_type", "AUTO")
        
        if not file_path or not objective:
            return jsonify({"error": "Missing file_path or objective"}), 400
            
        if not scheduler:
            return jsonify({"error": "Scheduler not initialized"}), 503
            
        ingester = RecursiveIngestion(scheduler)
        solar_system = ingester.ingest_content(file_path, objective, content_type)
        
        # Persist Working Model to Redis (Shared Blackboard)
        # Allows both agents to access the model without polluting System Geometry State
        if redis_client:
            try:
                redis_key = "arca:blackboard:working_model"
                redis_client.set(redis_key, json.dumps(solar_system))
                
                # Update History (LIFO)
                redis_client.lpush("arca:blackboard:geometry_history", json.dumps({
                    "id": file_path, "timestamp": str(datetime.now()), "solar_system": solar_system
                }))
                redis_client.ltrim("arca:blackboard:geometry_history", 0, 19) # Keep last 20

                # Also verify connectivity or log size
                size = len(json.dumps(solar_system))
                logger.info(f"Published working model to {redis_key} ({size} bytes)")
            except Exception as rx:
                logger.warning(f"Failed to publish to Redis: {rx}")
            
        return jsonify(solar_system), 200
        
    except Exception as e:
        logger.error(f"Recursive ingest error: {e}")
        return jsonify({"error": str(e)}), 500



@app.route("/analyze", methods=["POST"])
def analyze_query():
    """
    POST /analyze
    Returns the raw geometric state (working model) from Redis for agent analysis.
    User can provide a query to filter/focus, but currently extracting full state.
    """
    try:
        # We might use query for filtering later
        _ = request.get_json() or {}
        
        if not redis_client:
            return jsonify({"error": "Redis client not initialized"}), 500

        # Fetch directly from Blackboard
        raw_data = redis_client.get("arca:blackboard:working_model")
        
        if raw_data:
            # Return the raw structure (gravity_well, objects, etc.)
            # The calling agent (Gemma) will inspect this JSON.
            return jsonify(json.loads(raw_data)), 200
        else:
            return jsonify({
                "status": "empty", 
                "message": "No active geometric model found in arca:blackboard:working_model"
            }), 200

    except Exception as e:
        logger.error(f"Analyze error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/history", methods=["GET"])
def get_geometry_history():
    """
    GET /history
    Returns the list of all ingested solar systems from Redis history.
    """
    try:
        limit = request.args.get('limit', 10, type=int)
        
        if not redis_client:
             return jsonify({"error": "Redis client not initialized"}), 500

        # Fetch history list (LIFO)
        history_raw = redis_client.lrange("arca:blackboard:geometry_history", 0, limit - 1)
        
        history = []
        for item in history_raw:
            try:
                history.append(json.loads(item))
            except:
                pass # Skip malformed
                
        return jsonify({"history": history, "count": len(history)}), 200
        
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/force", methods=["POST"])
def apply_force_endpoint():
    """
    POST /geometry/force
    Agent tool endpoint: Apply a force to the system.
    Wrapper around simulate but implies Intent to change.
    """
    return simulate() # Functionally similar for now


@app.route("/render", methods=["GET"])
def render_concept_space():
    """
    Get the current state of the concept space for visualization.
    
    Query Params:
        state_id (optional): The ID of the state to render. Defaults to current.
        view (optional): The view to render (e.g. "global", "local"). Defaults to global.
        time_window (optional): The number of recent events to include. Defaults to 100.
        mode (optional): "system" (default) or "focus" (geometric subject)
    """
    try:
        mode = request.headers.get("X-Geometry-Mode", "system")
        logger.info(f"RENDER REQUEST: args={request.args}, mode={mode}, headers={request.headers}") # extended debug

        if mode == "focus":
            # Retrieve from Redis Blackboard
            try:
                # Reuse the global redis_client if initialized, otherwise create one for this request
                # Assuming redis_client provided by global scope or init
                r_client = redis.Redis(host=os.environ.get("REDIS_HOST", "redis"), port=int(os.environ.get("REDIS_PORT", 6379)), decode_responses=True)
                
                state_json = r_client.get("arca:blackboard:working_model")
                if not state_json:
                    # Fallback to history
                    history = r_client.lrange("arca:blackboard:geometry_history", 0, 0)
                    if history:
                        # history stores a list of JSON strings, each containing "solar_system"
                        history_entry = json.loads(history[0])
                        state_json = json.dumps(history_entry.get("solar_system"))
                
                if state_json:
                    # Parse into dict if string
                    data = json.loads(state_json)
                        
                    # Transform Solar System to Render Format
                    # Solar System: { center_mass: {label, ...}, orbiting_bodies: [{label, mass, ...}] }
                    # Render Format: { concepts: [{x,y,z,mass,label}], attractors: [] }
                    
                    concepts = []
                    
                    # 1. Sun (Center)
                    # Support both V2.1 (gravity_well) and V2.0 (center_mass) keys
                    center = data.get("gravity_well") or data.get("center_mass", {})
                    if center:
                        concepts.append({
                            "id": "center",
                            "label": center.get("concept") or center.get("label", "Unknown"),
                            "mass": 2.0, # Big sun
                            "x": 0, "y": 0, "z": 0,
                            "color": 0xFFD700 # Gold
                        })
                        
                    # 2. Planets (Orbiting Bodies)
                    # Support both V2.1 (objects) and V2.0 (orbiting_bodies) keys
                    bodies = data.get("objects") or data.get("orbiting_bodies", [])
                    import math
                    for i, body in enumerate(bodies):
                        # Simple orbital layout
                        angle = (i / max(len(bodies), 1)) * 2 * math.pi
                        radius = 2.0 + (i * 0.5) 
                        x = radius * math.cos(angle)
                        z = radius * math.sin(angle)
                        
                        # Handle varied object structure (key/value vs label/mass)
                        if "key" in body:
                            label = body.get("key")
                            desc = str(body.get("value", ""))
                        else:
                            label = body.get("label") or body.get("concept", "Unknown")
                            desc = body.get("summary") or str(body)

                        concepts.append({
                            "id": f"p_{i}",
                            "label": label,
                            "mass": body.get("mass", 0.5), 
                            "x": x, "y": 0, "z": z,
                            "description": desc
                        })

                    return jsonify({
                        "concepts": concepts,
                        "attractors": [],
                        "meta": {"mode": "focus", "source": "redis"}
                    })
                else:
                     return jsonify({
                        "concepts": [{"id": "empty", "label": "No Active Subject", "mass": 0.1, "x": 0, "y":0, "z":0}],
                        "attractors": [],
                        "meta": {"mode": "focus", "msg": "Blackboard empty"}
                    })

            except Exception as e:
                logger.error(f"Focus render failed: {e}")
                return jsonify({"error": str(e)}), 500

        # Default System Mode
        state_id = request.args.get("state_id")
        view = request.args.get("view", "concepts") # Original default was "concepts"
        time_window = int(request.args.get("time_window", "10"))

        state = (
            kernel.state_history.get(state_id)
            if state_id
            else kernel.current_state
        )

        if state is None:
            return jsonify({"error": "State not found"}), 404

        # Build visualization based on requested view
        viz_data = {
            "state_id": state.id,
            "timestamp": state.timestamp.isoformat(),
            "view": view,
            "time_window": time_window,
        }

        if view == "concepts":
            viz_data["nodes"] = [
                {
                    "id": node.id,
                    "position": node.position.to_list(),
                    "size": node.mass,
                    "color": f"hsl(0, {int(node.confidence*100)}%, 50%)",
                    "glow": node.energy,
                    "confidence": node.confidence,
                }
                for node in state.nodes.values()
            ]

        elif view == "attractors":
            viz_data["attractors"] = [
                {
                    "id": attr.id,
                    "center": attr.center.to_list(),
                    "radius": attr.radius,
                    "depth": attr.depth,
                    "confidence": attr.confidence,
                    "mode": attr.created_by.value,
                }
                for attr in state.attractors.values()
            ]

        elif view == "energy":
            viz_data["energy_field"] = {
                "total_energy": sum(n.energy for n in state.nodes.values()),
                "nodes_by_energy": [
                    {"id": node.id, "energy": node.energy}
                    for node in sorted(state.nodes.values(), key=lambda n: n.energy, reverse=True)[:5]
                ],
            }

        elif view == "trajectories":
            viz_data["trajectories"] = [
                {
                    "id": node.id,
                    "current": node.position.to_list(),
                    "velocity": node.velocity.to_list(),
                    "speed": node.velocity.magnitude(),
                }
                for node in state.nodes.values()
            ]

        return jsonify(viz_data), 200

    except Exception as e:
        logger.error(f"Render error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/metrics", methods=["GET"])
def metrics():
    """
    GET /geometry/metrics

    Get kernel performance and stability metrics.
    """
    if kernel.current_state is None:
        return jsonify({"error": "No current state"}), 503

    state = kernel.current_state
    total_energy = sum(n.energy for n in state.nodes.values())
    avg_stability = sum(n.stability for n in state.nodes.values()) / len(state.nodes) if state.nodes else 0
    avg_confidence = sum(n.confidence for n in state.nodes.values()) / len(state.nodes) if state.nodes else 0

    return jsonify({
        "timestamp": state.timestamp.isoformat(),
        "kernel_constraints": {
            "v_max": kernel.v_max,
            "curvature_cap": kernel.curvature_cap,
            "inertia_friction": kernel.inertia_friction,
        },
        "system_metrics": {
            "total_energy": total_energy,
            "avg_stability": avg_stability,
            "avg_confidence": avg_confidence,
            "num_concepts": len(state.nodes),
            "num_attractors": len(state.attractors),
        },
        "health_metrics": state.health_metrics,
    }), 200


# ============================================================================
# Startup
# ============================================================================

@app.before_request
def startup():
    """Initialize on first request."""
    global kernel
    if kernel is None:
        init_kernel()


if __name__ == "__main__":
    init_kernel()
    port = int(os.environ.get("PORT", 8087))
    app.run(host="0.0.0.0", port=port, debug=False)
