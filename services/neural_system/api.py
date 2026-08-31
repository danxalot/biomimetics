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
    gate_entropy: Optional[float] = 0.0
    expert_load: Optional[List[float]] = []


class StatusResponse(BaseModel):
    status: str
    tick: int
    focus_monads: list
    is_dreaming: bool
    active_contexts: List[str]


class AttentionResponse(BaseModel):
    contexts: List[Dict[str, float]]  # Name -> Score

class KinematicSimulationInput(BaseModel):
    base_tensor: List[Any]  # Multi-dimensional list
    domain_name: str = "relativity"
    mutations: List[Dict[str, Any]]

class LatentRolloutInput(BaseModel):
    base_tensor: List[Any]  # Multi-dimensional list
    domain_name: str = "relativity"
    steps: int = 32

class SystemConfigInput(BaseModel):
    bg3_coupling: Optional[float] = None
    bg3_target: Optional[float] = None
    decay_hypo: Optional[float] = None
    decay_hyper: Optional[float] = None
    decay_base: Optional[float] = None
    thermal_clamp_max: Optional[float] = None
    energy_gain: Optional[float] = None

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
            engine = core.rotor_predictor.engine
            hidden = np.zeros(256)
            if hasattr(engine, 'layers') and len(engine.layers) > 0:
                layer = engine.layers[0]
                if isinstance(layer, dict) and 'mamba' in layer:
                    mamba = layer['mamba']
                    if hasattr(mamba, 'h_state') and mamba.h_state is not None:
                        hidden = mamba.h_state
            elif hasattr(engine, 'blocks') and len(engine.blocks) > 0:
                mamba_block = engine.blocks[0]
                if hasattr(mamba_block, 'hidden_state') and mamba_block.hidden_state is not None:
                    hidden = mamba_block.hidden_state

            return {
                "mamba_hidden_l2": float(np.linalg.norm(hidden)),
                "mamba_hidden_mean": float(np.mean(hidden)),
                "mamba_hidden_var": float(np.var(hidden)),
                "engine_ready": core.rotor_predictor.is_ready,
            }
        return {"error": "engine not available"}
    except Exception as e:
        return {"error": str(e)}


class TickInput(BaseModel):
    """Optional parameters for a cognitive tick."""
    stride_scale: int = 1


@app.post("/tick", response_model=TickResponse)
async def trigger_tick(payload: Optional[TickInput] = None):
    """
    Manually trigger a cognitive cycle (Heartbeat).
    Supports Multi-Scale Rollout via stride_scale.
    """
    stride_scale = payload.stride_scale if payload else 1
    try:
        result = core.tick(stride_scale=stride_scale)
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


@app.post("/dream/kinematic")
async def run_kinematic_dream(payload: KinematicSimulationInput):
    """
    Mode A (Kinematic Mutation): Mutate raw features, single forward pass per
    hypothesis. Cheap, safe, answers "what if momentum flipped?".
    """
    try:
        import numpy as np
        base_tensor = np.array(payload.base_tensor, dtype=np.float32)
        # Ensure active_manifold (PhenomenologicalCore) is passed correctly
        result = core.dream_lab.run_kinematic_simulation(
            base_tensor=base_tensor,
            active_manifold=core,
            domain_name=payload.domain_name,
            mutations=payload.mutations
        )
        
        # Convert NumPy arrays to lists for JSON serialization
        if "predicted_mv" in result and isinstance(result["predicted_mv"], np.ndarray):
            result["predicted_mv"] = result["predicted_mv"].tolist()
        if "hamiltonian" in result and isinstance(result["hamiltonian"], np.ndarray):
            result["hamiltonian"] = result["hamiltonian"].tolist()

        return result
    except Exception as e:
        import traceback
        logger.error(f"Kinematic Dream failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/dream/latent")
async def run_latent_dream(payload: LatentRolloutInput):
    """
    Mode B (Latent Rollout): After initial bridge pass, evolve in latent space
    using the SMoE-HE Hamiltonian integrator directly.
    """
    try:
        import numpy as np
        base_tensor = np.array(payload.base_tensor, dtype=np.float32)
        result = core.dream_lab.run_latent_rollout(
            base_tensor=base_tensor,
            active_manifold=core,
            domain_name=payload.domain_name,
            steps=payload.steps
        )
        
        # Convert NumPy arrays to lists
        if "trajectory_h" in result and isinstance(result["trajectory_h"], np.ndarray):
            result["trajectory_h"] = result["trajectory_h"].tolist()
        if "final_q" in result and isinstance(result["final_q"], np.ndarray):
            result["final_q"] = result["final_q"].tolist()
            
        return result
    except Exception as e:
        import traceback
        logger.error(f"Latent Dream failed: {e}")
        logger.error(traceback.format_exc())
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


def _get_mamba_rope_coherence_and_state(engine):
    """Extracts first layer's hidden state and calculates true RoPE oscillator coherence."""
    if engine is None:
        return 0.5, None, 0.0
        
    first_mamba = None
    if hasattr(engine, 'layers') and engine.layers:
        layer = engine.layers[0]
        first_mamba = layer.get('mamba') if isinstance(layer, dict) else getattr(layer, 'mamba', None)
    elif hasattr(engine, 'blocks') and engine.blocks:
        block = engine.blocks[0]
        first_mamba = block.mamba if hasattr(block, 'mamba') else block
        
    if first_mamba is None:
        return 0.5, None, 0.0
        
    hidden = getattr(first_mamba, 'h_state', getattr(first_mamba, 'h', getattr(first_mamba, 'hidden_state', None)))
    if hidden is None:
        return 0.5, None, 0.0
        
    try:
        # Reshape to (d_inner, d_state)
        # In V3 stack, h_state is (batch_size, nheads, headdim, d_state) or similar
        if hidden.ndim >= 3:
            h_flat = hidden.reshape(-1, hidden.shape[-1])
        else:
            h_flat = hidden
            
        if h_flat.shape[-1] >= 2:
            x1 = h_flat[:, 0::2]
            x2 = h_flat[:, 1::2]
            phases = np.arctan2(x2, x1)
            complex_phases = np.exp(1j * phases)
            mamba_coherence = float(np.abs(np.mean(complex_phases)))
            global_phase = float(np.angle(np.mean(complex_phases)))
            return mamba_coherence, h_flat, global_phase
    except Exception as e:
        logger.warning(f"RoPE coherence calculation failed: {e}")
        
    return 0.5, hidden, 0.0


@app.get("/system/vitals")
async def get_vitals():
    """Command Deck vitals endpoint."""
    import numpy as np
    try:
        engine_ready = hasattr(core, 'rotor_predictor') and core.rotor_predictor.is_ready
        engine = core.rotor_predictor.engine if engine_ready else None

        l2_norm = float(np.linalg.norm(engine.global_rotor)) if (engine_ready and hasattr(engine, 'global_rotor')) else 0.0

        # READ cached coherence metrics — do NOT step the field here. This endpoint is
        # polled by the UI (~800ms) and pythia (1Hz); calling core.field.step() on every
        # GET advanced the Kuramoto physics at the polling cadence (non-idempotent) and
        # caused erratic bg3_coherence. The field is advanced once per heartbeat in tick().
        try:
            coherence_metrics = getattr(core, "last_coherence_metrics", None) or {}
            field_coherence = float(coherence_metrics.get("global_coherence", 0.5))
            bg3_coherence = float(coherence_metrics.get("bg3_coherence", 0.0))
        except Exception as e:
            logger.warning(f"Coherence read failed: {e}, using fallback")
            field_coherence = 0.5
            bg3_coherence = 0.0

        # True Mamba RoPE oscillator coherence
        mamba_coherence, _, _ = _get_mamba_rope_coherence_and_state(engine)

        blocks = engine.layers if (engine_ready and hasattr(engine, 'layers')) else []
        if not blocks and engine_ready and hasattr(engine, 'blocks'):
            blocks = engine.blocks

        total_energy = 0.0
        n_layers_counted = 0
        layer_energies = []  # per-layer mean|h| — the live 32-dim signal driving the manifold viz
        for b in blocks:
            # Handle both 'h', 'h_state', and 'hidden_state' for compatibility
            mamba = b.get('mamba') if isinstance(b, dict) else (getattr(b, 'mamba', b) if hasattr(b, 'mamba') else b)
            h_state = getattr(mamba, 'h_state', getattr(mamba, 'h', getattr(mamba, 'hidden_state', None)))
            if h_state is not None:
                # Metabolic energy = mean |h| per layer, bounded in [0, thermal_clamp_max]
                # because h_state is clipped per-element to ±thermal_clamp_max in absorb_pulse.
                # This is the scale everything is calibrated for — healthy band ~1-4 — and the
                # SAME quantity absorb_pulse's allostatic decay gating and pythia_pulse's loop use.
                # (Full L2 inflates to hundreds; summed-bivector-L2 to ~180 — both break the disk.)
                e_layer = float(np.mean(np.abs(h_state)))
                total_energy += e_layer
                layer_energies.append(round(e_layer, 4))
                n_layers_counted += 1

        # Average across blocks → result stays in [0, thermal_clamp_max]
        hamiltonian_energy = float(total_energy / n_layers_counted) if n_layers_counted else 0.0

        # Per-layer signal for the manifold viz: prefer the live forward-pass activity
        # (genuinely differentiated across depth, refreshed each tick) over the uniform
        # pulse-broadcast h_state. hamiltonian_energy above stays the metabolic (h_state)
        # energy that the allostatic loop is calibrated on — these are deliberately distinct.
        try:
            la = getattr(engine, "layer_activity", None)
            if la is not None and np.any(la):
                layer_energies = [round(float(v), 4) for v in np.asarray(la).ravel()]
        except Exception:
            pass
        
        gate_entropy = 0.0
        expert_load = [0.0, 0.0, 0.0, 0.0]
        if hasattr(core, 'last_engine_result'):
            gate_entropy = core.last_engine_result.get("gate_entropy", 0.0)
            expert_load = core.last_engine_result.get("expert_load", [0.0, 0.0, 0.0, 0.0])

        # [I] BG3 lock fraction: fraction of monads within 0.1 rad of φ target
        bg3_lock_fraction = 0.0
        try:
            if hasattr(core.field, 'compute_bg3_lock_fraction'):
                bg3_lock_fraction = float(core.field.compute_bg3_lock_fraction(tolerance=0.1))
        except Exception:
            pass

        return {
            "mamba_pulse_l2": round(l2_norm, 4),
            "kuramoto_coherence": round(mamba_coherence, 4),
            "bg3_coherence": round(bg3_coherence, 4),
            "bg3_lock_fraction": round(bg3_lock_fraction, 4),
            "hamiltonian_energy": round(hamiltonian_energy, 4),
            "hopfield_capacity": 1868,
            "gate_entropy": round(gate_entropy, 4),
            "expert_load": expert_load,
            "layer_energies": layer_energies,
            "n_layers": n_layers_counted
        }
    except Exception as e:
        logger.error(f"Vitals error: {e}")
        return {"mamba_pulse_l2": 0, "kuramoto_coherence": 0.5, "bg3_coherence": 0, "bg3_lock_fraction": 0.0, "hamiltonian_energy": 0, "hopfield_capacity": 1868, "gate_entropy": 0.0, "expert_load": [], "layer_energies": [], "n_layers": 0}


@app.get("/debug/engine")
async def debug_engine():
    """Debug endpoint to inspect engine structure."""
    try:
        if not hasattr(core, 'rotor_predictor'):
            return {"error": "no rotor_predictor"}
        engine = core.rotor_predictor.engine
        
        num_blocks = 0
        if hasattr(engine, 'layers'):
            num_blocks = len(engine.layers)
        elif hasattr(engine, 'blocks'):
            num_blocks = len(engine.blocks)
            
        return {
            "passthrough": getattr(engine, '_passthrough', False),
            "num_blocks": num_blocks,
            "hopfield_patterns": engine.hopfield.num_patterns if hasattr(engine, 'hopfield') else 0,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/system/manifold_3d")
async def get_manifold_3d():
    """Command Deck manifold 3D endpoint - projects Mamba hidden state to 3D."""
    try:
        if hasattr(core, 'rotor_predictor') and hasattr(core.rotor_predictor, 'engine'):
            engine = core.rotor_predictor.engine
            mamba_coherence, h_flat, global_phase = _get_mamba_rope_coherence_and_state(engine)
            
            if h_flat is not None:
                # 1. Map to 32 dimensions via deterministic projection matrix
                d_inner = h_flat.shape[0]
                # Seed deterministically to ensure coordinate stability across calls
                rng = np.random.RandomState(42)
                P = rng.randn(d_inner, 32).astype(np.float32)
                
                # Mean hidden state across d_state
                mean_hidden = np.mean(h_flat, axis=1)
                projected = mean_hidden @ P
                
                # 2. Conformal Normalization
                scalar_part = projected[0]
                geometric_part = projected[1:]
                geo_norm = np.linalg.norm(geometric_part) + 1e-12
                geometric_part = geometric_part / geo_norm
                mv = np.concatenate([[scalar_part], geometric_part])
                
                # 3. Extract Spatial Bivector components representing rotational planes:
                # e23 (index 10), e31 (negative of index 7, which is e13), e12 (index 6)
                X = float(mv[10])
                Y = float(-mv[7])
                Z = float(mv[6])
                
                # 4. Scale coordinate based on L2 energy to show expansion/contraction
                # The thermal clamp boundary in the visualizer is at R = 5.0.
                l2_norm = float(np.linalg.norm(mean_hidden))
                scale_factor = float(np.clip(l2_norm * 0.8, 0.5, 4.8))
                
                coord_3d = np.array([X, Y, Z])
                raw_norm = np.linalg.norm(coord_3d) + 1e-12
                
                # Respect the dimensional variants: do not flatten the 3D space by projection onto a sphere.
                # Instead, preserve the relative spatial bivector magnitudes (conformal density proportions)
                # and scale the norm dynamically, clamping smoothly near the R = 5.0 boundary with np.tanh.
                max_radius = 4.9
                scaled_norm = raw_norm * (scale_factor / 1.0)
                compressed_norm = max_radius * np.tanh(scaled_norm / max_radius)
                coord_3d = (coord_3d / raw_norm) * compressed_norm
                
                return {
                    "x": float(coord_3d[0]),
                    "y": float(coord_3d[1]),
                    "z": float(coord_3d[2]),
                    "kuramoto_coherence": round(mamba_coherence, 4),
                    "kuramoto_phase": round(global_phase, 4),
                    "status": "active"
                }
        return {"x": 0.0, "y": 0.0, "z": 0.0, "status": "no_state"}
    except Exception as e:
        logger.error(f"Failed to calculate Cl(4,1) projection: {e}")
        return {"x": 0.0, "y": 0.0, "z": 0.0, "error": str(e)}


@app.get("/system/config")
async def get_system_config():
    """Get dynamic engine configuration."""
    try:
        config = {}
        if hasattr(core, 'field'):
            config['bg3_coupling'] = getattr(core.field, 'bg3_coupling', None)
            config['bg3_target'] = getattr(core.field, 'bg3_target', None)
        
        if hasattr(core, 'rotor_predictor') and hasattr(core.rotor_predictor, 'engine'):
            engine = core.rotor_predictor.engine
            config['decay_hypo'] = getattr(engine, 'decay_hypo', None)
            config['decay_hyper'] = getattr(engine, 'decay_hyper', None)
            config['decay_base'] = getattr(engine, 'decay_base', None)
            config['thermal_clamp_max'] = getattr(engine, 'thermal_clamp_max', None)
            config['energy_gain'] = getattr(engine, 'energy_gain', None)

        return config
    except Exception as e:
        return {"error": str(e)}

@app.post("/system/config")
async def update_system_config(payload: SystemConfigInput):
    """Update dynamic engine configuration safely."""
    try:
        import numpy as np
        
        updated = {}
        if hasattr(core, 'field'):
            if payload.bg3_coupling is not None:
                # Clamp to [0, 1]
                val = float(np.clip(payload.bg3_coupling, 0.0, 1.0))
                core.field.bg3_coupling = val
                updated['bg3_coupling'] = val
            if payload.bg3_target is not None:
                core.field.bg3_target = float(payload.bg3_target)
                updated['bg3_target'] = core.field.bg3_target
                
        if hasattr(core, 'rotor_predictor') and hasattr(core.rotor_predictor, 'engine'):
            engine = core.rotor_predictor.engine
            if payload.decay_hypo is not None:
                val = float(np.clip(payload.decay_hypo, 0.50, 0.99))
                engine.decay_hypo = val
                updated['decay_hypo'] = val
            if payload.decay_hyper is not None:
                val = float(np.clip(payload.decay_hyper, 0.50, 0.99))
                engine.decay_hyper = val
                updated['decay_hyper'] = val
            if payload.decay_base is not None:
                val = float(np.clip(payload.decay_base, 0.50, 0.99))
                engine.decay_base = val
                updated['decay_base'] = val
            if payload.thermal_clamp_max is not None:
                val = float(np.clip(payload.thermal_clamp_max, 0.0, 6.0))
                engine.thermal_clamp_max = val
                updated['thermal_clamp_max'] = val
            if payload.energy_gain is not None:
                # Operating-energy multiplier on the injected pulse. 0 = silent, 1 = neutral.
                val = float(np.clip(payload.energy_gain, 0.0, 2.0))
                engine.energy_gain = val
                updated['energy_gain'] = val

        return {"status": "success", "updated": updated}
    except Exception as e:
        logger.error(f"Config update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def start():
    """Launched by Docker CMD"""
    port = int(os.environ.get("PORT", 8086))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    start()
