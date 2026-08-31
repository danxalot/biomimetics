import numpy as np
import hashlib
import re
try:
    from .hdc_native import bind as c_bind, similarity as c_similarity
    HAS_NATIVE = True
except ImportError:
    HAS_NATIVE = False

class HDCEngine:
    """
    A NumPy-based Hyperdimensional Computing (VSA) Engine.
    Implements MAP (Multiply-Add-Permute) architecture.
    """
    def __init__(self, dimensionality=10000):
        self.D = dimensionality
        # Use a fixed seed for reproducibility of base vectors if needed, 
        # but generally we want distinct runs or persistent bases.
        # For now, we generate on the fly or deterministic hashing.
        self.rng = np.random.default_rng(42)
        # Cache for basis vectors (deterministic by name)
        self._basis_cache = {}

    def _hash_to_seed(self, name: str) -> int:
        """Creates a deterministic seed from a string name."""
        hash_digest = hashlib.sha256(name.encode('utf-8')).hexdigest()
        return int(hash_digest[:8], 16)

    def get_basis(self, name: str):
        """
        Returns a deterministic basis hypervector for a given concept name.
        Always returns the same vector for the same name.
        """
        if name not in self._basis_cache:
            seed = self._hash_to_seed(name)
            local_rng = np.random.default_rng(seed)
            self._basis_cache[name] = local_rng.choice([-1.0, 1.0], size=self.D).astype(np.float32)
        return self._basis_cache[name]

    def create_hypervector(self):
        """Generates a random bipolar hypervector {-1, 1}."""
        # We use float32 for easier math (cosine sim), but values are -1.0 or 1.0
        return self.rng.choice([-1.0, 1.0], size=self.D).astype(np.float32)

    def bind(self, v1, v2):
        """
        Binding operation (Element-wise multiplication).
        In binary (XOR), in bipolar (Multiplication).
        Associative, Commutative, Distributive.
        Preserves distance (dissimilar to inputs).
        """
        return np.multiply(v1, v2)

    def bundle(self, vectors):
        """
        Bundling operation (Element-wise Sum).
        Creates a superposition similar to inputs.
        """
        if not vectors:
            return np.zeros(self.D, dtype=np.float32)
        
        # Sum
        result = np.sum(vectors, axis=0)
        
        # Bipolarize / Normalize (Sign function)
        # We keep it as 'soft' bundle (integers) for better capacity or hard bundle?
        # For "Lossless Accumulator", keeping the sum (magnitude) is better to retrieve oldest memories,
        # but standard HDC usually normalizes. 
        # Let's use the sign function to keep it bipolar for stability in recursive ops,
        # OR keep it as float for "analog" memory. 
        # Let's use soft clamping or simple sign to stick to canonical HDC.
        # Result = sign(sum)
        result = np.sign(result)
        # Handle zeros (randomly assign 1 or -1, or 0)
        result[result == 0] = 1.0 
        return result

    def permute(self, v, shifts=1):
        """
        Permutation (Cyclic Shift).
        Encodes sequence/order.
        """
        return np.roll(v, shifts)

    def similarity(self, v1, v2):
        """Cosine similarity."""
        if v1 is None or v2 is None: return 0.0
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0: return 0.0
        return np.dot(v1, v2) / (norm1 * norm2)

    def bind_native(self, v1, v2):
        """
        Native Binding (XOR) using NEON if available.
        Requires inputs to be uint8 (packed or distinct bytes).
        """
        if HAS_NATIVE:
            return c_bind(v1, v2)
        else:
            # Fallback for uint8 arrays if c_bind missing (unlikely due to wrapper)
            return np.bitwise_xor(v1, v2)

    def similarity_native(self, v1, v2):
        """
        Native Similarity (Hamming -> Cosine) using NEON if available.
        """
        if HAS_NATIVE:
            return c_similarity(v1, v2)
        else:
            # Fallback
            dist = np.sum(np.bitwise_xor(v1, v2)) # Assuming unpacked 0/1 for simplicity in fallback
            total = len(v1)
            return 1.0 - 2.0 * (dist / total)

class AFLASHEncoder:
    """
    Adaptive Feature Learning via Associative Holographic Structures.
    Encodes text into hypervectors.
    """
    def __init__(self, hdc_engine: HDCEngine):
        self.hdc = hdc_engine
        self.token_cache = {}
        
    def _hash_to_seed(self, token):
        """Creates a deterministic seed from a string token."""
        hash_digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
        # Take first 8 chars (32 bits)
        return int(hash_digest[:8], 16)

    def get_token_vector(self, token):
        """Returns a deterministic hypervector for a given token."""
        if token not in self.token_cache:
            # Deterministic generation based on token hash
            seed = self._hash_to_seed(token)
            local_rng = np.random.default_rng(seed)
            self.token_cache[token] = local_rng.choice([-1.0, 1.0], size=self.hdc.D).astype(np.float32)
        return self.token_cache[token]

    def encode_text(self, text):
        """
        Encodes a string into a sentence hypervector.
        Uses Bag-of-Words (BoW) encoding for robust keyword matching.
        V_sentence = Sum(V_word)
        """
        tokens = re.findall(r'\w+', text.lower())
        if not tokens:
            return np.zeros(self.hdc.D, dtype=np.float32)
            
        vector_sum = np.zeros(self.hdc.D, dtype=np.float32)
        
        for token in tokens:
            token_vec = self.get_token_vector(token)
            # Simple Bundle (Superposition) for BoW
            vector_sum = np.add(vector_sum, token_vec)
            
        # Normalize (Bipolarize)
        result = np.sign(vector_sum)
        result[result == 0] = 1.0
        return result
