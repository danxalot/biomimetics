# Inference Topology Map

> [!IMPORTANT]
> This map outlines the services and inference engine components replicated for the Sonnet 4.6 Deployment Phase. All services are anchored in `/Users/danexall/biomimetics/Inference`.

## Inference Engine: Qwen3-VL (Vulkan/Metal)
- **Script**: [run_qwen_vulkan.py](file:///Users/danexall/biomimetics/Inference/run_qwen_vulkan.py)
- **Base Model**: `models/Huihui-Qwen3-VL-2B-Instruct-abliterated-Q8_0.gguf`
- **Vision Projector**: `models/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf`
- **Custom Patch**: `mtmd` alias `qwen3vl_merger` -> `PROJECTOR_TYPE_QWEN25VL`
- **Invariants**: 2048d Latent Bypass verified via Rosetta Stone.

## Service Layer Architecture

### 1. Gateway ([/gateway](file:///Users/danexall/biomimetics/Inference/gateway))
- **Role**: Request routing and model limit management.
- **Entry Point**: `main.py`
- **Status**: Ready for Litellm integration.

### 2. Neural System ([/neural_system](file:///Users/danexall/biomimetics/Inference/neural_system))
- **Role**: Core phenomenological processing and memory maintenance.
- **Key Modules**: 
  - `phenomenological_core.py` (Main Logic)
  - `hdc_infini_memory.py` (High-Dimensional Computing)
  - `liquid_neural_network.py` (Temporal Dynamics)
- **Status**: Verified alignment with NoumenalEngine baseline.

### 3. Pythia Lab ([/pythia_lab](file:///Users/danexall/biomimetics/Inference/pythia_lab))
- **Role**: Visualization and interactive experimentation server.
- **Entry Point**: `server.py`
- **Status**: Active.

## Environment Manifest
| Artifact | Path | Verification |
| :--- | :--- | :--- |
| **Vulkan Build** | `~/biomimetics/llama_cpp_bypass/` | In Progress (Patch Applied) |
| **Archivist Fix** | `~/biomimetics/scripts/archivist/` | Syntax Verified (8192 Cap) |
| **Rosetta Stone** | `~/models/c2_1kinematics30k.npz` | 2048d Invariant Confirmed |
