"""Int8 fake-quantization with ARM NEON saturation semantics.

Used during T4 training as QAT to harden weights for FP32-on-Ampere-A1 inference.
Runtime (Pythia on OCI) does NOT quantize — this module is training-only.

Originally from `train_script.py:229-279`. The step-aware wrapper (with `step` and
`qat_scale` args) supersedes the global-step variant from older revisions.
"""
import torch
from .config import CONFIG


class Int8SaturationFakeQuantize(torch.autograd.Function):
    """Fake int8 quant with vqadd/vqsub saturation clamping (-128, +127).

    Saturation prevents catastrophic overflow that would flip Self vectors
    to Non-Self in the geometric manifold. Backward is a Straight-Through
    Estimator — gradients pass unchanged.
    """
    @staticmethod
    def forward(ctx, x):
        x_f32 = x.float()
        max_val = x_f32.abs().max()
        scale = max_val / 127.0 if max_val > 0 else torch.tensor(
            1.0, device=x.device, dtype=torch.float32
        )
        # CRITICAL: keep scale above the FP16 subnormal floor (~5.96e-8).
        scale = torch.clamp(scale, min=1e-7)
        x_scaled = (x_f32 / scale).round()
        x_clamped = torch.clamp(x_scaled, min=-128.0, max=127.0)
        ctx.save_for_backward(x)
        ctx.scale = scale
        return (x_clamped * scale).to(x.dtype)

    @staticmethod
    def backward(ctx, grad_output):
        return grad_output


def fake_quant_int8(x: torch.Tensor, step: int, qat_scale: float = 1.0) -> torch.Tensor:
    """QAT-warmup-aware fake quantizer.

    The quantization intensity α ramps linearly from 0→1 over `qat_warmup_steps`,
    then is gated by the external `qat_scale`. After warmup, α = qat_scale = 1.0.

    Args:
        x: tensor to quantize.
        step: global training step (must be passed in; no module-level state).
        qat_scale: external gate (e.g. for emergency unfreezing). 0 = bypass quant.
    """
    if not CONFIG["qat_enabled"]:
        return x
    warmup = CONFIG["qat_warmup_steps"]
    if step < warmup:
        alpha = (step / max(warmup, 1)) * qat_scale
    else:
        alpha = qat_scale
    quantized = Int8SaturationFakeQuantize.apply(x)
    return (1.0 - alpha) * x + alpha * quantized
