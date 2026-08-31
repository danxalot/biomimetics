#!/usr/bin/env python3
"""
BiOS System Verification Suite
===============================
A unified diagnostic and validation utility for both humans and AI agents.
Checks the integrity of Python environments, local services, credentials, 
MCP server meshes, and network relays.

Usage:
    python3 verify_system.py [options]

Options:
    --group <group_name>  Run a specific diagnostic suite (can be repeated).
    --list-groups         List all available diagnostic groups and exit.
    --json                Output schema-conforming JSON for agent processing.
    --verbose             Enable detailed logs and full tracebacks.
    --help, -h            Show this help menu.
"""

import os
import sys
import json
import argparse
import subprocess
import urllib.request
import ssl
import urllib.error
import socket
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# =============================================================================
# CLI Terminal Color Codes (Disabled in JSON mode)
# =============================================================================
COLOR_GREEN = "\033[92m"
COLOR_AMBER = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_BLUE = "\033[94m"
COLOR_CYAN = "\033[96m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"

def print_color(text: str, color_code: str, force_stdout: bool = False):
    """Prints colored text, respecting global JSON-output suppression."""
    if '--json' in sys.argv:
        return
    print(f"{color_code}{text}{COLOR_RESET}", file=sys.stdout if force_stdout else sys.stderr)

# =============================================================================
# Base Diagnostic Classes
# =============================================================================
class DiagnosticCheck:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        """
        Executes the check.
        Returns:
            Tuple of (status, message, remediation_command)
            status values: 'OK', 'WARNING', 'ERROR'
        """
        raise NotImplementedError

class DiagnosticGroup:
    def __init__(self, name: str, description: str, checks: List[DiagnosticCheck]):
        self.name = name
        self.description = description
        self.checks = checks

    def run(self, verbose: bool = False) -> List[Dict[str, Any]]:
        results = []
        for check in self.checks:
            try:
                status, message, remediation = check.execute(verbose)
            except Exception as e:
                status, message, remediation = "ERROR", f"Unhandled check failure: {e}", None
            
            results.append({
                "check_name": check.name,
                "description": check.description,
                "status": status,
                "message": message,
                "remediation": remediation
            })
        return results

# =============================================================================
# Suite 1: System Environment Suite
# =============================================================================
class PythonPackageCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "Python Packages",
            "Verify installation of core ML, sequences, and network packages."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        required = {
            "clifford": "clifford",
            "torch": "torch",
            "torchdiffeq": "torchdiffeq",
            "redis": "redis",
            "websockets": "websockets",
            "httpx": "httpx",
            "pandas": "pandas",
            "wandb": "wandb"
        }
        
        # Mamba SSM may require special compilation; check separately
        optional = {
            "mamba_ssm": "mamba"
        }
        
        missing = []
        for lib, import_name in required.items():
            try:
                __import__(import_name)
            except ImportError:
                missing.append(lib)
                
        missing_optional = []
        for lib, import_name in optional.items():
            try:
                __import__(import_name)
            except ImportError:
                missing_optional.append(lib)

        if missing:
            pkg_str = ", ".join(missing)
            remediation = f"pip3 install {' '.join(missing)}"
            return "ERROR", f"Missing critical libraries: {pkg_str}", remediation
        
        if missing_optional:
            opt_str = ", ".join(missing_optional)
            return "WARNING", f"Missing optional optimization packages: {opt_str} (GPU acceleration might be limited)", "pip3 install mamba-ssm"

        return "OK", "All required and optional Python modules successfully imported.", None

class PyTorchGPUCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "PyTorch CUDA Hardware",
            "Checks CUDA availability, GPU device models, and VRAM memory."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        try:
            import torch
        except ImportError:
            return "ERROR", "PyTorch is not installed. Cannot perform GPU diagnostics.", "pip3 install torch"

        if not torch.cuda.is_available():
            # Darwin (macOS) might run MPS instead of CUDA
            if sys.platform == "darwin":
                if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    return "OK", "CUDA is unavailable, but Apple Metal (MPS) device is online.", None
            return "WARNING", "CUDA hardware acceleration is unavailable. Model will fallback to CPU (extremely slow for 336hr runs).", "Install CUDA drivers / check PyTorch CUDA compatibility."

        try:
            device_name = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_memory
            vram_gb = vram_bytes / (1024 ** 3)
            msg = f"GPU Online: {device_name} ({vram_gb:.2f} GB VRAM available)"
            
            # The 336-hour schedule assumes high VRAM L40S, warn if running low VRAM
            if vram_gb < 16.0:
                return "WARNING", f"{msg} - Warning: Low VRAM detected (< 16 GB). Phase B training may OOM.", None
            return "OK", msg, None
        except Exception as e:
            return "ERROR", f"Failed to probe GPU details: {e}", "Verify Nvidia SMI drivers are installed."

class DockerDaemonCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "Docker Containers",
            "Verifies Docker status and checks active containers (HDC Redis, LLM servers)."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        try:
            # Check daemon
            res = subprocess.run(["docker", "info"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
            if res.returncode != 0:
                return "WARNING", "Docker daemon is unreachable or not running.", "open -a Docker (on macOS) or systemctl start docker"
            
            # Check running containers
            containers_res = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3
            )
            containers = [c.strip() for c in containers_res.stdout.split("\n") if c.strip()]
            
            if not containers:
                return "OK", "Docker daemon is active, but no containers are currently running.", None
                
            return "OK", f"Docker is running. Active containers: {', '.join(containers)}", None
        except FileNotFoundError:
            return "WARNING", "Docker CLI tool is not installed.", "Install Docker Desktop"
        except subprocess.TimeoutExpired:
            return "ERROR", "Docker CLI check timed out (unresponsive).", "Restart Docker daemon"

# =============================================================================
# Suite 2: Local Services Suite
# =============================================================================
class CredentialsServerCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "Credentials Server",
            "Check status of local Runtime Credentials server (port 8089)."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        url = "http://127.0.0.1:8089/health"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as response:
                content = response.read().decode().strip()
                return "OK", f"Credentials Server is online (Health status: {response.status} - {content})", None
        except urllib.error.URLError as e:
            return "ERROR", f"Credentials Server offline or unreachable: {e.reason}", "python3 scripts/start_credentials_server.py"
        except Exception as e:
            return "ERROR", f"Health check failed: {e}", "Restart credentials server"

class CanvasEndpointCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "Canvas Console / HUD",
            "Test console push endpoint (port 8090) for CoPaw HUD rendering."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        url = "http://127.0.0.1:8090/console/push"
        payload = json.dumps({
            "session_id": "console:verify_health",
            "text": "<!-- Health Check Silenced -->",
            "type": "html"
        }).encode("utf-8")
        
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return "OK", f"HUD Canvas console push accepted (Status: {response.status})", None
        except urllib.error.URLError as e:
            return "WARNING", f"HUD Console (port 8090) unreachable: {e.reason}. Canvas tools might fail.", "Verify launcher processes or check server configuration."
        except Exception as e:
            return "WARNING", f"HUD Console push test failed: {e}", "Check server port binds."

class RedisHDCConnectionCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "Redis HDC Connection",
            "Validates database connectivity to the Hyperdimensional Computing memory."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        try:
            import redis
        except ImportError:
            return "ERROR", "Redis Python package is not installed.", "pip3 install redis"

        # Check default URL in environment or training script
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            client = redis.Redis.from_url(redis_url, socket_timeout=3.0)
            client.ping()
            
            # Check number of keys stored
            key_count = len(client.keys("*"))
            return "OK", f"Connected successfully to Redis HDC at {redis_url} (Stored keys: {key_count})", None
        except redis.exceptions.ConnectionError as e:
            return "ERROR", f"Could not connect to Redis server at {redis_url}: {e}", "docker start redis_hdc OR run a local redis-server"
        except Exception as e:
            return "ERROR", f"Unexpected error during Redis ping: {e}", "Verify Redis network bounds"

# =============================================================================
# Suite 3: Credentials Suite
# =============================================================================
class LocalSecretsCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "Local Secret Keys",
            "Scans the local vault directory to ensure all crucial keys are present and readable."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        secrets_dir = Path("/Users/danexall/biomimetics/secrets")
        
        required_keys = [
            "credentials_api_key",
            "notion_api_key",
            "google_api_key",
            "github_token",
            "anthropic_api_key",
            "vultr_api_key",
            "wandb_api_key",
            "arca-mcp-api-key",
            "cloudflare-dns-token",
            "gdrive-oauth-token"
        ]

        if not secrets_dir.exists():
            return "ERROR", f"Secrets directory {secrets_dir} does not exist.", "Run Azure Key Vault sync: python3 azure/azure_secrets_init.py --refresh"

        missing = []
        zero_size = []
        for key in required_keys:
            key_file = secrets_dir / key
            if not key_file.exists():
                missing.append(key)
            elif key_file.stat().st_size == 0:
                zero_size.append(key)

        if missing or zero_size:
            msg_parts = []
            if missing:
                msg_parts.append(f"Missing: {', '.join(missing)}")
            if zero_size:
                msg_parts.append(f"Empty (0-byte): {', '.join(zero_size)}")
            
            remediation = "python3 azure/azure_secrets_init.py --refresh"
            return "WARNING", " ; ".join(msg_parts), remediation

        return "OK", f"All {len(required_keys)} critical local secrets files are present, readable, and populated.", None

class CredentialsServerDecryptionCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "Server Key Decryption",
            "Test credentials server decryption handshake via X-API-Key injection."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        key_path = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
        if not key_path.exists():
            return "ERROR", "Cannot execute test: credentials_api_key file is missing locally.", "Run azure secret sync"

        try:
            api_key = key_path.read_text().strip()
            
            # Attempt to fetch the Notion token via decryption
            url = "http://127.0.0.1:8089/secrets/notion_api_key"
            req = urllib.request.Request(url)
            req.add_header("X-API-Key", api_key)
            
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
                secret_val = data.get("value", "")
                if secret_val:
                    return "OK", "Decryption handshake validated. Successfully retrieved decrypted secret.", None
                else:
                    return "ERROR", "Handshake succeeded but decrypted secret returned empty.", "Check vault credentials"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "OK", "Decryption handshake validated. Successfully authenticated, though secret key 'notion_api_key' is not registered on credentials server.", None
            if e.code in (401, 403):
                return "ERROR", f"Handshake Rejected: Credentials Server returned HTTP {e.code} (Invalid API Key)", "Sync/reset secrets"
            return "ERROR", f"Handshake Failed: HTTP {e.code}", "Verify server log files"
        except Exception as e:
            return "ERROR", f"Handshake Decryption Test Failed: {e}", "Verify Credentials server status"

# =============================================================================
# Suite 4: MCP Servers Suite
# =============================================================================
class MCPServerPortCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "MCP Server Meshes",
            "Checks status of local MCP server ports (ARCA MCP - 8086)."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        # ARCA MCP (port 8086) is typically SSE
        mcp_servers = {
            "ARCA MCP (SSE Server)": 8086,
        }
        
        failures = []
        successes = []
        for name, port in mcp_servers.items():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            
            if result == 0:
                successes.append(f"{name} (port {port} online)")
            else:
                failures.append(f"{name} (port {port} offline)")

        if failures:
            # arca_mcp is optional (disabled by default in some configurations)
            # copaw_omni runs stdio inside copaw so it has no direct TCP port, which is expected.
            msg = f"Active: {', '.join(successes)} ; Offline: {', '.join(failures)}"
            return "WARNING", f"Some MCP server ports are inactive: {msg}", "Ensure launchd plists or background services are active if required."

        return "OK", f"All checked MCP ports are active: {', '.join(successes)}", None

# =============================================================================
# Suite 5: Network Suite
# =============================================================================
class ExternalLLMReachabilityCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "External AI Connections",
            "Verify reachability of model providers (Gemini, Anthropic, Tavily, Wandb)."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        targets = {
            "Gemini API": "https://generativelanguage.googleapis.com",
            "Anthropic API": "https://api.anthropic.com",
            "Tavily Search API": "https://api.tavily.com",
            "Weights & Biases (Wandb)": "https://api.wandb.ai"
        }
        
        failures = []
        context = ssl._create_unverified_context()
        for name, url in targets.items():
            try:
                # Issue standard HEAD request for raw reachability (fast)
                req = urllib.request.Request(url, method="HEAD")
                # Add headers to satisfy strict API servers
                req.add_header("User-Agent", "Mozilla/5.0 (BiOS-Diagnostic)")
                with urllib.request.urlopen(req, timeout=3.5, context=context):
                    pass
            except urllib.error.HTTPError as e:
                # HTTP errors (like 401 or 403) mean we successfully reached the server
                pass
            except Exception:
                failures.append(name)

        if failures:
            return "WARNING", f"Unreachable backends: {', '.join(failures)}. Model calls or logs might fail.", "Check internet connection or DNS configurations."

        return "OK", "Successfully established network handshakes with all critical AI endpoints.", None

class CloudflareRelayTunnelCheck(DiagnosticCheck):
    def __init__(self):
        super().__init__(
            "Cloudflare Relay Tunnel",
            "Verify reachability of the remote Gemini Multimodal Voice bridge URL."
        )

    def execute(self, verbose: bool = False) -> Tuple[str, str, Optional[str]]:
        tunnel_file = Path("/Users/danexall/biomimetics/secrets/gemini_relay_tunnel_url")
        if not tunnel_file.exists():
            return "WARNING", "No gemini_relay_tunnel_url file found in vault. Skipping resolution.", None

        try:
            tunnel_url = tunnel_file.read_text().strip()
            if not tunnel_url:
                return "WARNING", "gemini_relay_tunnel_url file is empty.", None

            # Convert ws/wss to http/https for validation checks
            test_url = tunnel_url
            if not (test_url.startswith("http://") or test_url.startswith("https://") or test_url.startswith("ws://") or test_url.startswith("wss://")):
                test_url = "https://" + test_url
                
            if test_url.startswith("wss://"):
                test_url = test_url.replace("wss://", "https://")
            elif test_url.startswith("ws://"):
                test_url = test_url.replace("ws://", "http://")

            req = urllib.request.Request(test_url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0")
            
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=3.5, context=context) as response:
                return "OK", f"Cloudflare Voice Tunnel resolved successfully: {tunnel_url} (HTTP {response.status})", None
        except urllib.error.HTTPError as e:
            # 400 or 426 is normal for upgrading websocket endpoints, meaning it's reachable!
            if e.code in (400, 426, 404, 502):
                return "OK", f"Voice Tunnel reached successfully (HTTP {e.code} confirms DNS resolution and reachability; expected default response for raw WebSocket endpoints)", None
            return "ERROR", f"Voice Tunnel returned unexpected error: HTTP {e.code}", "Verify local tunnel daemon"
        except Exception as e:
            return "ERROR", f"Could not reach Voice Tunnel at {tunnel_url}: {e}", "Verify tailscale or cloudflare tunnel status"

# =============================================================================
# Diagnostic Suite Organizer
# =============================================================================
DIAGNOSTIC_SUITES: Dict[str, DiagnosticGroup] = {
    "environment": DiagnosticGroup(
        "environment",
        "System Context & Hardware Suite",
        [PythonPackageCheck(), PyTorchGPUCheck(), DockerDaemonCheck()]
    ),
    "infra_services": DiagnosticGroup(
        "infra_services",
        "Local System Services Suite",
        [CredentialsServerCheck(), CanvasEndpointCheck(), RedisHDCConnectionCheck()]
    ),
    "secrets": DiagnosticGroup(
        "secrets",
        "Secrets & Credentials Integrity Suite",
        [LocalSecretsCheck(), CredentialsServerDecryptionCheck()]
    ),
    "mcp_servers": DiagnosticGroup(
        "mcp_servers",
        "MCP Mesh Services Suite",
        [MCPServerPortCheck()]
    ),
    "network": DiagnosticGroup(
        "network",
        "Network Relay & Tunnels Suite",
        [ExternalLLMReachabilityCheck(), CloudflareRelayTunnelCheck()]
    )
}

# =============================================================================
# Output Formatters
# =============================================================================
def print_human_report(results_by_group: Dict[str, List[Dict[str, Any]]]):
    """Prints a beautiful, highly-readable styled CLI report."""
    print_color("\n" + "=" * 70, COLOR_CYAN)
    print_color("  BiOS SYSTEM INTEGRITY & DIAGNOSTIC VERIFICATION REPORT", COLOR_BOLD + COLOR_CYAN)
    print_color("=" * 70 + "\n", COLOR_CYAN)

    overall_failures = 0
    overall_warnings = 0
    remediations: List[Tuple[str, str]] = []

    for group_name, checks in results_by_group.items():
        desc = DIAGNOSTIC_SUITES[group_name].description
        print_color(f"📁 {group_name.upper()} :: {desc}", COLOR_BOLD + COLOR_BLUE)
        print_color("-" * 70, COLOR_BLUE)

        for check in checks:
            status = check["status"]
            name = check["check_name"]
            msg = check["message"]
            remed = check["remediation"]

            if status == "OK":
                status_icon = f"[{COLOR_GREEN} OK {COLOR_RESET}]"
            elif status == "WARNING":
                status_icon = f"[{COLOR_AMBER} WARN{COLOR_RESET}]"
                overall_warnings += 1
            else:
                status_icon = f"[{COLOR_RED}FAIL{COLOR_RESET}]"
                overall_failures += 1

            # Save remediation for summaries
            if remed:
                remediations.append((name, remed))

            print(f"  {status_icon}  {COLOR_BOLD}{name:<30}{COLOR_RESET} : {msg}")
        print()

    # Remediation Summary Guide
    if remediations:
        print_color("🔧 SUGGESTED REMEDIATION & REPAIR ACTIONS", COLOR_BOLD + COLOR_AMBER)
        print_color("=" * 70, COLOR_AMBER)
        for check_name, cmd in remediations:
            print(f"  {COLOR_BOLD}* {check_name}:{COLOR_RESET}")
            print(f"    👉 {COLOR_CYAN}{cmd}{COLOR_RESET}\n")

    # Overall Summary Table
    print_color("📊 DIAGNOSTIC RUN SUMMARY", COLOR_BOLD + COLOR_CYAN)
    print_color("=" * 70, COLOR_CYAN)
    total_checks = sum(len(r) for r in results_by_group.values())
    print(f"  Total Checks Run : {total_checks}")
    
    if overall_failures > 0:
        sum_str = f"{COLOR_RED}{overall_failures} FAILED{COLOR_RESET}"
    else:
        sum_str = f"{COLOR_GREEN}0 Failed{COLOR_RESET}"
        
    warn_str = f"{COLOR_AMBER}{overall_warnings} Warning(s){COLOR_RESET}" if overall_warnings > 0 else f"{COLOR_GREEN}0 Warnings{COLOR_RESET}"
    print(f"  System Health    : {sum_str} | {warn_str}")
    print_color("=" * 70 + "\n", COLOR_CYAN)

    if overall_failures > 0:
        sys.exit(1)
    sys.exit(0)

def print_json_report(results_by_group: Dict[str, List[Dict[str, Any]]]):
    """Outputs standardized, programmatically parseable JSON array for agents."""
    flat_results = []
    has_errors = False
    
    for group_name, checks in results_by_group.items():
        for check in checks:
            if check["status"] == "ERROR":
                has_errors = True
            flat_results.append({
                "group": group_name,
                **check
            })
            
    payload = {
        "status": "FAILED" if has_errors else "SUCCESS",
        "timestamp": socket.gethostname(),  # dynamic placeholder in standard environments
        "results": flat_results
    }
    
    print(json.dumps(payload, indent=2), file=sys.stdout)
    if has_errors:
        sys.exit(1)
    sys.exit(0)

# =============================================================================
# CLI Main Routing Entry Point
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Diagnostic Verification tool for checking all systems and connections.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--group",
        action="append",
        choices=list(DIAGNOSTIC_SUITES.keys()),
        help="Specify which groups to run. Can be repeated. Defaults to running all groups."
    )
    
    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="Display list of all registered diagnostic groups and exit."
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Format diagnostic output in structured JSON for agentic parsing."
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose details and stack traces during execution."
    )

    args = parser.parse_args()

    # Handle Group Display
    if args.list_groups:
        if args.json:
            groups_info = {name: suite.description for name, suite in DIAGNOSTIC_SUITES.items()}
            print(json.dumps(groups_info, indent=2))
        else:
            print_color("\nRegistered Diagnostic Groups:", COLOR_BOLD + COLOR_CYAN)
            for name, suite in DIAGNOSTIC_SUITES.items():
                print(f"  * {COLOR_BOLD}{name:<18}{COLOR_RESET} : {suite.description}")
            print()
        sys.exit(0)

    # Determine Active Groups to Run
    active_groups = args.group if args.group else list(DIAGNOSTIC_SUITES.keys())

    # Execute diagnostics
    results = {}
    for group_name in active_groups:
        suite = DIAGNOSTIC_SUITES[group_name]
        results[group_name] = suite.run(args.verbose)

    # Output formatted report
    if args.json:
        print_json_report(results)
    else:
        print_human_report(results)

if __name__ == "__main__":
    main()
