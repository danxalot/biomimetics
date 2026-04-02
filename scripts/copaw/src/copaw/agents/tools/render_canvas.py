# -*- coding: utf-8 -*-
"""Tool for rendering visual components in the CoPaw console HUD."""
from __future__ import annotations

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

async def render_canvas(view: str, content: str) -> ToolResponse:
    """
    Render visual components (HTML or Markdown) in the CoPaw HUD.
    
    Args:
        view (str):
            The type of view to render (e.g., 'email', 'research', 'task', 'status').
        content (str):
            The HTML or Markdown content to render in the HUD.
            
    Returns:
        ToolResponse: The tool response confirming the render request was sent.
    """
    # This tool is a signaling anchor. The actual rendering is intercepted
    # by the channel (e.g. VoiceChannel/VultrRelayClient) and pushed to the 
    # frontend.
    
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=f"Successfully rendered {view} to canvas HUD.",
            ),
        ],
    )
