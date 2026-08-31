
import logging
import sys
import os
import torch
import numpy as np
import torchvision.transforms as transforms
from PIL import Image
from typing import Dict, Any, List, Optional, Tuple

# Setup logging
logger = logging.getLogger(__name__)

# Add TransGeo repo to path
# Add TransGeo repo to path - ensure absolute path
TRANSGEO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'TransGeo2022'))
if TRANSGEO_PATH not in sys.path:
    sys.path.append(TRANSGEO_PATH)
    logger.info(f"Added {TRANSGEO_PATH} to sys.path")

try:
    from model.TransGeo import TransGeo # Import from cloned repo
except ImportError as e:
    TransGeo = None
    logger.error(f"Could not import TransGeo class: {e}")
    # Also print to stderr for immediate visibility in docker logs/exec
    import traceback
    traceback.print_exc()

class MockArgs:
    def __init__(self):
        self.dim = 512 # Default feature dim
        self.dataset = 'vigor' # Align with ARCA's VIGOR usage
        self.sat_res = 320 # Default for VIGOR
        self.fov = 0 # Default
        self.crop = False # Default

class TransGeoTool:
    """
    Implements TransGeo (Transformer Is All You Need for Cross-view Image Geo-localization).
    Role: Spatial Anchoring - Aligns concepts with real-world locations.
    """

    def __init__(self):
        self.device = torch.device("cpu") # CPU inference
        self.model = None
        self.transform = transforms.Compose([
            transforms.Resize((320, 640)), # VIGOR ground size
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        if TransGeo:
            self._load_model()

    def _load_model(self):
        try:
            args = MockArgs()
            self.model = TransGeo(args)
            
            # Load Weights
            # User must provide these from the Google Drive link
            weights_path = "/app/models/transgeo/transgeo_weights.pth"
            # Fallback for local testing outside docker
            local_weights = "models/transgeo/transgeo_weights.pth"
            
            # Check local first for dev
            if os.path.exists(local_weights):
                weights_path = local_weights
            
            if os.path.exists(weights_path):
                 checkpoint = torch.load(weights_path, map_location=self.device)
                 if 'model_state_dict' in checkpoint:
                     self.model.load_state_dict(checkpoint['model_state_dict'], strict=False)
                 else:
                     self.model.load_state_dict(checkpoint, strict=False)
                 logger.info(f"TransGeo model loaded from {weights_path}.")
            else:
                 logger.warning(f"TransGeo weights not found at {weights_path}. Please download from Google Drive link in README.")
            
            self.model.to(self.device)
            self.model.eval()
            
        except Exception as e:
            logger.error(f"Failed to load TransGeo model: {e}")
            self.model = None

    def localization_estimate(self, image_input: str) -> Dict[str, Any]:
        """
        Estimates location features from a query image (Ground View).
        Returns the feature vector which can be matched against a Satellite database.
        
        Args:
            image_input: Path to local image file
        """
        if self.model is None:
            return {"error": "TransGeo model not initialized"}
            
        try:
            if not os.path.exists(image_input):
                return {"error": f"Image not found: {image_input}"}

            img = Image.open(image_input).convert('RGB')
            img_tensor = self.transform(img).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                # TransGeo forward: query_net(im_q) -> features
                # forward(im_q, im_k=None) -> returns query_feat, ref_feat
                # We only have query (ground) image here
                query_feat = self.model.query_net(img_tensor)
                
                # Normalize features
                query_feat = query_feat / query_feat.norm(dim=1, keepdim=True)
                
                return {
                    "status": "success",
                    "feature_vector": query_feat.squeeze().tolist()[:10], # Preview
                    "vector_dim": len(query_feat.squeeze().tolist())
                }

        except Exception as e:
            logger.error(f"TransGeo inference failed: {e}")
            return {"error": str(e)}
