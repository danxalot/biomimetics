"""
Full Integration - NumPy/ONNX Version
=====================================

PyTorch-free implementation using ONNX Runtime and NumPy.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import redis

# Qwen replacement - using ONNX Runtime or simple template-based interpreter
try:
    import onnxruntime as ort
    _ONNX_AVAILABLE = True
except ImportError:
    _ONNX_AVAILABLE = False

# ============================================================
# ROTOR DECOMPOSITION
# ============================================================

@dataclass
class RotorDecomposition:
    """Geometric primitives extracted from 32-component CGA rotor."""
    
    rotation_axis: np.ndarray  # Unit vector [3]
    rotation_angle: float  # Radians
    translation: np.ndarray  # Vector [3]
    translation_magnitude: float
    scale_factor: float
    screw_pitch: float  # Translation per radian of rotation
    raw_rotor: np.ndarray  # Original [32]
    grade_energies: Dict[str, float]  # Energy per grade


class RotorDecomposer:
    """
    Decomposes CGA Cl(4,1) rotors into interpretable geometric primitives.
    
    CGA basis (32 components):
    [0]      : scalar (grade 0)
    [1-5]    : vectors e1,e2,e3,e+,e- (grade 1)
    [6-15]   : bivectors (grade 2) - encode rotations
    [16-25]  : trivectors (grade 3)
    [26-30]  : quadvectors (grade 4)
    [31]     : pseudoscalar (grade 5)
    
    For rotors: R = cos(θ/2) + sin(θ/2)*B where B is unit bivector
    """
    
    # Grade index slices
    GRADE_0 = slice(0, 1)
    GRADE_1 = slice(1, 6)
    GRADE_2 = slice(6, 16)
    GRADE_3 = slice(16, 26)
    GRADE_4 = slice(26, 31)
    GRADE_5 = slice(31, 32)
    
    # Bivector basis mapping to rotation planes
    # e12, e13, e14, e15, e23, e24, e25, e34, e35, e45
    BIVECTOR_LABELS = [
        "e12",
        "e13",
        "e1+",
        "e1-",
        "e23",
        "e2+",
        "e2-",
        "e3+",
        "e3-",
        "e+-",
    ]
    
    def decompose(self, rotor: np.ndarray) -> RotorDecomposition:
        """Extract geometric primitives from rotor."""
        # Ensure numpy array (no torch check needed - we only accept numpy)
        rotor = rotor.flatten().astype(np.float32)
        assert len(rotor) == 32, f"Expected 32 components, got {len(rotor)}"
        
        # Grade energies
        grade_energies = {
            "scalar": float(np.sum(rotor[self.GRADE_0] ** 2)),
            "vector": float(np.sum(rotor[self.GRADE_1] ** 2)),
            "bivector": float(np.sum(rotor[self.GRADE_2] ** 2)),
            "trivector": float(np.sum(rotor[self.GRADE_3] ** 2)),
            "quadvector": float(np.sum(rotor[self.GRADE_4] ** 2)),
            "pseudoscalar": float(np.sum(rotor[self.GRADE_5] ** 2)),
        }
        
        # Extract rotation from bivector part
        scalar = rotor[0]
        bivector = rotor[self.GRADE_2]
        
        # Rotation angle: R = cos(θ/2) + sin(θ/2)*B
        # So scalar = cos(θ/2), |bivector| = sin(θ/2)
        biv_norm = np.linalg.norm(bivector)
        
        if biv_norm < 1e-9:
            rotation_angle = 0.0
            rotation_axis = np.array([0.0, 0.0, 1.0])
        else:
            rotation_angle = 2 * np.arctan2(biv_norm, scalar)
            
            # Extract 3D rotation axis from bivector
            # Euclidean bivectors are e12, e13, e23 (indices 0, 1, 4 in bivector array)
            euclidean_biv = np.array([bivector[0], bivector[1], bivector[4]])
            euc_norm = np.linalg.norm(euclidean_biv)
            
            if euc_norm < 1e-9:
                rotation_axis = np.array([0.0, 0.0, 1.0])
            else:
                # Bivector e_ij corresponds to rotation in i-j plane
                # Axis is perpendicular: e12 -> z, e13 -> -y, e23 -> x
                rotation_axis = np.array(
                    [
                        euclidean_biv[2],  # e23 component
                        -euclidean_biv[1],  # e13 component
                        euclidean_biv[0],  # e12 component
                    ]
                )
                rotation_axis /= np.linalg.norm(rotation_axis)
        
        # Extract translation from conformal part
        # In CGA, translation involves e+ and e- (indices 3,4 in grade-1)
        # Translation T appears in rotor as components with e_inf = e+ + e-
        e_plus_components = np.array(
            [bivector[2], bivector[5], bivector[7]]
        )  # e1+, e2+, e3+
        e_minus_components = np.array(
            [bivector[3], bivector[6], bivector[8]]
        )  # e1-, e2-, e3-
        
        # Translation vector (simplified extraction)
        translation = e_plus_components - e_minus_components
        translation_magnitude = np.linalg.norm(translation)
        
        if translation_magnitude > 1e-9:
            translation_normalized = translation / translation_magnitude
        else:
            translation_normalized = np.zeros(3)
        
        # Scale factor from e+e- component (index 9 in bivector)
        e_pm_component = bivector[9]
        scale_factor = np.exp(e_pm_component) if abs(e_pm_component) < 10 else 1.0
        
        # Screw pitch
        if abs(rotation_angle) > 1e-9:
            screw_pitch = translation_magnitude / rotation_angle
        else:
            screw_pitch = 0.0
        
        return RotorDecomposition(
            rotation_axis=rotation_axis,
            rotation_angle=rotation_angle,
            translation=translation_normalized,
            translation_magnitude=translation_magnitude,
            scale_factor=scale_factor,
            screw_pitch=screw_pitch,
            raw_rotor=rotor,
            grade_energies=grade_energies,
        )
    
    def to_text(self, decomp: RotorDecomposition, precision: int = 3) -> str:
        """Convert decomposition to human-readable text."""
        
        angle_deg = np.degrees(decomp.rotation_angle)
        axis = decomp.rotation_axis
        trans = decomp.translation
        
        lines = [
            f"Rotation: {angle_deg:.{precision}f}° about axis [{axis[0]:.{precision}f}, {axis[1]:.{precision}f}, {axis[2]:.{precision}f}]",
            f"Translation: {decomp.translation_magnitude:.{precision}f} units along [{trans[0]:.{precision}f}, {trans[1]:.{precision}f}, {trans[2]:.{precision}f}]",
            f"Scale: {decomp.scale_factor:.{precision}f}×",
        ]
        
        if abs(decomp.screw_pitch) > 1e-6:
            lines.append(
                f"Screw pitch: {decomp.screw_pitch:.{precision}f} units/radian"
            )
        
        # Grade energy distribution
        total_energy = sum(decomp.grade_energies.values())
        if total_energy > 1e-9:
            dominant_grade = max(decomp.grade_energies, key=decomp.grade_energies.get)
            lines.append(
                f"Dominant grade: {dominant_grade} ({100 * decomp.grade_energies[dominant_grade] / total_energy:.1f}%)"
            )
        
        return "\n".join(lines)


# ============================================================
# HEAVY LIFTER OUTPUT LOADER
# ============================================================

@dataclass
class DocumentGeometry:
    """Parsed output from geometry_heavy_lifter."""
    
    doc_id: str
    source_path: str
    gravity_well: np.ndarray  # Central embedding [512] or [2048]
    objects: List[Dict[str, Any]]  # Semantic objects with positions
    trajectory: List[np.ndarray]  # Ordered path through semantic space
    artifacts: List[Dict[str, Any]]  # Extracted concepts/entities
    themes: List[str]  # Document themes


class HeavyLifterLoader:
    """
    Loads and parses geometry_heavy_lifter output.
    
    Expected directory structure:
    output_dir/
      doc_name/
        SolarSystem.json    # gravity_well, trajectory
        Objects.json        # semantic objects with positions
        Vectors.json        # embeddings
        Artifacts.json      # extracted concepts
    """
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
    
    def load_document(self, doc_name: str) -> Optional[DocumentGeometry]:
        """Load all geometry files for a document."""
        
        doc_dir = self.output_dir / doc_name
        if not doc_dir.exists():
            return None
        
        solar_path = doc_dir / "SolarSystem.json"
        objects_path = doc_dir / "Objects.json"
        vectors_path = doc_dir / "Vectors.json"
        artifacts_path = doc_dir / "Artifacts.json"
        
        # Load SolarSystem (required)
        if not solar_path.exists():
            return None
        
        with open(solar_path) as f:
            solar = json.load(f)
        
        # Parse gravity well
        gravity_well = np.array(solar.get("gravity_well", []), dtype=np.float32)
        
        # Parse trajectory
        trajectory_raw = solar.get("trajectory", [])
        trajectory = [np.array(t, dtype=np.float32) for t in trajectory_raw]
        
        # Load objects (optional)
        objects = []
        if objects_path.exists():
            with open(objects_path) as f:
                objects = json.load(f)
        
        # Load artifacts (optional)
        artifacts = []
        themes = []
        if artifacts_path.exists():
            with open(artifacts_path) as f:
                artifacts_data = json.load(f)
                artifacts = artifacts_data.get("artifacts", [])
                themes = artifacts_data.get("themes", [])
        
        return DocumentGeometry(
            doc_id=doc_name,
            source_path=str(doc_dir),
            gravity_well=gravity_well,
            objects=objects,
            trajectory=trajectory,
            artifacts=artifacts,
            themes=themes,
        )
    
    def load_all(self) -> List[DocumentGeometry]:
        """Load all documents in output directory."""
        docs = []
        for subdir in self.output_dir.iterdir():
            if subdir.is_dir():
                doc = self.load_document(subdir.name)
                if doc is not None:
                    docs.append(doc)
        return docs
    
    def to_dragonfly_batch(
        self, doc: DocumentGeometry, prefix: str = "vec:"
    ) -> List[Tuple[str, np.ndarray]]:
        """Convert document geometry to Dragonfly key-value pairs."""
        
        pairs = []
        
        # Gravity well
        pairs.append((f"{prefix}{doc.doc_id}:gravity", doc.gravity_well))
        
        # Trajectory points
        for i, point in enumerate(doc.trajectory):
            pairs.append((f"{prefix}{doc.doc_id}:traj:{i:04d}", point))
        
        # Object embeddings
        for obj in doc.objects:
            if "embedding" in obj and "id" in obj:
                pairs.append(
                    (
                        f"{prefix}{doc.doc_id}:obj:{obj['id']}",
                        np.array(obj["embedding"], dtype=np.float32),
                    )
                )
        
        return pairs


# ============================================================
# TEMPLATE-BASED INTERPRETER (Replaces Qwen)
# ============================================================

class TemplateInterpreter:
    """
    Template-based interpreter for rotor decompositions.
    Replaces Qwen2-VL for torch-free operation.
    
    For production use with LLM capability, integrate with:
    - ONNX Runtime + quantized Qwen model
    - External API call to LLM service
    - Simplified rule-based system
    """
    
    def __init__(self, use_external_llm: bool = False):
        self.use_external_llm = use_external_llm
        
    def interpret(
        self,
        rotor_text: str,
        context: Dict[str, Any],
        question: Optional[str] = None,
        max_tokens: int = 256,
    ) -> str:
        """
        Interpret a rotor decomposition with context.
        Uses template-based interpretation (no torch needed).
        """
        
        # Build interpretation from context and rotor
        lines = [
            "## Geometric Transformation Interpretation",
            "",
            "### Rotor Analysis",
            rotor_text,
            "",
            "### Context",
            f"Source domain: {context.get('source_domain', 'unknown')}",
            f"BG3 coherence: {context.get('bg3_coherence', 0):.3f}",
            f"Global coherence: {context.get('global_coherence', 0):.3f}",
            f"Uncertainty: {context.get('uncertainty', 0):.3f}",
        ]
        
        if "active_concepts" in context:
            concepts = context["active_concepts"][:5]  # Top 5
            lines.append(f"Active concepts: {', '.join(concepts)}")
        
        if "nearest_attractors" in context:
            attractors = context["nearest_attractors"][:3]  # Top 3
            lines.append(f"Nearest Hopfield attractors: {', '.join(attractors)}")
        
        if "dissidences" in context:
            lines.append(f"Detected dissonances: {context['dissonances']}")
        
        lines.append("")
        
        # Generate interpretation based on metrics
        interpretation = self._generate_interpretation(context, rotor_text)
        lines.append("### Interpretation")
        lines.append(interpretation)
        
        return "\n".join(lines)
    
    def _generate_interpretation(self, context: Dict[str, Any], rotor_text: str) -> str:
        """Generate interpretation from metrics."""
        coherence = context.get('global_coherence', 0.5)
        bg3 = context.get('bg3_coherence', 0.5)
        uncertainty = context.get('uncertainty', 0.5)
        
        if coherence > 0.8 and bg3 > 0.7:
            return "The system exhibits high coherence and stability. This transformation represents a smooth, well-integrated conceptual shift."
        elif coherence > 0.6:
            return "Moderate coherence detected. The transformation indicates a meaningful but controlled conceptual evolution."
        elif uncertainty > 0.7:
            return "High uncertainty detected. This transformation may represent exploration of new conceptual territory."
        else:
            return "The transformation shows standard geometric properties. Continue monitoring system coherence."
    
    def interpret_trajectory(
        self,
        rotors: List[np.ndarray],
        decomposer: RotorDecomposer,
        context: Dict[str, Any],
    ) -> str:
        """Interpret a sequence of rotors as a narrative trajectory."""
        
        decompositions = [decomposer.decompose(r) for r in rotors]
        
        # Summarize trajectory
        angles = [np.degrees(d.rotation_angle) for d in decompositions]
        translations = [d.translation_magnitude for d in decompositions]
        
        trajectory_summary = [
            f"Trajectory length: {len(rotors)} transformations",
            f"Total rotation: {sum(angles):.1f}°",
            f"Mean rotation per step: {np.mean(angles):.2f}° (std: {np.std(angles):.2f}°)",
            f"Total translation: {sum(translations):.3f}",
            f"Mean translation per step: {np.mean(translations):.4f}",
        ]
        
        # Check for patterns
        if np.std(angles) < 5.0:
            trajectory_summary.append("Pattern: Steady rotation (low variance)")
        if any(a > 90 for a in angles):
            trajectory_summary.append("Pattern: Contains major reorientation (>90°)")
        
        prompt = "\n".join(
            [
                "## Trajectory Analysis",
                *trajectory_summary,
                "",
                "## First transformation",
                decomposer.to_text(decompositions[0]),
                "",
                "## Last transformation",
                decomposer.to_text(decompositions[-1]),
            ]
        )
        
        return self.interpret(
            prompt,
            context,
            question="Describe the overall geometric journey and what conceptual shift it represents.",
        )


# ============================================================
# ONNX ROTOR PREDICTOR (Replaces NoumenalEngine)
# ============================================================

class OnnxRotorPredictor:
    """
    ONNX-based rotor prediction (replaces PyTorch NoumenalEngine).
    """
    
    def __init__(self, model_path: str, toroidal_bridge_path: Optional[str] = None):
        self.session = None
        self.toroidal_bridge_session = None
        
        if not _ONNX_AVAILABLE:
            raise ImportError("onnxruntime not installed. Install with: pip install onnxruntime")
        
        # Load main rotor prediction model
        if model_path and Path(model_path).exists():
            self.session = ort.InferenceSession(
                model_path, providers=["CPUExecutionProvider"]
            )
            self.input_name = self.session.get_inputs()[0].name
        
        # Load toroidal bridge if available
        if toroidal_bridge_path and Path(toroidal_bridge_path).exists():
            self.toroidal_bridge_session = ort.InferenceSession(
                toroidal_bridge_path, providers=["CPUExecutionProvider"]
            )
    
    def predict(self, cga_input: np.ndarray) -> np.ndarray:
        """Predict rotor from CGA input."""
        if self.session is None:
            raise RuntimeError("ONNX model not loaded")
        
        # Ensure correct shape
        if cga_input.ndim == 1:
            cga_input = cga_input[np.newaxis, :]
        
        ort_inputs = {self.input_name: cga_input.astype(np.float32)}
        ort_outputs = self.session.run(None, ort_inputs)
        
        return ort_outputs[0].flatten()
    
    def predict_toroidal(self, state: np.ndarray) -> np.ndarray:
        """Predict using toroidal bridge."""
        if self.toroidal_bridge_session is None:
            raise RuntimeError("Toroidal bridge ONNX model not loaded")
        
        if state.ndim == 1:
            state = state[np.newaxis, :]
        
        input_name = self.toroidal_bridge_session.get_inputs()[0].name
        ort_inputs = {input_name: state.astype(np.float32)}
        ort_outputs = self.toroidal_bridge_session.run(None, ort_inputs)
        
        return ort_outputs[0].flatten()


# ============================================================
# MAIN INTEGRATION LOOP (ONNX + NumPy Version)
# ============================================================

class PythiaOnnxLoop:
    """
    Full integration using ONNX Runtime + NumPy (no torch).
    
    Components:
    - HeavyLifterLoader: Ingests processed document geometry
    - OnnxRotorPredictor: CGA rotor generation (replaces NoumenalEngine)
    - RotorDecomposer: Geometric primitive extraction
    - TemplateInterpreter: Interpretation (replaces Qwen)
    - HyperbolicKuramotoField: Oscillator dynamics + Poincaré attention
    """
    
    def __init__(
        self,
        engine_checkpoint: Path,
        heavy_lifter_output: Path,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        target_hz: float = 10.0,
        onnx_model_path: Optional[str] = None,
        toroidal_bridge_path: Optional[str] = None,
    ):
        self.target_hz = target_hz
        self.dt = 1.0 / target_hz
        
        # Load ONNX rotor predictor (replaces PyTorch NoumenalEngine)
        print("Loading ONNX Rotor Predictor...")
        
        # Try to extract ONNX from checkpoint, or use provided path
        onnx_path = onnx_model_path or str(engine_checkpoint).replace('.pt', '.onnx')
        toroidal_path = toroidal_bridge_path
        
        try:
            self.rotor_predictor = OnnxRotorPredictor(onnx_path, toroidal_path)
        except Exception as e:
            print(f"Warning: Could not load ONNX model: {e}")
            print("Using identity rotor predictor (for testing)")
            self.rotor_predictor = None
        
        # Initialize Kuramoto field (assumes HyperbolicKuramotoField is numpy-based)
        print("Initializing HyperbolicKuramotoField...")
        try:
            from services.neural_system.kuramoto_field import HyperbolicKuramotoField
            self.kuramoto = HyperbolicKuramotoField(
                n_monads=1000, poincare_dim=2, k_bg3=0.5, dt=self.dt
            )
            self.kuramoto.register_self("ARCA")
        except ImportError:
            print("Warning: HyperbolicKuramotoField not available")
            self.kuramoto = None
        
        # Load Hopfield attractors (from checkpoint if numpy-based)
        self.hopfield_patterns = {}
        self.attractor_names = []
        
        if engine_checkpoint.exists():
            try:
                # Try to load numpy checkpoint
                import pickle
                with open(engine_checkpoint, 'rb') as f:
                    checkpoint = pickle.load(f)
                    if "hopfield_state" in checkpoint:
                        self.hopfield_patterns = checkpoint["hopfield_state"]
                        self.attractor_names = list(self.hopfield_patterns.keys())
                        print(f"Loaded {len(self.attractor_names)} Hopfield attractors")
            except Exception as e:
                print(f"Note: Could not load checkpoint: {e}")
        
        # Initialize decomposer
        self.decomposer = RotorDecomposer()
        
        # Initialize interpreter (template-based, no torch)
        print("Initializing template interpreter...")
        self.interpreter = TemplateInterpreter()
        
        # Initialize Heavy Lifter loader
        self.loader = HeavyLifterLoader(heavy_lifter_output)
        
        # Redis for storing vectors
        self.redis = redis.Redis(
            host=redis_host, port=redis_port, decode_responses=False
        )
        
        # State tracking
        self.tick = 0
        self.rotor_history: List[np.ndarray] = []
        self.interpretation_history: List[str] = []
        
        print("PythiaOnnxLoop initialized (torch-free).")
    
    def ingest_document(self, doc_name: str) -> bool:
        """Ingest a document from Heavy Lifter output."""
        doc = self.loader.load_document(doc_name)
        if doc is None:
            print(f"Document not found: {doc_name}")
            return False
        
        # Store vectors in Redis
        pairs = self.loader.to_dragonfly_batch(doc)
        for key, vec in pairs:
            self.redis.set(key, vec.astype(np.float32).tobytes())
        
        print(f"Stored {len(pairs)} vectors for {doc_name}")
        
        # Create monad for document (if kuramoto available)
        if self.kuramoto:
            doc_monad = f"doc:{doc_name}"
            self.kuramoto.register_monad(doc_monad, natural_freq=1.0, uncertainty=0.3)
        
        print(f"Created monads for {doc_name}")
        return True
    
    def process_trajectory(self, doc_name: str) -> List[np.ndarray]:
        """Process a document's trajectory through the ONNX engine."""
        doc = self.loader.load_document(doc_name)
        if doc is None or len(doc.trajectory) == 0:
            return []
        
        rotors = []
        
        for i, point in enumerate(doc.trajectory):
            # Ensure correct dimension
            if len(point) > 512:
                point = point[:512]
            elif len(point) < 512:
                point = np.pad(point, (0, 512 - len(point)))
            
            # Lift to CGA (simplified - using identity if no model)
            if self.rotor_predictor:
                rotor = self.rotor_predictor.predict(point)
            else:
                # Fallback: use point directly as "rotor" (for testing)
                rotor = point[:32] if len(point) >= 32 else np.pad(point, (0, 32 - len(point)))
            
            rotors.append(rotor)
        
        return rotors
    
    def find_nearest_attractors(self, rotor: np.ndarray, k: int = 3) -> List[str]:
        """Find k nearest Hopfield attractors to a rotor."""
        if len(self.hopfield_patterns) == 0:
            return []
        
        distances = []
        for name, pattern in self.hopfield_patterns.items():
            if isinstance(pattern, np.ndarray):
                # Compare grade-1 components (the meaningful input structure)
                dist = np.linalg.norm(rotor[1:6] - pattern.flatten()[1:6])
                distances.append((name, dist))
        
        distances.sort(key=lambda x: x[1])
        return [name for name, _ in distances[:k]]
    
    def step(
        self,
        input_source: str = "kuramoto",
        interpret: bool = False,
        interpretation_question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute one tick of the integration loop."""
        
        self.tick += 1
        
        # Step Kuramoto dynamics
        kuramoto_metrics = {}
        if self.kuramoto:
            kuramoto_metrics = self.kuramoto.step()
        
        # Generate input for engine
        rotor_np = None
        
        if input_source == "kuramoto" and self.kuramoto:
            # Use Kuramoto phase state
            n_active = len(self.kuramoto.monad_names)
            if n_active >= 2:
                # Sample two phases as toroidal input
                idx1, idx2 = 0, min(1, n_active - 1)
                theta1 = self.kuramoto.phases[idx1]
                theta2 = self.kuramoto.phases[idx2]
                omega1 = self.kuramoto.natural_frequencies[idx1]
                omega2 = self.kuramoto.natural_frequencies[idx2]
                
                state = np.array([[theta1, theta2, omega1, omega2]], dtype=np.float32)
                
                # Use toroidal bridge if available
                if self.rotor_predictor and self.rotor_predictor.toroidal_bridge_session:
                    cga_input = self.rotor_predictor.predict_toroidal(state)
                else:
                    cga_input = np.zeros(32, dtype=np.float32)
                
                source_domain = "kuramoto_toroidal"
            else:
                cga_input = np.zeros(32, dtype=np.float32)
                source_domain = "null"
        else:
            # Load document vector from Redis
            key = f"vec:{input_source}:gravity"
            vec_bytes = self.redis.get(key)
            
            if vec_bytes:
                vec = np.frombuffer(vec_bytes, dtype=np.float32)
                if self.rotor_predictor:
                    cga_input = self.rotor_predictor.predict(vec)
                else:
                    cga_input = vec[:32] if len(vec) >= 32 else np.pad(vec, (0, 32 - len(vec)))
                source_domain = f"document:{input_source}"
            else:
                cga_input = np.zeros(32, dtype=np.float32)
                source_domain = "null"
        
        # Store rotor
        if rotor_np is None:
            rotor_np = cga_input  # Fallback
        
        self.rotor_history.append(rotor_np)
        if len(self.rotor_history) > 1000:
            self.rotor_history = self.rotor_history[-1000:]
        
        # Decompose rotor
        decomp = self.decomposer.decompose(rotor_np)
        rotor_text = self.decomposer.to_text(decomp)
        
        # Find nearest attractors
        nearest = self.find_nearest_attractors(rotor_np)
        
        # Build result
        result = {
            "tick": self.tick,
            "rotor": rotor_np.tolist(),
            "decomposition": {
                "rotation_angle": float(decomp.rotation_angle),
                "translation_magnitude": float(decomp.translation_magnitude),
                "scale_factor": float(decomp.scale_factor),
                "grade_energies": decomp.grade_energies,
            },
            "rotor_text": rotor_text,
            "source_domain": source_domain,
            "nearest_attractors": nearest,
            "kuramoto": kuramoto_metrics,
            "active_concepts": [],
        }
        
        # Optional interpretation
        if interpret:
            context = {
                "source_domain": source_domain,
                "bg3_coherence": kuramoto_metrics.get("bg3_coherence", 0),
                "global_coherence": kuramoto_metrics.get("global_coherence", 0),
                "uncertainty": np.mean(
                    self.kuramoto.uncertainties[: len(self.kuramoto.monad_names)]
                ) if self.kuramoto else 0.5,
                "active_concepts": result["active_concepts"],
                "nearest_attractors": nearest,
            }
            
            interpretation = self.interpreter.interpret(
                rotor_text, context, question=interpretation_question
            )
            
            result["interpretation"] = interpretation
            self.interpretation_history.append(interpretation)
        
        return result
    
    def run(
        self,
        n_ticks: int = 100,
        interpret_every: int = 10,
        callback: Optional[callable] = None,
    ) -> List[Dict]:
        """Run the integration loop for n ticks."""
        results = []
        tick_duration = 1.0 / self.target_hz
        
        for i in range(n_ticks):
            start_time = time.time()
            
            # Interpret periodically
            interpret = interpret_every > 0 and i % interpret_every == 0
            
            result = self.step(interpret=interpret)
            results.append(result)
            
            if callback:
                callback(result)
            
            # Rate limiting
            elapsed = time.time() - start_time
            if elapsed < tick_duration:
                time.sleep(tick_duration - elapsed)
        
        return results


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    """Example usage."""
    loop = PythiaOnnxLoop(
        engine_checkpoint=Path("checkpoints/arca_c2e_500.pt"),
        heavy_lifter_output=Path("heavy_lifter_output/"),
        target_hz=10.0,
    )
    
    # Ingest documents
    loop.ingest_document("tesla_longitudinal_waves")
    loop.ingest_document("schwarzschild_vortex")
    loop.ingest_document("biogeometry_karim")
    
    # Process a trajectory
    rotors = loop.process_trajectory("tesla_longitudinal_waves")
    print(f"Generated {len(rotors)} rotors from Tesla trajectory")
    
    # Run integration loop
    def on_tick(result):
        if "interpretation" in result:
            print(f"\n[Tick {result['tick']}] Interpretation: {result['interpretation'][:200]}...")
        else:
            print(f"[Tick {result['tick']}] BG3: {result['kuramoto'].get('bg3_coherence', 0):.3f}")
    
    results = loop.run(n_ticks=100, interpret_every=25, callback=on_tick)
    
    print("\n=== Final State ===")
    print(json.dumps({
        "tick": loop.tick,
        "n_rotors_stored": len(loop.rotor_history),
        "n_interpretations": len(loop.interpretation_history),
    }, indent=2))


if __name__ == "__main__":
    main()
