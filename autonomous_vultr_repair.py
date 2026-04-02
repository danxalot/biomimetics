#!/usr/bin/env python3
"""
Autonomous Vultr SSH Key Repair Script
Fetches credentials from Azure Key Vault, retrieves Vultr password via API,
and repairs SSH authorized_keys file without manual intervention.
"""

import subprocess
import json
import requests
import sys
import os
import time


def run_command(cmd, capture_output=True, check=True):
    """Run a shell command and return result."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture_output, text=True, check=check
        )
        return result.stdout.strip() if capture_output else None
    except subprocess.CalledProcessError as e:
        print(f"Error running command '{cmd}': {e}")
        if capture_output:
            return None
        raise


def get_azure_secret(vault_name, secret_name):
    """Fetch a secret from Azure Key Vault."""
    cmd = f"az keyvault secret show --vault-name {vault_name} --name {secret_name} --query value -o tsv"
    return run_command(cmd)


def get_vultr_instances(api_key):
    """Fetch Vultr instances and return the one matching our IP."""
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get("https://api.vultr.com/v2/instances", headers=headers)
    response.raise_for_status()
    return response.json()


def find_instance_by_ip(instances_data, target_ip):
    """Find instance by public IP and return its default_password."""
    for instance in instances_data.get("instances", []):
        # Check if the instance has our target IP in its public IPs
        public_ip = instance.get("main_ip")
        if public_ip == target_ip:
            return instance.get("default_password")
    return None


def repair_ssh_key(tailscale_ip, password, public_key):
    """Use sshpass to SSH into server and repair authorized_keys."""
    # Commands to run on remote server
    remote_commands = [
        "mkdir -p ~/.ssh",
        "chmod 700 ~/.ssh",
        f'echo "{public_key}" > ~/.ssh/authorized_keys',
        "chmod 600 ~/.ssh/authorized_keys",
        "systemctl restart sshd",
    ]

    # Execute each command via SSH
    for cmd in remote_commands:
        ssh_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@{tailscale_ip} '{cmd}'"
        result = run_command(ssh_cmd, capture_output=False, check=False)
        if result is not None and result != 0:
            print(f"Warning: Command '{cmd}' returned non-zero exit code")

    # Verify the key was set correctly
    verify_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@{tailscale_ip} 'cat ~/.ssh/authorized_keys'"
    output = run_command(verify_cmd, capture_output=True, check=False)
    if output and public_key in output:
        print("SUCCESS: Public key properly installed in authorized_keys")
        return True
    else:
        print("ERROR: Failed to verify public key installation")
        return False


def test_key_based_auth(tailscale_ip):
    """Test that key-based authentication now works (no password needed)."""
    test_cmd = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@{tailscale_ip} 'echo \"Key-based auth successful\"'"
    try:
        result = run_command(test_cmd, capture_output=True, check=False)
        if result is not None and "Key-based auth successful" in result:
            return True
    except:
        pass
    return False


def main():
    print("Starting autonomous Vultr SSH key repair...")

    # Configuration
    VAULT_NAME = "arca-mcp-kv-dae"
    VULTR_API_KEY_SECRET = "vultr-api-key"  # Assuming this is the secret name
    SSH_PUBLIC_KEY_SECRET = "ssh-public-key"  # Assuming this is the secret name
    TAILSCALE_IP = "100.86.112.119"
    TARGET_PUBLIC_IP = "149.248.32.53"

    try:
        # Step 1: Retrieve secrets from Azure Key Vault
        print("Fetching Vultr API key from Azure Key Vault...")
        vultr_api_key = get_azure_secret(VAULT_NAME, VULTR_API_KEY_SECRET)
        if not vultr_api_key:
            raise Exception("Failed to retrieve Vultr API key from Key Vault")

        print("Fetching SSH public key from Azure Key Vault...")
        ssh_public_key = get_azure_secret(VAULT_NAME, SSH_PUBLIC_KEY_SECRET)
        if not ssh_public_key:
            raise Exception("Failed to retrieve SSH public key from Key Vault")

        # Step 2: Get Vultr password via API
        print("Querying Vultr API for instance information...")
        instances_data = get_vultr_instances(vultr_api_key)
        password = find_instance_by_ip(instances_data, TARGET_PUBLIC_IP)
        if not password:
            raise Exception(
                f"Could not find instance with IP {TARGET_PUBLIC_IP} or retrieve default_password"
            )

        print(f"Retrieved password for instance {TARGET_PUBLIC_IP}")

        # Step 3: Repair SSH key using the password
        print("Repairing SSH authorized_keys file...")
        if not repair_ssh_key(TAILSCALE_IP, password, ssh_public_key):
            raise Exception("Failed to repair SSH authorized_keys")

        # Step 4: Verify key-based auth works
        print("Verifying key-based authentication is restored...")
        max_attempts = 5
        for attempt in range(max_attempts):
            if test_key_based_auth(TAILSCALE_IP):
                print("SUCCESS: Key-based SSH access is fully restored!")
                return 0
            else:
                print(f"Attempt {attempt + 1}/{max_attempts} failed, retrying...")
                time.sleep(2)

        raise Exception(
            "Failed to restore key-based SSH access after multiple attempts"
        )

    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
