import logging
import sys
import os
import io
import json
import torch
import numpy as np
from PIL import Image, ImageDraw
import torchvision.transforms as transforms
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

# Setup logging
logger = logging.getLogger(__name__)

# Add Safe-Net repo to path
SAFE_NET_PATH = os.path.join(os.path.dirname(__file__), '../safe_net_repo')
sys.path.append(SAFE_NET_PATH)

# Import Safe-Net model (try-except block to handle build time import checks)
try:
    from models.create_model import Safe_Net
except ImportError:
    logger.warning("Could not import Safe_Net. Ensure 'safe_net_repo' is cloned and dependencies are installed.")
    Safe_Net = None

class GeometryVAETool:
    """
    Implements the 'Manifold Engine' using the STRM (VAE-Transformer) model from Safe-Net.
    Converts system logs/state into a visual heatmap and encodes it into a 3D latent vector.
    """

    def __init__(self):
        self.device = torch.device("cpu") # User requested CPU for VAE
        self.model = None
        self.transform = transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
        
        # Load Model lazy
        self._load_model()

    def _load_model(self):
        try:
            from diffusers import AutoencoderKL
            
            vae_path = "/app/models/vae"
            if not os.path.exists(vae_path):
                 # Fallback for local dev
                 if os.path.exists("services/mcp_server/models/vae"):
                     vae_path = "services/mcp_server/models/vae"
                 else:
                     raise FileNotFoundError("REPA-E VAE model not found at services/mcp_server/models/vae")

            self.model = AutoencoderKL.from_pretrained(vae_path)
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"REPA-E VAE Model loaded successfully from {vae_path}.")
            
        except ImportError:
            logger.error("diffusers library not installed. Cannot load REPA-E VAE.")
            self.model = None
        except Exception as e:
            logger.error(f"Failed to load REPA-E VAE model: {e}")
            self.model = None

    def generate_geometry_vae(self, system_state: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generates a 3D latent vector from system state logs.
        
        Args:
            system_state: List of log entries or metric dicts (e.g. [{"service": "redis", "error_rate": 0.1}, ...])
        """
        if self.model is None:
            return {"error": "Model not initialized"}

        try:
            # 1. Visualization (Manifold Projection)
            # Create a heatmap image from data
            img = self._visualize_state(system_state)
            
            # 2. Preprocess
            input_tensor = self.transform(img).unsqueeze(0).to(self.device)
            
            # 3. Inference (Encode)
            # 3. Inference (Encode)
            with torch.no_grad():
                # Encode the image to latent space
                # VAE outputs a posterior distribution (DiagonalGaussianDistribution)
                posterior = self.model.encode(input_tensor).latent_dist
                
                # Sample a latent vector (or use mode for deterministic output)
                latent = posterior.sample() # Shape: [1, 4, 32, 32] for 256x256 img
                
                # Flatten to vector
                latent_vector = latent.view(-1).tolist()
                
                # Generate simple 3D coords from latent stats for "Manifold" visualization
                # Just using mean of channels for this demo
                z_mean = torch.mean(latent, dim=[2, 3]).squeeze() # [4]
                manifold_coords = z_mean[:3].tolist() # x, y, z

            return {
                "latent_vector": latent_vector[:10], # Return short preview
                "manifold_coords": manifold_coords,
                "status": "success"
            }

        except Exception as e:
            logger.error(f"VAE Encoding failed: {e}")
            return {"error": str(e)}

    def _visualize_state(self, system_state: List[Dict[str, Any]]) -> Image.Image:
        """
        Converts textual/numerical state to a 256x256 RGB heatmap.
        """
        img = Image.new('RGB', (256, 256), color='black')
        draw = ImageDraw.Draw(img)
        
        # Simple algorithm: Hash service names to (x,y) positions, mapped metric values to color intensity
        # This creates a deterministic "constellation" of system state.
        
        for i, item in enumerate(system_state):
            name = item.get("service", f"item_{i}")
            value = float(item.get("value", item.get("error_rate", 0.5)))
            
            # Hash to position
            h = hash(name)
            x = (h % 200) + 28
            y = ((h >> 8) % 200) + 28
            
            # Color based on value (Red = bad/high, Green = good/low)
            intensity = int(min(value * 255, 255))
            color = (intensity, 255 - intensity, 100)
            
            # Draw point/blob
            radius = 5 + int(value * 10)
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
            
        return img
