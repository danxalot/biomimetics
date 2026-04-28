#!/usr/bin/env python3
"""
Vultr Free Tier VPS Provisioning Script
========================================

Automatically provisions a free tier VPS instance on Vultr with the following specs:
- Plan: vc2-1c-0.5gb-free (0.5GB RAM, 10GB storage, 0.5 vCPU)
- Region: London, UK (lhr) or closest available European region
- OS: Debian 12 (bookworm)
- Backups: Disabled (no hidden charges)
- Cloud-Init: User-provided startup scripts

API Documentation: https://www.vultr.com/api/#tag/instances

Requirements:
    - Vultr API key (set via VULTR_API_KEY environment variable or --api-key)
    - Python 3.8+
    - httpx library (pip install httpx)

Usage:
    python3 vultr_provision.py --api-key YOUR_API_KEY
    python3 vultr_provision.py  # Will prompt for API key if not in environment

Author: BiOS Infrastructure Team
Date: 2026-03-23
"""

import os
import sys
import json
import time
import argparse
import base64
from pathlib import Path
from typing import Optional, Dict, List, Any

import httpx

# ============================================================================
# Configuration
# ============================================================================

VULTR_API_BASE = "https://api.vultr.com/v2"

# Free tier plan details
FREE_TIER_PLAN = "vc2-1c-0.5gb-free"
FREE_TIER_REGIONS = [
    "lhr",      # London, UK (primary - closest to EU)
    "ams",      # Amsterdam, Netherlands
    "fra",      # Frankfurt, Germany
    "cdg",      # Paris, France
    "waw",      # Warsaw, Poland
    "mad",      # Madrid, Spain
]

# Debian 12 (bookworm) - OS ID 477
DEBIAN_12_OS_ID = 477

# Default instance label
DEFAULT_LABEL = "bios-gemini-relay"


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
                "User-Agent": "BiOS-Vultr-Provisioner/1.0"
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
    
    # Account Methods
    def get_account_info(self) -> Dict:
        """Get account information."""
        return self.get("/account")
    
    def get_account_balance(self) -> Dict:
        """Get account balance."""
        return self.get("/users/available_plans")
    
    # Plans Methods
    def get_plans(self) -> List[Dict]:
        """Get all available plans."""
        response = self.get("/plans")
        return response.get("plans", [])
    
    def get_free_tier_plan(self) -> Optional[Dict]:
        """Get free tier plan details."""
        plans = self.get_plans()
        for plan in plans:
            if plan.get("id") == FREE_TIER_PLAN:
                return plan
        return None
    
    # Regions Methods
    def get_regions(self) -> List[Dict]:
        """Get all available regions."""
        response = self.get("/regions")
        return response.get("regions", [])
    
    def get_available_region(self) -> Optional[str]:
        """Get first available region from free tier regions list."""
        regions = self.get_regions()
        
        for region_id in FREE_TIER_REGIONS:
            for region in regions:
                if region.get("id") == region_id and region.get("available"):
                    print(f"✅ Selected region: {region['city']} ({region['id']})")
                    return region_id
        
        # Fallback to first available region
        for region in regions:
            if region.get("available"):
                print(f"⚠️  Free tier regions unavailable, using: {region['city']} ({region['id']})")
                return region["id"]
        
        return None
    
    # OS Methods
    def get_os_list(self) -> List[Dict]:
        """Get list of available operating systems."""
        response = self.get("/os")
        return response.get("os", [])
    
    def verify_os_available(self, os_id: int) -> bool:
        """Verify if specific OS is available."""
        os_list = self.get_os_list()
        for os_info in os_list:
            if os_info.get("id") == os_id:
                return True
        return False
    
    # Instances Methods
    def create_instance(self, instance_config: Dict) -> Dict:
        """Create a new VPS instance."""
        return self.post("/instances", json=instance_config)
    
    def get_instance(self, instance_id: str) -> Dict:
        """Get instance details."""
        return self.get(f"/instances/{instance_id}")
    
    def list_instances(self) -> List[Dict]:
        """List all instances."""
        response = self.get("/instances")
        return response.get("instances", [])
    
    def delete_instance(self, instance_id: str) -> None:
        """Delete an instance."""
        self.delete(f"/instances/{instance_id}")
    
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
# Provisioning Script
# ============================================================================

class VultrProvisioner:
    """Handles the complete VPS provisioning workflow."""
    
    def __init__(self, api_key: str, label: str = DEFAULT_LABEL):
        self.client = VultrClient(api_key)
        self.label = label
        self.instance_id: Optional[str] = None
    
    def print_header(self):
        """Print script header."""
        print("\n" + "=" * 70)
        print("  Vultr Free Tier VPS Provisioner")
        print("  BiOS Infrastructure Automation")
        print("=" * 70 + "\n")
    
    def verify_account(self) -> bool:
        """Verify Vultr account and API key."""
        print("📋 Verifying Vultr account...")
        
        try:
            account = self.client.get_account_info()
            user = account.get("user", {})
            
            print(f"   Account: {user.get('email', 'N/A')}")
            print(f"   Name: {user.get('name', 'N/A')}")
            
            return True
            
        except Exception as e:
            print(f"❌ Account verification failed: {e}")
            return False
    
    def verify_free_tier_plan(self) -> bool:
        """Verify free tier plan is available."""
        print(f"\n📦 Checking free tier plan availability ({FREE_TIER_PLAN})...")
        
        plan = self.client.get_free_tier_plan()
        
        if plan:
            print(f"   ✅ Free tier plan available")
            print(f"      RAM: {plan.get('ram', 'N/A')} MB")
            print(f"      Disk: {plan.get('disk', 'N/A')} GB")
            print(f"      CPU: {plan.get('vcpu', 'N/A')} cores")
            print(f"      Price: ${plan.get('monthly_price', 'N/A')}/month")
            return True
        else:
            print(f"   ⚠️  Free tier plan not found in your region")
            print(f"      Available plans will be listed during provisioning")
            return False
    
    def verify_debian_os(self) -> bool:
        """Verify Debian 12 is available."""
        print(f"\n🐧 Verifying Debian 12 (OS ID: {DEBIAN_12_OS_ID})...")
        
        if self.client.verify_os_available(DEBIAN_12_OS_ID):
            print(f"   ✅ Debian 12 is available")
            return True
        else:
            print(f"   ⚠️  Debian 12 not available, will use default OS")
            return False
    
    def get_cloud_init_script(self) -> Optional[str]:
        """Prompt user for cloud-init script path and encode it."""
        print("\n" + "=" * 70)
        print("  Cloud-Init Configuration")
        print("=" * 70)
        print("\nPlease provide the local path to your startup/provisioning scripts")
        print("(e.g., the Gemini Relay setup script) to inject via Cloud-Init:")
        print("\nExample paths:")
        print("  - /Users/danexall/biomimetics/gemini_relay/scripts/setup_vps.sh")
        print("  - /path/to/your/provisioning_script.sh")
        print("\nLeave empty to skip cloud-init configuration")
        
        script_path = input("\n📁 Script path: ").strip()
        
        if not script_path:
            print("   ⊘ Skipping cloud-init configuration")
            return None
        
        # Validate path
        script_file = Path(script_path).expanduser()
        
        if not script_file.exists():
            print(f"   ⚠️  Warning: File not found at {script_file}")
            retry = input("   Continue anyway? (y/n): ").strip().lower()
            if retry != 'y':
                return None
        
        if not script_file.is_file():
            print(f"   ⚠️  Warning: Path is not a file")
            return None
        
        # Read and encode script
        try:
            script_content = script_file.read_text()
            
            # Encode to base64 for cloud-init user-data
            encoded_script = base64.b64encode(script_content.encode()).decode()
            
            print(f"   ✅ Script loaded: {script_file.name}")
            print(f"      Size: {len(script_content)} bytes")
            
            return encoded_script
            
        except Exception as e:
            print(f"   ❌ Error reading script: {e}")
            return None
    
    def build_instance_config(self, region: str, cloud_init_script: Optional[str] = None) -> Dict:
        """Build instance creation payload."""
        config = {
            "region": region,
            "plan": FREE_TIER_PLAN,
            "os_id": DEBIAN_12_OS_ID,
            "label": self.label,
            "backups": "disabled",  # Critical: no hidden charges
            "enable_ipv6": False,   # Keep it simple for free tier
            "ddos_protection": False,
            "activation_email": True,
            "hostname": f"{self.label}.bios.local",
            "tags": ["bios", "gemini-relay", "free-tier"],
        }
        
        # Add cloud-init user-data if provided
        if cloud_init_script:
            config["user_data"] = cloud_init_script
            print(f"\n   ✅ Cloud-init script attached")
        
        return config
    
    def confirm_provisioning(self, config: Dict) -> bool:
        """Show configuration and get user confirmation."""
        print("\n" + "=" * 70)
        print("  Provisioning Configuration")
        print("=" * 70)
        print(f"\n   Region: {config['region']}")
        print(f"   Plan: {config['plan']}")
        print(f"   OS: Debian 12 (bookworm)")
        print(f"   Label: {config['label']}")
        print(f"   Hostname: {config['hostname']}")
        print(f"   Backups: {config['backups']}")
        print(f"   IPv6: {config['enable_ipv6']}")
        print(f"   DDoS Protection: {config['ddos_protection']}")
        print(f"   Cloud-Init: {'Yes' if config.get('user_data') else 'No'}")
        
        print("\n⚠️  IMPORTANT: This will create a VPS instance on your Vultr account")
        print("   While this is the free tier plan, please verify:")
        print("   - Backups are disabled (no extra charges)")
        print("   - You are within Vultr's free tier limits")
        
        confirm = input("\n🔐 Proceed with provisioning? (yes/no): ").strip().lower()
        return confirm == "yes"
    
    def provision(self) -> Optional[str]:
        """Execute the complete provisioning workflow."""
        self.print_header()
        
        # Step 1: Verify account
        if not self.verify_account():
            return None
        
        # Step 2: Verify free tier plan
        self.verify_free_tier_plan()
        
        # Step 3: Verify Debian OS
        self.verify_debian_os()
        
        # Step 4: Get cloud-init script from user
        cloud_init_script = self.get_cloud_init_script()
        
        # Step 5: Get available region
        print(f"\n🌍 Selecting region...")
        region = self.client.get_available_region()
        
        if not region:
            print("❌ No available regions found")
            return None
        
        # Step 6: Build configuration
        config = self.build_instance_config(region, cloud_init_script)
        
        # Step 7: Confirm with user
        if not self.confirm_provisioning(config):
            print("\n❌ Provisioning cancelled by user")
            return None
        
        # Step 8: Create instance
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
            print(f"   Label: {self.label}")
            
            # Step 9: Wait for instance to become active
            instance_data = self.client.wait_for_instance_active(self.instance_id)
            
            # Step 10: Print connection details
            self.print_connection_details(instance_data)
            
            return self.instance_id
            
        except Exception as e:
            print(f"\n❌ Provisioning failed: {e}")
            return None
    
    def print_connection_details(self, instance_data: Dict):
        """Print instance connection details."""
        instance = instance_data.get("instance", {})
        
        print("\n" + "=" * 70)
        print("  ✅ Provisioning Complete!")
        print("=" * 70)
        print(f"\n📋 Instance Details:")
        print(f"   ID: {instance.get('id')}")
        print(f"   Label: {instance.get('label')}")
        print(f"   Hostname: {instance.get('hostname')}")
        print(f"   Region: {instance.get('region')}")
        print(f"   Plan: {instance.get('plan')}")
        print(f"   OS: {instance.get('os')}")
        print(f"   Status: {instance.get('status')}")
        
        print(f"\n🔌 Connection Details:")
        print(f"   IPv4: {instance.get('main_ip')}")
        print(f"   IPv6: {instance.get('v6_main_ip', 'Not enabled')}")
        
        print(f"\n🔐 SSH Access:")
        print(f"   ssh root@{instance.get('main_ip')}")
        print(f"   (Use the SSH key configured in your Vultr account)")
        
        print(f"\n📝 Next Steps:")
        print(f"   1. Wait 2-3 minutes for OS to fully boot")
        print(f"   2. SSH into the instance")
        print(f"   3. Your cloud-init script will run automatically on first boot")
        print(f"   4. Check /var/log/cloud-init-output.log for script output")
        
        print("\n" + "=" * 70 + "\n")
    
    def cleanup(self, instance_id: str, confirm: bool = True) -> bool:
        """Delete an instance."""
        if confirm:
            print(f"\n⚠️  WARNING: This will permanently delete instance {instance_id}")
            confirm_delete = input("Are you sure? (yes/no): ").strip().lower()
            if confirm_delete != "yes":
                print("❌ Deletion cancelled")
                return False
        
        try:
            print(f"🗑️  Deleting instance {instance_id}...")
            self.client.delete_instance(instance_id)
            print(f"✅ Instance deleted successfully")
            return True
        except Exception as e:
            print(f"❌ Deletion failed: {e}")
            return False


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Vultr Free Tier VPS Provisioner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use API key from environment
  export VULTR_API_KEY="your_api_key"
  python3 vultr_provision.py

  # Provide API key via argument
  python3 vultr_provision.py --api-key your_api_key

  # Custom instance label
  python3 vultr_provision.py --label my-gemini-relay

  # Delete an instance
  python3 vultr_provision.py --delete INSTANCE_ID
        """
    )
    
    parser.add_argument(
        "--api-key",
        help="Vultr API key (or set VULTR_API_KEY environment variable)"
    )
    
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Instance label (default: {DEFAULT_LABEL})"
    )
    
    parser.add_argument(
        "--delete",
        metavar="INSTANCE_ID",
        help="Delete the specified instance instead of provisioning"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all instances in your account"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show configuration without creating instance"
    )
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.getenv("VULTR_API_KEY")
    
    if not api_key and not args.list:
        print("❌ Vultr API key required")
        print("\nSet via environment variable:")
        print("  export VULTR_API_KEY='your_api_key'")
        print("\nOr provide via argument:")
        print("  python3 vultr_provision.py --api-key your_api_key")
        sys.exit(1)
    
    # Create provisioner
    provisioner = VultrProvisioner(api_key, label=args.label)
    
    # Handle list instances
    if args.list:
        print("\n📋 Your Vultr Instances:\n")
        try:
            # Try without auth first for listing
            client = VultrClient(api_key if api_key else "")
            instances = client.list_instances()
            
            if not instances:
                print("   No instances found")
            else:
                for instance in instances:
                    print(f"   ID: {instance.get('id')}")
                    print(f"      Label: {instance.get('label')}")
                    print(f"      Region: {instance.get('region')}")
                    print(f"      Plan: {instance.get('plan')}")
                    print(f"      Status: {instance.get('status')}")
                    print(f"      IP: {instance.get('main_ip')}")
                    print()
        except Exception as e:
            print(f"   Error listing instances: {e}")
        sys.exit(0)
    
    # Handle delete instance
    if args.delete:
        success = provisioner.cleanup(args.delete)
        sys.exit(0 if success else 1)
    
    # Handle dry run
    if args.dry_run:
        provisioner.print_header()
        provisioner.verify_account()
        provisioner.verify_free_tier_plan()
        provisioner.verify_debian_os()
        print("\n🔍 Dry run complete - no instance created")
        sys.exit(0)
    
    # Provision new instance
    instance_id = provisioner.provision()
    
    if instance_id:
        print("✅ Provisioning successful!")
        sys.exit(0)
    else:
        print("❌ Provisioning failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
