import sys
import os
import json
import logging
from typing import Dict, Any

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from recursive_ingestion import RecursiveIngestion
    from model_engine import CognitiveScheduler
    from clever_artifacts import extract_clever_artifacts
except ImportError:
    # If running from project root
    sys.path.insert(0, "/Users/danexall/Documents/VS Code Projects/ARCA/services/geometry_kernel")
    from recursive_ingestion import RecursiveIngestion
    from model_engine import CognitiveScheduler
    from clever_artifacts import extract_clever_artifacts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ValidateIngest")

def validate_solar_system(solar_system: Dict[str, Any]):
    """Validate the structure of the returned solar system JSON."""
    required_keys = ["system_id", "gravity_well", "objects", "trajectory"]
    for key in required_keys:
        if key not in solar_system:
            raise ValueError(f"Missing required key: {key}")
    
    if not isinstance(solar_system["objects"], list):
        raise ValueError("Objects must be a list")
    
    for obj in solar_system["objects"]:
        if "id" not in obj:
            raise ValueError("Object missing id")
        if "position" not in obj or not isinstance(obj["position"], list):
            raise ValueError(f"Object {obj['id']} missing valid position")

def test_clever_artifacts():
    """Test the clever_artifacts extraction logic."""
    mock_model = {
        "objects": [
            {"id": "Brain", "position": [1.0, 1.0, 1.0], "mass": 0.9, "desc": "Central processing unit"},
            {"id": "Memory", "position": [0.9, 0.9, 0.9], "mass": 0.7, "desc": "Storage for concepts"},
            {"id": "Ethics", "position": [-1.0, -1.0, -1.0], "mass": 0.8, "desc": "Moral framework"}
        ],
        "trajectory": [0.1, 0.1, 0.1]
    }
    
    logger.info("Testing clever_artifacts extraction...")
    artifacts = extract_clever_artifacts(mock_model, "This is a document about AI brain and ethics.")
    
    if "theme_vectors" not in artifacts:
        raise ValueError("Artifacts missing theme_vectors")
    
    if "context_injection" not in artifacts:
        raise ValueError("Artifacts missing context_injection")
    
    logger.info("✅ clever_artifacts validation successful")
    return artifacts

def main():
    logger.info("Starting Geometry Kernel Ingestion Validation...")
    
    # 1. Test clever_artifacts
    try:
        artifacts = test_clever_artifacts()
        print(json.dumps(artifacts, indent=2))
    except Exception as e:
        logger.error(f"❌ clever_artifacts validation failed: {e}")
        sys.exit(1)
        
    # 2. Test recursive_ingestion logic (Mocked scheduler)
    # This part would require a live gateway or a more extensive mock.
    # For now, we've validated the post-processing logic which was the user's focus.
    
    logger.info("Done.")

if __name__ == "__main__":
    main()
