import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys

import httpx
import redis

# Add shared module to path for model_config import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/shared")
from shared.model_config import compressor_model

logger = logging.getLogger(__name__)


class CompressorTool:
    def __init__(self):
        # Default to llm_gateway service in docker-compose
        self.llm_gateway_url = os.getenv(
            "LLM_GATEWAY_URL", "http://llm_gateway:8000/v1/chat/completions"
        )
        self.model = (
            compressor_model()
        )  # Read from model_config (gemini-2.5-flash via compressor role)

        # Redis cache for compressed results (optional optimization)
        self.redis_host = os.getenv("REDIS_HOST", "redis")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self._redis_client = None
        self.cache_ttl = 3600  # 1 hour TTL for cached compressions

    def _get_redis(self):
        """Lazy Redis connection for caching"""
        if self._redis_client is None:
            try:
                self._redis_client = redis.Redis(
                    host=self.redis_host, port=self.redis_port, decode_responses=True
                )
                self._redis_client.ping()
            except Exception as e:
                logger.warning(f"Redis cache unavailable: {e}")
                self._redis_client = None
        return self._redis_client

    def _cache_key(self, text: str, focus: str) -> str:
        """Generate cache key for compression result"""
        content_hash = hashlib.sha256(f"{text}:{focus}".encode()).hexdigest()[:16]
        return f"cache:compress:{content_hash}"

    def _get_cached(self, key: str) -> str | None:
        """Try to get cached compression result"""
        try:
            client = self._get_redis()
            if client:
                return client.get(key)
        except Exception:
            pass
        return None

    def _set_cached(self, key: str, value: str):
        """Cache compression result with TTL"""
        try:
            client = self._get_redis()
            if client:
                client.setex(key, self.cache_ttl, value)
        except Exception as e:
            logger.debug(f"Cache write failed: {e}")

    async def _make_request(self, payload: dict, timeout: float = 60.0) -> dict:
        """Helper to make requests with retry logic for rate limits"""
        retries = 3
        base_delay = 2

        headers = {
            "Content-Type": "application/json",
            "X-Genesis-Chain": "enabled",
            "X-Genesis-Agent": "mcp_compressor",
        }

        async with httpx.AsyncClient() as client:
            for attempt in range(retries):
                try:
                    response = await client.post(
                        self.llm_gateway_url,
                        json=payload,
                        headers=headers,
                        timeout=timeout,
                    )

                    if response.status_code == 429:
                        if attempt < retries - 1:
                            wait_time = base_delay * (2**attempt)
                            logger.warning(
                                f"Rate limit hit (429). Retrying in {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)
                            continue

                    response.raise_for_status()
                    return response.json()

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < retries - 1:
                        wait_time = base_delay * (2**attempt)
                        logger.warning(
                            f"Rate limit hit (429). Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    raise e
                except Exception as e:
                    if attempt == retries - 1:
                        raise e
                    logger.warning(f"Request failed: {e}. Retrying...")
                    await asyncio.sleep(1)

            raise Exception("Max retries exceeded")

    async def compress_text(self, raw_text: str, focus_point: str) -> str:
        """
        Compress massive logs without token overflow.
        Uses Redis cache to avoid redundant API calls.

        Note: Quota tracking is centralized in llm_gateway service.
        All calls to self.model are tracked at the gateway level.
        """
        # Check cache first
        cache_key = self._cache_key(raw_text, focus_point)
        cached = self._get_cached(cache_key)
        if cached:
            logger.info(f"Cache hit for compression: {cache_key}")
            return cached

        system_prompt = f"""Compress this data. Retain all UUIDs, Error Codes, and High-Level Concepts. Discard boilerplate. Focus on: {focus_point}."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
        }

        try:
            result = await self._make_request(payload, timeout=60.0)
            compressed = result["choices"][0]["message"]["content"]

            # Cache the result
            self._set_cached(cache_key, compressed)

            return compressed
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return f"Error: {str(e)}"

    async def compress_file(self, file_path: str, focus_point: str) -> str:
        """
        Compress a file specified by path.
        Reads file content and passes to compress_text.
        Useful to avoid passing massive strings via CLI args.
        """
        logger.info(f"DEBUG: compress_file invoked for {file_path}")
        try:
            if not os.path.exists(file_path):
                logger.error(f"DEBUG: File not found: {file_path}")
                return f"Error: File not found at {file_path}"

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            logger.info(f"DEBUG: Read {len(content)} bytes. Calling compress_text...")
            result = await self.compress_text(content, focus_point)
            logger.info(f"DEBUG: compress_text returned: {result[:50]}...")
            return result
        except Exception as e:
            logger.error(f"File compression failed: {e}")
            return f"Error processing file {file_path}: {str(e)}"

    async def compress_codebase(
        self, focus_area: str, repo_path: str = "/app/project_root"
    ) -> str:
        """
        Smart repository compression using Tree-Based Retrieval.
        1. Maps the repo (Level 1).
        2. Identifies relevant modules for the focus area (Level 2).
        3. Extracts and synthesizes specific files (Level 3 & 4).
        """
        try:
            # Level 1: Map the repo
            tree_cmd = [
                "tree",
                "-L",
                "2",
                "--noreport",
                "-I",
                "__pycache__|.git|.venv|node_modules",
                repo_path,
            ]
            # Fallback if tree is not installed
            try:
                tree_output = subprocess.check_output(tree_cmd, text=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Simple python fallback for tree
                tree_output = ""
                for root, dirs, files in os.walk(repo_path):
                    level = root.replace(repo_path, "").count(os.sep)
                    if level < 2:
                        indent = " " * 4 * (level)
                        tree_output += "{}{}/\n".format(indent, os.path.basename(root))
                        subindent = " " * 4 * (level + 1)
                        for f in files:
                            tree_output += "{}{}\n".format(subindent, f)

            # Level 2: Identify relevant modules
            selection_prompt = f"""
            Given this file tree, identify the specific file paths (relative to root) that are most relevant to: "{focus_area}".
            Return ONLY a JSON list of file paths. Example: ["src/auth/login.py", "config/settings.json"]
            Tree:
            {tree_output}
            """

            # Get file selection
            sel_payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": selection_prompt}],
                "response_format": {"type": "json_object"},
            }
            sel_response_json = await self._make_request(sel_payload, timeout=30.0)
            paths = json.loads(
                sel_response_json["choices"][0]["message"]["content"]
            ).get("paths", [])

            # Handle if the model returns a list directly or wrapped
            if isinstance(paths, str):  # Sometimes models return string representation
                paths = json.loads(paths)

            # Level 3: Extract content
            combined_content = ""
            for path in paths:
                full_path = os.path.join(repo_path, path)
                if os.path.exists(full_path) and os.path.isfile(full_path):
                    try:
                        with open(full_path, "r") as f:
                            content = f.read()
                            combined_content += f"\n--- FILE: {path} ---\n{content}\n"
                    except Exception as read_err:
                        logger.warning(f"Could not read {path}: {read_err}")

            if not combined_content:
                return f"No relevant files found for focus area: {focus_area}"

            # Level 4: Synthesize
            return await self.compress_text(combined_content, focus_area)

        except Exception as e:
            logger.error(f"Codebase compression failed: {e}")
            return f"Error compressing codebase: {str(e)}"
