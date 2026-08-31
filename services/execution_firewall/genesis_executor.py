"""
ARCA Genesis Chain Helper - Authorized Maintainer Agent Calls

Provides utilities for Genesis Chain to properly dispatch jobs to Maintainer Agents
with required firewall authentication headers.

This module is used BY Genesis Chain agents ONLY to generate valid requests
that pass the execution firewall in maintainer_agents service.
"""

import os
import json
import hmac
import hashlib
from typing import Dict, Any, Optional


class GenesisChainExecutor:
    """
    Genesis Chain authenticated executor for Maintainer Agents.
    
    This class generates properly signed requests that pass the execution firewall.
    ONLY Genesis Chain should use this - other services will be blocked.
    """
    
    def __init__(self, api_key: Optional[str] = None, agent_name: str = "genesis_chain"):
        """
        Initialize Genesis Chain executor.
        
        Args:
            api_key: Genesis Chain API key for request signing (from GENESIS_CHAIN_API_KEY env)
            agent_name: Name of the Genesis Chain agent making the request
        """
        self.api_key = api_key or os.environ.get("GENESIS_CHAIN_API_KEY")
        self.agent_name = agent_name
        
        if not self.api_key:
            raise ValueError("GENESIS_CHAIN_API_KEY environment variable must be set for Genesis Chain execution")
    
    def create_authorized_request_headers(self, request_body: Dict[str, Any]) -> Dict[str, str]:
        """
        Create HTTP headers for authorized Genesis Chain request.
        
        These headers will pass the execution firewall in maintainer_agents service.
        
        Args:
            request_body: The request body to sign
            
        Returns:
            Headers dict with firewall authentication
        """
        # Create HMAC signature of request body
        message = json.dumps(request_body, sort_keys=True)
        signature = hmac.new(
            self.api_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "X-Genesis-Chain": "true",  # Identifies as Genesis Chain
            "X-Genesis-Signature": signature,  # HMAC verification
            "X-Genesis-Agent": self.agent_name,  # Which Genesis agent
            "Content-Type": "application/json"
        }
    
    def create_request(
        self,
        agent_type: str,
        operation: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a properly formatted and authenticated request.
        
        Args:
            agent_type: Type of agent (git, docker, security, development)
            operation: Operation to perform
            params: Operation parameters
            
        Returns:
            Dict with 'headers' and 'body' ready for HTTP POST
        """
        request_body = {
            "agent_type": agent_type,
            "operation": operation,
            "params": params or {}
        }
        
        headers = self.create_authorized_request_headers(request_body)
        
        return {
            "headers": headers,
            "body": request_body,
            "url": "http://maintainer_agents:8090/execute"  # Default URL
        }


def create_genesis_executor(agent_name: str = "genesis_chain") -> GenesisChainExecutor:
    """
    Factory function to create Genesis Chain executor.
    
    Args:
        agent_name: Name of the Genesis Chain agent
        
    Returns:
        GenesisChainExecutor instance ready to create authorized requests
    """
    return GenesisChainExecutor(agent_name=agent_name)


# Example usage (for testing purposes):
if __name__ == "__main__":
    import os
    
    # Set up test API key
    os.environ["GENESIS_CHAIN_API_KEY"] = "test_key_12345"
    
    # Create executor
    executor = create_genesis_executor("architect")
    
    # Create a request
    request = executor.create_request(
        agent_type="git",
        operation="status",
        params={"repo": "/app/repo"}
    )
    
    print("Authorized Request:")
    print(f"URL: {request['url']}")
    print(f"Headers: {json.dumps(request['headers'], indent=2)}")
    print(f"Body: {json.dumps(request['body'], indent=2)}")
