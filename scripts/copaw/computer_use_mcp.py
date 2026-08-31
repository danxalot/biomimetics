#!/usr/bin/env python3
"""
Computer Use MCP Server for CoPaw BiOS.
Provides OS-level interaction tools: Screenshots, Mouse, and Keyboard control.
"""

import os
import sys
import json
import base64
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from mcp.server.fastmcp import FastMCP
import pyautogui
import mss
from PIL import Image
import io

# Disable fail-safe for remote execution safety if needed, 
# but for local use it's better to keep it enabled.
# pyautogui.FAILSAFE = False 

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("computer_use_mcp")

mcp = FastMCP(
    "BiOS Computer Use",
    instructions="""
    Tools for OS interaction on the local host machine.
    Allows taking screenshots, moving the mouse, clicking, and typing.
    
    Coordinate System:
    - (0, 0) is the top-left corner of the primary monitor.
    - X increases to the right, Y increases downwards.
    """,
)

@mcp.tool()
def get_screen_size() -> str:
    """Get the primary monitor resolution."""
    width, height = pyautogui.size()
    return f"Screen Resolution: {width}x{height}"

@mcp.tool()
def take_screenshot(format: str = "base64") -> str:
    """
    Capture a screenshot of the primary monitor.
    Args:
        format: 'base64' (default) or 'file' (saves to ~/biomimetics/logs/screenshots/)
    """
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1] # Primary
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            if format == "file":
                log_dir = Path("/Users/danexall/biomimetics/logs/screenshots")
                log_dir.mkdir(parents=True, exist_ok=True)
                filename = f"screenshot_{int(time.time())}.png"
                filepath = log_dir / filename
                img.save(filepath)
                return f"Screenshot saved to {filepath}"
            else:
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG", quality=70)
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                return f"data:image/jpeg;base64,{img_str}"
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return f"Error: {e}"

@mcp.tool()
def mouse_click(x: int, y: int, button: str = "left", clicks: int = 1, normalized: bool = True) -> str:
    """
    Click the mouse at specific screen coordinates.
    Args:
        x: X-coordinate (0-1000 if normalized, else raw pixels)
        y: Y-coordinate (0-1000 if normalized, else raw pixels)
        button: 'left', 'right', or 'middle'
        clicks: Number of clicks
        normalized: Whether coordinates are 0-1000 (default: True)
    """
    try:
        real_x, real_y = x, y
        if normalized:
            width, height = pyautogui.size()
            real_x = int((x / 1000) * width)
            real_y = int((y / 1000) * height)
        
        pyautogui.click(x=real_x, y=real_y, button=button, clicks=clicks)
        return f"Clicked {button} button at ({real_x}, {real_y}) {clicks} times."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def mouse_move(x: int, y: int, duration: float = 0.5, normalized: bool = True) -> str:
    """
    Move mouse to coordinates.
    Args:
        x: X-coordinate (0-1000 if normalized)
        y: Y-coordinate (0-1000 if normalized)
        normalized: Whether coordinates are 0-1000 (default: True)
    """
    try:
        real_x, real_y = x, y
        if normalized:
            width, height = pyautogui.size()
            real_x = int((x / 1000) * width)
            real_y = int((y / 1000) * height)
            
        pyautogui.moveTo(x=real_x, y=real_y, duration=duration)
        return f"Moved mouse to ({real_x}, {real_y})."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def mouse_drag(x: int, y: int, duration: float = 1.0, normalized: bool = True) -> str:
    """
    Drag mouse from current position to coordinates.
    Args:
        x: X-coordinate (0-1000 if normalized)
        y: Y-coordinate (0-1000 if normalized)
        normalized: Whether coordinates are 0-1000 (default: True)
    """
    try:
        real_x, real_y = x, y
        if normalized:
            width, height = pyautogui.size()
            real_x = int((x / 1000) * width)
            real_y = int((y / 1000) * height)
            
        pyautogui.dragTo(x=real_x, y=real_y, duration=duration)
        return f"Dragged mouse to ({real_x}, {real_y})."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def keyboard_type(text: str, interval: float = 0.1) -> str:
    """Type a string of text."""
    try:
        pyautogui.write(text, interval=interval)
        return f"Typed: '{text}'"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def keyboard_press(key: str) -> str:
    """
    Press a specific key (e.g., 'enter', 'esc', 'space', 'command', 'option').
    """
    try:
        pyautogui.press(key)
        return f"Pressed key: {key}"
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run()
