
import sys
import os
import json
import requests

# Add the agent_service directory to the python path to import MCPClient
sys.path.append('/home/ubuntu/ARCA/services/agent_service')

from mcp_client import MCPClient

def connect_and_list_tools():
    """
    Connects to the MCP server and lists available tools to confirm connection.
    """
    mcp_server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8086")
    
    print(f"Attempting to connect to MCP server at: {mcp_server_url}")
    
    try:
        client = MCPClient(mcp_server_url)
        
        # Verify the connection by listing the available tools
        tools_response = client.list_tools()
        
        print("Successfully connected to MCP server.")
        print("I will not take any further action as instructed.")
        
        if tools_response and tools_response.get('result'):
            print("\nAvailable tools:")
            print(json.dumps(tools_response['result'].get('tools', []), indent=2))
        else:
            print("\nCould not retrieve the list of tools.")

    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error: Failed to connect to MCP server at {mcp_server_url}.")
        print("Please ensure the MCP server is running and accessible.")
        print(f"Details: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    connect_and_list_tools()
