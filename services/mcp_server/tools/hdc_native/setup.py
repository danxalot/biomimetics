from setuptools import setup, Extension
import sys
import platform

extra_compile_args = ["-O3"]
if platform.machine() == "aarch64" or platform.machine() == "arm64":
    extra_compile_args.append("-march=armv8-a+simd")  # Enable NEON

module = Extension(
    "services.mcp_server.tools.hdc_native.hdc_ops_native",
    sources=["services/mcp_server/tools/hdc_native/hdc_ops.c"],
    include_dirs=["."],
    extra_compile_args=extra_compile_args
)

setup(
    name="hdc_native",
    version="0.1.0",
    description="Native C extension for HDC operations (NEON Optimized)",
    ext_modules=[module]
)
