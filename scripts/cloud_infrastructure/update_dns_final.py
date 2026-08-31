import os
import requests
import json
import urllib.request

def fetch_secret(secret_name):
    api_key_path = "/Users/danexall/biomimetics/secrets/credentials_api_key"
    with open(api_key_path, "r") as f:
        api_key = f.read().strip()
    
    url = f"http://localhost:8089/secrets/{secret_name}"
    req = urllib.request.Request(url)
    req.add_header("X-API-Key", api_key)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())["value"]

def main():
    token = fetch_secret("cloudflare-dns-token")
    zone_id = "22300411fc34d5337bfd96f60bd27218"
    root_domain = "arca-vsa.tech"
    
    # GCP Provided IP addresses
    ipv4_targets = ["216.239.32.21", "216.239.34.21", "216.239.36.21", "216.239.38.21"]
    ipv6_targets = [
        "2001:4860:4802:32::15", "2001:4860:4802:34::15", 
        "2001:4860:4802:36::15", "2001:4860:4802:38::15"
    ]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Clean up existing records for root domain
    print(f"🧹 Cleaning up existing records for {root_domain}...")
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    resp = requests.get(url, headers=headers, params={"name": root_domain})
    for record in resp.json().get("result", []):
        requests.delete(f"{url}/{record['id']}", headers=headers)
        print(f"   Deleted {record['type']} record: {record['id']}")

    # 2. Add new A records
    for ip in ipv4_targets:
        payload = {"type": "A", "name": root_domain, "content": ip, "proxied": True}
        requests.post(url, headers=headers, json=payload)
        print(f"✅ Added A record: {ip}")

    # 3. Add new AAAA records
    for ip in ipv6_targets:
        payload = {"type": "AAAA", "name": root_domain, "content": ip, "proxied": True}
        requests.post(url, headers=headers, json=payload)
        print(f"✅ Added AAAA record: {ip}")

if __name__ == "__main__":
    main()
