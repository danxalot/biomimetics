#!/usr/bin/env python3
"""
Vision Model Router for CoPaw
Routes screenshot analysis to local Qwen-VL model instead of cloud Minimax
Saves cloud tokens by processing images locally
"""

import os
import sys
import json
import base64
import httpx
from typing import Optional, Dict, Any, List

# Configuration
LOCAL_VISION_URL = os.environ.get(
    "LOCAL_VISION_URL",
    "http://localhost:11435/v1/chat/completions"
)
LOCAL_VISION_MODEL = os.environ.get(
    "LOCAL_VISION_MODEL",
    "qwen2.5-vl-7b-instruct"
)
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "minimax-m2.5")
TOKEN_THRESHOLD = int(os.environ.get("VISION_TOKEN_THRESHOLD", "1000"))


class VisionRouter:
    """Route vision tasks to local model"""
    
    def __init__(
        self,
        local_url: str = None,
        local_model: str = None,
        cloud_model: str = None
    ):
        self.local_url = local_url or LOCAL_VISION_URL
        self.local_model = local_model or LOCAL_VISION_MODEL
        self.cloud_model = cloud_model or CLOUD_MODEL
        self._client = None
    
    def _get_client(self) -> httpx.Client:
        """Get HTTP client"""
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(60.0),
                headers={"Content-Type": "application/json"}
            )
        return self._client
    
    def should_use_local(self, task_type: str, image_size: int = 0) -> bool:
        """Determine if task should use local model"""
        # Always use local for vision tasks
        if task_type in ["screenshot_analysis", "ui_element_detection", "coordinate_mapping"]:
            return True
        
        # Use local for large images (saves cloud tokens)
        if image_size > TOKEN_THRESHOLD:
            return True
        
        return False
    
    def analyze_screenshot(
        self,
        image_base64: str,
        prompt: str = "Analyze this screenshot and identify UI elements with their coordinates"
    ) -> Dict[str, Any]:
        """Analyze screenshot using local Qwen-VL model"""
        try:
            client = self._get_client()
            
            # Build vision request
            payload = {
                "model": self.local_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "max_tokens": 2048,
                "stream": False
            }
            
            response = client.post(self.local_url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Extract response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            return {
                "status": "success",
                "model": "local_qwen_vl",
                "content": content,
                "usage": result.get("usage", {}),
                "tokens_saved": self._estimate_cloud_tokens(content)
            }
            
        except httpx.ConnectError as e:
            return {
                "status": "error",
                "error": f"Local vision model not available at {self.local_url}",
                "fallback": "cloud"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "fallback": "cloud"
            }
    
    def detect_ui_elements(
        self,
        image_base64: str
    ) -> Dict[str, Any]:
        """Detect UI elements and their coordinates for click actions"""
        prompt = """
Analyze this screenshot and identify all clickable UI elements.
For each element, provide:
1. Element type (button, link, input, checkbox, etc.)
2. Element description/label
3. Bounding box coordinates [x1, y1, x2, y2]
4. Center click coordinates [x, y]

Format as JSON array:
[
  {
    "type": "button",
    "label": "Submit",
    "bbox": [100, 200, 200, 250],
    "click_point": [150, 225]
  }
]

Only return the JSON array, no other text.
"""
        
        result = self.analyze_screenshot(image_base64, prompt)
        
        if result["status"] == "success":
            try:
                # Try to parse JSON from response
                content = result["content"]
                # Extract JSON from markdown code blocks if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                elements = json.loads(content.strip())
                result["ui_elements"] = elements
            except json.JSONDecodeError:
                result["parse_error"] = "Could not parse UI elements as JSON"
        
        return result
    
    def sequence_click_actions(
        self,
        image_base64: str,
        goal: str
    ) -> Dict[str, Any]:
        """Generate sequence of click actions to achieve a goal"""
        prompt = f"""
Given this screenshot and the goal: "{goal}"

Generate a sequence of mouse actions (click, move, type) to achieve the goal.
For each action, specify:
1. Action type (click, move, type, press_key)
2. Target coordinates [x, y] for click/move
3. Text for type actions
4. Key for press_key actions
5. Brief description of why this action is needed

Format as JSON:
{{
  "actions": [
    {{"type": "click", "x": 150, "y": 225, "description": "Click Submit button"}},
    {{"type": "type", "text": "hello", "description": "Enter text in input"}}
  ],
  "estimated_steps": 2
}}

Only return the JSON, no other text.
"""
        
        result = self.analyze_screenshot(image_base64, prompt)
        
        if result["status"] == "success":
            try:
                content = result["content"]
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                action_plan = json.loads(content.strip())
                result["action_plan"] = action_plan
            except json.JSONDecodeError:
                result["parse_error"] = "Could not parse action plan as JSON"
        
        return result
    
    def _estimate_cloud_tokens(self, content: str) -> int:
        """Estimate cloud tokens saved by using local model"""
        # Rough estimate: 4 characters ≈ 1 token
        return len(content) // 4


# Global router instance
vision_router = VisionRouter()


# CoPaw integration functions
async def copaw_vision_interceptor(tool_name: str, arguments: dict, result: dict) -> dict:
    """
    CoPaw hook: Intercept screenshot tool results and route to local vision model
    
    Add to CoPaw config:
    {
      "hooks": {
        "post_tool_call": ["copaw_vision_interceptor"]
      }
    }
    """
    if tool_name != "take_screenshot":
        return result  # Only process screenshots
    
    try:
        result_data = json.loads(result) if isinstance(result, str) else result
        
        # Check if full image is available
        image_base64 = result_data.get("image_full_base64")
        if not image_base64:
            return result
        
        # Automatically analyze with local model
        analysis = vision_router.analyze_screenshot(image_base64)
        
        # Add analysis to result
        result_data["vision_analysis"] = {
            "model": "local_qwen_vl",
            "content": analysis.get("content", ""),
            "tokens_saved": analysis.get("tokens_saved", 0)
        }
        
        return json.dumps(result_data, indent=2)
        
    except Exception as e:
        # Don't block - return original result on error
        return result


async def copaw_click_planner(goal: str, screenshot_result: dict) -> dict:
    """
    CoPaw helper: Plan click sequence from screenshot to achieve goal
    """
    try:
        result_data = screenshot_result if isinstance(screenshot_result, dict) else json.loads(screenshot_result)
        image_base64 = result_data.get("image_full_base64")
        
        if not image_base64:
            return {"error": "No screenshot image available"}
        
        # Generate action plan
        plan = vision_router.sequence_click_actions(image_base64, goal)
        
        return plan
        
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Vision Model Router")
    parser.add_argument("--test", action="store_true", help="Test local vision model connection")
    parser.add_argument("--url", type=str, default=LOCAL_VISION_URL, help="Local vision model URL")
    parser.add_argument("--model", type=str, default=LOCAL_VISION_MODEL, help="Local vision model name")
    
    args = parser.parse_args()
    
    if args.test:
        print(f"Testing connection to {args.url}")
        print(f"Model: {args.model}")
        
        router = VisionRouter(local_url=args.url, local_model=args.model)
        
        # Test with a small base64 image (1x1 pixel)
        test_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
        result = router.analyze_screenshot(
            test_image,
            "What do you see in this image? Respond in one word."
        )
        
        print(f"\nResult: {json.dumps(result, indent=2)}")
        
        if result["status"] == "success":
            print("\n✅ Local vision model is working!")
            print(f"   Tokens saved: {result.get('tokens_saved', 0)}")
        else:
            print(f"\n❌ Local vision model error: {result.get('error', 'Unknown')}")
            print("   Make sure Qwen-VL is running at the specified URL")
