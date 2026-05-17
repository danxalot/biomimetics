import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import PhenomenologicalCore
from .concept_monad import ConceptMonad

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Core
# Global singleton instance
core = PhenomenologicalCore()

app = FastAPI(
    title="ARCA Neural System (Phenomenological Core)",
    description="The Living Geometric Intelligence & Physics Engine of ARCA.",
    version="1.0.0",
)

# --- Pydantic Models ---


class SensationInput(BaseModel):
    """External stimulus to be ingested."""

    name: str
    origin: str = "user"
    vector: Optional[list] = None  # List of floats/ints (direct vector)
    hdc_vector: Optional[list] = None  # List of floats (10k-dim HDC vector)


class TickResponse(BaseModel):
    tick: int
    coherence: float
    energy: float
    rotational_energy: Optional[float] = 0.0
    hamiltonian: Optional[float] = 0.0
    hopfield_energy: Optional[float] = 0.0


class StatusResponse(BaseModel):
    status: str
    tick: int
    focus_monads: list
    is_dreaming: bool
    active_contexts: List[str]


class AttentionResponse(BaseModel):
    contexts: List[Dict[str, float]]  # Name -> Score


# --- Endpoints ---


@app.on_event("startup")
async def startup_event():
    logger.info("Neural System Awakening...")
    # Initialize Identity if not already done
    core._initialize_identity()


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "neural_system"}


@app.get("/engine/state")
async def get_engine_state():
    """Expose Mamba hidden state and engine metrics for monitoring."""
    try:
        import numpy as np

        if hasattr(core, 'rotor_predictor') and hasattr(core.rotor_predictor, 'engine'):
            mamba_block = core.rotor_predictor.engine.blocks[0]
            hidden = mamba_block.hidden_state if hasattr(mamba_block, 'hidden_state') and mamba_block.hidden_state is not None else np.zeros(256)
            return {
                "mamba_hidden_l2": float(np.linalg.norm(hidden)),
                "mamba_hidden_mean": float(np.mean(hidden)),
                "mamba_hidden_var": float(np.var(hidden)),
                "engine_ready": core.rotor_predictor.is_ready,
            }
        return {"error": "engine not available"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/tick", response_model=TickResponse)
async def trigger_tick():
    """
    Manually trigger a cognitive cycle (Heartbeat).
    In production, this might be a background task, but explicit ticking
    allows for synchronized time-steps with other agents.
    """
    try:
        result = core.tick()
        return result
    except Exception as e:
        logger.error(f"Tick failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sensation", response_model=Dict[str, str])
async def ingest_sensation(sensation: SensationInput):
    """
    Inject a new concept/sensation into the field.
    Supports direct vector or 10k-dim HDC vector input.
    """
    try:
        import numpy as np
        
        # Convert hdc_vector if provided
        hdc_vec = None
        if sensation.hdc_vector is not None:
            hdc_vec = np.array(sensation.hdc_vector, dtype=np.float32)
        
        monad_id = core.ingest_concept(
            name=sensation.name, 
            vector=sensation.vector, 
            origin=sensation.origin,
            hdc_vector=hdc_vec
        )
        return {"id": monad_id, "status": "ingested"}
    except Exception as e:
        logger.error(f"Sensation ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/resonance")
async def inject_resonance(payload: Dict[str, Any]):
    """Injects 256D Hamiltonians directly into the Mamba hidden state."""
    try:
        import numpy as np

        vec_256 = np.array(payload["vector"], dtype=np.float32)
        if vec_256.shape[0] != 256:
            raise ValueError(f"Expected 256D, got {vec_256.shape[0]}D")

        core.inject_resonance(vec_256)
        l2_norm = float(np.linalg.norm(vec_256))
        return {"status": "resonant", "l2_norm": l2_norm}
    except Exception as e:
        import traceback
        logger.error(f"Resonance injection failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/system/thought")
async def get_system_thought():
    """
    Extract the holistic 'Gestalt Thought' super-vector.
    This aggregates all phase-locked and focused monads into a single normalized vector.
    Used by the LLM to understand the collective state of the system's focus.
    """
    try:
        gestalt_data = core.extract_focus_gestalt()
        return gestalt_data
    except Exception as e:
        logger.error(f"Gestalt extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status", response_model=StatusResponse)
async def get_status():
    return {
        "status": "conscious",
        "tick": core.tick_count,
        "focus_monads": core.focus_monads,
        "is_dreaming": core.is_dreaming,
        "active_contexts": [
            name for name, score in core.poincare.get_active_contexts()
        ],
    }


@app.get("/attention/context", response_model=AttentionResponse)
async def get_attention_context():
    """
    Get the Geometrically Active Contexts (Poincare Focus).
    Used by LangGraph to filter prompt context.
    """
    active = core.poincare.get_active_contexts(threshold=0.01)
    return {"contexts": [{"name": n, "score": s} for n, s in active]}


@app.get("/concept/focus")
async def get_focus_concept():
    """
    Get the active ConceptMonad's hv_signature (10k HDC vector).
    Returns the focus monad's holographic vector for external pipeline consumption.
    """
    try:
        # First try focus monad
        focus_ids = core.focus_monads
        if focus_ids:
            focus_id = focus_ids[0]
            monad = core.field.monads.get(focus_id)
            if monad and hasattr(monad, 'hv_signature') and monad.hv_signature is not None:
                vector = monad.hv_signature
                if hasattr(vector, 'any') and vector.any():
                    if hasattr(vector, 'tolist'):
                        vector = vector.tolist()
                    return {"concept_id": focus_id, "hv_signature": vector, "dimension": len(vector)}
        
        # Check active_contexts from poincare
        active = core.poincare.get_active_contexts(threshold=0.0)
        for name, score in active:
            monad = core.field.monads.get(name)
            if monad and hasattr(monad, 'hv_signature') and monad.hv_signature is not None:
                vector = monad.hv_signature
                if hasattr(vector, 'any') and vector.any():
                    if hasattr(vector, 'tolist'):
                        vector = vector.tolist()
                    return {"concept_id": name, "hv_signature": vector, "dimension": len(vector), "score": score}
        
        # Fallback: find ANY monad with non-empty hv_signature
        for monad_id, monad in core.field.monads.items():
            if hasattr(monad, 'hv_signature') and monad.hv_signature is not None:
                vector = monad.hv_signature
                if hasattr(vector, 'any') and vector.any():
                    if hasattr(vector, 'tolist'):
                        vector = vector.tolist()
                    return {"concept_id": monad_id, "hv_signature": vector, "dimension": len(vector)}
        
        return {"status": "error", "message": "No ConceptMonad with hv_signature found. Send a sensation first."}
    except Exception as e:
        logger.error(f"Failed to get focus concept: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/geometry/poincare")
async def get_poincare_map():
    """Raw coordinates for Geometry Kernel visualization"""
    serialized = {}
    for name, vec in core.poincare.structures.items():
        serialized[name] = vec.tolist()
    return serialized


@app.get("/energy")
async def get_energy_metrics():
    """
    Get current energy metrics for system stability monitoring.

    Priority 1 from integration_roadmap.md:
    Exposes E_total, E_hopfield, E_jepa, E_rot for agent consumption.

    Returns:
        Energy metrics with status classification
    """
    try:
        # Get current TickFrame from pipeline
        from .tickframe_pipeline import get_tickframe_pipeline

        pipeline = get_tickframe_pipeline()

        if pipeline.current_frame is None:
            return {
                "status": "no_data",
                "E_total": 0.0,
                "E_hopfield": 0.0,
                "E_jepa": 0.0,
                "E_rot": 0.0,
                "E_curvature": 0.0,
                "omega_magnitude": 0.0,
                "message": "No TickFrame data available yet",
            }

        frame = pipeline.current_frame
        energy = frame.energy

        # Classify system status based on E_total
        if energy.E_total < 0.3:
            status = "stable"
        elif energy.E_total < 0.7:
            status = "moderate"
        elif energy.E_total < 1.5:
            status = "confused"
        else:
            status = "unstable"

        return {
            "status": status,
            "E_total": energy.E_total,
            "E_hopfield": energy.E_hopfield,
            "E_jepa": energy.E_jepa,
            "E_rot": energy.E_rot,
            "E_curvature": energy.E_curvature,
            "omega_magnitude": frame.omega_magnitude,
            "alpha_magnitude": frame.alpha_magnitude,
            "tick_id": frame.tick_id,
            "timestamp_ms": frame.timestamp_ms,
        }
    except Exception as e:
        logger.error(f"Failed to get energy metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Entrypoint ---


@app.post("/system/snapshot")
async def trigger_manifold_snapshot():
    """
    Trigger a full manifold snapshot capture and upload to GCS.
    Captures HDC memory pools, Mamba hidden states, and Noumenal Engine coordinates.
    """
    try:
        from .app.state_extraction import capture_and_upload_manifold
        success = capture_and_upload_manifold(core)
        if success:
            return {"status": "success", "message": "Manifold snapshot captured and uploaded"}
        else:
            raise HTTPException(status_code=500, detail="Failed to capture/upload manifold snapshot")
    except Exception as e:
        logger.error(f"Manifold snapshot failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/system/vitals")
async def get_vitals():
    """Command Deck vitals endpoint."""
    import numpy as np
    try:
        l2_norm = float(np.linalg.norm(core.rotor_predictor.engine.global_rotor))
        
        try:
            coherence_metrics = core.field.step()
            kuramoto_order = float(coherence_metrics.get("global_coherence", 0.5)) if isinstance(coherence_metrics, dict) else float(coherence_metrics)
            bg3_coherence = float(coherence_metrics.get("bg3_coherence", 0.0)) if isinstance(coherence_metrics, dict) else 0.0
        except Exception as e:
            logger.warning(f"Field step failed: {e}, using fallback coherence")
            kuramoto_order = 0.5
            bg3_coherence = 0.0
        
        blocks = core.rotor_predictor.engine.blocks
        total_energy = 0.0
        for b in blocks:
            # Handle both 'h' and 'hidden_state' for compatibility
            h_state = getattr(b, 'h', getattr(b, 'hidden_state', None))
            if h_state is not None:
                total_energy += float(np.linalg.norm(h_state))
        
        avg_energy = float(total_energy / len(blocks)) if blocks else 0.0

        return {
            "mamba_pulse_l2": round(l2_norm, 4),
            "kuramoto_coherence": round(kuramoto_order, 4),
            "bg3_coherence": round(bg3_coherence, 4),
            "hamiltonian_energy": round(avg_energy, 4),
            "hopfield_capacity": 1868
        }
    except Exception as e:
        logger.error(f"Vitals error: {e}")
        return {"mamba_pulse_l2": 0, "kuramoto_coherence": 0.5, "bg3_coherence": 0, "hamiltonian_energy": 0, "hopfield_capacity": 1868}


@app.get("/debug/engine")
async def debug_engine():
    """Debug endpoint to inspect engine structure."""
    try:
        if not hasattr(core, 'rotor_predictor'):
            return {"error": "no rotor_predictor"}
        engine = core.rotor_predictor.engine
        return {
            "passthrough": getattr(engine, '_passthrough', False),
            "num_blocks": len(getattr(engine, 'blocks', [])),
            "block_0_hidden": str(type(engine.blocks[0])) if engine.blocks else "no blocks",
            "hopfield_patterns": engine.hopfield.num_patterns if hasattr(engine, 'hopfield') else 0,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/system/manifold_3d")
async def get_manifold_3d():
    """Command Deck manifold 3D endpoint - projects Mamba hidden state to 3D."""
    try:
        # Get first block hidden state
        if hasattr(core, 'rotor_predictor') and hasattr(core.rotor_predictor, 'engine'):
            engine = core.rotor_predictor.engine
            if hasattr(engine, 'blocks') and engine.blocks:
                block = engine.blocks[0]
                if hasattr(block, 'hidden_state') and block.hidden_state is not None:
                    hs = block.hidden_state.flatten()
                    # Project 256D to 3D via simple slicing/transform
                    x = float(np.mean(hs[0:85])) - 0.5
                    y = float(np.mean(hs[85:170])) - 0.5
                    z = float(np.mean(hs[170:256])) - 0.5
                    return {"x": x, "y": y, "z": z, "status": "active"}
        return {"x": 0.0, "y": 0.0, "z": 0.0, "status": "no_state"}
    except Exception as e:
        return {"x": 0.0, "y": 0.0, "z": 0.0, "error": str(e)}


def start():
    """Launched by Docker CMD"""
    port = int(os.environ.get("PORT", 8086))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    start()
