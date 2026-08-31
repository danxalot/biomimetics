"""
OTEL Mapping
Translates low-level system signals (telemetry) into high-level semantic forces.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum
from .core import Force, Vector3D

class SignalType(Enum):
    ERROR_RATE = "error_rate"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    CPU_USAGE = "cpu_usage"
    QUEUE_DEPTH = "queue_depth"
    HEALTH_STATE = "health_state"

@dataclass
class OTELSignal:
    signal_type: SignalType
    service: str
    metric: str
    value: float
    baseline: float
    timestamp: float

class SignalForceMapper:
    """
    Deterministic mapping engine.
    """
    
    @staticmethod
    def map_signal(signal: OTELSignal) -> List[Force]:
        forces = []
        
        # 1. Error Rate -> Impacts 'sys_coherence' and 'error_rate' concepts
        if signal.signal_type == SignalType.ERROR_RATE:
            deviation = signal.value - signal.baseline
            if deviation > 0: # Errors increasing
                # Push 'error_rate' concept DOWN (since High Position = Healthy/Low Error)
                forces.append(Force(
                    source="telemetry_mapper",
                    target_id="error_rate",
                    vector=Vector3D(0.0, 0.0, -1.0), # Push down Z (Stability)
                    type="stress",
                    magnitude=min(5.0, deviation * 2.0)
                ))
                # Push 'sys_coherence' slightly down
                forces.append(Force(
                    source="telemetry_mapper",
                    target_id="sys_coherence",
                    vector=Vector3D(-0.1, -0.1, 0.0),
                    type="stress",
                    magnitude=min(1.0, deviation * 0.5)
                ))

        # 2. Latency -> Impacts 'latency' concept
        elif signal.signal_type == SignalType.LATENCY:
             deviation = signal.value - signal.baseline
             if deviation > 100: # ms limit?
                 forces.append(Force(
                    source="telemetry_mapper",
                    target_id="agent_reliability", # Laggy agents are less reliable
                    vector=Vector3D(0.0, -1.0, 0.0), # Less Evidence
                    type="degradation",
                    magnitude=min(2.0, deviation / 1000.0)
                ))

        # 3. Health State -> Global Throttling Signals (Virtual Forces?)
        # Actually, health state changes the Physics Constants (Invariants), handled by Kernel Config.
        # But we can represent it as a 'stabilizing' field.
        
        return forces

    @staticmethod
    def get_throttle_params(stability_score: float) -> Dict[str, float]:
        """
        Returns physics invariant modifiers based on health.
        stability > 0.8: Full learning
        stability < 0.4: Crisis mode
        """
        if stability_score > 0.8:
            return {"v_max_mult": 1.0, "mass_mult": 1.0, "dreaming": 1.0}
        elif stability_score > 0.6:
            return {"v_max_mult": 0.85, "mass_mult": 1.2, "dreaming": 1.0}
        elif stability_score > 0.4:
            return {"v_max_mult": 0.7, "mass_mult": 1.5, "dreaming": 0.0} # Dreaming disabled
        else: # Crisis
            return {"v_max_mult": 0.5, "mass_mult": 2.0, "dreaming": 0.0}
