def get_bg3_coherence(self, external_id: str, bg3_target: float = 0.0) -> float:
    """Measures how well a mirrored entity resonates with the BG3 center."""
    if external_id not in self.field.monads:
        return 0.0
    mirror = self.field.monads[external_id]
    # Calculate phase resonance (Kuramoto-style) using numpy
    deviation = np.abs(mirror.phase - bg3_target)
    return np.exp(-deviation).item()