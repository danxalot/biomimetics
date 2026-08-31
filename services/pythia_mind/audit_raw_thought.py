import urllib.request
import json
import numpy as np

PYTHIA_CORE_URL = "http://100.70.0.13:8086"
print("[*] Polling /concept/focus for raw thought...")
try:
    req = urllib.request.Request(f"{PYTHIA_CORE_URL}/concept/focus", method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    vector = data.get("hv_signature") or data.get("vector")
    if vector:
        arr = np.array(vector, dtype=np.float32)
        print(f"--- RAW 10,000D MANIFOLD STATE ---")
        print(f"L2 Norm:  {np.linalg.norm(arr):.4f}")
        print(f"Variance: {np.var(arr):.6f}")
        print(f"Min Val:  {np.min(arr):.6f}")
        print(f"Max Val:  {np.max(arr):.6f}")
    else:
        print("[!] No vector found in payload.")
except Exception as e:
    print(f"[!] Endpoint failure: {e}")