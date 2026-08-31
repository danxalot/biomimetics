"""
Pythia Database Service

FastAPI service for isolated Pythia databases (Redis + Dragonfly)
and core function loading
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import logging
import time

# Import Pythia modules
from pythia_databases import (
    get_trajectory_db,
    get_dragonfly_db,
    load_b1_training_data,
    clear_pythia_databases,
)
from b1_training_loader import load_and_populate_b1_data
from pythia_core_functions import (
    conformal_lift,
    inverse_conformal_lift,
    bridge_hdc_to_dense,
    bridge_dense_to_hdc,
    store_hopfield_pattern,
    retrieve_hopfield_pattern,
    compute_hopfield_energy,
    initialize_pythia_functions,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Pythia Isolated Database Service",
    description="Manages Redis (trajectories) and Dragonfly (cache) on isolated network",
    version="1.0.0",
)

# Global state
b1_data_loaded = False
functions_initialized = False


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class ClearRequest(BaseModel):
    confirm: bool = False


class ConformalLiftRequest(BaseModel):
    vector_512: List[float]
    params: Optional[Dict[str, Any]] = None


class BridgeRequest(BaseModel):
    vector: List[float]
    direction: str  # "hdc_to_dense" or "dense_to_hdc"


class HopfieldRequest(BaseModel):
    pattern: List[float]
    operation: str  # "store", "retrieve", "energy"


# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "pythia_isolated_databases",
        "b1_data_loaded": b1_data_loaded,
        "functions_initialized": functions_initialized,
    }


@app.get("/status")
async def get_status():
    """Get database and function status"""
    trajectory_db = get_trajectory_db()
    dragonfly_db = get_dragonfly_db()

    # Count trajectories
    trajectory_keys = list(trajectory_db.client.scan_iter("trajectory:*"))
    multivector_keys = list(trajectory_db.client.scan_iter("multivector_seq:*"))
    hopfield_keys = list(trajectory_db.client.scan_iter("hopfield:*"))

    return {
        "databases": {
            "redis_trajectories": f"{len(trajectory_keys)} entries",
            "dragonfly_cache": "active",
            "arca_staging_vault": trajectory_db.vault_path,
        },
        "functions": {
            "conformal_lift": "loaded",
            "cycle_consistent_bridge": "loaded",
            "hopfield_network": "loaded",
        },
        "b1_data": {
            "loaded": b1_data_loaded,
            "trajectories": len(trajectory_keys),
            "multivector_sequences": len(multivector_keys),
            "hopfield_patterns": len(hopfield_keys),
        },
    }


# ============================================================================
# DATABASE MANAGEMENT ENDPOINTS
# ============================================================================


@app.post("/clear")
async def clear_databases(request: ClearRequest):
    """Clear all Pythia databases"""
    if not request.confirm:
        raise HTTPException(
            status_code=400, detail="Must confirm clearing databases. Set confirm=true."
        )

    clear_pythia_databases()
    global b1_data_loaded
    b1_data_loaded = False

    logger.info("Pythia databases cleared")
    return {"status": "cleared", "message": "All Pythia databases cleared"}


@app.post("/load-b1-data")
async def load_b1_endpoint():
    """Load B1 training data and populate databases"""
    global b1_data_loaded

    try:
        b1_data = load_and_populate_b1_data()
        b1_data_loaded = True

        return {
            "status": "loaded",
            "message": "B1 training data loaded successfully",
            "data_summary": {
                "trajectories": len(b1_data.get("trajectories", [])),
                "multivectors": len(b1_data.get("multivectors", [])),
                "hopfield_patterns": len(b1_data.get("hopfield_patterns", [])),
            },
        }
    except Exception as e:
        logger.error(f"Error loading B1 data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/initialize-functions")
async def initialize_functions_endpoint():
    """Initialize Pythia core functions from B1 data"""
    global functions_initialized

    try:
        b1_data = load_b1_training_data()

        if not b1_data:
            raise HTTPException(
                status_code=404, detail="B1 data not found. Run /load-b1-data first."
            )

        functions = initialize_pythia_functions(b1_data)
        functions_initialized = True

        return {
            "status": "initialized",
            "message": "Pythia core functions initialized",
            "functions": {
                "conformal_lift": "loaded",
                "cycle_consistent_bridge": "loaded",
                "hopfield_network": "loaded",
            },
        }
    except Exception as e:
        logger.error(f"Error initializing functions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONFORMAL LIFT ENDPOINTS
# ============================================================================


@app.post("/conformal-lift")
async def conformal_lift_endpoint(request: ConformalLiftRequest):
    """Project 512-dim vector to 32-dim CGA space"""
    try:
        result = conformal_lift(request.vector_512, request.params)
        return {
            "input_dim": len(request.vector_512),
            "output_dim": len(result),
            "multivector_32": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conformal-inverse")
async def conformal_inverse_endpoint(request: ConformalLiftRequest):
    """Project 32-dim multivector back to 512-dim space"""
    try:
        result = inverse_conformal_lift(request.vector_512, request.params)
        return {
            "input_dim": len(request.vector_512),
            "output_dim": len(result),
            "vector_512": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BRIDGE ENDPOINTS
# ============================================================================


@app.post("/bridge")
async def bridge_endpoint(request: BridgeRequest):
    """Convert between HDC and dense vectors"""
    try:
        if request.direction == "hdc_to_dense":
            result = bridge_hdc_to_dense(request.vector)
            return {
                "direction": "hdc_to_dense",
                "input_dim": len(request.vector),
                "output_dim": len(result),
                "dense_vector": result,
            }
        elif request.direction == "dense_to_hdc":
            result = bridge_dense_to_hdc(request.vector)
            return {
                "direction": "dense_to_hdc",
                "input_dim": len(request.vector),
                "output_dim": len(result),
                "hdc_vector": result,
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="direction must be 'hdc_to_dense' or 'dense_to_hdc'",
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HOPFIELD ENDPOINTS
# ============================================================================


@app.post("/hopfield")
async def hopfield_endpoint(request: HopfieldRequest):
    """Store, retrieve, or compute energy of Hopfield patterns"""
    try:
        if request.operation == "store":
            store_hopfield_pattern(request.pattern)
            return {"operation": "store", "status": "success", "pattern_stored": True}

        elif request.operation == "retrieve":
            result = retrieve_hopfield_pattern(request.pattern)
            return {
                "operation": "retrieve",
                "input_pattern": request.pattern[:5],  # Show first 5 dims
                "retrieved_pattern": result[:5],
                "full_pattern": result,
            }

        elif request.operation == "energy":
            energy = compute_hopfield_energy(request.pattern)
            return {"operation": "energy", "pattern_energy": energy}

        else:
            raise HTTPException(
                status_code=400,
                detail="operation must be 'store', 'retrieve', or 'energy'",
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TRAJECTORY ENDPOINTS
# ============================================================================


@app.get("/trajectories")
async def get_trajectories():
    """Get all stored trajectories"""
    db = get_trajectory_db()
    trajectories = db.get_all_trajectories()

    return {
        "count": len(trajectories),
        "trajectory_ids": list(trajectories.keys())[:10],  # Show first 10
        "total_trajectories": len(trajectories),
    }


@app.get("/trajectories/{trajectory_id}")
async def get_trajectory(trajectory_id: str):
    """Get a specific trajectory"""
    db = get_trajectory_db()
    trajectory = db.retrieve_trajectory(trajectory_id)

    if not trajectory:
        raise HTTPException(
            status_code=404, detail=f"Trajectory {trajectory_id} not found"
        )

    return {"id": trajectory_id, "length": len(trajectory), "trajectory": trajectory}


# ============================================================================
# STARTUP EVENT
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize databases and load B1 data on startup"""
    logger.info("🚀 Starting Pythia Isolated Database Service...")

    # Load B1 data
    try:
        b1_data = load_and_populate_b1_data()
        global b1_data_loaded
        b1_data_loaded = True
        logger.info("✓ B1 training data loaded")
    except Exception as e:
        logger.warning(f"⚠ Could not load B1 data: {e}")

    # Initialize functions
    try:
        initialize_pythia_functions(b1_data if b1_data_loaded else {})
        global functions_initialized
        functions_initialized = True
        logger.info("✓ Pythia core functions initialized")
    except Exception as e:
        logger.warning(f"⚠ Could not initialize functions: {e}")

    logger.info("✅ Pythia Database Service ready!")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8097)
