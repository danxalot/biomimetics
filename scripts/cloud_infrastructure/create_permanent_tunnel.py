#!/usr/bin/env python3
"""
Create permanent Cloudflare Tunnel via API
"""

import json
import httpx
import sys

# Cloudflare API Token (service token from secrets)
CLOUDFLARE_API_TOKEN = "ML8BZLukboXHltcyrPoMOxBvdQt-5tM15HemWtiX"
TUNNEL_NAME = "gemini-relay-tunnel"
TUNNEL_HOSTNAME = "gemini-relay.arca-vsa.tech"
VPS_IP = "149.248.32.53"
VPS_PASSWORD = "9[NorZ3)X2+G$[oM"
RELAY_PORT = 8765

HEADERS = {
    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
    "Content-Type": "application/json"
}

def main():
    print("=" * 70)
    print("  Cloudflare Permanent Tunnel Setup")
    print("=" * 70)
    print()
    
    with httpx.Client(timeout=30) as client:
        # Step 1: Get Account ID
        print("📋 Step 1: Getting account info...")
        response = client.get("https://api.cloudflare.com/client/v4/accounts", headers=HEADERS)
        data = response.json()
        
        if not data.get("success"):
            print(f"❌ Failed to get accounts: {data}")
            return False
            
        account_id = data["result"][0]["id"]
        print(f"   ✅ Account ID: {account_id}")
        print()
        
        # Step 2: Create Tunnel
        print("📋 Step 2: Creating tunnel...")
        response = client.post(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel",
            headers=HEADERS,
            json={"name": TUNNEL_NAME}
        )
        data = response.json()
        
        if not data.get("success"):
            print(f"❌ Failed to create tunnel: {data}")
            return False
            
        tunnel_id = data["result"]["id"]
        tunnel_secret = data["result"]["tunnel_secret"]
        print(f"   ✅ Tunnel ID: {tunnel_id}")
        print(f"   ✅ Tunnel Secret: {tunnel_secret[:20]}...")
        print()
        
        # Step 3: Create credentials file content
        print("📋 Step 3: Generating credentials...")
        credentials = {
            "a": account_id.replace("-", ""),
            "t": tunnel_id,
            "s": tunnel_secret
        }
        print(f"   ✅ Credentials generated")
        print()
        
        # Step 4: Create DNS route (CNAME)
        print("📋 Step 4: Creating DNS route...")
        # First get zone ID for arca-vsa.tech
        response = client.get(
            "https://api.cloudflare.com/client/v4/zones",
            headers=HEADERS,
            params={"name": "arca-vsa.tech"}
        )
        data = response.json()
        
        if data.get("success") and data.get("result"):
            zone_id = data["result"][0]["id"]
            print(f"   ✅ Zone ID: {zone_id}")
            
            # Create CNAME record
            response = client.post(
                f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
                headers=HEADERS,
                json={
                    "type": "CNAME",
                    "name": "gemini-relay",
                    "content": f"{tunnel_id}.cfargotunnel.com",
                    "proxied": True,
                    "comment": "Gemini Relay Cloudflare Tunnel"
                }
            )
            data = response.json()
            
            if data.get("success"):
                print(f"   ✅ DNS record created: {TUNNEL_HOSTNAME}")
            else:
                # Might already exist
                print(f"   ⚠️  DNS record: {data}")
        else:
            print(f"   ⚠️  Zone not found, using trycloudflare fallback")
        print()
        
        # Step 5: Create cloudflared config for VPS
        print("📋 Step 5: Creating VPS configuration...")
        
        # Credentials JSON for VPS
        credentials_json = json.dumps(credentials, indent=2)
        
        # cloudflared config YAML
        config_yml = f"""tunnel: {tunnel_id}
credentials-file: /etc/cloudflared/tunnel.json

ingress:
  - hostname: {TUNNEL_HOSTNAME}
    service: http://localhost:{RELAY_PORT}
  - service: http_status:404
"""
        
        # systemd service
        service_file = """[Unit]
Description=Cloudflare Tunnel - gemini-relay-tunnel
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --config /etc/cloudflared/config.yml run
Restart=always
RestartSec=5
Environment=TUNNEL_NO_AUTOUPDATE=true

[Install]
WantedBy=multi-user.target
"""
        
        print(f"   ✅ Configuration files generated")
        print()
        
        # Step 6: Push to VPS via SSH
        print("📋 Step 6: Pushing configuration to VPS...")
        
        import paramiko
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(VPS_IP, username="root", password=VPS_PASSWORD)
            
            # Create directories
            ssh.exec_command("mkdir -p /etc/cloudflared")
            
            # Write credentials
            stdin, stdout, stderr = ssh.exec_command("cat > /etc/cloudflared/tunnel.json")
            stdin.write(credentials_json)
            stdin.close()
            
            # Write config
            stdin, stdout, stderr = ssh.exec_command("cat > /etc/cloudflared/config.yml")
            stdin.write(config_yml)
            stdin.close()
            
            # Write service file
            stdin, stdout, stderr = ssh.exec_command("cat > /etc/systemd/system/cloudflared-tunnel.service")
            stdin.write(service_file)
            stdin.close()
            
            # Restart services
            ssh.exec_command("systemctl daemon-reload")
            ssh.exec_command("systemctl restart cloudflared-tunnel")
            ssh.exec_command("systemctl enable cloudflared-tunnel")
            
            print(f"   ✅ Configuration pushed to {VPS_IP}")
            print()
            
            # Check status
            print("📋 Step 7: Verifying tunnel status...")
            stdin, stdout, stderr = ssh.exec_command("sleep 5 && journalctl -u cloudflared-tunnel --no-pager -n 10")
            logs = stdout.read().decode()
            print(logs)
            
            ssh.close()
            
        except Exception as e:
            print(f"   ❌ SSH error: {e}")
            print("   Manual SSH required")
        print()
        
        # Summary
        print("=" * 70)
        print("  ✅ Tunnel Setup Complete!")
        print("=" * 70)
        print()
        print(f"🌐 Public URL: https://{TUNNEL_HOSTNAME}")
        print(f"🔌 WebSocket URL: wss://{TUNNEL_HOSTNAME}/")
        print()
        print("📝 Configuration saved:")
        print(f"   - Tunnel ID: {tunnel_id}")
        print(f"   - Account: {account_id}")
        print()
        
        # Save credentials locally
        with open("/Users/danexall/biomimetics/secrets/cloudflare_tunnel_credentials.json", "w") as f:
            json.dump({
                "tunnel_id": tunnel_id,
                "account_id": account_id,
                "tunnel_secret": tunnel_secret,
                "hostname": TUNNEL_HOSTNAME
            }, f, indent=2)
        
        print("💾 Credentials saved to: secrets/cloudflare_tunnel_credentials.json")
        print()
        
        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
