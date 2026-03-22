#!/usr/bin/env python3
"""
Azure Secrets Provider Client
Fetches secrets from the local credentials server or Azure Key Vault directly.
Provides a unified interface for all Biomimetics/ARCA services.

Usage:
    from azure_secrets_provider import SecretsProvider

    # Option 1: Use credentials server (recommended)
    provider = SecretsProvider()

    # Option 2: Direct Azure Key Vault (bypasses credentials server)
    provider = SecretsProvider(use_azure_direct=True)

    # Fetch secrets
    github_token = provider.get("github-token")
    notion_key = provider.get("notion-api-key")

    # Batch fetch
    secrets = provider.get_batch(["github-token", "notion-api-key", "gemini-api-key"])

Environment Variables:
    CREDENTIALS_SERVER_URL  - URL of credentials server (default: http://127.0.0.1:8089)
    CREDENTIALS_API_KEY     - API key for credentials server
    AZURE_KEY_VAULT_NAME   - Key vault name (for direct mode)
    AZURE_TENANT_ID         - Azure AD tenant ID
    AZURE_CLIENT_ID         - Service principal app ID
    AZURE_CLIENT_SECRET     - Service principal secret
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("secrets_provider")


@dataclass
class SecretsProvider:
    """
    Unified secrets provider supporting two modes:
    1. Credentials server (default) - faster, cached, single auth point
    2. Direct Azure Key Vault - bypasses server, uses Azure SDK directly
    """

    server_url: str = "http://127.0.0.1:8089"
    api_key: Optional[str] = None
    use_azure_direct: bool = False
    cache_ttl: int = 300
    timeout: float = 10.0

    _cache: Dict[str, tuple] = field(default_factory=dict)
    _azure_token: Optional[str] = None
    _azure_token_expires: float = 0

    def __post_init__(self):
        self.api_key = self.api_key or os.getenv("CREDENTIALS_API_KEY")
        self.server_url = os.getenv("CREDENTIALS_SERVER_URL", self.server_url)

        if not self.api_key and not self.use_azure_direct:
            logger.warning("No CREDENTIALS_API_KEY set - authentication may fail")

    def _get_cached(self, name: str) -> Optional[str]:
        """Get from local cache if valid."""
        if name in self._cache:
            value, timestamp = self._cache[name]
            if time.time() - timestamp < self.cache_ttl:
                return value
        return None

    def _set_cached(self, name: str, value: str):
        """Set local cache entry."""
        self._cache[name] = (value, time.time())
        if len(self._cache) > 500:
            oldest = min(self._cache.items(), key=lambda x: x[1][1])
            del self._cache[oldest[0]]

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Fetch a single secret.

        Args:
            name: Secret name in Azure Key Vault
            default: Default value if not found

        Returns:
            Secret value or default
        """
        cached = self._get_cached(name)
        if cached is not None:
            return cached

        try:
            if self.use_azure_direct:
                value = self._get_from_azure(name)
            else:
                value = self._get_from_server(name)

            if value:
                self._set_cached(name, value)
            return value or default

        except Exception as e:
            logger.error(f"Failed to fetch '{name}': {e}")
            return default

    def get_batch(self, names: List[str]) -> Dict[str, Optional[str]]:
        """
        Fetch multiple secrets at once.

        Args:
            names: List of secret names

        Returns:
            Dict mapping names to values (None if not found)
        """
        results = {}
        uncached = []

        for name in names:
            cached = self._get_cached(name)
            if cached is not None:
                results[name] = cached
            else:
                uncached.append(name)

        if not uncached:
            return results

        try:
            if self.use_azure_direct:
                for name in uncached:
                    results[name] = self._get_from_azure(name)
            else:
                batch_results = self._get_batch_from_server(uncached)
                results.update(batch_results)

            for name, value in results.items():
                if value:
                    self._set_cached(name, value)

        except Exception as e:
            logger.error(f"Batch fetch failed: {e}")
            for name in uncached:
                if name not in results:
                    results[name] = None

        return results

    def _get_from_server(self, name: str) -> Optional[str]:
        """Fetch from credentials server."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.server_url}/secrets/{name}",
                headers=headers,
            )

        if response.status_code == 404:
            return None
        if response.status_code == 401:
            raise PermissionError("Invalid API key")
        if response.status_code != 200:
            raise RuntimeError(f"Server error: {response.status_code}")

        return response.json().get("value")

    def _get_batch_from_server(self, names: List[str]) -> Dict[str, Optional[str]]:
        """Batch fetch from credentials server."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.server_url}/secrets/batch",
                json={"secrets": names},
                headers=headers,
            )

        if response.status_code == 401:
            raise PermissionError("Invalid API key")
        if response.status_code != 200:
            raise RuntimeError(f"Server error: {response.status_code}")

        data = response.json()
        return data.get("secrets", {})

    def _get_azure_token(self) -> str:
        """Get Azure AD access token."""
        if self._azure_token and time.time() < self._azure_token_expires:
            return self._azure_token

        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        if not all([tenant_id, client_id, client_secret]):
            raise RuntimeError("Azure credentials not configured")

        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://vault.azure.net/.default",
                },
            )

        if response.status_code != 200:
            raise RuntimeError(f"Azure auth failed: {response.status_code}")

        data = response.json()
        self._azure_token = data["access_token"]
        self._azure_token_expires = time.time() + data.get("expires_in", 3600) - 60
        return self._azure_token

    def _get_from_azure(self, name: str) -> Optional[str]:
        """Fetch directly from Azure Key Vault."""
        vault_name = os.getenv("AZURE_KEY_VAULT_NAME", "arca-mcp-kv-dae")
        token = self._get_azure_token()

        url = f"https://{vault_name}.vault.azure.net/secrets/{name}?api-version=7.4"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise RuntimeError(f"Key Vault error: {response.status_code}")

        return response.json().get("value")

    def list_secrets(self) -> List[str]:
        """List all secret names in the vault."""
        if self.use_azure_direct:
            return self._list_azure_secrets()
        return self._list_server_secrets()

    def _list_server_secrets(self) -> List[str]:
        """List secrets via credentials server."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.server_url}/secrets",
                headers=headers,
            )

        if response.status_code != 200:
            raise RuntimeError(f"Server error: {response.status_code}")

        return response.json().get("secrets", [])

    def _list_azure_secrets(self) -> List[str]:
        """List secrets directly from Azure Key Vault."""
        vault_name = os.getenv("AZURE_KEY_VAULT_NAME", "arca-mcp-kv-dae")
        token = self._get_azure_token()

        url = f"https://{vault_name}.vault.azure.net/secrets?api-version=7.4"

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )

        if response.status_code != 200:
            raise RuntimeError(f"Key Vault error: {response.status_code}")

        data = response.json()
        return [item["id"].split("/")[-1] for item in data.get("value", [])]

    def clear_cache(self, name: Optional[str] = None):
        """Clear local cache."""
        if name:
            self._cache.pop(name, None)
        else:
            self._cache.clear()

    def rotate(self, name: Optional[str] = None):
        """Invalidate cache (force re-fetch on next request)."""
        if name:
            self._cache.pop(name, None)
            if not self.use_azure_direct:
                headers = {}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key
                with httpx.Client(timeout=self.timeout) as client:
                    client.post(
                        f"{self.server_url}/secrets/rotate",
                        json={"name": name} if name else None,
                        headers=headers,
                    )
        else:
            self._cache.clear()
            if not self.use_azure_direct:
                headers = {}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key
                with httpx.Client(timeout=self.timeout) as client:
                    client.post(
                        f"{self.server_url}/secrets/rotate",
                        headers=headers,
                    )


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Convenience function for single secret fetch.
    Uses global provider instance.
    """
    provider = SecretsProvider()
    return provider.get(name, default)


def get_batch(names: List[str]) -> Dict[str, Optional[str]]:
    """
    Convenience function for batch fetch.
    Uses global provider instance.
    """
    provider = SecretsProvider()
    return provider.get_batch(names)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    provider = SecretsProvider()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            print("Available secrets:")
            for name in provider.list_secrets():
                print(f"  - {name}")
        elif sys.argv[1] == "--get":
            if len(sys.argv) < 3:
                print("Usage: azure_secrets_provider.py --get <secret-name>")
                sys.exit(1)
            value = provider.get(sys.argv[2])
            if value:
                print(value)
            else:
                print(f"Secret '{sys.argv[2]}' not found")
        elif sys.argv[1] == "--batch":
            if len(sys.argv) < 3:
                print(
                    "Usage: azure_secrets_provider.py --batch <comma-separated-names>"
                )
                sys.exit(1)
            names = sys.argv[2].split(",")
            results = provider.get_batch(names)
            for name, value in results.items():
                print(
                    f"{name}: {value[:20] + '...' if value and len(value) > 20 else value}"
                )
        else:
            print("Usage:")
            print("  --list              List all secrets")
            print("  --get <name>        Get a single secret")
            print("  --batch <names>    Get multiple secrets (comma-separated)")
    else:
        # Test connectivity
        print("Testing credentials server...")
        try:
            secrets = provider.list_secrets()
            print(f"✓ Connected! Found {len(secrets)} secrets")
            print("\nFirst 10 secrets:")
            for name in secrets[:10]:
                print(f"  - {name}")
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            print("\nFalling back to direct Azure...")
            try:
                provider.use_azure_direct = True
                secrets = provider.list_secrets()
                print(f"✓ Direct Azure connected! Found {len(secrets)} secrets")
            except Exception as e2:
                print(f"✗ Direct Azure also failed: {e2}")
