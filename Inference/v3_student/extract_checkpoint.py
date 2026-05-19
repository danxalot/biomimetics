"""
extract_checkpoint.py — no-torch extractor for the nested C2.5 checkpoint.

The 45k checkpoint stores TWO separate models plus optimizer state:

    C2.5_..._step_45000.pt
    ├── model_state        (379 keys)  → the TEACHER  (Akasha SMoE-HE Mamba-2)
    ├── v3_student_state   (384 keys)  → the V3 STUDENT (pure Mamba-3 backbone)
    ├── optimizer
    └── step

The existing convert_pth_to_npz.py does NOT descend into this split — it treats
the top-level dict as a flat state_dict, which yields a garbage npz on a nested
checkpoint. This script extracts each sub-model into its own npz:

    teacher_45k.npz    ← model_state       (has smoe_he.*, rotor_head, phase_head, hopfield)
    student_45k.npz    ← v3_student_state  (pure 32-layer Mamba-3, should == deployed npz)

Pure Python stdlib (zipfile + pickle) with mocked torch types. No torch needed.

Usage:
    python3 extract_checkpoint.py [checkpoint.pt] [out_dir]
"""

from __future__ import annotations

import os
import sys
import zipfile
import pickle
from types import ModuleType

import numpy as np

# ── Mock torch serialization types so pickle can resolve them ────────────────
_torch = ModuleType("torch")
sys.modules["torch"] = _torch
for _cls in (
    "FloatStorage", "DoubleStorage", "HalfStorage", "BFloat16Storage",
    "LongStorage", "IntStorage", "ShortStorage", "CharStorage",
    "ByteStorage", "BoolStorage",
):
    setattr(_torch, _cls, type(_cls, (object,), {}))

_DTYPE = {
    "FloatStorage": np.float32, "DoubleStorage": np.float64,
    "HalfStorage": np.float16, "BFloat16Storage": np.uint16,   # bf16 → uint16, expand later
    "LongStorage": np.int64, "IntStorage": np.int32,
    "ShortStorage": np.int16, "CharStorage": np.int8,
    "ByteStorage": np.uint8, "BoolStorage": np.bool_,
}

_utils = ModuleType("torch._utils")
sys.modules["torch._utils"] = _utils


def _bf16_to_f32(u16: np.ndarray) -> np.ndarray:
    """bfloat16 stored as uint16 → float32 (bf16 is just the top 16 bits of f32)."""
    u32 = u16.astype(np.uint32) << 16
    return u32.view(np.float32)


def _rebuild_tensor_v2(storage, storage_offset, size, stride, requires_grad, backward_hooks, *extra):
    arr = storage
    if arr.dtype == np.uint16:           # bfloat16
        arr = _bf16_to_f32(arr)
    if not size:                          # 0-d scalar
        return arr.reshape(())[()] if arr.size else np.float32(0.0)
    n = int(np.prod(size))
    flat = arr[storage_offset:storage_offset + n]
    try:
        return np.ascontiguousarray(flat.reshape(size))
    except Exception:
        sb = [s * arr.itemsize for s in stride]
        return np.ascontiguousarray(
            np.lib.stride_tricks.as_strided(arr[storage_offset:], shape=size, strides=sb)
        )


def _rebuild_parameter(data, requires_grad, backward_hooks):
    return data


_utils._rebuild_tensor_v2 = _rebuild_tensor_v2
_utils._rebuild_tensor = _rebuild_tensor_v2
_utils._rebuild_parameter = _rebuild_parameter


class _CkptUnpickler(pickle.Unpickler):
    def __init__(self, fh, zf, prefix):
        super().__init__(fh)
        self._zf = zf
        self._prefix = prefix

    def find_class(self, module, name):
        if name in ("_rebuild_tensor_v2", "_rebuild_tensor"):
            return _rebuild_tensor_v2
        if name == "_rebuild_parameter":
            return _rebuild_parameter
        try:
            return super().find_class(module, name)
        except Exception:
            return lambda *a, **k: None

    def persistent_load(self, pid):
        if isinstance(pid, tuple) and pid[0] == "storage":
            cls, key, location, numel = pid[1:]
            cls_name = getattr(cls, "__name__", str(cls)).split(".")[-1].strip("'>")
            dtype = _DTYPE.get(cls_name, np.float32)
            raw = self._zf.read(f"{self._prefix}data/{key}")
            return np.frombuffer(raw, dtype=dtype)
        return None


def load_checkpoint(pt_path: str) -> dict:
    with zipfile.ZipFile(pt_path, "r") as zf:
        prefix = ""
        for n in zf.namelist():
            if n.endswith("data.pkl"):
                prefix = n[: -len("data.pkl")]
                break
        if not prefix:
            raise RuntimeError("data.pkl not found in archive")
        with zf.open(f"{prefix}data.pkl") as fh:
            return _CkptUnpickler(fh, zf, prefix).load()


def _save_split(sub: dict, out_path: str, label: str) -> None:
    clean = {}
    for k, v in sub.items():
        if isinstance(v, np.ndarray):
            clean[k] = np.ascontiguousarray(v)
        elif np.isscalar(v):
            clean[k] = np.asarray(v, dtype=np.float32)
        else:
            print(f"  ! skipped non-array key {label}.{k} ({type(v).__name__})")
    np.savez(out_path, **clean)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"  saved {label}: {len(clean)} keys → {out_path}  ({size_mb:.1f} MB)")


def main() -> None:
    pt_path = sys.argv[1] if len(sys.argv) > 1 else (
        "/Users/danexall/biomimetics/pythia/Gold_Standard_Archive/checkpoints/"
        "C2.5_Akasha_Experts_&_Mamba_Checkpoints_permanent_step_45000.pt"
    )
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "/Users/danexall/biomimetics/Inference/models"
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isfile(pt_path):
        print(f"ERROR: checkpoint not found: {pt_path}")
        sys.exit(1)

    print(f"Loading {pt_path} ...")
    obj = load_checkpoint(pt_path)

    if not isinstance(obj, dict):
        print(f"ERROR: top-level object is {type(obj).__name__}, expected dict")
        sys.exit(1)

    print(f"Top-level keys: {list(obj.keys())}")
    step = obj.get("step", "unknown")
    print(f"Checkpoint step: {step}")

    # Map known sub-model keys → output filenames.
    splits = {
        "model_state": "teacher_45k.npz",       # the Akasha teacher (has experts/heads)
        "v3_student_state": "student_45k.npz",  # the V3 Mamba-3 backbone
    }
    found = False
    for split_key, out_name in splits.items():
        if split_key in obj and isinstance(obj[split_key], dict):
            found = True
            _save_split(obj[split_key], os.path.join(out_dir, out_name), split_key)

    if not found:
        # Fallback: maybe it's already a flat state dict.
        tensor_keys = [k for k, v in obj.items() if isinstance(v, np.ndarray)]
        if tensor_keys:
            print("No model_state/v3_student_state split — treating as flat state dict.")
            _save_split({k: obj[k] for k in tensor_keys},
                        os.path.join(out_dir, "flat_state.npz"), "flat")
        else:
            print("ERROR: no recognisable model state found.")
            sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
