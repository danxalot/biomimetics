#!/usr/bin/env python3
import os
import subprocess
import sys

# 1. Read API Key
with open("/Users/danexall/biomimetics/secrets/credentials_api_key", "r") as f:
    api_key = f.read().strip()

# 1b. Fetch Notion Secrets from Credentials Server
import urllib.request
import json
def fetch_secret(name):
    req = urllib.request.Request(f"http://localhost:8089/secrets/{name}")
    req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())["value"]
    except:
        return None

notion_key = fetch_secret("notion-api-key")
notion_db = fetch_secret("notion-email-db-id")

# 2. Set Env
env = os.environ.copy()
env["CREDENTIALS_API_KEY"] = api_key
if notion_key:
    env["NOTION_API_KEY"] = notion_key
if notion_db:
    env["NOTION_EMAIL_DB_ID"] = notion_db
env["COPAW_WORKING_DIR"] = "/Users/danexall/biomimetics/config_copaw"
env["COPAW_ENABLED_CHANNELS"] = "voice,whatsapp,console"
env["PYTHONPATH"] = "/Users/danexall/biomimetics/scripts/copaw/src:" + os.environ.get("PYTHONPATH", "")

# 3. Virtualenv Python
PYTHON_EXE = "/Users/danexall/biomimetics/config_copaw/venv/bin/python3"

# 4. Kill existing
subprocess.run(["pkill", "-f", "copaw app"], stderr=subprocess.DEVNULL)

# 5. Launch
print("🚀 Launching Unified CoPaw Junction...")
proc = subprocess.Popen(
    [PYTHON_EXE, "-m", "copaw", "app", "--port", "8090"],
    env=env,
    stdout=open("/Users/danexall/biomimetics/logs/copaw_stdout.log", "w"),
    stderr=open("/Users/danexall/biomimetics/logs/copaw_stderr.log", "w"),
    start_new_session=True
)

print(f"✅ CoPaw Junction launched with PID {proc.pid}. Logs in biomimetics/logs/")
