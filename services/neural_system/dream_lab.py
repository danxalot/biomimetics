import copy
import numpy as np
from typing import Dict, List, Any, Optional
from .kuramoto_field import UniversalKuramotoField
from .energy_service import EnergyService

class DreamLaboratory:
    """
    The Simulation Sandbox.
    
    Allows ARCA to:
    1. Clone the current state of a sub-graph (Concept Cluster).
    2. Apply mutations (Hypothetical Relations: "What if I trusted X?").
    3. Run the physics engine forward in time (Simulate outcome).
    4. Measure result (Does Energy drop? Does Coherence rise?).
    
    Used for:
    - Planning (Pre-computation of social dynamics).
    - Creativity (Random mutation of concepts).
    - Self-Reflection (Analyzing past failures).
    """

    def __init__(self):
        pass

    def validate_thermodynamics(self, forward_sequence: List[np.ndarray], engine: Any) -> bool:
        """
        Thermodynamic Guardrail (Time-Reversal Veto).
        
        The model was trained with a Time-reversal contrastive margin loss.
        E(fwd) < E(rev) - 0.2.
        
        If the reverse-time energy calculation does not incur the minimum 0.2 penalty,
         the model has hallucinated a physically impossible state.
        """
        if not forward_sequence:
            return True
            
        # Calculate Forward Energy
        e_fwd_list = []
        for state in forward_sequence:
            # We assume state is the multivector [32,]
            res = engine.predict(state)
            e_fwd_list.append(res.get("hamiltonian", 0.0))
        e_fwd = np.mean(e_fwd_list)
        
        # Calculate Reverse Energy (pass the sequence backward)
        e_rev_list = []
        for state in reversed(forward_sequence):
            # In reverse time, we expect higher energy / entropy violation
            res = engine.predict(state)
            e_rev_list.append(res.get("hamiltonian", 0.0))
        e_rev = np.mean(e_rev_list)
        
        # Veto if entropy-violating (E_fwd should be significantly lower than E_rev)
        margin = e_rev - e_fwd
        is_valid = margin > 0.2
        
        if not is_valid:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Thermodynamic Veto Triggered! Margin: {margin:.4f} < 0.2. Hallucination detected.")
            
        return is_valid

    def run_simulation(self, 
                       base_field: UniversalKuramotoField, 
                       target_ids: List[str], 
                       mutations: List[Dict[str, Any]],
                       steps: int = 100,
                       engine: Optional[Any] = None) -> Dict[str, Any]:
        """
        Run a 'Dream' simulation with Thermodynamic Guardrails.
        """
        # 1. Clone the Sub-Graph
        dream_field = UniversalKuramotoField(dt=base_field.dt)
        
        for mid in target_ids:
            # UniversalKuramotoField stores monads in a dict — no get_monad() method
            original = base_field.monads.get(mid)
            if original:
                clone = copy.deepcopy(original)
                dream_field.add_monad(clone)
                
        # 2. Apply Mutations
        for mut in mutations:
            m_type = mut.get("type")
            if m_type == "coupling":
                src = mut["source"]; tgt = mut["target"]; val = mut["value"]
                if src in dream_field.monads:
                    dream_field.monads[src].couplings[tgt] = val
            elif m_type == "frequency_shift":
                mid = mut["id"]; shift = mut["value"]
                if mid in dream_field.monads:
                    dream_field.monads[mid].frequency += shift

        # 3. Initialize Energy Service
        dream_energy = EnergyService(dream_field)
        initial_energy = dream_energy.compute_total_energy()["total"]
        initial_coherence = dream_field.compute_coherence() if hasattr(dream_field, 'compute_coherence') else dream_field.compute_global_coherence() if hasattr(dream_field, 'compute_global_coherence') else 0.0
        
        # 4. Run Physics (The "Evolution") & Track Sequence for Guardrail
        state_sequence = []
        for _ in range(steps):
            dream_field.step()
            # Capture aggregate state (e.g. mean phase or a representive vector)
            # For simplicity, we capture the phase of the first monad if available
            if target_ids:
                # Access monad via dict — get_monad() does not exist
                m = dream_field.monads.get(target_ids[0])
                if m is not None and hasattr(m, "vector"):
                    state_sequence.append(m.vector)
            
        # 5. Thermodynamic Veto (If engine provided)
        if engine and state_sequence:
            if not self.validate_thermodynamics(state_sequence, engine):
                return {
                    "energy_delta": 0,
                    "coherence_delta": 0,
                    "is_stable": False,
                    "vetoed": True,
                    "message": "Thermodynamic Veto: Entropy violation detected."
                }
            
        # 6. Measure Outcome
        final_energy = dream_energy.compute_total_energy()["total"]
        final_coherence = dream_field.compute_coherence() if hasattr(dream_field, 'compute_coherence') else dream_field.compute_global_coherence() if hasattr(dream_field, 'compute_global_coherence') else 0.0
        
        return {
            "energy_delta": final_energy - initial_energy,
            "coherence_delta": final_coherence - initial_coherence,
            "is_stable": final_coherence > 0.3,
            "vetoed": False,
            "final_state": {mid: m.phase for mid, m in dream_field.monads.items()}
        }

    # ─────────────────────────────────────────────────────────────────────
    # Mode A: Kinematic Mutation — single forward pass per hypothesis (NumPy Port)
    # ─────────────────────────────────────────────────────────────────────
    def run_kinematic_simulation(
        self,
        base_tensor: np.ndarray,
        active_manifold: Any,
        domain_name: str,
        mutations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Mutate raw kinematic features and observe the engine's prediction.
        Ported to pure NumPy.

        Parameters
        ----------
        base_tensor : np.ndarray (B, T, N, 8) or (B, T, 8)
            Raw kinematic state — BEFORE the conformal lift.
        active_manifold : NumpyPythiaManifold or PhenomenologicalCore
            The live system possessing a kinematic bridge and engine.
        domain_name : str
            Domain key for bridge routing.
        mutations : list of dicts
            Each: {"type": "invert_momentum"|"shift_phase"|"perturb_position", "node": int, "value": float (optional)}
        """
        dream_state = np.copy(base_tensor)

        for mut in mutations:
            m_type = mut.get("type")
            node_idx = mut.get("node", 0)
            value = mut.get("value", 0.1)

            if dream_state.ndim == 3:
                # 2D domain (B, T, F)
                if m_type == "invert_momentum":
                    dream_state[:, :, 4:7] *= -1.0
                elif m_type == "shift_phase":
                    dream_state[:, :, 0] += value
                elif m_type == "perturb_position":
                    dream_state[:, :, 1:4] += value * np.random.randn(*dream_state[:, :, 1:4].shape)
            else:
                # 3D domain (B, T, N, 8)
                if m_type == "invert_momentum":
                    dream_state[:, :, node_idx, 4:7] *= -1.0
                elif m_type == "shift_phase":
                    dream_state[:, :, node_idx, 0] += value
                elif m_type == "perturb_position":
                    dream_state[:, :, node_idx, 1:4] += value * np.random.randn(*dream_state[:, :, node_idx, 1:4].shape)

        # Helper to get the kinematic bridge if passed a manifold wrapper
        bridge = getattr(active_manifold, 'kinematic_bridge', None)
        if not bridge and hasattr(active_manifold, 'rotor_predictor'):
            bridge = active_manifold.kinematic_bridge
            active_manifold = active_manifold.rotor_predictor
            
        if bridge is None:
             raise ValueError("KinematicBridge not found on the provided active_manifold.")

        # Lift
        cga_mutated = bridge.physics_to_cga(dream_state, domain=domain_name)
        cga_baseline = bridge.physics_to_cga(base_tensor, domain=domain_name)

        # Predict
        out_mutated = active_manifold.predict(cga_mutated)
        out_baseline = active_manifold.predict(cga_baseline)

        pred_m = out_mutated["predicted_rotor"].flatten()
        pred_b = out_baseline["predicted_rotor"].flatten()
        
        # Cosine div
        norm_m = np.linalg.norm(pred_m)
        norm_b = np.linalg.norm(pred_b)
        if norm_m > 0 and norm_b > 0:
            cos_div = 1.0 - (np.dot(pred_m, pred_b) / (norm_m * norm_b))
        else:
            cos_div = 0.0

        ham_delta = out_mutated["hamiltonian"] - out_baseline["hamiltonian"]

        return {
            "predicted_mv": out_mutated["predicted_rotor"],
            "hamiltonian": out_mutated["hamiltonian"],
            "hamiltonian_delta": ham_delta,
            "divergence": cos_div,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Mode B: Latent Rollout — symplectic evolution in phase space (NumPy Port)
    # ─────────────────────────────────────────────────────────────────────
    def run_latent_rollout(
        self,
        base_tensor: np.ndarray,
        active_manifold: Any,
        domain_name: str,
        steps: int = 32,
    ) -> Dict[str, Any]:
        """
        Roll forward in phase space using the Hamiltonian integrator.
        Ported to pure NumPy.
        """
        bridge = getattr(active_manifold, 'kinematic_bridge', None)
        if not bridge and hasattr(active_manifold, 'rotor_predictor'):
            bridge = active_manifold.kinematic_bridge
            active_manifold = active_manifold.rotor_predictor

        if bridge is None:
             raise ValueError("KinematicBridge not found on the provided active_manifold.")

        cga = bridge.physics_to_cga(base_tensor, domain=domain_name)
        out = active_manifold.predict(cga)

        q = out["q"]
        p = out["p"]

        engine = active_manifold.engine
        if not hasattr(engine, 'smoe_he'):
            raise ValueError("Engine does not have smoe_he for symplectic rollout.")
        smoe = engine.smoe_he

        trajectory_q = [np.copy(q)]
        trajectory_h = [out["hamiltonian"]]

        for _ in range(steps):
            q, p, _, _ = smoe(q, p)
            # Ensure p^2 sum matches how predict calculates hamiltonian loosely, or call compute_hamiltonian
            if hasattr(smoe, "compute_hamiltonian"):
                h = smoe.compute_hamiltonian(q, p)
                if h.ndim == 3:
                    h_total = np.sum(h, axis=-1)
                else:
                    h_total = h
                trajectory_h.append(float(np.mean(h_total)))
            else:
                trajectory_h.append(float(np.sum(p**2) / 1000.0))
            trajectory_q.append(np.copy(q))

        if len(trajectory_h) > 2:
            h_init = abs(trajectory_h[0]) + 1e-8
            h_final = abs(trajectory_h[-1]) + 1e-8
            lyap = float(abs(h_final - h_init) / (h_init * steps))
        else:
            lyap = 0.0

        return {
            "trajectory_length": len(trajectory_q),
            "trajectory_h": trajectory_h,
            "final_q": trajectory_q[-1],
            "lyapunov_estimate": lyap,
        }
