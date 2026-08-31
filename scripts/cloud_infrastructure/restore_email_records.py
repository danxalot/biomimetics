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
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"

    # Restore MX records
    mx_records = [
        {"type": "MX", "name": root_domain, "content": "mail.protonmail.ch", "priority": 10},
        {"type": "MX", "name": root_domain, "content": "mailsec.protonmail.ch", "priority": 20}
    ]
    for mx in mx_records:
        requests.post(url, headers=headers, json=mx)
        print(f"✅ Restored MX: {mx['content']}")

    # Restore ProtonMail Verification TXT
    txt_records = [
        {"type": "TXT", "name": root_domain, "content": "protonmail-verification=053a479268846c483d467776f3f88f1e60416973"},
        {"type": "TXT", "name": root_domain, "content": "v=spf1 include:_spf.protonmail.ch ~all"}
    ]
    for txt in txt_records:
        requests.post(url, headers=headers, json=txt)
        print(f"✅ Restored TXT: {txt['content'][:30]}...")

if __name__ == "__main__":
    main()
