"""
LLM Interface — geometry_kernel
================================
Calls the local llama.cpp server (port 11435, macOS Vulkan/Metal) for
instruct work, and the OCI geometry_embedding server (port 8081) for
embedding work.

Prompts are deliberately short and constrained — the instruct model
(Qwen3VL-2B-Instruct-Q8 running on a Vulkan device) benefits from precise,
low-temperature instructions rather than long verbose prompts.
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# ── Connection defaults ───────────────────────────────────────────────────────
# Instruct: macOS llama-server (Qwen3VL-2B-Instruct-Q8, Vulkan 0, port 11435)
_INSTRUCT_BASE = os.getenv("LLM_GATEWAY_URL", "http://localhost:11435")
_INSTRUCT_MODEL = os.getenv("LLM_MODEL_NAME", "local")

# Embedding: OCI llama-server (Qwen3VL-Embedding-2B + mmproj, port 8081)
_EMBED_BASE = os.getenv("EMBEDDING_SERVICE_URL", "http://geometry_embedding:8081")


# ── Embedding prompts (Qwen3-VL-Embedding-2B, E5-instruct style) ─────────────
EMBED_INSTRUCT_PREFIX = (
    "Instruct: Represent this passage for geometric concept retrieval.\nText: "
)


# ── Concept-extraction JSON schema (kept minimal for CPU-class models) ────────
_CONCEPT_SCHEMA = """{
  "vector": [float, float, float],
  "objects": [
    {"id": "<concept_name>", "mass": 0.0-1.0, "position": [x, y, z], "desc": "<15 words max>"}
  ]
}"""

_CONCEPT_SYSTEM = (
    "You are a precise concept extractor. "
    "Return ONLY valid JSON matching the schema exactly. No prose. No markdown."
)

_CONCEPT_USER_TMPL = (
    "Extract the most important geometric or metaphysical concepts from the text below "
    "as JSON.  Schema:\n{schema}\n\nObjective: {objective}\n\nText:\n{chunk}"
)

# ── Vision prompt (for diagram / figure crops) ────────────────────────────────
_VISION_SYSTEM = (
    "You are a geometric structure analyser. Be concise and precise."
)

_VISION_USER = (
    "Describe the geometric or mathematical structure in this image in 2-3 sentences. "
    "Identify: objects, transformations, spatial relationships, or symbolic notation. "
    "Then output JSON: "
    '{"concept": "<name>", "mass": 0.5, "position": [0,0,0], "desc": "<30 words max>"}'
)


class LocalQwenVL:
    """
    Interface to the local Qwen3VL instruct + embedding servers.

    Instruct calls  → LLM_GATEWAY_URL (port 11435, macOS Vulkan/Metal)
    Embedding calls → EMBEDDING_SERVICE_URL (port 8081, OCI ARM64 llama.cpp)
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or _INSTRUCT_BASE).rstrip("/")
        self._session = requests.Session()

    # ── Instruct: text concept extraction ────────────────────────────────────

    def extract_concepts(
        self,
        chunk: str,
        objective: str = "Extract geometric concepts",
        max_tokens: int = 512,
    ) -> Dict[str, Any]:
        """
        Ask the instruct model to extract concept nodes from a text chunk.
        Returns parsed JSON dict (keys: vector, objects) or {} on failure.
        """
        prompt = _CONCEPT_USER_TMPL.format(
            schema=_CONCEPT_SCHEMA,
            objective=objective,
            chunk=chunk[:1200],   # keep well within context window
        )
        raw = self._chat(
            system=_CONCEPT_SYSTEM,
            user=prompt,
            max_tokens=max_tokens,
            temperature=0.05,
        )
        return _parse_json(raw, context="concept extraction")

    # ── Instruct: image/diagram description ──────────────────────────────────

    def describe_image(
        self,
        image_path: str,
        max_tokens: int = 256,
    ) -> Dict[str, Any]:
        """
        Send an image crop to the VL instruct model and extract a concept node.
        Returns parsed JSON dict or {} on failure.
        """
        try:
            img_b64 = _encode_image(image_path)
        except (FileNotFoundError, OSError) as e:
            logger.warning(f"Cannot read image {image_path}: {e}")
            return {}

        messages = [
            {"role": "system", "content": _VISION_SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                    {"type": "text", "text": _VISION_USER},
                ],
            },
        ]
        raw = self._complete(messages, max_tokens=max_tokens, temperature=0.1)
        return _parse_json(raw, context="image description")

    # ── Legacy compat — generate() used by audit_service etc. ────────────────

    def generate(self, prompt: str, image: Optional[str] = None) -> str:
        """
        Simple text generation.  Returns the model's raw reply string.
        """
        if image:
            result = self.describe_image(image)
            return json.dumps(result) if result else "ERROR: vision call failed"
        return self._chat(system=_CONCEPT_SYSTEM, user=prompt, max_tokens=256)

    # ── Embedding ─────────────────────────────────────────────────────────────

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts via geometry_embedding server (E5-instruct style).
        Returns list of float vectors.
        """
        # Prepend instruct prefix so Qwen3-VL-Embedding activates retrieval mode
        prefixed = [EMBED_INSTRUCT_PREFIX + t for t in texts]
        url = _EMBED_BASE.rstrip("/") + "/v1/embeddings"
        try:
            resp = self._session.post(
                url,
                json={"input": prefixed, "model": "embedding"},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data.get("data", [])]
        except Exception as e:
            logger.warning(f"Embedding request failed: {e}")
            return [[] for _ in texts]

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
        return self._complete(messages, max_tokens=max_tokens, temperature=temperature)

    def _complete(
        self,
        messages: List[Dict],
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> str:
        url = self.base_url + "/v1/chat/completions"
        payload = {
            "model":       _INSTRUCT_MODEL,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
        }
        try:
            resp = self._session.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.ConnectionError:
            logger.error(
                f"Cannot reach LLM at {self.base_url}.  "
                "Start scripts/start_vulkan_llama.sh on macOS."
            )
            return ""
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            return ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _encode_image(path: str) -> str:
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode("utf-8")


def _parse_json(raw: str, context: str = "") -> Dict[str, Any]:
    """Extract JSON from model output; returns {} on failure."""
    if not raw:
        return {}
    # Strip wrapping markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first {...} block
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    logger.debug(f"JSON parse failed ({context}): {raw[:200]}")
    return {}

