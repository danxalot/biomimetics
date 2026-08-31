import numpy as np
import logging

logger = logging.getLogger(__name__)

HAS_NATIVE = False

try:
    from .hdc_ops_native import bind_native as _c_bind, hamming_native as _c_hamming
    HAS_NATIVE = True
    logger.info("✅ HDC Native Extension loaded (NEON/C)")
except ImportError:
    logger.warning("⚠️ HDC Native Extension NOT loaded. Using NumPy fallback (Slow).")
    
    def _c_bind(out, a, b):
        """NumPy Fallback for XOR Binding"""
        # Convert bytes to numpy array of uint8 if strictly needed, 
        # but here we assume 'a' and 'b' are bytes-like objects compatible with buffer protocol.
        # But wait, the C extension expects buffers.
        # For python fallback, inputs might be memoryviews or bytes.
        
        # This fallback mimics the C signature: out is a writable buffer.
        # Ideally, we manipulate the buffer directly.
        
        arr_a = np.frombuffer(a, dtype=np.uint8)
        arr_b = np.frombuffer(b, dtype=np.uint8)
        arr_out = np.frombuffer(out, dtype=np.uint8)
        
        # In-place XOR
        np.bitwise_xor(arr_a, arr_b, out=arr_out)

    def _c_hamming(a, b):
        """NumPy Fallback for Hamming Distance"""
        arr_a = np.frombuffer(a, dtype=np.uint8)
        arr_b = np.frombuffer(b, dtype=np.uint8)
        
        # XOR
        diff = np.bitwise_xor(arr_a, arr_b)
        
        # Count bits set.
        # NumPy doesn't have a fast generic 'popcount' for uint8 arrays until recently (unpackbits is slow).
        # We can use a lookup table for speed or unpacking.
        # Actually, standard np.unpackbits is okayish.
        bits = np.unpackbits(diff)
        return int(np.sum(bits))

def bind(vector_a, vector_b):
    """
    Binds two vectors using XOR.
    Args:
        vector_a, vector_b: numpy arrays (uint8 packed or unpacked).
    Returns:
        New vector.
    """
    # Ensure contiguous C-order bytes
    a_bytes = vector_a.tobytes()
    b_bytes = vector_b.tobytes()
    
    # Pre-allocate output buffer
    out_buf = bytearray(len(a_bytes))
    
    _c_bind(out_buf, a_bytes, b_bytes)
    
    # Convert back to numpy
    return np.frombuffer(out_buf, dtype=vector_a.dtype)

def similarity(vector_a, vector_b):
    """
    Calculates Cosine Similarity via Hamming Distance.
    Sim = 1 - 2 * (HammingDist / TotalBits)
    """
    a_bytes = vector_a.tobytes()
    b_bytes = vector_b.tobytes()
    
    dist_bits = _c_hamming(a_bytes, b_bytes)
    
    # Total bits
    # if vector is unpacked {0, 1}, len(bytes) == dimensions.
    # if vector is packed, len(bytes) * 8 == dimensions.
    # Logic in _c_hamming just counts bit diffs.
    
    # Assuming packed/byte level:
    total_bits = len(a_bytes) * 8
    
    return 1.0 - 2.0 * (float(dist_bits) / float(total_bits))
