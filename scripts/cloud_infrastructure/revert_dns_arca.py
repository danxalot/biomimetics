import os
import sys
import requests
import json

def revert_dns():
    token = os.environ.get("CLOUDFLARE_TOKEN")
    zone_id = "22300411fc34d5337bfd96f60bd27218"
    root_domain = "arca-vsa.tech"
    # The old Argo Tunnel target
    target = "dc9abbe3-8740-41ae-a571-89e6b00c9d76.cfargotunnel.com"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    resp = requests.get(url, headers=headers, params={"name": root_domain})
    records = resp.json().get("result", [])
    
    if records:
        record_id = records[0]["id"]
        payload = {
            "type": "CNAME",
            "name": root_domain,
            "content": target,
            "proxied": True
        }
        update_resp = requests.put(f"{url}/{record_id}", headers=headers, json=payload)
        if update_resp.ok:
            print(f"✅ Reverted {root_domain} -> {target}")
        else:
            print(f"❌ Failed: {update_resp.text}")

if __name__ == "__main__":
    revert_dns()
