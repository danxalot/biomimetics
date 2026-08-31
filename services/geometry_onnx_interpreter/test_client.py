"""
Test client for Geometry ONNX Interpreter Service

Demonstrates how to:
1. Format input data from recursive_ingestion.py output
2. Call the ONNX interpreter API
3. Process the interpretation results
"""

import json
import requests
from typing import Dict, Any


def format_sample_solar_system() -> Dict[str, Any]:
    """
    Create a sample solar system data structure matching recursive_ingestion.py output.

    This format is what recursive_ingestion.py produces.
    """
    return {
        "system_id": "test_document_001",
        "gravity_well": {"concept": "document_analysis", "mass": 5},
        "objects": [
            {
                "id": "concept:system_coherence",
                "mass": 0.8,
                "position": [0.0, 0.0, 0.0],
                "desc": "Core system coherence concept",
            },
            {
                "id": "concept:user_intent",
                "mass": 0.6,
                "position": [1.5, 0.2, 0.1],
                "desc": "User intent and goals",
            },
            {
                "id": "concept:data_pattern",
                "mass": 0.5,
                "position": [-0.5, 1.0, 0.3],
                "desc": "Key data patterns detected",
            },
            {
                "id": "concept:anomaly_detection",
                "mass": 0.3,
                "position": [0.8, -0.5, 0.2],
                "desc": "Potential anomaly flags",
            },
        ],
        "trajectory": [0.1, 0.2, 0.0],
    }


def test_onnx_only(api_url: str = "http://localhost:8096"):
    """Test ONNX model only (no Qwen3VL interpretation)."""
    print("=" * 60)
    print("TEST 1: ONNX Model Only")
    print("=" * 60)

    solar_system = format_sample_solar_system()

    response = requests.post(
        f"{api_url}/interpret/onnx_only",
        json=solar_system,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ ONNX inference completed")
        print(f"   Vector: {result['vector']}")
        print(f"   Confidence: {result['confidence']:.4f}")
        print(f"   Energy: {result['energy']:.4f}")
        print(f"   Inference time: {result['inference_time_ms']:.2f}ms")
        return result
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None


def test_full_pipeline(api_url: str = "http://localhost:8096"):
    """Test full pipeline: ONNX + Qwen3VL interpretation."""
    print("\n" + "=" * 60)
    print("TEST 2: Full Pipeline (ONNX + Qwen3VL)")
    print("=" * 60)

    solar_system = format_sample_solar_system()

    response = requests.post(
        f"{api_url}/interpret/predict",
        json=solar_system,
        headers={"Content-Type": "application/json"},
        timeout=120,  # Longer timeout for Qwen3VL
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Full pipeline completed")
        print(f"   System ID: {result['system_id']}")
        print(f"   Processing time: {result['processing_time_ms']:.2f}ms")
        print()
        print("   ONNX Output:")
        print(f"     - Vector: {result['onnx_output']['vector']}")
        print(f"     - Confidence: {result['onnx_output']['confidence']:.4f}")
        print(f"     - Energy: {result['onnx_output']['energy']:.4f}")
        print()
        print("   Qwen3VL Interpretation:")
        print(f"     Summary: {result['qwen3vl_interpretation']['summary']}")
        print(f"     Key Insights: {result['qwen3vl_interpretation']['key_insights']}")
        print(
            f"     Recommendations: {result['qwen3vl_interpretation']['recommendations']}"
        )
        return result
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None


def test_batch_processing(api_url: str = "http://localhost:8096"):
    """Test batch processing."""
    print("\n" + "=" * 60)
    print("TEST 3: Batch Processing")
    print("=" * 60)

    # Create multiple solar systems
    batch_input = {
        "items": [
            format_sample_solar_system(),
            {**format_sample_solar_system(), "system_id": "test_document_002"},
            {**format_sample_solar_system(), "system_id": "test_document_003"},
        ]
    }

    response = requests.post(
        f"{api_url}/interpret/batch",
        json=batch_input,
        headers={"Content-Type": "application/json"},
        timeout=180,  # Longer timeout for batch
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Batch processing completed")
        print(f"   Total items: {len(result['results'])}")
        print(f"   Total time: {result['total_time_ms']:.2f}ms")
        print()
        for i, item in enumerate(result["results"]):
            print(f"   Item {i + 1}: {item['system_id']}")
            print(f"     - ONNX confidence: {item['onnx_output']['confidence']:.4f}")
            print(
                f"     - Qwen3VL summary: {item['qwen3vl_interpretation']['summary'][:60]}..."
            )
        return result
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None


def test_health_check(api_url: str = "http://localhost:8096"):
    """Test service health check."""
    print("\n" + "=" * 60)
    print("TEST 4: Health Check")
    print("=" * 60)

    response = requests.get(f"{api_url}/interpret/health", timeout=5)

    if response.status_code == 200:
        health = response.json()
        print(f"✅ Service is {health['status']}")
        print(f"   ONNX loaded: {health['onnx_loaded']}")
        print(f"   MCP Satellite: {health['mcp_satellite_url']}")
        print(f"   Mode: {health['mode']}")
        return health
    else:
        print(f"❌ Health check failed: {response.status_code}")
        return None


def test_model_info(api_url: str = "http://localhost:8096"):
    """Test getting model information."""
    print("\n" + "=" * 60)
    print("TEST 5: Model Information")
    print("=" * 60)

    response = requests.get(f"{api_url}/interpret/model_info", timeout=5)

    if response.status_code == 200:
        info = response.json()
        print(f"✅ Model info retrieved")
        print(f"   Model path: {info['model_path']}")
        print(f"   Input shape: {info['input_shape']}")
        print(f"   Output shape: {info['output_shape']}")
        return info
    else:
        print(f"❌ Model info failed: {response.status_code} - {response.text}")
        return None


def main():
    """Run all tests."""
    api_url = "http://localhost:8096"

    print("Geometry ONNX Interpreter - Test Client")
    print("=" * 60)

    # Test 1: Health check
    test_health_check(api_url)

    # Test 2: Model info
    test_model_info(api_url)

    # Test 3: ONNX only
    test_onnx_only(api_url)

    # Test 4: Full pipeline
    test_full_pipeline(api_url)

    # Test 5: Batch processing
    test_batch_processing(api_url)

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
