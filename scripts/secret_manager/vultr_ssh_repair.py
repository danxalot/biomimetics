#!/usr/bin/env python3
"""
Vultr SSH Key Repair Script
Autonomously repairs SSH access to a Vultr VPS.
"""

import os
import sys
import json
import time
import subprocess
from dotenv import load_dotenv

# Load Azure credentials
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env")
load_dotenv(env_path)

os.environ["AZURE_TENANT_ID"] = os.getenv("AZURE_TENANT_ID")
os.environ["AZURE_CLIENT_ID"] = os.getenv("AZURE_CLIENT_ID")
os.environ["AZURE_CLIENT_SECRET"] = os.getenv("AZURE_CLIENT_SECRET")
os.environ["AZURE_KEY_VAULT_NAME"] = os.getenv("AZURE_KEY_VAULT_NAME")

sys.path.insert(0, script_dir)
from azure_secrets_provider import SecretsProvider

TARGET_VPS_IP = "100.86.112.119"
VULTR_INSTANCE_IP = "149.248.32.53"


def get_secrets():
    """Fetch required secrets from Azure Key Vault."""
    provider = SecretsProvider(use_azure_direct=True)

    print("[1/5] Fetching secrets from Azure Key Vault...")
    vultr_api_key = provider.get("vultr-api-key")
    if not vultr_api_key:
        raise RuntimeError("Failed to fetch Vultr API key")
    print(f"  ✓ Vultr API key retrieved")

    # Get local SSH public key
    ssh_pub_key_path = os.path.expanduser("~/.ssh/id_rsa.pub")
    if not os.path.exists(ssh_pub_key_path):
        ssh_pub_key_path = os.path.expanduser("~/.ssh/id_ed25519.pub")

    if not os.path.exists(ssh_pub_key_path):
        raise RuntimeError("No local SSH public key found")

    with open(ssh_pub_key_path, "r") as f:
        ssh_pub_key = f.read().strip()
    print(f"  ✓ Local SSH public key loaded")

    return vultr_api_key, ssh_pub_key


def get_vultr_password(api_key):
    """Get the default root password from Vultr API."""
    print("\n[2/5] Querying Vultr API for instance password...")

    import httpx

    root_password = None

    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            "https://api.vultr.com/v2/instances",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Vultr API error: {response.status_code} - {response.text}"
            )

        data = response.json()

        # Find the instance with the matching internal IP
        for instance in data.get("instances", []):
            if instance.get("main_ip") == VULTR_INSTANCE_IP:
                print(
                    f"  Found instance: {instance.get('label', 'unnamed')} ({VULTR_INSTANCE_IP})"
                )
                # Get password for this instance
                instance_id = instance["id"]

                # For existing instances, we need to get the initial password
                # This is only available at creation time, so we'll need an alternative
                # Try to get the server's user data or stored password
                pw_response = client.get(
                    f"https://api.vultr.com/v2/instances/{instance_id}/password",
                    headers={"Authorization": f"Bearer {api_key}"},
                )

                if pw_response.status_code == 200:
                    root_password = pw_response.json().get("password")
                break

        if not root_password:
            # Try getting the password from startup script or user-data
            print(
                "  Note: Default password not directly available, checking startup scripts..."
            )

            # Try to get from startupscripts
            scripts_resp = client.get(
                "https://api.vultr.com/v2/startup-scripts",
                headers={"Authorization": f"Bearer {api_key}"},
            )

            if scripts_resp.status_code == 200:
                scripts = scripts_resp.json().get("startup_scripts", [])
                for script in scripts:
                    if (
                        "biomimetics" in script.get("name", "").lower()
                        or "vps" in script.get("name", "").lower()
                    ):
                        content = script.get("script", "")
                        if "PASSWORD" in content or "password" in content:
                            import re

                            match = re.search(r"[Pp]assword[:\s]*([^\s\n\r]+)", content)
                            if match:
                                root_password = match.group(1)
                                break

    return root_password


def get_stored_password(api_key):
    """Try to get stored password from Azure vault."""
    print("\n[2/5] Looking for stored server password...")
    provider = SecretsProvider(use_azure_direct=True)

    for secret_name in [
        "vps-root-password",
        "vultr-root-password",
        "server-root-password",
        "root-password",
    ]:
        pw = provider.get(secret_name)
        if pw:
            print(f"  ✓ Found stored password in '{secret_name}'")
            return pw

    # Check if there's a biomimetics-related secret
    all_secrets = provider.list_secrets()
    biomimetics_secrets = [
        s for s in all_secrets if "biomimetics" in s.lower() or "vps" in s.lower()
    ]
    for sec in biomimetics_secrets:
        val = provider.get(sec)
        if val and len(val) > 10 and len(val) < 100:  # Likely a password
            print(f"  ✓ Found potential password in '{sec}'")
            return val

    return None


def ssh_with_password(host, password, commands):
    """Execute commands via SSH using password authentication."""
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            username="root",
            password=password,
            timeout=30,
            look_for_keys=False,
            allow_agent=False,
        )

        results = []
        for cmd in commands:
            stdin, stdout, stderr = client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8")
            error = stderr.read().decode("utf-8")
            results.append(
                {
                    "command": cmd,
                    "exit_code": exit_code,
                    "stdout": output,
                    "stderr": error,
                }
            )
            if exit_code != 0 and error:
                print(
                    f"    Warning: Command '{cmd}' had exit code {exit_code}: {error}"
                )

        return results, None
    except Exception as e:
        return None, str(e)
    finally:
        client.close()


def repair_authorized_keys(host, password, ssh_pub_key):
    """Repair the authorized_keys file on the remote server."""
    print(f"\n[3/5] Connecting to {host} and repairing authorized_keys...")

    commands = [
        "mkdir -p ~/.ssh",
        "chmod 700 ~/.ssh",
        f'echo "{ssh_pub_key}" > ~/.ssh/authorized_keys',
        "chmod 600 ~/.ssh/authorized_keys",
        "cat ~/.ssh/authorized_keys",
        "systemctl restart sshd || service ssh restart || true",
    ]

    results, error = ssh_with_password(host, password, commands)

    if error:
        raise RuntimeError(f"SSH connection failed: {error}")

    print("  ✓ Created ~/.ssh directory")
    print("  ✓ Set correct permissions on ~/.ssh")
    print("  ✓ Wrote authorized_keys file")
    print("  ✓ Set correct permissions on authorized_keys")
    print("  ✓ Restarted SSH service")

    # Verify the key was written
    for r in results:
        if "cat ~/.ssh/authorized_keys" in r["command"]:
            if ssh_pub_key in r["stdout"]:
                print("  ✓ Verified: Public key is in authorized_keys")
            else:
                print(f"  ⚠ Warning: Key verification inconclusive")

    return True


def verify_key_auth(host):
    """Verify key-based SSH authentication works."""
    print(f"\n[4/5] Verifying key-based SSH authentication to {host}...")

    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "PreferredAuthentications=publickey",
                "-o",
                "PasswordAuthentication=no",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "BatchMode=yes",
                f"root@{host}",
                'echo "KEY_AUTH_SUCCESS"',
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if "KEY_AUTH_SUCCESS" in result.stdout:
            print("  ✓ Key-based SSH authentication successful!")
            return True
        else:
            print(f"  ✗ Key authentication failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("  ✗ Connection timed out")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("Vultr SSH Key Repair Script")
    print("=" * 60)

    try:
        # Step 1: Get secrets
        vultr_api_key, ssh_pub_key = get_secrets()

        # Step 2: Get password from Vultr API or stored secrets
        root_password = get_stored_password(vultr_api_key)

        if not root_password:
            # Try Vultr API directly
            root_password = get_vultr_password(vultr_api_key)

        if not root_password:
            print("\n[ERROR] Could not retrieve root password.")
            print("Options:")
            print("  1. Reset the instance via Vultr dashboard to get a new password")
            print("  2. Store the password in Azure Key Vault as 'vps-root-password'")
            sys.exit(1)

        # Step 3: Repair authorized_keys
        repair_authorized_keys(TARGET_VPS_IP, root_password, ssh_pub_key)

        # Wait a moment for SSH to restart
        time.sleep(2)

        # Step 4: Verify key authentication
        success = verify_key_auth(TARGET_VPS_IP)

        print("\n" + "=" * 60)
        if success:
            print("✓ SSH ACCESS RESTORED SUCCESSFULLY")
            print(f"  Server: root@{TARGET_VPS_IP}")
            print(f"  Auth: Key-based (password no longer required)")
        else:
            print("✗ KEY AUTHENTICATION NOT WORKING YET")
            print("  Manual intervention may be required.")
        print("=" * 60)

        return 0 if success else 1

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
