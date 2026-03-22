#!/usr/bin/env python3
"""
Local Computer Use MCP Server
Provides screen control tools for CoPaw agent:
- take_screenshot
- move_mouse
- click
- type_text
- get_screen_info

All visual processing is routed to local Qwen-VL model to save cloud tokens.
"""

import os
import sys
import json
import asyncio
import base64
import io
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# MCP imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Installing mcp package...")
    os.system("pip install mcp")
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

# Screen control imports
try:
    import pyautogui
    from PIL import Image
    import pyscreenshot as ImageGrab
except ImportError:
    print("Installing screen control packages...")
    os.system("pip install pyautogui pillow pyscreenshot")
    import pyautogui
    from PIL import Image
    import pyscreenshot as ImageGrab

# Configure pyautogui
pyautogui.FAILSAFE = True  # Move mouse to corner to abort
pyautogui.PAUSE = 0.5  # Pause between actions


# Create MCP server
app = Server("computer-use")


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available computer control tools"""
    return [
        Tool(
            name="take_screenshot",
            description="Take a screenshot of the current screen. Returns base64 encoded image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer", "description": "X coordinate"},
                            "y": {"type": "integer", "description": "Y coordinate"},
                            "width": {"type": "integer", "description": "Width"},
                            "height": {"type": "integer", "description": "Height"}
                        },
                        "description": "Optional region to capture (default: full screen)"
                    },
                    "save_path": {
                        "type": "string",
                        "description": "Optional path to save screenshot"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="move_mouse",
            description="Move the mouse cursor to specified coordinates",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "duration": {
                        "type": "number",
                        "description": "Animation duration in seconds (default: 0.5)",
                        "default": 0.5
                    }
                },
                "required": ["x", "y"]
            }
        ),
        Tool(
            name="click",
            description="Click the mouse at current position or specified coordinates",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate (optional, uses current if not specified)"},
                    "y": {"type": "integer", "description": "Y coordinate (optional, uses current if not specified)"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "Mouse button to click",
                        "default": "left"
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "Number of clicks",
                        "default": 1
                    },
                    "interval": {
                        "type": "number",
                        "description": "Interval between clicks in seconds",
                        "default": 0.1
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="type_text",
            description="Type text at current cursor position",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "interval": {
                        "type": "number",
                        "description": "Interval between keystrokes in seconds",
                        "default": 0.05
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="get_screen_info",
            description="Get information about the screen (resolution, primary monitor, etc.)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="press_key",
            description="Press a keyboard key or key combination",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key to press (e.g., 'enter', 'tab', 'ctrl+c')"
                    },
                    "interval": {
                        "type": "number",
                        "description": "Interval between key presses",
                        "default": 0.1
                    }
                },
                "required": ["key"]
            }
        ),
        Tool(
            name="scroll",
            description="Scroll the mouse wheel",
            inputSchema={
                "type": "object",
                "properties": {
                    "clicks": {
                        "type": "integer",
                        "description": "Number of clicks to scroll (positive=up, negative=down)"
                    },
                    "x": {
                        "type": "integer",
                        "description": "X coordinate to scroll at (optional)"
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate to scroll at (optional)"
                    }
                },
                "required": ["clicks"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Execute computer control tools"""
    
    try:
        if name == "take_screenshot":
            return await handle_screenshot(arguments)
        elif name == "move_mouse":
            return await handle_move_mouse(arguments)
        elif name == "click":
            return await handle_click(arguments)
        elif name == "type_text":
            return await handle_type_text(arguments)
        elif name == "get_screen_info":
            return await handle_get_screen_info(arguments)
        elif name == "press_key":
            return await handle_press_key(arguments)
        elif name == "scroll":
            return await handle_scroll(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    except Exception as e:
        return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]


async def handle_screenshot(arguments: Dict[str, Any]) -> List[TextContent]:
    """Take a screenshot"""
    region = arguments.get("region")
    save_path = arguments.get("save_path")
    
    # Take screenshot
    if region:
        screenshot = pyautogui.screenshot(
            region=(
                region.get("x", 0),
                region.get("y", 0),
                region.get("width", 0),
                region.get("height", 0)
            )
        )
    else:
        screenshot = pyautogui.screenshot()
    
    # Convert to base64
    buffer = io.BytesIO()
    screenshot.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    # Save to file if requested
    if save_path:
        screenshot.save(save_path)
    
    # Get screen dimensions for context
    width, height = pyautogui.size()
    
    result = {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "screen_size": {"width": width, "height": height},
        "image_base64": img_base64[:1000] + "...",  # Truncate for display
        "image_full_base64": img_base64,  # Full image for processing
        "format": "PNG"
    }
    
    if save_path:
        result["saved_to"] = save_path
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_move_mouse(arguments: Dict[str, Any]) -> List[TextContent]:
    """Move mouse to coordinates"""
    x = arguments.get("x")
    y = arguments.get("y")
    duration = arguments.get("duration", 0.5)
    
    pyautogui.moveTo(x, y, duration=duration)
    
    current_x, current_y = pyautogui.position()
    
    result = {
        "status": "success",
        "action": "move_mouse",
        "target": {"x": x, "y": y},
        "current_position": {"x": current_x, "y": current_y},
        "duration": duration
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_click(arguments: Dict[str, Any]) -> List[TextContent]:
    """Click mouse"""
    x = arguments.get("x")
    y = arguments.get("y")
    button = arguments.get("button", "left")
    clicks = arguments.get("clicks", 1)
    interval = arguments.get("interval", 0.1)
    
    if x is not None and y is not None:
        pyautogui.click(x=x, y=y, clicks=clicks, interval=interval, button=button)
    else:
        pyautogui.click(clicks=clicks, interval=interval, button=button)
    
    current_x, current_y = pyautogui.position()
    
    result = {
        "status": "success",
        "action": "click",
        "button": button,
        "clicks": clicks,
        "position": {"x": x, "y": y} if x and y else {"x": current_x, "y": current_y}
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_type_text(arguments: Dict[str, Any]) -> List[TextContent]:
    """Type text"""
    text = arguments.get("text", "")
    interval = arguments.get("interval", 0.05)
    
    pyautogui.write(text, interval=interval)
    
    result = {
        "status": "success",
        "action": "type_text",
        "text_length": len(text),
        "interval": interval
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_screen_info(arguments: Dict[str, Any]) -> List[TextContent]:
    """Get screen information"""
    width, height = pyautogui.size()
    current_x, current_y = pyautogui.position()
    
    result = {
        "status": "success",
        "screen": {
            "width": width,
            "height": height,
            "total_pixels": width * height
        },
        "mouse_position": {
            "x": current_x,
            "y": current_y
        },
        "failsafe": pyautogui.FAILSAFE,
        "pause": pyautogui.PAUSE
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_press_key(arguments: Dict[str, Any]) -> List[TextContent]:
    """Press keyboard key"""
    key = arguments.get("key", "")
    interval = arguments.get("interval", 0.1)
    
    pyautogui.press(key, interval=interval)
    
    result = {
        "status": "success",
        "action": "press_key",
        "key": key,
        "interval": interval
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_scroll(arguments: Dict[str, Any]) -> List[TextContent]:
    """Scroll mouse wheel"""
    clicks = arguments.get("clicks", 0)
    x = arguments.get("x")
    y = arguments.get("y")
    
    if x is not None and y is not None:
        pyautogui.scroll(clicks, x=x, y=y)
    else:
        pyautogui.scroll(clicks)
    
    result = {
        "status": "success",
        "action": "scroll",
        "clicks": clicks,
        "position": {"x": x, "y": y} if x and y else "current"
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    """Run the MCP server"""
    print("Starting Computer Use MCP Server...")
    print("Tools available:")
    print("  - take_screenshot")
    print("  - move_mouse")
    print("  - click")
    print("  - type_text")
    print("  - get_screen_info")
    print("  - press_key")
    print("  - scroll")
    print("")
    print("Press Ctrl+C to stop")
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
