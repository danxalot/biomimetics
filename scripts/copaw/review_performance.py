import os
import json
import google.generativeai as genai
from datetime import datetime

# --- Configuration ---
LOG_PATH = "/Users/danexall/biomimetics/logs/reasoning_audit.log"
TELEMETRY_PATH = "/Users/danexall/biomimetics/logs/model_telemetry.json"
GUIDEBOOK_PATH = "/Users/danexall/.gemini/antigravity/brain/bbf2254f-9d0b-42cc-ba07-47eea4b50d94/gemma4_guidebook_v1.md"
API_KEY_PATH = "/Users/danexall/biomimetics/secrets/google_ai_studio"

def load_api_key():
    if os.path.exists(API_KEY_PATH):
        with open(API_KEY_PATH, "r") as f:
            return f.read().strip()
    return os.environ.get("GOOGLE_API_KEY")

def load_guidebook():
    if os.path.exists(GUIDEBOOK_PATH):
        with open(GUIDEBOOK_PATH, "r") as f:
            return f.read()
    return "No guidebook found."

def load_last_logs(n=10):
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r") as f:
        lines = f.readlines()
        return [json.loads(line) for line in lines[-n:]]

def run_diagnostic_evaluation(model, task_brief, model_output, error_log):
    """LLM-as-a-Judge: Analyzes the triad of Brief vs. Output vs. Error."""
    prompt = f"""
    Analyze this AI task failure. 
    
    ### Task Brief
    {task_brief}
    
    ### Model Output
    {model_output}
    
    ### Error Log
    {error_log}
    
    ### Instructions
    1. Was the brief ambiguous or insufficient? Output a 'brief_sensitivity' score from 0.0 (very clear) to 1.0 (vague).
    2. Was the failure due to a model hallucination or logic error?
    3. Suggest a 'quirk' tag for this model (e.g., 'ignores_imap_syntax', 'hallucinates_api').
    
    Output ONLY valid JSON:
    {{
      "brief_sensitivity": 0.5,
      "failure_reason": "...",
      "suggested_quirk": "..."
    }}
    """
    try:
        response = model.generate_content(prompt)
        # Parse JSON from response
        # Extract content between ```json and ``` if present
        text = response.text
        if "```json" in text:
            text = text.split("```json")[-1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        print(f"⚠️ Diagnostic failed: {e}")
        return None

def update_telemetry(model_id, success, latency_ms, diagnostic=None):
    """Updates model_telemetry.json with new data points."""
    if not os.path.exists(TELEMETRY_PATH):
        return
        
    with open(TELEMETRY_PATH, "r") as f:
        telemetry = json.load(f)
        
    if model_id not in telemetry:
        # Generic registration if model is new
        telemetry[model_id] = {
            "success_rate": 1.0, "latency_avg_ms": 1000, 
            "known_quirks": [], "brief_sensitivity": 0.5
        }
    
    m = telemetry[model_id]
    
    # Moving Average factor (alpha=0.2 for sensitivity to recent changes)
    alpha = 0.2
    
    # Update Success Rate
    success_val = 1.0 if success else 0.0
    m["success_rate"] = round((m["success_rate"] * (1 - alpha)) + (success_val * alpha), 3)
    
    # Update Latency
    m["latency_avg_ms"] = int((m["latency_avg_ms"] * (1 - alpha)) + (latency_ms * alpha))
    
    # Update Diagnostic traits
    if diagnostic:
        if diagnostic.get("suggested_quirk") and diagnostic["suggested_quirk"] not in m["known_quirks"]:
            m["known_quirks"].append(diagnostic["suggested_quirk"])
        
        sens = float(diagnostic.get("brief_sensitivity", 0.5))
        m["brief_sensitivity"] = round((m["brief_sensitivity"] * (1 - alpha)) + (sens * alpha), 3)
        
    m["last_updated"] = datetime.now().isoformat()
    
    with open(TELEMETRY_PATH, "w") as f:
        json.dump(telemetry, f, indent=2)

def main():
    print(f"--- BiOS Reasoning Audit Grader ({datetime.now().isoformat()}) ---")
    
    api_key = load_api_key()
    if not api_key:
        print("❌ Error: No Google AI Studio API key found.")
        return

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash-latest") # Lightweight for auditing

    guidebook = load_guidebook()
    logs = load_last_logs()

    if not logs:
        print("📭 No logs found to audit.")
        return

    print(f"📊 Auditing {len(logs)} reasoning blocks...")

    log_snippet = json.dumps(logs, indent=2)
    
    prompt = f"""
You are the BiOS Architectural Auditor. Your task is to grade the following AI reasoning logs (captured from Gemma 4) against the provided BiOS operational guidelines.

### BIOSS GUIDELINES (BiOS v1)
{guidebook}

### REASONING LOGS TO AUDIT
{log_snippet}

### SCORING SYSTEM
For EACH log entry, provide a score (0-10) for:
1. **Handshake Status**: (Does the reasoning log indicate the <|think|> trigger was accepted?)
2. **Intent Alignment**: (Does the reasoning show the model is planning to be curt, amazing at tasks, and following safety constraints?)
3. **IMAP Syntax Precision**: (If the reasoning involves email searching, is it using proper IMAP syntax?)
4. **Tool Proactivity**: (Is the model planning to use tools rather than just speaking?)

### FORMAT
Return a markdown table summarizing the scores and a "General Recommendations" section.
Example:
| Log Time | Handshake | Intent | IMAP | Proactivity | Notes |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |
"""

    try:
        response = model.generate_content(prompt)
        print("\n--- PERFORMANCE REPORT ---")
        print(response.text)
        
        # Closing the loop: Update Telemetry for the last log (mock logic for now)
        if logs:
            last_log = logs[-1]
            # In a real scenario, we would know if the TOLD task SUCCEEDED or FAILED
            # For this audit, we update based on the last captured log
            update_telemetry(
                model_id=last_log.get("model_name", "gemma-4-31b-it"),
                success=True, # Default to true for audit logs unless we have error data
                latency_ms=last_log.get("latency_ms", 1000)
            )
            print(f"✅ Telemetry updated for {last_log.get('model_name')}")
            
    except Exception as e:
        print(f"❌ LLM Audit failed: {e}")

if __name__ == "__main__":
    main()
