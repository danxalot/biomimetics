import numpy as np
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class PoincareStructure:
    """A structure living in hyperbolic space with full lifecycle tracking."""
    name: str
    position: np.ndarray
    access_count: float = 0.0
    stress: float = 0.0
    creation_tick: int = 0
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    consecutive_low_attention: int = 0
    alive: bool = True


class PoincareKernel:
    """
    Hyperbolic Geometry Kernel for Geometric Attention.
    
    Implements Poincaré Disk model where forgetting is physical movement
    toward the boundary (r -> 1).
    
    Improvements over base implementation:
    - Numerical clamping to keep points inside disk
    - Access count decay (stress reflects recent activity, not lifetime)
    - Apoptosis (death) for structures stuck at edge
    - Ancestry tracking through mitosis events
    - Merge capability for convergent daughter cells
    """
    
    def __init__(self, dimension: int = 2, curvature: float = 1.0,
                 decay_rate: float = 0.95,
                 apoptosis_threshold: float = 0.05,
                 apoptosis_ticks: int = 10,
                 boundary_epsilon: float = 0.999):
        
        self.dim = dimension
        self.c = curvature
        self.decay_rate = decay_rate
        self.apoptosis_threshold = apoptosis_threshold
        self.apoptosis_ticks = apoptosis_ticks
        self.boundary_epsilon = boundary_epsilon
        
        self.structures: Dict[str, PoincareStructure] = {}
        self.tick = 0
        self.lineage_roots: Set[str] = set()
        
        # Event log for debugging/visualization
        self.events: List[Tuple[int, str]] = []
    
    def _clamp_to_disk(self, v: np.ndarray) -> np.ndarray:
        """Ensure point stays strictly inside the Poincaré disk."""
        norm = np.linalg.norm(v)
        if norm >= self.boundary_epsilon:
            v = v * (self.boundary_epsilon / norm)
        return v
    
    def _mobius_add(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """
        Hyperbolic vector addition (Möbius addition).
        Result is clamped to stay within disk.
        """
        u2 = np.sum(u * u)
        v2 = np.sum(v * v)
        uv = np.sum(u * v)
        
        denom = 1 + 2 * self.c * uv + self.c**2 * u2 * v2
        if abs(denom) < 1e-9:
            denom = 1e-9
        
        term1 = (1 + 2 * self.c * uv + self.c * v2) * u
        term2 = (1 - self.c * u2) * v
        
        result = (term1 + term2) / denom
        return self._clamp_to_disk(result)
    
    def _exp_map(self, p: np.ndarray, v: np.ndarray) -> np.ndarray:
        """
        Exponential map: Move from point p along tangent vector v.
        This gives geodesic (shortest path) movement in hyperbolic space.
        """
        v_norm = np.linalg.norm(v)
        if v_norm < 1e-9:
            return p
        
        # Conformal factor at p
        lambda_p = 2.0 / (1 - np.sum(p * p))
        
        # Scaled norm
        scaled_norm = lambda_p * v_norm
        
        # Direction
        direction = v / v_norm
        
        # Geodesic endpoint
        tanh_term = np.tanh(self.c**0.5 * scaled_norm / 2)
        result = self._mobius_add(p, tanh_term * direction)
        
        return self._clamp_to_disk(result)
    
    def _log_map(self, p: np.ndarray, q: np.ndarray) -> np.ndarray:
        """
        Logarithmic map: Get tangent vector at p pointing toward q.
        Inverse of exp_map.
        """
        diff = self._mobius_add(-p, q)
        diff_norm = np.linalg.norm(diff)
        
        if diff_norm < 1e-9:
            return np.zeros(self.dim)
        
        lambda_p = 2.0 / (1 - np.sum(p * p))
        
        return (2 / (self.c**0.5 * lambda_p)) * np.arctanh(diff_norm) * (diff / diff_norm)
    
    def distance(self, u: np.ndarray, v: np.ndarray) -> float:
        """Hyperbolic distance. Approaches infinity as points near boundary."""
        sq_norm_diff = np.sum((u - v) ** 2)
        u2 = min(np.sum(u ** 2), self.boundary_epsilon**2)
        v2 = min(np.sum(v ** 2), self.boundary_epsilon**2)
        
        arg = 1 + 2 * sq_norm_diff / ((1 - u2) * (1 - v2))
        return np.arccosh(max(arg, 1.0))
    
    def register_structure(self, name: str, vector: Optional[np.ndarray] = None,
                          parent: Optional[str] = None) -> PoincareStructure:
        """Initialize a new context structure."""
        if vector is None:
            vector = np.zeros(self.dim)
        else:
            vector = self._clamp_to_disk(vector.copy())
        
        structure = PoincareStructure(
            name=name,
            position=vector,
            creation_tick=self.tick,
            parent=parent
        )
        
        self.structures[name] = structure
        
        if parent is None:
            self.lineage_roots.add(name)
        elif parent in self.structures:
            self.structures[parent].children.append(name)
        
        self.events.append((self.tick, f"BIRTH: {name}"))
        return structure
    
    def apply_force(self, name: str, force_vector: np.ndarray, 
                    geodesic: bool = True) -> np.ndarray:
        """
        Apply physics push to a structure.
        
        Args:
            geodesic: If True, use exponential map for smooth geodesic movement.
                     If False, use Möbius addition (faster but less smooth).
        """
        if name not in self.structures:
            self.register_structure(name)
        
        s = self.structures[name]
        
        if geodesic:
            s.position = self._exp_map(s.position, force_vector)
        else:
            s.position = self._mobius_add(s.position, force_vector)
        
        return s.position
    
    def retract(self, name: str, intensity: float = 0.1) -> None:
        """Push structure toward boundary (forgetting)."""
        if name not in self.structures:
            return
        
        s = self.structures[name]
        norm = np.linalg.norm(s.position)
        
        if norm < 1e-6:
            direction = np.random.randn(self.dim)
            direction /= np.linalg.norm(direction)
        else:
            direction = s.position / norm
        
        force = direction * intensity
        self.apply_force(name, force)
    
    def attract(self, name: str, intensity: float = 0.1) -> None:
        """Pull structure toward center (focusing). Increments access count."""
        if name not in self.structures:
            self.register_structure(name)
            return
        
        s = self.structures[name]
        s.access_count += 1
        s.stress += 1
        
        norm = np.linalg.norm(s.position)
        if norm < 1e-6:
            return
        
        direction = -s.position / norm
        force = direction * intensity
        self.apply_force(name, force)
        
        # Reset apoptosis counter when accessed
        s.consecutive_low_attention = 0
    
    def tick_update(self) -> Dict[str, List[str]]:
        """
        Advance one tick. Applies:
        - Access count decay
        - Apoptosis check
        - Returns dict of events {splits: [...], deaths: [...], merges: [...]}
        """
        self.tick += 1
        events = {"splits": [], "deaths": [], "merges": []}
        
        # Decay access counts
        for s in self.structures.values():
            s.access_count *= self.decay_rate
            s.stress *= self.decay_rate
        
        # Check apoptosis
        to_kill = []
        for name, s in self.structures.items():
            attention = self.get_attention(name)
            if attention < self.apoptosis_threshold:
                s.consecutive_low_attention += 1
                if s.consecutive_low_attention >= self.apoptosis_ticks:
                    to_kill.append(name)
            else:
                s.consecutive_low_attention = 0
        
        for name in to_kill:
            self._apoptosis(name)
            events["deaths"].append(name)
        
        return events
    
    def _apoptosis(self, name: str) -> None:
        """Kill a structure. Update lineage tracking."""
        if name not in self.structures:
            return
        
        s = self.structures[name]
        s.alive = False
        
        # Reparent children to grandparent
        for child_name in s.children:
            if child_name in self.structures:
                self.structures[child_name].parent = s.parent
                if s.parent and s.parent in self.structures:
                    self.structures[s.parent].children.append(child_name)
        
        # Remove from parent's children list
        if s.parent and s.parent in self.structures:
            parent = self.structures[s.parent]
            if name in parent.children:
                parent.children.remove(name)
        
        # Update lineage roots
        if name in self.lineage_roots:
            self.lineage_roots.discard(name)
            for child_name in s.children:
                if child_name in self.structures:
                    self.lineage_roots.add(child_name)
        
        del self.structures[name]
        self.events.append((self.tick, f"DEATH: {name}"))
    
    def check_mitosis(self, stress_threshold: float = 50) -> List[Tuple[str, str, str]]:
        """
        Cell division when stress exceeds threshold.
        Returns list of (parent, child1, child2) tuples.
        """
        splits = []
        candidates = [name for name, s in self.structures.items() 
                     if s.stress > stress_threshold]
        
        for name in candidates:
            s = self.structures[name]
            
            # Create offset for daughters
            offset = np.random.randn(self.dim) * 0.05
            pos_1 = self._mobius_add(s.position, offset)
            pos_2 = self._mobius_add(s.position, -offset)
            
            name_1 = f"{name}_α"
            name_2 = f"{name}_β"
            
            # Handle naming collisions
            counter = 0
            while name_1 in self.structures:
                counter += 1
                name_1 = f"{name}_α{counter}"
                name_2 = f"{name}_β{counter}"
            
            # Create daughters with lineage
            self.register_structure(name_1, pos_1, parent=name)
            self.register_structure(name_2, pos_2, parent=name)
            
            # Transfer half stress to each daughter
            self.structures[name_1].stress = s.stress / 4
            self.structures[name_2].stress = s.stress / 4
            
            # Parent becomes inactive but preserved for lineage
            s.alive = False
            s.children = [name_1, name_2]
            
            splits.append((name, name_1, name_2))
            self.events.append((self.tick, f"MITOSIS: {name} -> {name_1}, {name_2}"))
        
        return splits
    
    def check_merge(self, distance_threshold: float = 0.1) -> List[Tuple[str, str, str]]:
        """
        Merge nearby structures that share a parent (sibling fusion).
        Returns list of (merged_name, source1, source2) tuples.
        """
        merges = []
        names = list(self.structures.keys())
        merged = set()
        
        for i, name_1 in enumerate(names):
            if name_1 in merged or not self.structures[name_1].alive:
                continue
                
            for name_2 in names[i+1:]:
                if name_2 in merged or not self.structures[name_2].alive:
                    continue
                
                s1 = self.structures[name_1]
                s2 = self.structures[name_2]
                
                # Only merge siblings
                if s1.parent != s2.parent or s1.parent is None:
                    continue
                
                dist = self.distance(s1.position, s2.position)
                if dist < distance_threshold:
                    # Merge into midpoint
                    midpoint = self._mobius_add(
                        s1.position * 0.5,
                        s2.position * 0.5
                    )
                    
                    # New name from common ancestor
                    base_name = s1.parent if s1.parent else "merged"
                    new_name = f"{base_name}_merged_{self.tick}"
                    
                    self.register_structure(new_name, midpoint, parent=s1.parent)
                    self.structures[new_name].stress = (s1.stress + s2.stress) / 2
                    self.structures[new_name].access_count = max(s1.access_count, s2.access_count)
                    
                    # Kill sources
                    merged.add(name_1)
                    merged.add(name_2)
                    
                    merges.append((new_name, name_1, name_2))
                    self.events.append((self.tick, f"MERGE: {name_1} + {name_2} -> {new_name}"))
        
        # Clean up merged structures
        for name in merged:
            if name in self.structures:
                del self.structures[name]
        
        return merges
    
    def apply_rotor_modulation(
        self,
        rotor_32d: np.ndarray,
        source: str,
        target: str,
        strength: float = 0.65,
    ) -> None:
        """
        Modulate target structure's Poincaré position using a CGA rotor.

        The rotor (32D Cl(4,1) multivector) encodes a geometric transformation.
        We extract a 2D projection from its bivector part (components 6-10 in CGA
        correspond to e12, e13, e14, e15, e23 — the spatial rotation bivectors).
        This 2D direction is then applied as a Möbius transformation displacement
        in the Poincaré disk:
            new_pos = Möbius_add(old_pos, strength × step_direction)

        This modulates geometric attention: the rotor steers target concept
        attention toward the configuration implied by the physics engine output.

        Args:
            rotor_32d: 32D CGA multivector from the NoumenalEngine.
            source: Name of the source structure (unused geometrically; for logging).
            target: Name of the target structure to modulate.
            strength: Displacement step magnitude (default 0.65).
        """
        if target not in self.structures:
            return

        rotor = np.asarray(rotor_32d, dtype=np.float64).flatten()

        # Extract 2D projection from bivector part of the rotor.
        # In CGA Cl(4,1) with 32-component multivectors:
        #   indices 6-15 are bivector components (e12, e13, e14, e15, e23, e24, e25, e34, e35, e45)
        # Use the first two bivector components for the 2D disk direction.
        if rotor.size >= 8:
            biv_2d = rotor[6:8].copy()
        else:
            biv_2d = np.zeros(2)

        biv_norm = np.linalg.norm(biv_2d)
        if biv_norm < 1e-9:
            # Fallback: use vector part components 1-2 (e1, e2)
            if rotor.size >= 3:
                biv_2d = rotor[1:3].copy()
                biv_norm = np.linalg.norm(biv_2d)
            if biv_norm < 1e-9:
                return  # No usable direction

        # Normalize to unit direction
        direction = biv_2d[:2] / biv_norm

        # Step in that direction (Möbius add for geodesic movement)
        step = direction * strength * 0.1  # scale down so disk stays stable
        self.apply_force(target, step, geodesic=True)

    def get_attention(self, name: str, query_point: Optional[np.ndarray] = None) -> float:
        """Attention score (0.0 to 1.0) based on hyperbolic distance from query."""
        if name not in self.structures:
            return 0.0
        
        if query_point is None:
            query_point = np.zeros(self.dim)
        
        pos = self.structures[name].position
        dist = self.distance(pos, query_point)
        
        return 1.0 / np.cosh(dist)
    
    def get_active_contexts(self, threshold: float = 0.1) -> List[Tuple[str, float]]:
        """Get structures currently in focus, sorted by attention."""
        active = []
        for name, s in self.structures.items():
            if not s.alive:
                continue
            att = self.get_attention(name)
            if att > threshold:
                active.append((name, att))
        return sorted(active, key=lambda x: x[1], reverse=True)
    
    def get_lineage(self, name: str) -> List[str]:
        """Trace ancestry back to root."""
        lineage = [name]
        current = name
        while current in self.structures and self.structures[current].parent:
            current = self.structures[current].parent
            if current in self.structures:
                lineage.append(current)
            else:
                break
        return list(reversed(lineage))
    
    def get_descendants(self, name: str) -> List[str]:
        """Get all descendants of a structure."""
        if name not in self.structures:
            return []
        
        descendants = []
        queue = list(self.structures[name].children)
        
        while queue:
            child = queue.pop(0)
            if child in self.structures:
                descendants.append(child)
                queue.extend(self.structures[child].children)
        
        return descendants


class HyperbolicKuramotoField:
    """
    Integration of Poincaré geometry with Kuramoto oscillator dynamics.
    
    Each ConceptMonad has:
    - A phase θ in the Kuramoto field
    - A position in the Poincaré disk
    - Coupling strength Kᵢⱼ modulated by hyperbolic attention
    
    Dynamics:
    dθᵢ/dt = ωᵢ + K_bg3·sin(φ - θᵢ) + Σⱼ Kᵢⱼ·A(i,j)·sin(θⱼ - θᵢ)
    
    Where A(i,j) is the geometric attention between monads i and j.
    """
    
    PHI = (1 + np.sqrt(5)) / 2  # Golden ratio
    
    def __init__(self, 
                 n_monads: int = 100,
                 poincare_dim: int = 2,
                 k_bg3: float = 0.5,
                 k_base: float = 1.0,
                 dt: float = 0.01):
        
        self.n_monads = n_monads
        self.k_bg3 = k_bg3
        self.k_base = k_base
        self.dt = dt
        
        # Poincaré kernel for geometric attention
        self.poincare = PoincareKernel(dimension=poincare_dim)
        
        # Kuramoto state
        self.phases = np.random.uniform(0, 2*np.pi, n_monads)
        self.natural_frequencies = np.random.normal(1.0, 0.1, n_monads)
        self.amplitudes = np.ones(n_monads)
        self.uncertainties = np.ones(n_monads) * 0.5
        
        # Monad objects (HDC signatures, etc.)
        self.monad_objects: Dict[str, Any] = {}
        
        # Monad metadata
        self.monad_names: List[str] = []
        self.name_to_idx: Dict[str, int] = {}
        
        # Base coupling matrix (before attention modulation)
        self.base_coupling = np.ones((n_monads, n_monads)) * k_base
        np.fill_diagonal(self.base_coupling, 0)
        
        # Special monads
        self.self_idx: Optional[int] = None
        
    @property
    def bg3_coupling(self) -> float:
        return self.k_bg3
        
    @bg3_coupling.setter
    def bg3_coupling(self, value: float):
        self.k_bg3 = value
        
    @property
    def bg3_target(self) -> float:
        if not hasattr(self, '_bg3_target') or self._bg3_target is None:
            return 2 * np.pi / self.PHI
        return self._bg3_target
        
    @bg3_target.setter
    def bg3_target(self, value: float):
        self._bg3_target = value
        
    @property
    def monads(self) -> Dict[str, Any]:
        """Proxy property for FractalSelf compatibility.
        Returns the dictionary of ConceptMonad objects."""
        return self.monad_objects
        
    def register_self(self, name: str):
        """Register the self-referential anchor (ARCA) with golden-ratio phase."""
        self.register_monad(name, natural_freq=(1+np.sqrt(5))/2, is_self=True)

    def add_monad(self, monad: Any):
        """Register a ConceptMonad object and initialize its field state."""
        # Extract name/id
        name = getattr(monad, 'concept_id', getattr(monad, 'id', None))
        if not name:
            name = str(id(monad))
        
        # Register in field arrays if not already present
        if name not in self.name_to_idx:
            self.register_monad(
                name, 
                natural_freq=getattr(monad, 'natural_frequency', 1.0),
                initial_phase=getattr(monad, 'phase', 0.0),
                uncertainty=getattr(monad, 'uncertainty', 0.5)
            )
        
        # Store object in the monad_objects dict
        self.monad_objects[name] = monad

    def register_concept(self, concept: Any):
        """Alias for add_monad."""
        self.add_monad(concept)
        
    def register_monad(self, name: str, 
                       natural_freq: Optional[float] = None,
                       initial_phase: Optional[float] = None,
                       poincare_pos: Optional[np.ndarray] = None,
                       uncertainty: float = 0.5,
                       is_self: bool = False) -> int:
        """
        Register a new concept monad with both Kuramoto and Poincaré state.
        """
        if name in self.name_to_idx:
            return self.name_to_idx[name]
        
        idx = len(self.monad_names)
        if idx >= self.n_monads:
            raise ValueError(f"Maximum monads ({self.n_monads}) exceeded")
        
        self.monad_names.append(name)
        self.name_to_idx[name] = idx
        
        if natural_freq is not None:
            self.natural_frequencies[idx] = natural_freq
        if initial_phase is not None:
            self.phases[idx] = initial_phase
        
        self.uncertainties[idx] = uncertainty
        
        # Register in Poincaré space
        self.poincare.register_structure(name, poincare_pos)
        
        if is_self:
            self.self_idx = idx
            self.uncertainties[idx] = 0.01  # High certainty for self
            # Self starts at center
            self.poincare.structures[name].position = np.zeros(self.poincare.dim)
        
        return idx
    
    def register_self(self, name: str = "ARCA") -> int:
        """Register the self-referential monad."""
        return self.register_monad(
            name,
            natural_freq=1.0,
            initial_phase=self.bg3_target,  # Start at golden angle
            poincare_pos=np.zeros(self.poincare.dim),
            uncertainty=0.01,
            is_self=True
        )
    
    def create_mirror(self, name: str, source_name: str,
                      initial_uncertainty: float = 0.8) -> int:
        """
        Create a mirror monad of an external entity.
        Starts at edge of Poincaré disk (low attention/confidence).
        """
        # Position at edge, random direction
        direction = np.random.randn(self.poincare.dim)
        direction /= np.linalg.norm(direction)
        edge_pos = direction * 0.9
        
        idx = self.register_monad(
            name,
            uncertainty=initial_uncertainty,
            poincare_pos=edge_pos
        )
        
        # Store mirror relationship
        self.poincare.structures[name].mirror_of = source_name
        
        return idx
    
    def get_attention_matrix(self) -> np.ndarray:
        """
        Compute pairwise attention based on Poincaré positions.
        A[i,j] = attention from i's perspective to j.
        """
        n = len(self.monad_names)
        A = np.zeros((self.n_monads, self.n_monads))
        
        for i, name_i in enumerate(self.monad_names):
            if name_i not in self.poincare.structures:
                continue
            pos_i = self.poincare.structures[name_i].position
            
            for j, name_j in enumerate(self.monad_names):
                if i == j or name_j not in self.poincare.structures:
                    continue
                pos_j = self.poincare.structures[name_j].position
                
                # Attention from i to j
                dist = self.poincare.distance(pos_i, pos_j)
                A[i, j] = 1.0 / np.cosh(dist)
        
        return A
    
    def get_effective_coupling(self) -> np.ndarray:
        """
        Coupling matrix modulated by geometric attention.
        K_eff[i,j] = K_base[i,j] * A[i,j]
        """
        A = self.get_attention_matrix()
        return self.base_coupling * A
    
    def compute_bg3_coherence(self) -> float:
        """
        Measure coherence with golden ratio phase.
        Returns value in [0, 1] where 1 = perfect φ-alignment.
        """
        target_phase = self.bg3_target
        n = len(self.monad_names)
        if n == 0:
            return 0.0

        # Weighted by amplitude and attention (distance from edge)
        weights = []
        phase_diffs = []

        for i, name in enumerate(self.monad_names):
            att = self.poincare.get_attention(name)
            weights.append(att * self.amplitudes[i])
            phase_diffs.append(np.cos(self.phases[i] - target_phase))

        weights = np.array(weights)
        phase_diffs = np.array(phase_diffs)

        if np.sum(weights) < 1e-9:
            return 0.0

        # Normalise weighted cosine from [-1,1] → [0,1]
        raw = float(np.sum(weights * phase_diffs) / np.sum(weights))
        return (raw + 1.0) / 2.0

    def compute_bg3_lock_fraction(self, tolerance: float = 0.1) -> float:
        """
        [I] Fraction of registered monads whose phase is within `tolerance`
        radians of the BG3 golden-ratio target phase (2π/φ).

        This is the strict phase-lock metric: 1.0 = all monads φ-locked,
        0.0 = none within tolerance.  Reported in /system/vitals as
        `bg3_lock_fraction`.

        Args:
            tolerance: Phase window in radians (default 0.1 rad ≈ 5.7°).
        """
        n = len(self.monad_names)
        if n == 0:
            return 0.0
        target_phase = self.bg3_target
        phases = self.phases[:n]
        # Circular distance (wrap to [0, π])
        diff = np.abs(phases - target_phase)
        diff = np.minimum(diff, 2 * np.pi - diff)
        locked = int(np.sum(diff <= tolerance))
        return float(locked) / float(n)
    
    def compute_global_coherence(self) -> float:
        """
        Kuramoto order parameter: R = |1/N Σ exp(iθⱼ)|
        """
        n = len(self.monad_names)
        if n == 0:
            return 0.0
        
        complex_phases = np.exp(1j * self.phases[:n])
        return np.abs(np.mean(complex_phases))
    
    def step(self) -> Dict[str, float]:
        """
        Advance Kuramoto dynamics by one timestep.
        
        dθᵢ/dt = ωᵢ + K_bg3·sin(φ - θᵢ) + Σⱼ K_eff[i,j]·sin(θⱼ - θᵢ)
        
        Returns metrics dict.
        """
        n = len(self.monad_names)
        if n == 0:
            return {}
        
        # Get attention-modulated coupling
        K_eff = self.get_effective_coupling()
        
        # BG3 target phase
        phi_target = self.bg3_target
        
        # Compute phase derivatives
        dtheta = np.zeros(self.n_monads)
        
        for i in range(n):
            # Intrinsic frequency
            dtheta[i] = self.natural_frequencies[i]
            
            # BG3 attractor
            dtheta[i] += self.k_bg3 * np.sin(phi_target - self.phases[i])
            
            # Coupling to neighbors
            for j in range(n):
                if i != j:
                    dtheta[i] += K_eff[i, j] * np.sin(self.phases[j] - self.phases[i])
        
        # Euler integration
        self.phases[:n] += dtheta[:n] * self.dt
        
        # Wrap to [0, 2π)
        self.phases = np.mod(self.phases, 2 * np.pi)
        
        # Update Poincaré kernel
        poincare_events = self.poincare.tick_update()
        
        # Compute metrics
        metrics = {
            "global_coherence": self.compute_global_coherence(),
            "bg3_coherence": self.compute_bg3_coherence(),
            "mean_phase": np.mean(self.phases[:n]),
            "phase_std": np.std(self.phases[:n]),
            "active_structures": len(self.poincare.get_active_contexts()),
            "deaths": len(poincare_events["deaths"]),
        }
        
        return metrics
    
    def focus_monad(self, name: str, intensity: float = 0.1) -> None:
        """
        Bring a monad into focus (attract to Poincaré center).
        Increases its coupling influence.
        """
        self.poincare.attract(name, intensity)
    
    def defocus_monad(self, name: str, intensity: float = 0.1) -> None:
        """
        Push a monad out of focus (retract to Poincaré edge).
        Decreases its coupling influence.
        """
        self.poincare.retract(name, intensity)
    
    def sync_mirror(self, mirror_name: str, observed_phase: float,
                    coupling_strength: float = 0.5) -> None:
        """
        Sync a mirror monad toward observed external phase.
        Also attracts it in Poincaré space (increasing confidence).
        """
        if mirror_name not in self.name_to_idx:
            return
        
        idx = self.name_to_idx[mirror_name]
        
        # Blend phase toward observed
        phase_diff = observed_phase - self.phases[idx]
        # Wrap to [-π, π]
        phase_diff = np.arctan2(np.sin(phase_diff), np.cos(phase_diff))
        
        self.phases[idx] += coupling_strength * phase_diff
        self.phases[idx] = np.mod(self.phases[idx], 2 * np.pi)
        
        # Reduce uncertainty
        s = self.poincare.structures.get(mirror_name)
        if s:
            self.uncertainties[idx] *= 0.99
            self.uncertainties[idx] = max(self.uncertainties[idx], 0.1)  # Floor
        
        # Attract toward center (increased confidence)
        self.poincare.attract(mirror_name, intensity=0.05)
    
    def detect_dissonance(self, threshold: float = 0.5) -> List[Tuple[str, str, float]]:
        """
        Detect phase dissonance between self and trusted monads.
        Returns list of (self, other, dissonance_score) for high-dissonance pairs.
        """
        if self.self_idx is None:
            return []
        
        dissonances = []
        self_phase = self.phases[self.self_idx]
        
        for i, name in enumerate(self.monad_names):
            if i == self.self_idx:
                continue
            
            # Only check monads in focus
            att = self.poincare.get_attention(name)
            if att < 0.3:  # Not in focus
                continue
            
            phase_diff = abs(self.phases[i] - self_phase)
            phase_diff = min(phase_diff, 2*np.pi - phase_diff)  # Wrap
            
            dissonance = phase_diff / np.pi  # Normalize to [0, 1]
            
            if dissonance > threshold:
                dissonances.append((
                    self.monad_names[self.self_idx],
                    name,
                    dissonance
                ))
        
        return sorted(dissonances, key=lambda x: x[2], reverse=True)
    
    def get_curiosity_ranking(self) -> List[Tuple[str, float]]:
        """
        Rank monads by "curiosity" - combination of uncertainty and low attention.
        High uncertainty + edge position = high curiosity target.
        """
        rankings = []
        
        for i, name in enumerate(self.monad_names):
            att = self.poincare.get_attention(name)
            unc = self.uncertainties[i]
            
            # Curiosity = uncertainty * (1 - attention)
            # High uncertainty AND at edge = very curious
            curiosity = unc * (1 - att)
            rankings.append((name, curiosity))
        
        return sorted(rankings, key=lambda x: x[1], reverse=True)
    
    def apply_rotor_modulation(self, rotor: np.ndarray, 
                               source_monad: str,
                               target_monad: str,
                               strength: float = 0.1) -> None:
        """
        Apply NoumenalEngine rotor output to modulate coupling between monads.
        
        The rotor encodes geometric transformation. We extract:
        - Rotation component (bivector) -> phase coupling adjustment
        - Translation component -> Poincaré position adjustment
        """
        if source_monad not in self.name_to_idx or target_monad not in self.name_to_idx:
            return
        
        src_idx = self.name_to_idx[source_monad]
        tgt_idx = self.name_to_idx[target_monad]
        
        # Extract bivector components (indices 6-15 in CGA)
        # These encode rotation in 3D -> use for phase coupling
        bivector_norm = np.linalg.norm(rotor[6:16])
        
        # Extract translation (from rotor structure)
        # In CGA, translation involves e_inf (index 5)
        translation_component = np.linalg.norm(rotor[1:5])
        
        # Modulate base coupling
        rotation_factor = 1.0 + strength * np.tanh(bivector_norm)
        self.base_coupling[src_idx, tgt_idx] *= rotation_factor
        self.base_coupling[tgt_idx, src_idx] *= rotation_factor
        
        # Modulate Poincaré positions based on translation
        if translation_component > 0.01:
            # Move target toward/away from source in Poincaré space
            src_pos = self.poincare.structures[source_monad].position
            tgt_pos = self.poincare.structures[target_monad].position
            
            direction = src_pos - tgt_pos
            dir_norm = np.linalg.norm(direction)
            if dir_norm > 1e-6:
                direction /= dir_norm
                force = direction * strength * translation_component
                self.poincare.apply_force(target_monad, force)
    
    def recalculate_coupling_matrix(self, coupling_dict: dict) -> None:
        """
        Update base_coupling[i, j] using RBF similarity on CGA coordinates.

        Mirrors UniversalKuramotoField.recalculate_coupling_matrix() but operates
        on HyperbolicKuramotoField's internal base_coupling numpy matrix rather
        than monad-level couplings dicts.

        Args:
            coupling_dict: {monad_name: cga_vector (np.ndarray, 32D)} — typically
                           the transient_cga dict from _recalculate_ephemeral_couplings.

        sigma² = 1.0 (RBF bandwidth). K_ij = exp(-‖cga_i − cga_j‖² / sigma²).
        Only pairs where both names are registered in name_to_idx are updated.
        """
        if not coupling_dict or len(coupling_dict) < 2:
            return

        sigma_sq = 1.0
        names = [n for n in coupling_dict if n in self.name_to_idx]
        if len(names) < 2:
            return

        for pi, name_i in enumerate(names):
            idx_i = self.name_to_idx[name_i]
            vec_i = np.asarray(coupling_dict[name_i], dtype=np.float64).flatten()

            for pj in range(pi + 1, len(names)):
                name_j = names[pj]
                idx_j = self.name_to_idx[name_j]
                vec_j = np.asarray(coupling_dict[name_j], dtype=np.float64).flatten()

                min_dim = min(vec_i.size, vec_j.size)
                sq_dist = float(np.sum((vec_i[:min_dim] - vec_j[:min_dim]) ** 2))
                k_ij = float(np.exp(-sq_dist / sigma_sq))

                self.base_coupling[idx_i, idx_j] = k_ij
                self.base_coupling[idx_j, idx_i] = k_ij

    def get_state_summary(self) -> Dict:
        """Get full state summary for debugging/logging."""
        n = len(self.monad_names)
        
        active = self.poincare.get_active_contexts()
        
        return {
            "tick": self.poincare.tick,
            "n_monads": n,
            "global_coherence": self.compute_global_coherence(),
            "bg3_coherence": self.compute_bg3_coherence(),
            "active_contexts": active[:10],  # Top 10
            "curiosity_top": self.get_curiosity_ranking()[:5],
            "dissonances": self.detect_dissonance(),
            "mean_uncertainty": np.mean(self.uncertainties[:n]) if n > 0 else 0,
            "poincare_events": self.poincare.events[-10:],  # Last 10 events
        }