import dataclasses
import random
import os
import sys

try:
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False
    print("WARNING: onnxruntime not found. Using mock Triad components.")

@dataclasses.dataclass
class GeometricStress:
    value: float
    latent_vector: list

@dataclasses.dataclass
class EnergyScore:
    value: float

class GATr_Wrapper:
    """
    Wrapper for the Geometric Algebra Transformer (GATr).
    Handles 3D/Geometric Logic and E(3) Equivariance.
    """
    def __init__(self, model_path="geometry_kernel/models/GATr_auditor.onnx"):
        self.session = None
        # Adjust path to be absolute or relative to project root
        if not os.path.isabs(model_path):
             base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
             model_path = os.path.join(base_dir, model_path)
        
        # Check for FP16 version first (Optimization + Precision for GATr)
        fp16_path = model_path.replace(".onnx", ".fp16.onnx")
        if HAS_ONNX and os.path.exists(fp16_path):
            try:
                self.session = ort.InferenceSession(fp16_path)
                print(f"GATr loaded from {fp16_path} (FP16)")
            except Exception as e:
                print(f"Failed to load FP16 GATr: {e}")
             
        if self.session is None and HAS_ONNX and os.path.exists(model_path):
            try:
                self.session = ort.InferenceSession(model_path)
                print(f"GATr loaded from {model_path} (FP32)")
            except Exception as e:
                print(f"Failed to load GATr: {e}")
        else:
            if self.session is None and HAS_ONNX:
                 # pass
                 pass

    def calculate_stress(self, vector_map):
        """
        Calculates geometric stress (line crossings, broken dependencies).
        """
        if self.session:
            try:
                # Placeholder for actual tensor preparation
                # This would require transforming vector_map into the specific 
                # (Batch, Multivector) shape GATr expects.
                # Since we don't have the transformation logic here yet:
                pass
            except Exception as e:
                print(f"GATr Inference Error: {e}")
                
        # Mock logic: random stress for now, low to allow progress
        # TODO: Connect to ONNX runtime
        stress_val = random.uniform(0.0, 0.3) 
        return GeometricStress(value=stress_val, latent_vector=[0.1]*128)

class EB_JEPA_Wrapper:
    """
    Wrapper for the Energy-Based Joint Embedding Predictive Architecture.
    Handles 'Conscience' and Energy Minimization.
    """
    def __init__(self, model_path="geometry_kernel/models/EB_JEPA.onnx"):
        self.session = None
        # Adjust path to be absolute or relative to project root
        if not os.path.isabs(model_path):
             base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
             model_path = os.path.join(base_dir, model_path)

        # Check for quantized version first (optimization for ARM64)
        quant_path = model_path.replace(".onnx", ".quant.onnx")
        if HAS_ONNX and os.path.exists(quant_path):
            try:
                self.session = ort.InferenceSession(quant_path)
                print(f"EB-JEPA loaded from {model_path} (Quantized)")
            except Exception as e:
                print(f"Failed to load Quantized EB-JEPA: {e}")

        if self.session is None and HAS_ONNX and os.path.exists(model_path):
            try:
                self.session = ort.InferenceSession(model_path)
                print(f"EB-JEPA loaded from {model_path}")
            except Exception as e:
                print(f"Failed to load EB-JEPA: {e}")
        else:
            if self.session is None and HAS_ONNX:
                 pass

    def predict_energy(self, state, action):
        """
        Predicts if a change increases system entropy.
        """
        if self.session:
            try:
                # Placeholder for actual inference
                pass
            except Exception as e:
                print(f"EB-JEPA Inference Error: {e}")

        # Mock logic: random energy
        # TODO: Connect to ONNX runtime
        energy_val = random.uniform(0.0, 0.4)
        return EnergyScore(value=energy_val)
