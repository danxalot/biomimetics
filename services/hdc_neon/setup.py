from setuptools import setup, Extension
import platform

# Only compile with NEON flags if on ARM64
extra_args = []
if platform.machine() == 'arm64':
    extra_args = ['-march=armv8-a+simd', '-O3']

module = Extension(
    'hdc_neon',
    sources=['src/hdc_neon.c'],
    extra_compile_args=extra_args
)

setup(
    name='hdc_neon',
    version='1.0',
    description='NEON-optimized HDC primitives for ARCA',
    ext_modules=[module]
)
