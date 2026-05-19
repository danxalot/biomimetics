import time
import numpy as np
import redis
import logging
import os
import json
import urllib.request
import urllib.error

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("AutonomicWatchdog")

API_BASE_URL = os.environ.get('API_BASE_URL', 'http://neural_system:8086')
VITALS_URL = f"{API_BASE_URL}/system/vitals"
RESONANCE_URL = f"{API_BASE_URL}/resonance"
TICK_URL = f"{API_BASE_URL}/tick"

# Ensure we hit the OCI Redis container with the Hamiltonians (not dragonfly)
REDIS_HOST = os.environ.get('REDIS_HOST', 'pythia_redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

PULSE_RATE = 1.0  # 1Hz Heartbeat

def post_json(url, data):
    """Helper to post JSON using urllib."""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=2) as response:
        return json.loads(response.read().decode("utf-8")), response.getcode()

def get_json(url):
    """Helper to get JSON using urllib."""
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8")), response.getcode()

def get_coupling_strength(energy: float) -> float:
    """Modulate injection strength based on metabolic energy (Allostasis)."""
    if energy < 1.0:
        return 1.00  # Hypometabolic: Wake up aggressively
    elif energy > 4.0:
        return 0.08  # Hypermetabolic: Back off to cool down
    else:
        return 0.80  # Stable Target Range (80% coupling strength to minimize damping)

def start_watchdog():
    logger.info(f"[*] Awakening Autonomic Watchdog (urllib variant)...")
    logger.info(f"[*] Target Vitals: {VITALS_URL}")
    logger.info(f"[*] Target Redis: {REDIS_HOST}:{REDIS_PORT}")

    try:
        r_store = redis.Redis(
            host=REDIS_HOST, 
            port=REDIS_PORT, 
            db=0, 
            decode_responses=False
        )
        # Verify connection
        r_store.ping()
        logger.info("[+] Connected to Pythia Redis (Hamiltonian Store)")
    except Exception as e:
        logger.error(f"[!] Redis connection failed: {e}")
        # We will attempt fallback inside the loop if Redis is dead
        r_store = None

    while True:
        try:
            # 1. Poll Vitals
            energy = 0.0
            try:
                vitals, code = get_json(VITALS_URL)
                if code == 200:
                    energy = vitals.get("hamiltonian_energy", 0.0)
                else:
                    logger.warning(f"Vitals endpoint returned {code}")
            except Exception as e:
                logger.warning(f"Failed to poll vitals: {e}")

            # 2. Calculate Dynamic Coupling
            coupling = get_coupling_strength(energy)
            
            # 3. Generate fresh random 256D Hamiltonian pulse each cycle for a net random shape imprint
            vec_256 = np.random.randn(256).astype(np.float32)
            norm = np.linalg.norm(vec_256) + 1e-12
            vec_256 = vec_256 / norm

            # 5. Inject Pulse
            try:
                # Apply coupling strength before injection
                pulse_vector = (vec_256 * coupling).tolist()
                
                res_data, res_code = post_json(RESONANCE_URL, {"vector": pulse_vector})
                
                if res_code == 200:
                    logger.info(
                        f"Pulse Injected | Energy: {energy:.2f} | Coupling: {coupling:.2f} | L2: {res_data.get('l2_norm', 0):.4f}"
                    )
                else:
                    logger.warning(f"Resonance injection failed: {res_code}")
                
                # 6. Trigger Heartbeat Tick
                tick_data, tick_code = post_json(TICK_URL, {})
                if tick_code == 200:
                    logger.info(f"Tick {tick_data.get('tick')} | Coherence: {tick_data.get('coherence'):.4f}")
                else:
                    logger.warning(f"Tick failed: {tick_code}")

            except Exception as e:
                logger.error(f"Injection/Tick failure: {e}")

        except Exception as e:
            logger.critical(f"Watchdog Loop Error: {e}")

        time.sleep(PULSE_RATE)

if __name__ == "__main__":
    start_watchdog()
