"""
OTEL → Geometry Force Mapping

This module closes the body-mind loop by converting observability signals
into cognitive forces that shape the geometry kernel.

The telemetry stack (Loki/Grafana/OTEL) becomes the sensory organs
through which the system feels itself.

Signal classes:
  - Error rate ↑ → epistemic stress → energy ↑
  - Latency ↑ → control degradation → friction ↑
  - Throughput ↓ → bottleneck → mass ↑
  - Retry spikes → instability → curvature penalty
  - Healthy steady state → confidence → attractor reinforcement
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime
import json

from .core import (
    Force,
    ForceSource,
    Vector3D,
    ConceptNode,
)


class SignalType(Enum):
    """Types of OTEL signals."""
    ERROR_RATE = "error_rate"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    RETRY_SPIKES = "retry_spikes"
    HEALTHY_STATE = "healthy_state"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    QUEUE_DEPTH = "queue_depth"


class SignalInterpretation(Enum):
    """What a signal means to the cognitive system."""
    EPISTEMIC_STRESS = "epistemic_stress"  # contradiction, uncertainty
    CONTROL_DEGRADATION = "control_degradation"  # system losing grip
    BOTTLENECK = "bottleneck"  # resource constraint
    INSTABILITY = "instability"  # unexpected behavior
    CONFIDENCE = "confidence"  # things working well


@dataclass
class OTELSignal:
    """
    Raw telemetry from OTEL.

    Typical source: Loki query result, Prometheus metric, trace.
    """
    signal_type: SignalType
    service: str
    metric: str
    value: float
    baseline: float
    timestamp: datetime
    additional_context: Optional[Dict[str, Any]] = None

    def delta_from_baseline(self) -> float:
        """How far from normal."""
        if self.baseline == 0:
            return 1.0 if self.value > 0 else 0.0
        return (self.value - self.baseline) / self.baseline


@dataclass
class ForceMapping:
    """
    Maps a signal to one or more geometry forces.

    One signal → multiple forces (e.g., error rate affects multiple concepts).
    """
    signal: OTELSignal
    forces: List[Force]
    interpretation: SignalInterpretation
    confidence: float  # How sure are we about this mapping


# ============================================================================
# Signal → Force Mapping Table
# ============================================================================

class SignalForceMapping:
    """
    Deterministic, documented mapping of OTEL signals to geometry forces.

    This is the bridge between observability and cognition.
    """

    @staticmethod
    def error_rate_to_forces(signal: OTELSignal) -> List[Force]:
        """
        Error rate ↑ → epistemic stress

        High error rate means the system is unreliable.
        This increases energy (contradiction) on reliability concepts.
        """
        delta = signal.delta_from_baseline()

        # Clamp to reasonable range
        delta = min(delta, 1.0)

        if delta < 0.1:
            # Slightly elevated, ignore
            return []

        # Primary effect: agent reliability
        force_mag = min(delta * 0.5, 1.0)

        forces = [
            Force(
                target_id="concept:agent_reliability",
                vector=Vector3D(0, 0, -1),  # push downward in confidence
                magnitude=force_mag,
                source=ForceSource.OTEL,
                rationale=f"Error rate increased {delta:.1%} above baseline",
            ),
        ]

        # Secondary effect: system coherence (if errors are widespread)
        if delta > 0.3:
            forces.append(
                Force(
                    target_id="concept:system_coherence",
                    vector=Vector3D(0, -0.5, 0),
                    magnitude=force_mag * 0.5,
                    source=ForceSource.OTEL,
                    rationale="High error rate affects system coherence",
                )
            )

        return forces

    @staticmethod
    def latency_to_forces(signal: OTELSignal) -> List[Force]:
        """
        Latency ↑ → control degradation

        High latency means the system is slower to respond.
        Increases friction (slows learning).
        """
        delta = signal.delta_from_baseline()

        if delta < 0.1:
            return []

        # Latency increases system inertia (harder to move)
        force_mag = min(delta * 0.3, 0.8)

        return [
            Force(
                target_id="concept:system_coherence",
                vector=Vector3D(-0.5, 0, 0),  # increase mass-equivalent
                magnitude=force_mag,
                source=ForceSource.OTEL,
                rationale=f"Latency increased {delta:.1%}, slowing learning",
            ),
        ]

    @staticmethod
    def throughput_to_forces(signal: OTELSignal) -> List[Force]:
        """
        Throughput ↓ → bottleneck

        Low throughput indicates resource constraint or queue buildup.
        Increases mass (resistance to change) locally.
        """
        delta = signal.delta_from_baseline()

        # Note: for throughput, DOWN is bad
        if delta > -0.1:
            return []

        force_mag = min(abs(delta) * 0.4, 0.7)

        return [
            Force(
                target_id="concept:semantic_coherence",
                vector=Vector3D(0, -0.3, 0),
                magnitude=force_mag,
                source=ForceSource.OTEL,
                rationale=f"Throughput dropped {abs(delta):.1%}, resource constraint",
            ),
        ]

    @staticmethod
    def retry_spikes_to_forces(signal: OTELSignal) -> List[Force]:
        """
        Retry spikes → instability

        Many retries indicate transient failures or oscillation.
        Increases energy (contradiction) and curvature penalty.
        """
        # Retry spikes are absolute counts, not ratios
        spike_count = signal.value
        baseline_retries = signal.baseline

        if spike_count < baseline_retries * 1.5:
            return []

        excess_retries = spike_count - baseline_retries
        force_mag = min(excess_retries * 0.1, 0.9)

        return [
            Force(
                target_id="concept:system_coherence",
                vector=Vector3D(0.5, 0, -0.5),  # contradictory pressure
                magnitude=force_mag,
                source=ForceSource.OTEL,
                rationale=f"Retry spikes: {excess_retries} above baseline",
            ),
        ]

    @staticmethod
    def healthy_state_to_forces(signal: OTELSignal) -> List[Force]:
        """
        Healthy steady state → confidence

        When things are working well, reinforce the current attractor.
        Mild positive pressure on stability concepts.
        """
        # Healthy state is positive signal
        if signal.value < 0.9:  # less than 90% healthy
            return []

        health_score = signal.value  # 0.9-1.0 → 0.0-0.1
        force_mag = (health_score - 0.9) * 10.0  # scale to 0-1

        return [
            Force(
                target_id="concept:system_coherence",
                vector=Vector3D(0.2, 0.2, 0),  # confidence push
                magnitude=force_mag * 0.3,
                source=ForceSource.OTEL,
                rationale="System healthy, reinforcing stable state",
            ),
            Force(
                target_id="concept:agent_reliability",
                vector=Vector3D(0.1, 0.1, 0),
                magnitude=force_mag * 0.2,
                source=ForceSource.OTEL,
                rationale="All agents functioning normally",
            ),
        ]

    @staticmethod
    def cpu_usage_to_forces(signal: OTELSignal) -> List[Force]:
        """
        High CPU usage → slows learning, increases inertia.
        """
        usage = signal.value  # percent (0-100)

        if usage < 60:
            return []  # comfortable range

        if usage > 90:
            # System under resource stress
            return [
                Force(
                    target_id="concept:system_coherence",
                    vector=Vector3D(-0.3, 0, 0),  # increase inertia
                    magnitude=min((usage - 90) * 0.1, 0.5),
                    source=ForceSource.OTEL,
                    rationale=f"High CPU usage {usage}%, slowing changes",
                ),
            ]

        return []

    @staticmethod
    def queue_depth_to_forces(signal: OTELSignal) -> List[Force]:
        """
        Deep queues → system saturated, increase mass globally.
        """
        depth = signal.value
        baseline_depth = signal.baseline

        if depth < baseline_depth * 1.2:
            return []

        excess = (depth - baseline_depth) / max(baseline_depth, 1)
        force_mag = min(excess * 0.3, 0.8)

        return [
            Force(
                target_id="concept:semantic_coherence",
                vector=Vector3D(-0.5, 0, 0),  # increase resistance
                magnitude=force_mag,
                source=ForceSource.OTEL,
                rationale=f"Queue depth {depth}, system saturated",
            ),
        ]


class SignalForceMapper:
    """
    Routes signals to appropriate force mappers.

    Single entry point: signal → forces
    """

    MAPPERS = {
        SignalType.ERROR_RATE: SignalForceMapping.error_rate_to_forces,
        SignalType.LATENCY: SignalForceMapping.latency_to_forces,
        SignalType.THROUGHPUT: SignalForceMapping.throughput_to_forces,
        SignalType.RETRY_SPIKES: SignalForceMapping.retry_spikes_to_forces,
        SignalType.HEALTHY_STATE: SignalForceMapping.healthy_state_to_forces,
        SignalType.CPU_USAGE: SignalForceMapping.cpu_usage_to_forces,
        SignalType.QUEUE_DEPTH: SignalForceMapping.queue_depth_to_forces,
    }

    @staticmethod
    def map_signal(signal: OTELSignal) -> ForceMapping:
        """
        Convert OTEL signal to geometry forces.

        Returns: ForceMapping with forces, interpretation, confidence.
        """
        mapper = SignalForceMapper.MAPPERS.get(signal.signal_type)

        if mapper is None:
            # Unknown signal type, ignore
            return ForceMapping(
                signal=signal,
                forces=[],
                interpretation=SignalInterpretation.EPISTEMIC_STRESS,
                confidence=0.0,
            )

        forces = mapper(signal)

        # Infer interpretation
        interpretation = SignalForceMapper._infer_interpretation(signal.signal_type)
        confidence = SignalForceMapper._confidence_from_signal(signal)

        return ForceMapping(
            signal=signal,
            forces=forces,
            interpretation=interpretation,
            confidence=confidence,
        )

    @staticmethod
    def _infer_interpretation(signal_type: SignalType) -> SignalInterpretation:
        """What does this signal mean conceptually."""
        mapping = {
            SignalType.ERROR_RATE: SignalInterpretation.EPISTEMIC_STRESS,
            SignalType.LATENCY: SignalInterpretation.CONTROL_DEGRADATION,
            SignalType.THROUGHPUT: SignalInterpretation.BOTTLENECK,
            SignalType.RETRY_SPIKES: SignalInterpretation.INSTABILITY,
            SignalType.HEALTHY_STATE: SignalInterpretation.CONFIDENCE,
            SignalType.CPU_USAGE: SignalInterpretation.CONTROL_DEGRADATION,
            SignalType.QUEUE_DEPTH: SignalInterpretation.BOTTLENECK,
        }
        return mapping.get(signal_type, SignalInterpretation.EPISTEMIC_STRESS)

    @staticmethod
    def _confidence_from_signal(signal: OTELSignal) -> float:
        """How confident are we in this signal's implications."""
        # Signals that are clearly out of baseline are more reliable
        delta = abs(signal.delta_from_baseline())

        if delta < 0.05:
            return 0.3  # barely different
        elif delta < 0.2:
            return 0.6  # noticeable
        elif delta < 0.5:
            return 0.8  # significant
        else:
            return 0.95  # clear change


# ============================================================================
# Health-Dependent Learning Throttle
# ============================================================================

class HealthDependentThrottling:
    """
    When system health degrades, automatically restrict learning.

    This is biological: under stress, you're conservative.
    """

    @staticmethod
    def compute_kernel_throttle(
        health_metrics: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Given system health, compute kernel parameter adjustments.

        Returns: {
            'v_max_multiplier': 0.7,  # slow learning
            'dreaming_enabled': False,
            'mass_multiplier': 1.5,  # harder to move
            'learning_throttle': 0.5,  # 50% of normal speed
        }
        """
        stability_index = health_metrics.get("stability_index", 1.0)
        error_rate = health_metrics.get("error_rate", 0.0)
        entropy_level = health_metrics.get("entropy_level", 0.0)

        # Composite health score
        health_score = (
            stability_index * 0.5 +  # stability is primary
            (1.0 - error_rate) * 0.3 +
            (1.0 - entropy_level) * 0.2
        )
        health_score = max(0.0, min(1.0, health_score))

        # Throttling based on health
        if health_score > 0.8:
            # System healthy, full learning
            return {
                "v_max_multiplier": 1.0,
                "dreaming_enabled": True,
                "mass_multiplier": 1.0,
                "learning_throttle": 1.0,
            }

        elif health_score > 0.6:
            # System partially stressed
            return {
                "v_max_multiplier": 0.85,
                "dreaming_enabled": True,
                "mass_multiplier": 1.2,
                "learning_throttle": 0.7,
            }

        elif health_score > 0.4:
            # System significantly stressed
            return {
                "v_max_multiplier": 0.7,
                "dreaming_enabled": False,  # disable speculative
                "mass_multiplier": 1.5,
                "learning_throttle": 0.4,
            }

        else:
            # System in crisis
            return {
                "v_max_multiplier": 0.5,
                "dreaming_enabled": False,
                "mass_multiplier": 2.0,
                "learning_throttle": 0.1,  # barely any change
            }


if __name__ == "__main__":
    from datetime import datetime, timedelta

    print("=" * 80)
    print("OTEL → Geometry Force Mapping System")
    print("=" * 80)

    # Example 1: Error rate spike
    print("\n1. Error Rate Spike:")
    signal1 = OTELSignal(
        signal_type=SignalType.ERROR_RATE,
        service="agent_service",
        metric="errors_per_minute",
        value=1.5,
        baseline=0.5,
        timestamp=datetime.utcnow(),
    )
    mapping1 = SignalForceMapper.map_signal(signal1)
    print(f"   Interpretation: {mapping1.interpretation.value}")
    print(f"   Confidence: {mapping1.confidence:.2f}")
    print(f"   Forces generated: {len(mapping1.forces)}")
    for force in mapping1.forces:
        print(f"     - {force.target_id}: magnitude={force.magnitude:.2f}, reason={force.rationale}")

    # Example 2: Healthy state
    print("\n2. Healthy State:")
    signal2 = OTELSignal(
        signal_type=SignalType.HEALTHY_STATE,
        service="system",
        metric="overall_health",
        value=0.95,
        baseline=0.95,
        timestamp=datetime.utcnow(),
    )
    mapping2 = SignalForceMapper.map_signal(signal2)
    print(f"   Interpretation: {mapping2.interpretation.value}")
    print(f"   Confidence: {mapping2.confidence:.2f}")
    print(f"   Forces generated: {len(mapping2.forces)}")
    for force in mapping2.forces:
        print(f"     - {force.target_id}: magnitude={force.magnitude:.2f}")

    # Example 3: High CPU usage
    print("\n3. High CPU Usage:")
    signal3 = OTELSignal(
        signal_type=SignalType.CPU_USAGE,
        service="agent_service",
        metric="cpu_percent",
        value=92.0,
        baseline=45.0,
        timestamp=datetime.utcnow(),
    )
    mapping3 = SignalForceMapper.map_signal(signal3)
    print(f"   Interpretation: {mapping3.interpretation.value}")
    print(f"   Forces: {len(mapping3.forces)}")

    # Example 4: Health-dependent throttling
    print("\n4. Health-Dependent Throttling Examples:")
    for health_score in [0.95, 0.75, 0.55, 0.35]:
        throttle = HealthDependentThrottling.compute_kernel_throttle({
            "stability_index": health_score,
            "error_rate": 1.0 - health_score,
            "entropy_level": 0.1 * (1.0 - health_score),
        })
        print(f"   Health={health_score:.2f}: v_max_mult={throttle['v_max_multiplier']:.1f}, "
              f"dreaming={throttle['dreaming_enabled']}, "
              f"throttle={throttle['learning_throttle']:.1f}")

    print("\nOTEL→Force Mapping initialized.")
