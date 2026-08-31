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
        return 0.20  # Hypometabolic: Push harder to wake up
    elif energy > 4.0:
        return 0.02  # Hypermetabolic: Back off to let system cool
    else:
        return 0.10  # Stable Target Range

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

    # PID controller coefficients for Hamiltonian Shock Absorber
    Kp = 0.15
    Ki = 0.02
    Kd = 0.05
    
    prev_energy = None
    prev_delta_energy = 0.0
    integral_error = 0.0
    
    # Autonomic Respite tracking
    hypermetabolic_duration = 0
    respite_active = False
    cooldown_counter = 0
    original_bg3_coupling = None

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

            # 2. Calculate PID brake
            delta_energy = 0.0
            if prev_energy is not None:
                delta_energy = energy - prev_energy
                integral_error += delta_energy
                # Clip integral error to prevent windup
                integral_error = np.clip(integral_error, -10.0, 10.0)
                
                error_d = delta_energy - prev_delta_energy
            else:
                error_d = 0.0
                
            pid_brake = Kp * delta_energy + Ki * integral_error + Kd * error_d
            
            prev_energy = energy
            prev_delta_energy = delta_energy

            # 3. Calculate Base Dynamic Coupling
            if energy < 1.0:
                base_coupling = 0.20  # Hypometabolic: Push harder to wake up
            elif energy > 4.0:
                base_coupling = 0.02  # Hypermetabolic: Back off to let system cool
            else:
                base_coupling = 0.10  # Stable Target Range
                
            # Apply PID brake to smoothly throttle injection coupling
            if pid_brake > 0:
                coupling = base_coupling / (1.0 + pid_brake)
            else:
                coupling = base_coupling

            # 4. Autonomic Respite & Cooldown Logic
            if energy > 4.0:
                hypermetabolic_duration += 1
            else:
                hypermetabolic_duration = 0
                
            # Trigger Autonomic Respite if hypermetabolic for >30s
            if hypermetabolic_duration >= 30 and not respite_active:
                logger.warning("[!] Autonomic Respite triggered! System hypermetabolic for >30s. Relaxing BG3 and pulse coupling by 50%.")
                respite_active = True
                
                # Halve bg3_coupling on the API
                try:
                    current_config, config_code = get_json(f"{API_BASE_URL}/system/config")
                    if config_code == 200:
                        original_bg3_coupling = current_config.get("bg3_coupling", 0.1)
                        target_bg3 = original_bg3_coupling * 0.5
                        logger.info(f"[*] Lowering bg3_coupling from {original_bg3_coupling} to {target_bg3}")
                        post_json(f"{API_BASE_URL}/system/config", {"bg3_coupling": target_bg3})
                except Exception as e:
                    logger.error(f"Failed to lower bg3_coupling during respite: {e}")
            
            # If respite is active, apply 50% relaxation brake to coupling
            if respite_active:
                coupling *= 0.5
                
                # Check for respite recovery (cooldown)
                if energy < 3.0:
                    cooldown_counter += 1
                else:
                    cooldown_counter = 0
                    
                if cooldown_counter >= 5:
                    logger.info("[+] System stabilized. Restoring baseline configurations and ending Autonomic Respite.")
                    respite_active = False
                    cooldown_counter = 0
                    
                    # Restore bg3_coupling
                    if original_bg3_coupling is not None:
                        try:
                            logger.info(f"[*] Restoring bg3_coupling to {original_bg3_coupling}")
                            post_json(f"{API_BASE_URL}/system/config", {"bg3_coupling": original_bg3_coupling})
                        except Exception as e:
                            logger.error(f"Failed to restore bg3_coupling: {e}")
                        original_bg3_coupling = None
            else:
                cooldown_counter = 0
            
            # 5. Retrieve Hamiltonian from Redis
            vec_256 = None
            if r_store:
                try:
                    keys = r_store.keys("attractor:*")
                    if keys:
                        key = np.random.choice(keys)
                        raw = r_store.get(key)
                        if raw:
                            vec_256 = np.frombuffer(raw, dtype=np.float32)
                            logger.debug(f"Loaded Hamiltonian from Redis: {key.decode('utf-8')}")
                    else:
                        logger.warning("Redis Hamiltonian buffer is empty!")
                except Exception as e:
                    logger.error(f"Redis retrieval error: {e}")
            
            # 6. Fallback: Generate random vector to prevent brain death
            if vec_256 is None:
                logger.info("[!] Redis Fallback: Generating random 256D Hamiltonian pulse.")
                vec_256 = np.random.randn(256).astype(np.float32)
                norm = np.linalg.norm(vec_256) + 1e-12
                vec_256 = vec_256 / norm

            # 7. Inject Pulse
            try:
                # Apply coupling strength before injection
                pulse_vector = (vec_256 * coupling).tolist()
                
                res_data, res_code = post_json(RESONANCE_URL, {"vector": pulse_vector})
                
                if res_code == 200:
                    status_msg = f"Pulse Injected | Energy: {energy:.2f} | ΔE: {delta_energy:.4f} | PID Brake: {pid_brake:.4f} | Coupling: {coupling:.4f} | L2: {res_data.get('l2_norm', 0):.4f}"
                    if respite_active:
                        status_msg += " [RESPITE ACTIVE]"
                    logger.info(status_msg)
                else:
                    logger.warning(f"Resonance injection failed: {res_code}")
                
                # 8. Trigger Heartbeat Tick
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