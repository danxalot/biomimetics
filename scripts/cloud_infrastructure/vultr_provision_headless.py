#!/usr/bin/env python3
"""
Vultr Free Tier VPS Provisioning Script - HEADLESS MODE
========================================================

Automatically provisions a free tier VPS instance on Vultr WITHOUT any human interaction.
Pulls API key from environment and uses hardcoded cloud-init path.

- Plan: vc2-1c-0.5gb-free (0.5GB RAM, 10GB storage, 0.5 vCPU)
- Region: London, UK (lhr) or closest available European region
- OS: Debian 12 (bookworm)
- Cloud-Init: /Users/danexall/biomimetics/gemini_relay/scripts/setup_vps.sh

Usage:
    export VULTR_API_KEY="your_api_key"
    python3 vultr_provision_headless.py

Output:
    Saves IP address to /Users/danexall/biomimetics/secrets/vultr_vps_ip
"""

import os
import sys
import json
import time
import base64
from pathlib import Path
from typing import Optional, Dict, List

import httpx

# ============================================================================
# Configuration
# ============================================================================

VULTR_API_BASE = "https://api.vultr.com/v2"

# Free tier plan details
# Available regions for vc2-1c-0.5gb-free: sea (Seattle), fra (Frankfurt), mia (Miami)
FREE_TIER_PLAN = "vc2-1c-0.5gb-free"
FREE_TIER_REGIONS = [
    "sea",      # Seattle, US (primary)
    "fra",      # Frankfurt, Germany
    "mia",      # Miami, US
]

# Debian 12 (bookworm) - OS ID 477
DEBIAN_12_OS_ID = 477

# Instance configuration
DEFAULT_LABEL = "bios-gemini-relay"

# Paths (hardcoded for headless mode)
CLOUD_INIT_PATH = "/Users/danexall/biomimetics/gemini_relay/scripts/setup_vps.sh"
SECRETS_DIR = "/Users/danexall/biomimetics/secrets"
OUTPUT_IP_FILE = os.path.join(SECRETS_DIR, "vultr_vps_ip")
OUTPUT_INSTANCE_FILE = os.path.join(SECRETS_DIR, "vultr_instance.json")
VULTR_SSH_KEY_FILE = os.path.join(SECRETS_DIR, "vultr_ssh_key")


# ============================================================================
# Vultr API Client
# ============================================================================

class VultrClient:
    """Vultr API client with retry logic and error handling."""

    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.Client(
            base_url=VULTR_API_BASE,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "BiOS-Vultr-Provisioner/1.0-Headless"
            },
            timeout=timeout
        )

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make API request with error handling."""
        try:
            response = self.client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            print(f"❌ API Error: {e.response.status_code}")
            print(f"   {error_body}")
            raise
        except httpx.RequestError as e:
            print(f"❌ Request Error: {e}")
            raise

    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """GET request."""
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json: Optional[Dict] = None) -> Dict:
        """POST request."""
        return self._request("POST", endpoint, json=json)

    def delete(self, endpoint: str) -> Optional[Dict]:
        """DELETE request."""
        try:
            response = self.client.delete(endpoint)
            response.raise_for_status()
            return response.json() if response.content else None
        except httpx.HTTPStatusError as e:
            print(f"❌ Delete Error: {e.response.status_code}")
            raise

    def get_account_info(self) -> Dict:
        """Get account information."""
        return self.get("/account")

    def get_free_tier_plan(self) -> Optional[Dict]:
        """Get free tier plan details."""
        plans = self.get("/plans").get("plans", [])
        for plan in plans:
            if plan.get("id") == FREE_TIER_PLAN:
                return plan
        return None

    def get_available_region(self) -> Optional[str]:
        """Get first available region from free tier regions list."""
        regions = self.get("/regions").get("regions", [])

        # Check for regions with explicit availability=True
        for region_id in FREE_TIER_REGIONS:
            for region in regions:
                if region.get("id") == region_id:
                    available = region.get("available")
                    # Accept if available=True or if availability is not specified (None)
                    if available is True or available is None:
                        print(f"✅ Selected region: {region['city']} ({region['id']})")
                        return region_id

        # Fallback to first region in our list
        for region_id in FREE_TIER_REGIONS:
            for region in regions:
                if region.get("id") == region_id:
                    print(f"⚠️  Using fallback region: {region['city']} ({region['id']})")
                    return region_id

        # Last resort: use first available region from API
        for region in regions:
            if region.get("available") is True or region.get("available") is None:
                print(f"⚠️  Using default region: {region['city']} ({region['id']})")
                return region["id"]

        return None

    def create_instance(self, instance_config: Dict) -> Dict:
        """Create a new VPS instance."""
        return self.post("/instances", json=instance_config)

    def get_instance(self, instance_id: str) -> Dict:
        """Get instance details."""
        return self.get(f"/instances/{instance_id}")

    def wait_for_instance_active(self, instance_id: str, timeout: int = 300) -> Dict:
        """Wait for instance to become active."""
        print(f"⏳ Waiting for instance to become active...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            instance = self.get_instance(instance_id)
            status = instance.get("instance", {}).get("status", "")

            if status == "active":
                print(f"✅ Instance is active!")
                return instance

            print(f"   Status: {status} ({int(time.time() - start_time)}s elapsed)")
            time.sleep(10)

        raise TimeoutError(f"Instance did not become active within {timeout} seconds")


# ============================================================================
# Headless Provisioner
# ============================================================================

class HeadlessProvisioner:
    """Handles the complete VPS provisioning workflow without user interaction."""

    def __init__(self, api_key: str, label: str = DEFAULT_LABEL):
        self.client = VultrClient(api_key)
        self.label = label
        self.instance_id: Optional[str] = None

    def load_cloud_init_script(self) -> Optional[str]:
        """Load and encode cloud-init script from hardcoded path."""
        script_path = Path(CLOUD_INIT_PATH).expanduser()

        if not script_path.exists():
            print(f"⚠️  Cloud-init script not found at {script_path}")
            print(f"   Continuing without cloud-init configuration")
            return None

        try:
            script_content = script_path.read_text()
            encoded_script = base64.b64encode(script_content.encode()).decode()
            print(f"✅ Cloud-init script loaded: {script_path.name}")
            print(f"   Size: {len(script_content)} bytes")
            return encoded_script
        except Exception as e:
            print(f"⚠️  Error reading cloud-init script: {e}")
            return None

    def load_ssh_key_id(self) -> Optional[str]:
        """Load SSH key ID from secrets file."""
        ssh_key_path = Path(VULTR_SSH_KEY_FILE).expanduser()

        if not ssh_key_path.exists():
            print(f"⚠️  SSH key file not found at {ssh_key_path}")
            return None

        try:
            ssh_key_id = ssh_key_path.read_text().strip()
            print(f"✅ SSH key loaded: {ssh_key_id}")
            return ssh_key_id
        except Exception as e:
            print(f"⚠️  Error reading SSH key: {e}")
            return None

    def provision(self) -> Optional[Dict]:
        """Execute the complete provisioning workflow."""
        print("\n" + "=" * 70)
        print("  Vultr Free Tier VPS Provisioner (HEADLESS MODE)")
        print("  BiOS Infrastructure Automation")
        print("=" * 70 + "\n")

        # Step 1: Verify account
        print("📋 Verifying Vultr account...")
        try:
            account = self.client.get_account_info()
            user = account.get("user", {})
            print(f"   Account: {user.get('email', 'N/A')}")
            print(f"   Name: {user.get('name', 'N/A')}")
        except Exception as e:
            print(f"❌ Account verification failed: {e}")
            return None

        # Step 2: Check free tier plan
        print(f"\n📦 Checking free tier plan ({FREE_TIER_PLAN})...")
        plan = self.client.get_free_tier_plan()
        if plan:
            print(f"   ✅ Free tier plan available")
            print(f"      RAM: {plan.get('ram', 'N/A')} MB")
            print(f"      Disk: {plan.get('disk', 'N/A')} GB")
            print(f"      CPU: {plan.get('vcpu', 'N/A')} cores")
        else:
            print(f"   ⚠️  Free tier plan not found, will use available plan")

        # Step 3: Load cloud-init script
        cloud_init_script = self.load_cloud_init_script()

        # Step 4: Load SSH key
        ssh_key_id = self.load_ssh_key_id()

        # Step 5: Get available region
        print(f"\n🌍 Selecting region...")
        region = self.client.get_available_region()
        if not region:
            print("❌ No available regions found")
            return None

        # Step 6: Build configuration
        config = {
            "region": region,
            "plan": FREE_TIER_PLAN,
            "os_id": DEBIAN_12_OS_ID,
            "label": self.label,
            "backups": "disabled",
            "enable_ipv6": False,
            "ddos_protection": False,
            "activation_email": True,
            "hostname": f"{self.label}.bios.local",
            "tags": ["bios", "gemini-relay", "free-tier", "headless"],
        }

        if cloud_init_script:
            config["user_data"] = cloud_init_script
            print(f"   ✅ Cloud-init script attached")

        if ssh_key_id:
            config["sshkey_ids"] = [ssh_key_id]  # Must be an array
            print(f"   ✅ SSH key attached: {ssh_key_id}")

        print(f"\n📋 Configuration:")
        print(f"   Region: {config['region']}")
        print(f"   Plan: {config['plan']}")
        print(f"   OS: Debian 12 (bookworm)")
        print(f"   Label: {config['label']}")
        print(f"   Backups: {config['backups']}")

        # Step 6: Create instance
        print(f"\n🚀 Creating VPS instance...")
        try:
            result = self.client.create_instance(config)
            instance = result.get("instance", {})
            self.instance_id = instance.get("id")

            if not self.instance_id:
                print(f"❌ Failed to create instance: {result}")
                return None

            print(f"\n✅ Instance creation initiated!")
            print(f"   Instance ID: {self.instance_id}")

            # Step 7: Wait for instance to become active
            instance_data = self.client.wait_for_instance_active(self.instance_id)

            # Step 8: Save connection details
            instance_info = instance_data.get("instance", {})
            ip_address = instance_info.get("main_ip")

            if ip_address:
                self.save_credentials(instance_info)
                print(f"\n✅ IP address saved to: {OUTPUT_IP_FILE}")
                print(f"   Instance details saved to: {OUTPUT_INSTANCE_FILE}")
            else:
                print(f"\n⚠️  No IP address found in instance data")

            return instance_info

        except Exception as e:
            print(f"\n❌ Provisioning failed: {e}")
            return None

    def save_credentials(self, instance_info: Dict):
        """Save IP address and instance details to secrets directory."""
        os.makedirs(SECRETS_DIR, exist_ok=True)

        # Save IP address
        ip_address = instance_info.get("main_ip", "")
        with open(OUTPUT_IP_FILE, "w") as f:
            f.write(ip_address)

        # Save full instance details
        with open(OUTPUT_INSTANCE_FILE, "w") as f:
            json.dump(instance_info, f, indent=2)

        print(f"\n📋 Instance Details:")
        print(f"   ID: {instance_info.get('id')}")
        print(f"   Label: {instance_info.get('label')}")
        print(f"   Hostname: {instance_info.get('hostname')}")
        print(f"   Region: {instance_info.get('region')}")
        print(f"   Plan: {instance_info.get('plan')}")
        print(f"   IP: {ip_address}")
        print(f"\n🔐 SSH Access:")
        print(f"   ssh root@{ip_address}")


def main():
    """Main entry point for headless provisioning."""
    # Get API key from environment
    api_key = os.getenv("VULTR_API_KEY")

    if not api_key:
        print("❌ VULTR_API_KEY environment variable not set")
        print(f"\nSet it with:")
        print(f"   export VULTR_API_KEY=\"your_api_key\"")
        print(f"\nOr read from secrets:")
        print(f"   export VULTR_API_KEY=$(cat {SECRETS_DIR}/vultr_api_key)")
        sys.exit(1)

    print(f"✅ VULTR_API_KEY loaded from environment")
    print(f"   Key: {api_key[:10]}...{api_key[-4:]}")

    # Create provisioner and run
    provisioner = HeadlessProvisioner(api_key)
    instance_info = provisioner.provision()

    if instance_info and instance_info.get("main_ip"):
        print("\n" + "=" * 70)
        print("  ✅ PROVISIONING COMPLETE!")
        print("=" * 70)
        print(f"\n🌐 VPS IP Address: {instance_info['main_ip']}")
        print(f"\n📝 Files created:")
        print(f"   - {OUTPUT_IP_FILE}")
        print(f"   - {OUTPUT_INSTANCE_FILE}")
        print("\n" + "=" * 70 + "\n")
        sys.exit(0)
    else:
        print("\n❌ Provisioning failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
