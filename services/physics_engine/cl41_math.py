import numpy as np

def get_cl41_cayley():
    """
    Generate the Cayley table for Cl(4,1) geometric product.
    Basis elements are represented as bitmasks (0-31).
    Metric: e1^2=e2^2=e3^2=e4^2=1, e5^2=-1.
    """
    # 32 basis elements
    # Bit i set means e_{i+1} is present
    basis_dim = 5
    n_elements = 1 << basis_dim
    
    # Table of (index_res, sign)
    table = np.zeros((n_elements, n_elements, 2), dtype=np.int32)
    
    metric = np.array([1, 1, 1, 1, -1])
    
    for i in range(n_elements):
        for j in range(n_elements):
            res_mask = i ^ j
            sign = 1
            
            # Multiplication of basis elements
            # e_i * e_j
            # We move each bit of j to the left to its sorted position
            temp_i = i
            temp_j = j
            
            # For each bit in j, move it past bits in i
            for bit_j in range(basis_dim):
                if not (temp_j & (1 << bit_j)):
                    continue
                
                # Bit bit_j is in j. Move it past all bits in i that are > bit_j
                for bit_i in range(bit_j + 1, basis_dim):
                    if temp_i & (1 << bit_i):
                        sign *= -1
                
                # If bit_j is also in i, they square
                if temp_i & (1 << bit_j):
                    sign *= metric[bit_j]
            
            table[i, j, 0] = res_mask
            table[i, j, 1] = sign
            
    return table

_CAYLEY_TABLE = get_cl41_cayley()

def geometric_product(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Pure NumPy geometric product for Cl(4,1).
    a, b: multivectors of shape (..., 32)
    """
    orig_shape = a.shape
    if a.ndim == 1:
        a_flat = a.reshape(1, 32)
    else:
        a_flat = a.reshape(-1, 32)
        
    if b.ndim == 1:
        b_flat = b.reshape(1, 32)
    else:
        b_flat = b.reshape(-1, 32)
        
    B = a_flat.shape[0]
    res_flat = np.zeros((B, 32), dtype=np.float32)
    
    # Using the Cayley table to perform the multiplication
    for i in range(32):
        ai = a_flat[:, i]
        for j in range(32):
            k = _CAYLEY_TABLE[i, j, 0]
            sign = _CAYLEY_TABLE[i, j, 1]
            res_flat[:, k] += ai * b_flat[:, j] * sign
            
    if a.ndim == 1:
        return res_flat[0]
    return res_flat.reshape(orig_shape)

def reverse(a: np.ndarray) -> np.ndarray:
    """
    Reverse of a multivector.
    a: multivector of shape (..., 32)
    """
    orig_shape = a.shape
    if a.ndim == 1:
        a_flat = a.reshape(1, 32)
    else:
        a_flat = a.reshape(-1, 32)
        
    res_flat = a_flat.copy()
    for i in range(32):
        # Count bits (grade k)
        k = bin(i).count('1')
        if (k * (k - 1) // 2) % 2 == 1:
            res_flat[:, i] *= -1
            
    if a.ndim == 1:
        return res_flat[0]
    return res_flat.reshape(orig_shape)

def sandwich_product(r: np.ndarray, m: np.ndarray) -> np.ndarray:
    """
    Geometric sandwich product: R * M * ~R.
    r: rotor (..., 32)
    m: multivector (..., 32)
    """
    # R * M
    rm = geometric_product(r, m)
    # (R * M) * ~R
    return geometric_product(rm, reverse(r))
