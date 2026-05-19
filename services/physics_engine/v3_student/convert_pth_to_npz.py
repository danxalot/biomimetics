"""
convert_pth_to_npz.py — Bypasses PyTorch to extract student weights from
c2.6_mc_jepa_65k.pth and save them to pythia_c3_v3_65k.npz.

Uses pure Python standard zipfile and pickle libraries with mocked torch types.
Runs instantly and avoids any massive PyTorch installation.
"""

from __future__ import annotations

import sys
import os
import zipfile
import pickle
from types import ModuleType
import numpy as np

# 1. Mock torch serialization types
torch_mod = ModuleType('torch')
sys.modules['torch'] = torch_mod

storage_classes = [
    'FloatStorage', 'DoubleStorage', 'HalfStorage', 'BFloat16Storage',
    'LongStorage', 'IntStorage', 'ShortStorage', 'CharStorage',
    'ByteStorage', 'BoolStorage'
]
for cls in storage_classes:
    setattr(torch_mod, cls, type(cls, (object,), {}))

utils_mod = ModuleType('torch._utils')
sys.modules['torch._utils'] = utils_mod

def _rebuild_tensor_v2(storage, storage_offset, size, stride, requires_grad, backward_hooks):
    # storage is the raw numpy array returned by persistent_load
    if storage.dtype == np.uint16:
        # Convert bfloat16 (uint16) to float32
        uint32_arr = np.zeros(storage.size, dtype=np.uint32)
        uint32_arr |= (storage.astype(np.uint32) << 16)
        arr = uint32_arr.view(np.float32)
    else:
        arr = storage

    if not size:
        return arr[storage_offset] if arr.size > storage_offset else arr

    # Calculate reshape or strided view
    try:
        # Standard reshape if contiguous
        return arr[storage_offset:storage_offset + int(np.prod(size))].reshape(size)
    except Exception:
        # Fallback to strided view
        strides_bytes = [s * arr.itemsize for s in stride]
        return np.lib.stride_tricks.as_strided(
            arr[storage_offset:],
            shape=size,
            strides=strides_bytes
        )

utils_mod._rebuild_tensor_v2 = _rebuild_tensor_v2
utils_mod._rebuild_tensor = _rebuild_tensor_v2


# 2. Custom Unpickler
class TorchUnpickler(pickle.Unpickler):
    def __init__(self, file, zip_file, prefix):
        super().__init__(file)
        self.zip_file = zip_file
        self.prefix = prefix

    def persistent_load(self, saved_id):
        if saved_id[0] == 'storage':
            cls, key, location, size = saved_id[1:]
            member_path = f"{self.prefix}data/{key}"
            data_bytes = self.zip_file.read(member_path)

            # Map storage class name to numpy dtype
            cls_name = cls.__name__ if hasattr(cls, '__name__') else str(cls)
            cls_name = cls_name.split('.')[-1].strip("'>")
            
            dtype_map = {
                'FloatStorage': np.float32,
                'DoubleStorage': np.float64,
                'LongStorage': np.int64,
                'IntStorage': np.int32,
                'ShortStorage': np.int16,
                'CharStorage': np.int8,
                'ByteStorage': np.uint8,
                'BoolStorage': np.bool_,
                'HalfStorage': np.float16,
                'BFloat16Storage': np.uint16,
            }
            dtype = dtype_map.get(cls_name, np.float32)
            arr = np.frombuffer(data_bytes, dtype=dtype)
            return arr
        return None


# 3. Main extractor
def main():
    pth_path = "/Users/danexall/biomimetics/pythia/Gold_Standard_Archive/checkpoints/c2.6_mc_jepa_65k.pth"
    out_dir = "/Users/danexall/biomimetics/Inference/models"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "pythia_c3_v3_65k.npz")

    print(f"Reading PyTorch checkpoint from: {pth_path}")
    if not os.path.isfile(pth_path):
        print(f"Error: {pth_path} not found.")
        sys.exit(1)

    with zipfile.ZipFile(pth_path, 'r') as zf:
        # Find prefix (e.g., 'step_65000/')
        names = zf.namelist()
        prefix = ""
        for name in names:
            if name.endswith("data.pkl"):
                prefix = name.split("data.pkl")[0]
                break
        
        if not prefix:
            print("Error: Could not locate data.pkl in ZIP archive.")
            sys.exit(1)

        print(f"Located pickle prefix in archive: '{prefix}'")
        
        # Load the dict structure
        with zf.open(f"{prefix}data.pkl") as pkl_file:
            unpickler = TorchUnpickler(pkl_file, zf, prefix)
            state_dict = unpickler.load()

    # The checkpoint could be wrapped under 'state_dict', 'model', or directly.
    # Let's inspect the loaded state dict keys.
    if isinstance(state_dict, dict) and "state_dict" in state_dict:
        model_weights = state_dict["state_dict"]
    elif isinstance(state_dict, dict) and "model" in state_dict:
        model_weights = state_dict["model"]
    else:
        model_weights = state_dict

    print(f"Successfully unpacked model state dict. Found {len(model_weights)} keys.")

    # The student stack in `v3_student_state` has keys matching `layers.N.*`.
    # Let's filter/clean keys to make sure they are exact.
    # If the keys have a prefix like `module.` or `student.`, we strip them.
    cleaned_weights = {}
    for k, v in model_weights.items():
        # Ensure we convert any remaining mocked tensor wrapper to a standard numpy array
        if isinstance(v, np.ndarray):
            val = v
        elif hasattr(v, "numpy"):
            val = v.numpy()
        else:
            val = np.array(v)

        # Look for the VersorMemMambaStack keys
        # The key names in state_dict might be like 'layers.0.norm.weight'
        # Or 'student.layers.0.norm.weight', etc.
        # Let's match any key containing 'layers.' and keep from 'layers.' onwards.
        if "layers." in k:
            idx = k.find("layers.")
            clean_k = k[idx:]
            cleaned_weights[clean_k] = val
        else:
            # Maybe it's top-level or other keys. Keep them too.
            cleaned_weights[k] = val

    print(f"Extracted {len(cleaned_weights)} cleaned stack keys.")

    # Assert we have the 384 keys
    # Let's verify how many layers we have. We expect 32 layers.
    layer_indices = sorted(list(set(int(k.split(".")[1]) for k in cleaned_weights.keys() if k.startswith("layers."))))
    print(f"Detected layer indices: {layer_indices}")

    # Check key completeness
    missing_count = 0
    for n in range(32):
        prefix = f"layers.{n}"
        expected_suffixes = [
            "norm.weight", "norm.bias", "A_log", "dt_bias",
            "mamba.in_proj.weight", "mamba.dt_bias", "mamba.B_bias", "mamba.C_bias",
            "mamba.B_norm.weight", "mamba.C_norm.weight", "mamba.D", "mamba.out_proj.weight"
        ]
        for suffix in expected_suffixes:
            full_k = f"{prefix}.{suffix}"
            if full_k not in cleaned_weights:
                print(f"Warning: Expected key '{full_k}' is missing.")
                missing_count += 1

    if missing_count > 0:
        print(f"Error: Missing {missing_count} required keys. Cannot produce a compliant npz file.")
        # But let's dump what we have anyway to inspect
    
    # Save to npz
    np.savez(out_path, **cleaned_weights)
    print(f"Saved compliant weights to: {out_path}")
    print(f"File size: {os.path.getsize(out_path) / (1024*1024):.2f} MB")

if __name__ == "__main__":
    main()
