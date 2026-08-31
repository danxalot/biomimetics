#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>

#ifdef __aarch64__
#include <arm_neon.h>
#endif

// -----------------------------------------------------------------------------
// Core Logic: Bind (XOR)
// -----------------------------------------------------------------------------

/*
 * Binds two binary hypervectors (packed as uint8 bytes) using XOR.
 * For HDC, binding is usually XOR.
 * If inputs are packed bits (1 bit = 1 dimension), XOR works directly on bytes.
 * If inputs are byte-per-dimension (0 or 1), XOR also works logically 0^0=0, 1^1=0, 1^0=1.
 */
static void xor_arrays(const unsigned char* a, const unsigned char* b, unsigned char* out, Py_ssize_t len) {
    Py_ssize_t i = 0;

#ifdef __aarch64__
    // NEON Optimization: Process 16 bytes (128 bits) at a time
    for (; i <= len - 16; i += 16) {
        uint8x16_t va = vld1q_u8(a + i);
        uint8x16_t vb = vld1q_u8(b + i);
        uint8x16_t vout = veorq_u8(va, vb);
        vst1q_u8(out + i, vout);
    }
#endif

    // Fallback / Cleanup loop
    for (; i < len; i++) {
        out[i] = a[i] ^ b[i];
    }
}

// -----------------------------------------------------------------------------
// Core Logic: Similarity (Hamming Distance) for Binary Vectors
// -----------------------------------------------------------------------------

/*
 * Calculates Hamming Distance between two packed binary vectors.
 * Returns the count of different bits.
 */
static long hamming_distance(const unsigned char* a, const unsigned char* b, Py_ssize_t len) {
    long dist = 0;
    Py_ssize_t i = 0;

#ifdef __aarch64__
    // NEON Optimization
    uint64_t total_bits = 0;
    for (; i <= len - 16; i += 16) {
        uint8x16_t va = vld1q_u8(a + i);
        uint8x16_t vb = vld1q_u8(b + i);
        uint8x16_t diff = veorq_u8(va, vb); // XOR detects differences
        uint8x16_t counts = vcntq_u8(diff); // Count set bits per byte
        
        // Sum across vector. vaddlvq_u8 sums 16 uint8s into one uint16? 
        // Note: vaddlvq_u8 returns uint32_t sum of all elements in uint8x16_t (AArch64 only).
        total_bits += vaddlvq_u8(counts);
    }
    dist = (long)total_bits;
#endif

    // Fallback
    for (; i < len; i++) {
        unsigned char diff = a[i] ^ b[i];
        // Builtin popcount is usually fast on modern x86 too
        dist += __builtin_popcount(diff);
    }
    
    return dist;
}

// -----------------------------------------------------------------------------
// Python Wrapper Functions
// -----------------------------------------------------------------------------

static PyObject* bind_native(PyObject* self, PyObject* args) {
    Py_buffer view_a, view_b, view_out;

    if (!PyArg_ParseTuple(args, "w*y*y*", &view_out, &view_a, &view_b)) {
        return NULL;
    }

    if (view_a.len != view_b.len || view_a.len != view_out.len) {
        PyErr_SetString(PyExc_ValueError, "All buffers must have the same length");
        goto error;
    }

    xor_arrays((unsigned char*)view_a.buf, (unsigned char*)view_b.buf, (unsigned char*)view_out.buf, view_a.len);

    PyBuffer_Release(&view_a);
    PyBuffer_Release(&view_b);
    PyBuffer_Release(&view_out);
    
    Py_RETURN_NONE;

error:
    PyBuffer_Release(&view_a);
    PyBuffer_Release(&view_b);
    PyBuffer_Release(&view_out);
    return NULL;
}

static PyObject* hamming_native(PyObject* self, PyObject* args) {
    Py_buffer view_a, view_b;

    if (!PyArg_ParseTuple(args, "y*y*", &view_a, &view_b)) {
        return NULL;
    }

    if (view_a.len != view_b.len) {
        PyErr_SetString(PyExc_ValueError, "Buffers must be same length");
        PyBuffer_Release(&view_a);
        PyBuffer_Release(&view_b);
        return NULL;
    }

    long dist = hamming_distance((unsigned char*)view_a.buf, (unsigned char*)view_b.buf, view_a.len);

    PyBuffer_Release(&view_a);
    PyBuffer_Release(&view_b);

    return PyLong_FromLong(dist);
}

// -----------------------------------------------------------------------------
// Module Definition
// -----------------------------------------------------------------------------

static PyMethodDef HDCOpsMethods[] = {
    {"bind_native",  bind_native, METH_VARARGS, "Apply XOR Binding (Native). Args: (out, a, b)"},
    {"hamming_native", hamming_native, METH_VARARGS, "Calculate Hamming Distance. Args: (a, b)"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef hdcopsmodule = {
    PyModuleDef_HEAD_INIT,
    "hdc_ops_native",   /* name of module */
    "Native C extension for HDC operations (NEON Optimized)", /* module documentation */
    -1,       /* size of per-interpreter state of the module */
    HDCOpsMethods
};

PyMODINIT_FUNC PyInit_hdc_ops_native(void) {
    return PyModule_Create(&hdcopsmodule);
}
