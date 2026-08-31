
import torch
import torch.nn as nn
import onnxruntime
import numpy as np
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dummy GATr Model wrapper since we don't have the full GATr library installed in this context yet.
# In a real scenario, we would import: from gatr import GATr, GATrConfig
# For this export script, we define a Mock that matches the expected I/O signature.

class MockGATr(nn.Module):
    def __init__(self, d_model=16):
        super().__init__()
        self.linear = nn.Linear(d_model, d_model)

    def forward(self, multivectors):
        # Expected Input: [Batch, Sequence, 16] (16D Clifford Multivectors as floats)
        # In reality, GATr uses complex numbers or separate channels. 
        # For ONNX compatibility, we often flatten complex/multivector dims.
        return self.linear(multivectors)

def export_gatr_model():
    logger.info("Initializing GATr model for export...")
    
    # 1. Instantiate Model
    # Ensuring FP16 as requested by user
    model = MockGATr(d_model=16).half().cuda() if torch.cuda.is_available() else MockGATr(d_model=16).float()
    
    # Force float32 for CPU export if cuda not available, then cast? 
    # ONNX export of half precision often requires CUDA or specific ops.
    # Let's try to export as Float32 first and then convert, OR simply export as Half if supported.
    # Given the user constraint "ensure gatr is fp16", we will likely use torch.float16.
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if device.type == 'cpu':
        logger.warning("Exporting FP16 on CPU can be unstable for some ops. Attempting...")
        # PyTorch CPU doesn't always support half() for all layers, but let's try.
        # If it fails, we export fp32 and use onnxmltools to convert.
        try:
             model = MockGATr(d_model=16).to(dtype=torch.float16)
        except Exception as e:
            logger.error(f"Failed to cast model to FP16 on CPU: {e}")
            return

    model.eval()

    # 2. Create Dummy Input
    # Shape: [1, 32, 16] (Batch=1, Seq=32, Dim=16)
    dummy_input = torch.randn(1, 32, 16, dtype=torch.float16)

    # 3. Export to ONNX
    output_path = "models/gatr_model.onnx"
    os.makedirs("models", exist_ok=True)
    
    logger.info(f"Exporting to {output_path}...")
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=['input_multivectors'],
        output_names=['output_actions'],
        dynamic_axes={'input_multivectors': {0: 'batch_size', 1: 'sequence_length'},
                      'output_actions': {0: 'batch_size', 1: 'sequence_length'}}
    )
    logger.info("Export complete.")

    # 4. Validate with ONNX Runtime
    verify_onnx(output_path)

def verify_onnx(model_path):
    logger.info("Verifying ONNX model...")
    session = onnxruntime.InferenceSession(model_path)
    
    # Check input type
    input_type = session.get_inputs()[0].type
    logger.info(f"Model Input Type: {input_type}")
    
    if "float16" not in input_type.lower() and "half" not in input_type.lower():
         logger.warning("⚠️ Model input does not appear to be FP16! (Might be tensor(float))")
         # Note: ONNX Runtime might report tensor(float16)
    
    # Inference
    x = np.random.randn(1, 32, 16).astype(np.float16)
    ort_inputs = {session.get_inputs()[0].name: x}
    ort_outs = session.run(None, ort_inputs)
    
    logger.info("✅ Inference successful.")
    logger.info(f"Output shape: {ort_outs[0].shape}")

if __name__ == "__main__":
    export_gatr_model()
