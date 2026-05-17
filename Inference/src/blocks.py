"""VersorMemMambaBlock — single Versor block for the Noumenal Engine backbone.

GPA → MemMamba-3 → NoteBlock → LayerNorm.

Combines geometric attention (spatial reasoning) with linear-time state-space
scanning (temporal sequence processing).

Uses the real `mamba_ssm.Mamba` library where available. If the library is
absent (e.g. local dev, no CUDA), a fallback `_PyMamba` is used so import
succeeds — but the fallback is approximate and is only intended for unit tests.

Originally from `train_script.py:409-446`.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from .attention import GeometricProductAttention
from .note_block import NoteBlock
from .config import CONFIG


# ════════════════════════════════════════════════════════════════════════
# Mamba kernel resolution: Mamba3 → Mamba2 → Mamba1 → _PyMamba fallback
# ════════════════════════════════════════════════════════════════════════
#
# CONFIG flag `mamba_impl` controls version selection:
#   - "auto"  : pick best available, prefer newest (default)
#   - "v1"    : force Mamba1 (use for state_dict compat with pre-Mamba2 ckpts)
#   - "v2"    : force Mamba2 (requires mamba_ssm.modules.mamba2)
# Mamba kernel resolution: Mamba2 → Mamba1 → _PyMamba fallback
# ════════════════════════════════════════════════════════════════════════
#
# CRITICAL: switching Mamba versions BREAKS state_dict compatibility because
# the parameter names and shapes differ:
#   Mamba1: in_proj, conv1d, A_log[d_inner, d_state], D, x_proj, dt_proj, out_proj
#   Mamba2: in_proj, conv1d, A_log[n_heads], D[n_heads], norm, dt_bias, out_proj
#
try:
    # Round 7.4 — probe for Mamba-2. If present, we prefer the SSD kernels
    # for foundation training as they are ~2x faster and support higher
    # rank d_state.
    from mamba_ssm.modules.mamba2 import Mamba2 as Mamba
    _HAS_MAMBA_SSM = True
    MAMBA_VERSION = 2
    _MAMBA_SRC = "mamba_ssm.modules.mamba2"
except ImportError:
    try:
        # Fallback to Mamba-1 (standard selective scan)
        from mamba_ssm import Mamba as MambaCls
        Mamba = MambaCls
        _HAS_MAMBA_SSM = True
        MAMBA_VERSION = 1
        _MAMBA_SRC = "mamba_ssm"
    except ImportError:
        # Final fallback — pure-Python toy for local dev (no CUDA)
        _HAS_MAMBA_SSM = False
        MAMBA_VERSION = 0
        _MAMBA_SRC = "fallback_toy"

        class _PyMamba(nn.Module):
            def __init__(self, d_model, d_state=128, d_conv=4, expand=2, **kwargs):
                super().__init__()
                self.d_inner = d_model * expand
                self.in_proj = nn.Linear(d_model, self.d_inner * 2)
                self.A_log = nn.Parameter(torch.randn(self.d_inner, d_state))
                self.D = nn.Parameter(torch.ones(self.d_inner))
                self.out_proj = nn.Linear(self.d_inner, d_model)

            def forward(self, x):
                # Simplified projection — no scan, just non-linearity
                xz = self.in_proj(x)
                x_in, z = xz.chunk(2, dim=-1)
                y = F.silu(x_in) * F.silu(z)
                return self.out_proj(y)

        Mamba = _PyMamba


class CrossTokenAttention(nn.Module):
    """Tier A: Interleaved MHA for long-range cross-token physics coupling."""
    def __init__(self, d_model, num_heads=4):
        super().__init__()
        self.mha = nn.MultiheadAttention(embed_dim=d_model, num_heads=num_heads, batch_first=True)
        self.norm = nn.LayerNorm(d_model)
        
    def forward(self, x):
        # x shape: [Batch, Time, Dim]
        x_norm = self.norm(x)
        attn_out, _ = self.mha(x_norm, x_norm, x_norm)
        return x + attn_out  # Residual connection


class VersorMemMambaBlock(nn.Module):
    """Single Versor block: GPA → Mamba → NoteBlock → LayerNorm.

    Args:
        d_model: embedding dim.
        n_heads: GPA head count.
        mv_dim: multivector dim (typically 32 for Cl(4,1)).
        layer_idx: index in the stack (drives cross-layer NoteBlock injection).
    """

    def __init__(self, d_model: int, n_heads: int, mv_dim: int, layer_idx: int, total_layers: int = 6):
        super().__init__()
        self.layer_idx = layer_idx
        self.gpa = GeometricProductAttention(d_model, n_heads, mv_dim)

        # ── d_state resolution (CONFIG-controllable) ────────────────────
        # Three modes:
        #   1. CONFIG["mamba_d_state_per_layer"] = [s0,s1,s2,s3,s4,s5] → use list
        #   2. CONFIG["mamba_d_state_hierarchical"] = True → use Tier B scaling
        #   3. (default) use uniform CONFIG["mamba_d_state"]
        #
        # Default is uniform — guarantees state_dict compat with prior phases.
        # Hierarchical or per-layer modes should only be enabled in dedicated
        # architecture-upgrade phases that include structural salvage.
        per_layer = CONFIG.get("mamba_d_state_per_layer")
        if per_layer is not None and len(per_layer) > layer_idx:
            d_state = per_layer[layer_idx]
        elif CONFIG.get("mamba_d_state_hierarchical", False):
            # Tier B: deep layers get more memory; matches multi-scale physics
            if layer_idx < total_layers // 3:
                d_state = 64 if MAMBA_VERSION >= 2 else 128
            elif layer_idx < (2 * total_layers) // 3:
                d_state = 128 if MAMBA_VERSION >= 2 else 256
            else:
                d_state = 256 if MAMBA_VERSION >= 2 else 512
        else:
            d_state = CONFIG.get("mamba_d_state", 256)

        # ── dt_scale resolution (CONFIG-controllable) ───────────────────
        dt_per_layer = CONFIG.get("mamba_dt_scale_per_layer")
        if dt_per_layer is not None and len(dt_per_layer) > layer_idx:
            dt_scale = dt_per_layer[layer_idx]
        elif CONFIG.get("mamba_dt_scale_hierarchical", False):
            if layer_idx < total_layers // 3:
                dt_scale = 0.05
            elif layer_idx < (2 * total_layers) // 3:
                dt_scale = 0.1
            else:
                dt_scale = 0.2
        else:
            dt_scale = CONFIG.get("mamba_dt_scale", 0.1)

        # ── Mamba kernel construction ───────────────────────────────────
        # `d_conv=4` is locked for CUDA kernel stability (was 8 before R7.4
        # hotfix). Each Mamba version takes a different kwarg set:
        #
        # Mamba1 (mamba_ssm.Mamba):
        #   d_model, d_state, d_conv, expand, dt_min, dt_max, dt_init, dt_scale
        # Mamba2 (mamba_ssm.modules.mamba2.Mamba2):
        #   d_model, d_state, d_conv, expand, headdim, ngroups,
        #   D_has_hdim, layer_idx, chunk_size, rmsnorm
        mamba_kwargs = dict(
            d_model=d_model,
            d_state=d_state,
            d_conv=CONFIG.get("mamba_d_conv", 4),
            expand=CONFIG.get("mamba_expand", 2),
        )

        if _HAS_MAMBA_SSM and MAMBA_VERSION == 1:
            for src_key, dst_key in [
                ("mamba_dt_min", "dt_min"),
                ("mamba_dt_max", "dt_max"),
                ("mamba_dt_init", "dt_init"),
                ("mamba_dt_scale", "dt_scale"),
            ]:
                if src_key in CONFIG:
                    mamba_kwargs[dst_key] = CONFIG[src_key]

        elif _HAS_MAMBA_SSM and MAMBA_VERSION == 2:
            mamba_kwargs["layer_idx"] = layer_idx
            # Mamba2-specific: head dim, group count, whether D is per-head or per-channel
            for src_key, dst_key in [
                ("mamba_headdim", "headdim"),
                ("mamba_ngroups", "ngroups"),
                ("mamba_chunk_size", "chunk_size"),
            ]:
                if src_key in CONFIG:
                    mamba_kwargs[dst_key] = CONFIG[src_key]
            # CRITICAL: D_has_hdim=True keeps D as [d_inner] (matches Mamba1),
            # which lets us transfer Mamba1's D weights cleanly via salvage.
            mamba_kwargs["D_has_hdim"] = CONFIG.get("mamba_d_has_hdim", True)

        self.mamba = Mamba(**mamba_kwargs)

        # ── Per-layer dt scale (post-construction, version-aware) ──────
        # NOTE: this is a no-op when state_dict is loaded over the layer.
        # Only matters at fresh-init time. Mamba1 has dt_proj.weight;
        # complex-valued and doesn't have a directly-tunable dt scalar.
        if _HAS_MAMBA_SSM and dt_scale != 1.0:
            try:
                with torch.no_grad():
                    if MAMBA_VERSION == 1 and hasattr(self.mamba, "dt_proj"):
                        if hasattr(self.mamba.dt_proj, "weight"):
                            self.mamba.dt_proj.weight.data.mul_(dt_scale)
                    elif MAMBA_VERSION == 2 and hasattr(self.mamba, "dt_bias"):
                        # Mamba2's dt_bias is the analogous knob
                        self.mamba.dt_bias.data.mul_(dt_scale)
                    # Mamba3: leave alone — no clean equivalent
            except Exception:
                pass  # Fail silently — dt scaling is best-effort cosmetic

        self.note_block = NoteBlock(d_model)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.norm3 = nn.LayerNorm(d_model)

        # ── TIER A: Cross-Token Attention (Interleaved) ────────────────
        # CONFIG-controllable: which layer indices get the MHA injection.
        # Default empty list = no cross-attention (preserves backward compat
        # with C2.1 / C2.2 baselines that didn't have these layers).
        # Set CONFIG["cross_attn_layers"] = [2, 5] to enable.
        cross_attn_layers = set(CONFIG.get("cross_attn_layers", []))
        if layer_idx in cross_attn_layers:
            self.cross_attn = CrossTokenAttention(d_model, num_heads=n_heads)
        else:
            self.cross_attn = None

        self.use_cross_layer = (
            layer_idx % CONFIG["cross_layer_interval"] == 0 and layer_idx > 0
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # 1. Geometric Product Attention (Spatial)
        x = x + self.gpa(self.norm1(x))
        
        # 2. State Space Integration (Time-domain causal)
        x = x + self.mamba(self.norm2(x))
        
        # 3. Cross-Token Coupling (Space-domain global - Tier A)
        if self.cross_attn is not None:
            x = self.cross_attn(x)
            
        # 4. Note Block: score, store, optionally inject
        scores = self.note_block.score_importance(x)
        self.note_block.update_pool(x, scores)
        if self.use_cross_layer:
            x = self.note_block.inject_memory(x)
            
        return self.norm3(x)


def real_mamba_available() -> bool:
    """Probe for the real `mamba_ssm` library — call before launching production training."""
    return _HAS_MAMBA_SSM


def mamba_resolution_report() -> str:
    """Human-readable summary of which Mamba implementation is active.

    Print this at trainer startup so the run logs which version was actually loaded.
    """
    lines = [f"📐 Mamba resolution: requested='{_MAMBA_FORCE}', active=v{MAMBA_VERSION}"]
    lines.extend(f"   {entry}" for entry in _MAMBA_RESOLUTION_LOG)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# HamiltonianExpert / SparseMixtureHamiltonianExperts used to be declared
# here AND in hamiltonian.py. hamiltonian.py is canonical now; we re-export
# below so any code doing `from blocks import HamiltonianExpert` still works.
# ──────────────────────────────────────────────────────────────────────
from .hamiltonian import HamiltonianExpert, SparseMixtureHamiltonianExperts  # noqa: F401
