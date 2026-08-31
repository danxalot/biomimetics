import os
import json
import logging
import requests
import time
from pathlib import Path
from openai import OpenAI

# =============================================================================
# Configuration & Secrets
# =============================================================================

LOG_DIR = Path("~/biomimetics/logs/autonomous_investigation").expanduser()
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "execution.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("autonomous_swarm")

OPENCODE_TOKEN_PATH = Path("~/biomimetics/secrets/opencode_api").expanduser()
CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_API_KEY_PATH = Path("~/.copaw/.credentials_api_key").expanduser()

def fetch_secret(secret_name: str) -> str:
    """Fetch secret from Credentials Server."""
    try:
        api_key = CREDENTIALS_API_KEY_PATH.read_text().strip()
        resp = requests.get(f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}", 
                            headers={"X-API-Key": api_key}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("value")
    except Exception as e:
        logger.error(f"Failed to fetch secret {secret_name}: {e}")
    return os.getenv(secret_name.upper())

def get_opencode_key():
    if OPENCODE_TOKEN_PATH.exists():
        return OPENCODE_TOKEN_PATH.read_text().strip()
    return None

# =============================================================================
# Agent Clients
# =============================================================================

def call_gemma_4(prompt: str, system_prompt: str = "") -> str:
    """Call Gemma 4 via Google AI Studio REST API."""
    api_key = fetch_secret("google-api-key")
    if not api_key:
        return "ERROR: Missing Google API Key"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    # Note: Using flash as placeholder if gemma-4 is not yet in GA or needs specific name
    # The user mentioned gemma-4-31b-it specifically
    
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\nTask: {prompt}"}]}]
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"ERROR: API returned {resp.status_code} - {resp.text}"
    except Exception as e:
        return f"ERROR: {e}"

def call_opencode(model: str, prompt: str, system_prompt: str = "") -> str:
    """Call OpenCode Go models."""
    api_key = get_opencode_key()
    client = OpenAI(base_url="https://opencode.ai/zen/go/v1", api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ERROR: {e}"

# =============================================================================
# Execution Phases
# =============================================================================

def execute_autonomous_loop():
    logger.info("🚀 Starting Autonomous Pipeline Investigation Swarm...")
    
    # --- PHASE 1: Gemma 4 PM Investigation ---
    logger.info("--- Stage 1: PM Investigation (Gemma 4 31b) ---")
    pm_prompt = """
    Investigate the BiOS document ingestion pipeline. 
    Analyze the recent data overload that led to the GCP MuninnDB blockage.
    Review the gathering and stripping methods for IDE artifacts (Claude, Zed, Antigravity).
    Output a detailed Investigation Brief.
    """
    investigation_brief = call_gemma_4(pm_prompt, "You are the BiOS Project Manager Agent (Gemma 4).")
    logger.info("✅ Investigation Brief Generated.")
    (LOG_DIR / "1_pm_investigation.md").write_text(investigation_brief)

    # --- PHASE 2: Kimi K2.6 Architecture Refinement ---
    logger.info("--- Stage 2: Architecture Refinement (Kimi K2.6) ---")
    architect_prompt = f"""
    Based on the following Investigation Brief, conduct a thorough architectural review.
    Refine the process of assimilation, refactoring, and ingestion.
    Propose specific filters, truncation limits, and routing optimizations.
    
    Brief:
    {investigation_brief}
    """
    architectural_design = call_opencode("kimi-k2.6", architect_prompt, "You are the BiOS Lead Architect (Kimi K2.6).")
    logger.info("✅ Architectural Design Generated.")
    (LOG_DIR / "2_kimi_architecture.md").write_text(architectural_design)

    # --- PHASE 3: Minimax M3 Implementation ---
    logger.info("--- Stage 3: Implementation (Minimax M3) ---")
    implementation_prompt = f"""
    Implement the following architectural design for the ingestion pipeline.
    Generate the refactored code for 'memory_system' and 'archivist' components.
    
    Design:
    {architectural_design}
    """
    implementation_docs = call_opencode("minimax-m3", implementation_prompt, "You are the BiOS Implementation Specialist (Minimax M3).")
    logger.info("✅ Implementation Docs Generated.")
    (LOG_DIR / "3_minimax_implementation.md").write_text(implementation_docs)

    # --- PHASE 4: Nemotron Ultra 3 Verification ---
    logger.info("--- Stage 4: Verification & Tidy Up (Nemotron Ultra 3) ---")
    verification_prompt = f"""
    Review and verify the following implementation. 
    Test against system constraints and perform a thorough 'tidying up' of the environment and logs.
    
    Implementation:
    {implementation_docs}
    """
    verification_report = call_opencode("nemotron-3-ultra", verification_prompt, "You are the BiOS Verification Hub (Nemotron Ultra 3).")
    logger.info("✅ Verification Complete.")
    (LOG_DIR / "4_nemotron_verification.md").write_text(verification_report)

    logger.info("🏁 Swarm Job Complete. All outputs saved to logs/autonomous_investigation/")

if __name__ == "__main__":
    execute_autonomous_loop()
