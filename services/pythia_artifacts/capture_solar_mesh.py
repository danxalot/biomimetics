# Direct URL/Endpoint: http://127.0.0.1:8096/interpret/full_pipeline
import json

import requests


def capture_mesh_diagnostics(data_path: str):
    url = "http://127.0.0.1:8096/interpret/full_pipeline"

    with open(data_path, "r") as f:
        solar_data = json.load(f)

    # Structuring based on your ONNX interpreter payload requirements
    payload = {
        "system_id": "solar_system_diagnostic",
        "objects": solar_data.get("objects", []),
        "trajectory": solar_data.get("trajectory", []),
    }

    try:
        print(f"Routing data to ONNX Interpreter at {url}...")
        response = requests.post(
            url, json=payload, headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()

        result = response.json()

        summary = {
            "kuramoto_coherence": result.get(
                "kuramoto_order_parameter", "Metric not returned by API"
            ),
            "topological_loss": result.get(
                "betti_void_loss", "Metric not returned by API"
            ),
            "hamiltonian_energy": result.get(
                "hamiltonian_energy", "Metric not returned by API"
            ),
        }

        print(json.dumps(summary, indent=2))
        return summary

    except requests.exceptions.RequestException as e:
        print(f"Mesh API routing failed: {e}")


if __name__ == "__main__":
    # Adjust path to your actual Solar System JSON
    capture_mesh_diagnostics("data/SolarSystem.json")
