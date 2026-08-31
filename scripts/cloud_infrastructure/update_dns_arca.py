import os
import sys
import requests

def update_dns():
    token = os.environ.get("CLOUDFLARE_TOKEN")
    if not token:
        print("❌ Error: CLOUDFLARE_TOKEN environment variable not set.")
        sys.exit(1)

    zone_id = "22300411fc34d5337bfd96f60bd27218"
    root_domain = "arca-vsa.tech"
    target = "arca-portal-757330161781.us-central1.run.app"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Find existing record
    print(f"🔍 Searching for DNS records for {root_domain}...")
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    params = {"name": root_domain}
    
    response = requests.get(url, headers=headers, params=params)
    if not response.ok:
        print(f"❌ Failed to fetch DNS records: {response.text}")
        sys.exit(1)
    
    records = response.json().get("result", [])
    if not records:
        print(f"⚠️ No existing record found for {root_domain}. Creating a new one...")
        # Create logic
        payload = {
            "type": "CNAME",
            "name": root_domain,
            "content": target,
            "proxied": True,
            "ttl": 1 # Auto
        }
        create_resp = requests.post(url, headers=headers, json=payload)
        if create_resp.ok:
            print(f"✅ Created CNAME record for {root_domain} -> {target}")
        else:
            print(f"❌ Failed to create record: {create_resp.text}")
            sys.exit(1)
    else:
        record = records[0]
        record_id = record["id"]
        print(f"🎯 Found record {record_id} ({record['type']}: {record['content']})")
        
        # 2. Update record
        payload = {
            "type": "CNAME",
            "name": root_domain,
            "content": target,
            "proxied": True
        }
        
        update_url = f"{url}/{record_id}"
        update_resp = requests.put(update_url, headers=headers, json=payload)
        
        if update_resp.ok:
            print(f"✅ Successfully updated {root_domain} -> {target} (Proxied)")
        else:
            print(f"❌ Failed to update record: {update_resp.text}")
            sys.exit(1)

if __name__ == "__main__":
    update_dns()
