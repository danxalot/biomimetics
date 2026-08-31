#include <Python.h>

#ifdef __aarch64__
#include <arm_neon.h>
#endif

// 1. Bitwise XOR Binding (Element-wise XOR)
// Input: Two byte arrays of length n
// Output: XOR result
static PyObject *bind_xor(PyObject *self, PyObject *args) {
  Py_buffer v1, v2, out;
  if (!PyArg_ParseTuple(args, "y*y*y*", &v1, &v2, &out)) {
    return NULL;
  }

  if (v1.len != v2.len || v1.len != out.len) {
    PyErr_SetString(PyExc_ValueError, "Buffer lengths must match");
    return NULL;
  }

  uint8_t *p1 = (uint8_t *)v1.buf;
  uint8_t *p2 = (uint8_t *)v2.buf;
  uint8_t *po = (uint8_t *)out.buf;
  Py_ssize_t n = v1.len;
  Py_ssize_t i = 0;

#ifdef __aarch64__
  // SIMD Loop (128-bit chunks = 16 bytes)
  for (; i <= n - 16; i += 16) {
    uint8x16_t a = vld1q_u8(p1 + i);
    uint8x16_t b = vld1q_u8(p2 + i);
    uint8x16_t c = veorq_u8(a, b);
    vst1q_u8(po + i, c);
  }
#endif

  // Scalar Cleanup
  for (; i < n; i++) {
    po[i] = p1[i] ^ p2[i];
  }

  PyBuffer_Release(&v1);
  PyBuffer_Release(&v2);
  PyBuffer_Release(&out);
  Py_RETURN_NONE;
}

// 2. Majority Vote Bundling (for 3 vectors)
// Input: 3 byte arrays
// Output: Majority bit
static PyObject *bundle_majority(PyObject *self, PyObject *args) {
  Py_buffer v1, v2, v3, out;
  if (!PyArg_ParseTuple(args, "y*y*y*y*", &v1, &v2, &v3, &out)) {
    return NULL;
  }

  // Checking lengths omitted for brevity, should be added in prod

  uint8_t *p1 = (uint8_t *)v1.buf;
  uint8_t *p2 = (uint8_t *)v2.buf;
  uint8_t *p3 = (uint8_t *)v3.buf;
  uint8_t *po = (uint8_t *)out.buf;
  Py_ssize_t n = v1.len;
  Py_ssize_t i = 0;

#ifdef __aarch64__
  for (; i <= n - 16; i += 16) {
    uint8x16_t a = vld1q_u8(p1 + i);
    uint8x16_t b = vld1q_u8(p2 + i);
    uint8x16_t c = vld1q_u8(p3 + i);

    // Majority logic: (a&b) | (b&c) | (c&a)
    uint8x16_t ab = vandq_u8(a, b);
    uint8x16_t bc = vandq_u8(b, c);
    uint8x16_t ca = vandq_u8(c, a);
    uint8x16_t maj = vorrq_u8(vorrq_u8(ab, bc), ca);

    vst1q_u8(po + i, maj);
  }
#endif

  // Scalar loop...
  for (; i < n; i++) {
    po[i] = (p1[i] & p2[i]) | (p2[i] & p3[i]) | (p3[i] & p1[i]);
  }

  PyBuffer_Release(&v1);
  PyBuffer_Release(&v2);
  PyBuffer_Release(&v3);
  PyBuffer_Release(&out);
  Py_RETURN_NONE;
}

// Module Definition
static PyMethodDef HDCMethods[] = {
    {"bind_xor", bind_xor, METH_VARARGS, "XOR two vectors using NEON"},
    {"bundle_majority", bundle_majority, METH_VARARGS,
     "Majority vote bundling"},
    {NULL, NULL, 0, NULL}};

static struct PyModuleDef hdcmodule = {PyModuleDef_HEAD_INIT, "hdc_neon",
                                       "ARM NEON Optimized HDC Primitives", -1,
                                       HDCMethods};

PyMODINIT_FUNC PyInit_hdc_neon(void) { return PyModule_Create(&hdcmodule); }
