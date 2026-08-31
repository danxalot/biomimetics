import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from shared.secrets_provider import SecretsProvider

# Initialize FastMCP
mcp = FastMCP("mcp-secrets-bridge")
logger = logging.getLogger(__name__)

# Initialize provider with defaults
provider = SecretsProvider()


@mcp.tool()
def get_arca_secret(key_name: str) -> str:
    """Authoritative retrieval of a secret using `shared.secrets_provider.SecretsProvider`.

    Returns the secret content or an error string prefixed with 'Error:'.
    """
    safe_name = os.path.basename(key_name).replace("..", "")
    logger.info("🔒 MCP Secret Bridge: Request for '%s'", safe_name)

    val = provider.get(safe_name)
    if val is None:
        logger.error("❌ Secret not found: %s", safe_name)
        return f"Error: Secret '{safe_name}' not found."

    logger.info("✅ Secret '%s' retrieved successfully via SecretsProvider.", safe_name)
    return val


if __name__ == "__main__":
    mcp.run()
