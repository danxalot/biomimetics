# -*- coding: utf-8 -*-
"""Isolated vision worker for GIL-free screen capture."""
import base64
import io
import mss
from PIL import Image, ImageOps

def capture_and_encode():
    """Isolated function for screen capture and encoding, safe for multiprocessing."""
    try:
        with mss.mss() as sct:
            # Capture from the primary/first external monitor
            # On macOS, monitor 1 is usually the main display
            sct_img = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Maintain aspect ratio and letterbox to 768x768 to prevent text squishing
            img = ImageOps.pad(img, (768, 768), method=Image.LANCZOS, color=(0, 0, 0))
            
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=75)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        # Return error string or handle it
        return f"ERROR:{str(e)}"
