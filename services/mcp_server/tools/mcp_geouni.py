
import os
import sys
import torch
import json
import logging
import base64
import io
import asyncio
from typing import Optional, Dict, Any, List
from mcp.server.fastmcp import FastMCP
from PIL import Image
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_geouni")

# Paths
MODELS_ROOT = "/app/models"
GEOUNI_ROOT = os.path.join(MODELS_ROOT, "geouni")

# Ensure cloned source code is in path
SOURCE_PATH = os.path.join(GEOUNI_ROOT) 
if SOURCE_PATH not in sys.path:
    sys.path.append(SOURCE_PATH)

# Global model cache (Lazy Loading)
_model_cache = {
    "llm": None,
    "tokenizer": None,
    "prompting": None,
    "vq_model": None,
    "device": None
}

def _get_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif torch.backends.mps.is_available():
         # MPS might be available on host, but in Docker likely CPU only unless using specialized setup
         # For safety in mcp_server container, default to CPU or CUDA
        return torch.device("cpu") 
    return torch.device("cpu")

def _load_geouni_models():
    """Lazy load the models."""
    global _model_cache
    if _model_cache["llm"] is not None:
        return _model_cache

    logger.info("loading GeoUni models (Lazy Load)...")
    try:
        from models.prompting_utils import UniversalPrompting # type: ignore
        from models.modeling_geomagvit import GeoMAGVIT # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError as e:
        logger.error(f"Failed to import GeoUni dependencies: {e}")
        raise RuntimeError("GeoUni dependencies missing. Ensure 'peft' and 'einops' are installed and models/geouni is in path.")

    device = _get_device()
    logger.info(f"Using device: {device}")

    # Paths to weights
    llm_path = os.path.join(GEOUNI_ROOT, "GeoUni-Instruct")
    adapter_path = os.path.join(GEOUNI_ROOT, "GeoUni-Reasoning-Adapter")
    vq_path = os.path.join(GEOUNI_ROOT, "Geo-MAGVIT")

    if not os.path.exists(llm_path):
        raise FileNotFoundError(f"Model not found at {llm_path}. Please run download_geouni_models.py")

    # Load LLM
    logger.info("Loading LLM...")
    model = AutoModelForCausalLM.from_pretrained(
        llm_path,
        attn_implementation="sdpa", # specialized attention
        torch_dtype=torch.float32, # CPU friendly
        device_map={"": device},
        trust_remote_code=True,
    ).to(device).eval()

    tokenizer = AutoTokenizer.from_pretrained(llm_path)
    prompting = UniversalPrompting(
        tokenizer,
        max_len=4096,
        special_tokens=(
            "<|soi|>", "<|eoi|>", "<|t2i|>", "<|mmu|>", "<|mix|>",
            "<formalization>", "</formalization>", "<answer>", "</answer>",
        ),
        ignore_id=-100,
    )

    # Load Adapter
    logger.info("Loading Adapter...")
    model = PeftModel.from_pretrained(model, adapter_path).to(device)
    model.eval()

    # Load VQ-VAE
    logger.info("Loading VQ-VAE...")
    vq_model = GeoMAGVIT.from_pretrained(vq_path, low_cpu_mem_usage=False).to(device)
    vq_model.eval().requires_grad_(False)

    _model_cache = {
        "llm": model,
        "tokenizer": tokenizer,
        "prompting": prompting,
        "vq_model": vq_model,
        "device": device
    }
    logger.info("GeoUni models loaded successfully.")
    return _model_cache

def _unload_geouni_models():
    """Clear memory by unloading models."""
    global _model_cache
    if _model_cache["llm"] is not None:
        logger.info("🧹 Unloading GeoUni models to free memory...")
        del _model_cache["llm"]
        del _model_cache["tokenizer"]
        del _model_cache["prompting"]
        del _model_cache["vq_model"]
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif torch.backends.mps.is_available():
            torch.mps.empty_cache()
            
    _model_cache = {
        "llm": None,
        "tokenizer": None,
        "prompting": None,
        "vq_model": None,
        "device": None
    }
    import gc
    gc.collect()
    logger.info("GeoUni models unloaded.")

# --- Helper Functions from simple_infer.py ---

def _find_bounds(image):
    np_image = np.array(image)
    non_white_pixels = np.any(np_image < [250, 250, 250], axis=-1)
    # Handle empty image
    if not np.any(non_white_pixels):
         return 0, image.height, 0, image.width
         
    rows, cols = np.where(non_white_pixels)
    if rows.size == 0 or cols.size == 0:
         return 0, image.height, 0, image.width
         
    min_row, max_row = rows.min(), rows.max()
    min_col, max_col = cols.min(), cols.max()
    return min_row, max_row, min_col, max_col

def _crop(image, buffer: int = 20):
    min_row, max_row, min_col, max_col = _find_bounds(image)
    min_row = max(0, min_row - buffer)
    max_row = min(image.height, max_row + buffer)
    min_col = max(0, min_col - buffer)
    max_col = min(image.width, max_col + buffer)
    return image.crop((min_col, min_row, max_col, max_row))

def _expand2square(pil_img: Image.Image, background_color=(255, 255, 255)):
    width, height = pil_img.size
    if width == height:
        return pil_img
    if width > height:
        result = Image.new(pil_img.mode, (width, width), background_color)
        result.paste(pil_img, (0, (width - height) // 2))
    else:
        result = Image.new(pil_img.mode, (height, height), background_color)
        result.paste(pil_img, ((height - width) // 2, 0))
    return result

def _image_transform(image: Image.Image, resolution: int = 512):
    from torchvision import transforms
    preprocess = transforms.Compose([
        transforms.Resize(resolution, interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.CenterCrop(resolution),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
    ])
    return preprocess(image)

# --- MCP Tools ---

async def geouni_visualize_geometry(prompt: str) -> str:
    """
    Generate a geometry diagram from a text description (Text-to-Diagram).
    
    Args:
        prompt: Description of the geometry figure (e.g., "A triangle ABC with angle A=90").
    """
    try:
        models = _load_geouni_models()
        model = models["llm"]
        prompting = models["prompting"]
        vq_model = models["vq_model"]
        device = models["device"]

        input_ids, attention_masks = prompting(prompt, "t2i_gen")
        input_ids = input_ids.to(device)
        attention_masks = attention_masks.to(device)

        with model.disable_adapter():
            code_ids = model.t2i_generate(
                input_ids=input_ids,
                attention_masks=attention_masks,
                pad_token_id=prompting.text_tokenizer.pad_token_id,
                temperature=1.0,
            )

        # Decode image
        image = vq_model.decode_code(code_ids)
        image = torch.clamp((image + 1.0) / 2.0, 0.0, 1.0) * 255.0
        image = image[0].permute(1, 2, 0).cpu().numpy().astype(np.uint8)
        pil_img = Image.fromarray(image)

        # Convert to base64
        buffered = io.BytesIO()
        pil_img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return f"Generated Diagram (Base64 PNG): data:image/png;base64,{img_str}"

    except Exception as e:
        logger.error(f"GeoUni T2D failed: {e}")
        return f"Error generating diagram: {str(e)}"

async def geouni_solve_problem(image_path: str, question: str) -> str:
    """
    Solve a geometry problem given a diagram image and a question.
    
    Args:
        image_path: Absolute path to the diagram image (inside container).
        question: The geometry question to answer.
    """
    try:
        models = _load_geouni_models()
        model = models["llm"]
        prompting = models["prompting"]
        vq_model = models["vq_model"]
        device = models["device"]

        if not os.path.exists(image_path):
            return f"Error: Image not found at {image_path}"

        img = Image.open(image_path).convert("RGB")
        img = _crop(img)
        img = _expand2square(img)
        img_tensor = _image_transform(img, resolution=512).unsqueeze(0).to(device)
        
        # Get visual tokens
        image_tokens = vq_model.get_code(img_tensor)

        full_prompt = f"Analyze the input geometry image to extract consCDL and imgCDL, then answer the question.\nQuestion: {question}"
        input_ids, _ = prompting([image_tokens, full_prompt], "mmu_gen")
        input_ids = input_ids.to(device)

        with torch.no_grad():
            output_ids = model.generate(
                input_ids=input_ids,
                max_new_tokens=2000,
                temperature=1.0, # Greedy-ish
                pad_token_id=prompting.text_tokenizer.pad_token_id,
                eos_token_id=prompting.text_tokenizer.eos_token_id,
                do_sample=False,
                use_cache=True,
            )
            # Decode response (skip input tokens)
            response = prompting.text_tokenizer.batch_decode(output_ids[:, input_ids.shape[1]:], skip_special_tokens=True)[0]
            
        return response

    except Exception as e:
        logger.error(f"GeoUni MMU failed: {e}")
        return f"Error solving problem: {str(e)}"
    finally:
        # Auto-unload to prevent crashes (Memory Areas policy)
        _unload_geouni_models()
