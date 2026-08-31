import requests
import json

headers = {"X-API-Key": ""}
resp = requests.get("http://localhost:8089/secrets", headers=headers)
if resp.status_code == 200:
    secrets = resp.json().get("secrets", [])
    cf_secrets = [s for s in secrets if "cloudflare" in s.lower()]
    for s in cf_secrets:
        val_resp = requests.get(f"http://localhost:8089/secrets/{s}", headers=headers)
        if val_resp.status_code == 200:
            print(f"{s}: {val_resp.json().get('value')}")
        else:
            print(f"Failed to fetch {s}")
else:
    print("Failed to list secrets")
