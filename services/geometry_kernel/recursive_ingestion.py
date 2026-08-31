"""
Recursive Ingestion Module (RLM Walker)
Implements the recursive document assimilation logic described in V2.1 Implementation Doc.
Enhanced with semantic chunking for natural topic boundaries.
"""

import os
import json
import re
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    import modal

    HAS_MODAL = True
except ImportError:
    HAS_MODAL = False

# Import scheduler from internal module (or will be passed in)
try:
    from .model_engine import CognitiveScheduler
    from .semantic_chunker import SemanticChunker, chunk_semantically
    from .clever_artifacts import extract_clever_artifacts
except ImportError:
    from model_engine import CognitiveScheduler

    try:
        from semantic_chunker import SemanticChunker, chunk_semantically
    except ImportError:
        SemanticChunker = None
        chunk_semantically = None

    try:
        from clever_artifacts import extract_clever_artifacts
    except ImportError:
        extract_clever_artifacts = None

logger = logging.getLogger(__name__)


class RecursiveIngestion:
    """
    Handles the "Recursive Loop" (RLM) to walk files and convert them into a 3D Solar System.

    Verbosity Modes:
    - "minimal": Just objects with id, mass, position (original magic moment)
    - "standard": Objects with short descriptions
    - "full": Complete output with all metadata
    """

    def __init__(self, scheduler: CognitiveScheduler):
        self.scheduler = scheduler
        # Create embedding function for SemanticChunker
        embedding_url = os.environ.get(
            "EMBEDDING_SERVICE_URL", "http://embedding_service:8005/embed"
        )

        def embed_fn(texts: List[str]) -> List[List[float]]:
            import requests

            try:
                response = requests.post(
                    embedding_url, json={"texts": texts}, timeout=30
                )
                if response.status_code == 200:
                    result = response.json()
                    return result.get("embeddings", [[0.0] * 2048 for _ in texts])
                else:
                    logger.warning(f"Embedding service returned {response.status_code}")
                    return [[0.0] * 2048 for _ in texts]
            except Exception as e:
                logger.warning(f"Failed to call embedding service: {e}")
                return [[0.0] * 2048 for _ in texts]

        self.semantic_chunker = (
            SemanticChunker(embed_fn=embed_fn) if SemanticChunker else None
        )
        self.use_heavy_lifter = (
            os.environ.get("USE_MODAL_HEAVY_LIFTER", "false").lower() == "true"
        )
        self.modal_app_name = os.environ.get(
            "MODAL_APP_NAME", "arca-geometry-heavy-lifter"
        )

    def ingest_content(
        self,
        file_path: str,
        objective: str,
        content_type: str = "AUTO",
        verbosity: str = "minimal",
        use_semantic_chunking: bool = True,
    ) -> Dict[str, Any]:
        """
        Uses Recursive Loop to walk file and convert to Solar System.

        Args:
            file_path: Path to file to ingest
            objective: Analysis objective
            content_type: "AUTO", "LOGS", or "NARRATIVE"
            verbosity: "minimal" | "standard" | "full"
            use_semantic_chunking: If True, use embedding-based topic boundaries
        """
        import time

        start_time = time.time()
        safe_name = os.path.basename(file_path).replace(".", "_")

        # 1. PROBE PHASE
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            full_text = f.read()
            head_sample = full_text[:2000]

        if content_type == "AUTO":
            if re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", head_sample):
                content_type = "LOGS"
            else:
                content_type = "NARRATIVE"

        # 2. DECOMPOSITION - Use semantic chunking if available
        chunks = []
        if (
            use_semantic_chunking
            and self.semantic_chunker
            and content_type == "NARRATIVE"
        ):
            logger.info("🧠 Using semantic chunking for topic boundaries")
            try:
                chunk_data = self.semantic_chunker.chunk_document(full_text)
                chunks = [c["text"] for c in chunk_data]
                logger.info(f"Created {len(chunks)} semantic chunks")
            except Exception as chunk_err:
                logger.warning(
                    f"Semantic chunking failed, falling back to paragraph split: {chunk_err}"
                )
                chunks = self._split_narrative(file_path)
        elif content_type == "LOGS":
            chunks = self._split_logs(file_path)
        else:
            chunks = self._split_narrative(file_path)

        # 3. RECURSIVE WALKING (The Loop)
        if self.use_heavy_lifter and HAS_MODAL:
            logger.info("🚀 Delegating to Modal HeavyGeometryIngester...")
            try:
                # Check if modal is available and we can access the function
                if modal is not None and hasattr(modal, "Function"):
                    f = modal.Function.lookup(  # type: ignore
                        self.modal_app_name, "HeavyGeometryIngester.process_file"
                    )
                    res = f.remote(
                        file_path=file_path, objective=objective, file_content=full_text
                    )

                    # The heavy lifter returns a dict with 'objects' and 'stats'
                    objects_list = res.get("objects", [])
                    vectors = [
                        obj.get("vector") for obj in objects_list
                    ]  # If available

                    solar_system = {
                        "system_id": file_path,
                        "gravity_well": {"concept": objective, "mass": len(chunks)},
                        "objects": objects_list,
                        "trajectory": [0, 0, 0],  # Placeholder for now
                    }

                    # Ensure artifacts are extracted
                    if extract_clever_artifacts:
                        solar_system["analysis_artifacts"] = extract_clever_artifacts(
                            solar_system, full_text
                        )

                    return solar_system
                else:
                    logger.warning(
                        "Modal not properly initialized, falling back to standard RLM"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Modal Heavy Lifter failed: {e}. Falling back to standard RLM."
                )

        running_state = {
            "trajectory_vector": [0, 0, 0],
            "objects": {},
            "current_context": "",
            "analysis_artifacts": {
                "theme_vectors": [],
                "dependencies": [],
                "contradictions": [],
                "novelty_scores": [],
                "implementation_density": 0.0,
                "context_injection": "",
            },
        }

        logger.info(
            f"🚀 Starting RLM Walk on {content_type} file: {file_path} (verbosity: {verbosity})"
        )

        # Build prompt based on verbosity - simplified to match expected output
        prompt_template = self._get_prompt_template(verbosity, objective)

        for i, chunk in enumerate(chunks):
            prompt = prompt_template.format(
                objective=objective,
                trajectory=json.dumps(running_state["trajectory_vector"]),
                context=running_state["current_context"][:500],
            )

            # Use Reasoning Phase (DeepSeek)
            tick_result = self.scheduler.run_reasoning_phase(
                context_text=chunk, prompt_template=prompt
            )
            self._update_state(running_state, tick_result, verbosity)

            # Extract artifacts after each chunk to match heavy lifter behavior
            if extract_clever_artifacts and len(running_state["objects"]) > 0:
                try:
                    # Pass current state for artifact extraction
                    model_for_artifacts = {
                        "objects": list(running_state["objects"].values()),
                        "trajectory_vector": running_state["trajectory_vector"],
                    }
                    artifacts = extract_clever_artifacts(model_for_artifacts)
                    running_state["analysis_artifacts"] = artifacts
                except Exception as e:
                    logger.warning(f"Failed to extract artifacts after chunk {i}: {e}")

        # 4. FINAL AGGREGATION
        objects_list = list(running_state["objects"].values())

        # Apply verbosity filter to output
        if verbosity == "minimal":
            # Strip to bare essentials - just geometric data
            objects_list = [
                {
                    "id": obj.get("id"),
                    "mass": float(obj.get("mass", 0.5)),
                    "position": obj.get("position", [0, 0, 0]),
                }
                for obj in objects_list
                if isinstance(obj, dict)
            ]
        elif verbosity == "standard":
            # Include short descriptions
            objects_list = [
                {
                    "id": obj.get("id", ""),
                    "desc": str(obj.get("desc", ""))[:100] if obj.get("desc") else "",
                    "mass": float(obj.get("mass", 0.5)),
                    "position": obj.get("position", [0, 0, 0]),
                }
                for obj in objects_list
                if isinstance(obj, dict)
            ]
        # "full" keeps everything as-is but ensures proper types

        solar_system = {
            "system_id": file_path,
            "gravity_well": {"concept": objective, "mass": len(chunks)},
            "objects": objects_list,
            "trajectory": running_state["trajectory_vector"],
        }

        # Add analysis artifacts if available
        if running_state["analysis_artifacts"] and any(
            v
            for k, v in running_state["analysis_artifacts"].items()
            if k != "context_injection" and v
        ):
            solar_system["analysis_artifacts"] = running_state["analysis_artifacts"]

        return solar_system

    def _get_prompt_template(self, verbosity: str, objective: str) -> str:
        """Get the prompt template based on verbosity level."""

        if verbosity == "minimal":
            # Bare bones - just extract concepts and positions (matches heavy lifter)
            return (
                "Objective: {objective}\n"
                "Current trajectory: {trajectory}\n\n"
                "Extract key concepts as geometric objects. Output ONLY valid JSON:\n"
                "{{\n"
                '    "vector": [float, float, float],\n'
                '    "objects": [\n'
                '        {{"id": "concept_name", "mass": 0.0-1.0, "position": [x, y, z]}}\n'
                "    ]\n"
                "}}\n"
                "No descriptions. No explanations. JSON only."
            )

        elif verbosity == "standard":
            # Include brief descriptions but keep vector requirement
            return (
                "Objective: {objective}\n"
                "Trajectory: {trajectory}\n"
                "Context: {context}\n\n"
                "Extract concepts with brief descriptions. Output valid JSON:\n"
                "{{\n"
                '    "vector": [float, float, float],\n'
                '    "summary": "One sentence summary",\n'
                '    "objects": [\n'
                '        {{"id": "Concept", "desc": "Brief description (max 15 words)", "mass": 0.5, "position": [x,y,z]}}\n'
                "    ]\n"
                "}}\n"
                "JSON only. No extra text."
            )

        else:  # "full"
            return (
                "Objective: {objective}\n"
                "Current System State: {trajectory}\n"
                "Previous Context: {context}\n\n"
                "Task: detailed analysis to update the geometric state.\n"
                "1. Analyze the text chunk for key concepts (objects).\n"
                "2. Update the trajectory vector based on narrative movement.\n"
                "3. Summarize the context.\n\n"
                "CRITICAL: Output MUST be valid JSON with this exact schema:\n"
                "{\n"
                '    "vector": [float, float, float],\n'
                '    "summary": "concise summary of this chunk",\n'
                '    "objects": [\n'
                "        {\n"
                '            "id": "Concept Name",\n'
                '            "desc": "Qualitative description of the concept",\n'
                '            "mass": 0.0-1.0,\n'
                '            "position": [x, y, z]\n'
                "        }\n"
                "    ]\n"
                "}\n"
                "Output JSON only. No markdown, no explanations."
            )

    def _split_logs(self, file_path):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return ["".join(lines[i : i + 100]) for i in range(0, len(lines), 100)]

    def _split_narrative(self, file_path):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return text.split("\n\n")

    def _update_state(self, state, new_data, verbosity: str = "full"):
        try:
            # 1. Clean and extract JSON
            text = new_data.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif text.startswith("```") and text.endswith("```"):
                text = text[3:-3].strip()
            text = text.strip()

            # 2. Parse JSON
            data = {}
            if text.startswith("{") and text.endswith("}"):
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"JSON decode failed: {e}. Trying to extract object..."
                    )
                    # Try to find JSON object in text
                    json_match = re.search(
                        r'\{[^{]*"vector"\s*:\s*\[[^\]]*\][^{]*"objects"\s*:\s*\[[^\]]*\][^}]*\}',
                        text,
                        re.DOTALL,
                    )
                    if json_match:
                        try:
                            data = json.loads(json_match.group(0))
                        except json.JSONDecodeError:
                            logger.warning("Failed to extract JSON object with regex")
                            return state
                    else:
                        logger.warning(f"No valid JSON object found in: {text[:200]}")
                        return state
            else:
                logger.warning(f"Output doesn't look like JSON object: {text[:100]}")
                return state

            # 3. Validate and normalize data structure
            if not isinstance(data, dict):
                logger.warning(f"Parsed data is not a dictionary: {type(data)}")
                return state

            # Ensure we have the required fields
            if (
                "vector" not in data
                or not isinstance(data["vector"], list)
                or len(data["vector"]) != 3
            ):
                logger.warning(
                    f"Missing or invalid 'vector' field: {data.get('vector')}"
                )
                # Try to recover if possible
                if "vector" in data and isinstance(data["vector"], list):
                    # Pad or truncate to 3 elements
                    vec = data["vector"]
                    while len(vec) < 3:
                        vec.append(0.0)
                    data["vector"] = vec[:3]
                else:
                    data["vector"] = [0.0, 0.0, 0.0]

            if "objects" not in data or not isinstance(data["objects"], list):
                logger.warning(
                    f"Missing or invalid 'objects' field: {data.get('objects')}"
                )
                data["objects"] = []

            # 4. Update trajectory with validation and scaling
            try:
                vector = [float(x) for x in data["vector"]]
                for i in range(3):
                    state["trajectory_vector"][i] += vector[i]

                # Apply magnitude scaling to prevent runaway values
                import math

                mag = math.sqrt(sum(v * v for v in state["trajectory_vector"]))
                if mag > 100:  # Same threshold as before
                    scale = 100.0 / mag
                    state["trajectory_vector"] = [
                        v * scale for v in state["trajectory_vector"]
                    ]
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Invalid vector values: {data.get('vector')}, error: {e}"
                )
                # Keep existing trajectory if update fails

            # 5. Update context
            if "summary" in data and isinstance(data["summary"], str):
                state["current_context"] = data["summary"][:500]  # Limit context length

            # 6. Update objects with normalization
            objs = data.get("objects", [])
            if isinstance(objs, list):
                logger.info(f"Ingested {len(objs)} objects from chunk")
                for obj in objs:
                    if isinstance(obj, dict):
                        # Normalize object fields
                        obj_id = (
                            obj.get("id")
                            or obj.get("name")
                            or f"concept_{len(state['objects'])}"
                        )
                        # Ensure mass is float between 0 and 1
                        try:
                            mass = float(obj.get("mass", 0.5))
                            mass = max(0.0, min(1.0, mass))  # Clamp to 0-1
                        except (ValueError, TypeError):
                            mass = 0.5

                        # Ensure position is list of 3 floats
                        try:
                            pos = obj.get("position", [0.0, 0.0, 0.0])
                            if not isinstance(pos, list):
                                pos = [0.0, 0.0, 0.0]
                            # Pad or truncate to 3 elements
                            while len(pos) < 3:
                                pos.append(0.0)
                            pos = [float(p) for p in pos[:3]]
                        except (ValueError, TypeError):
                            pos = [0.0, 0.0, 0.0]

                        # Build normalized object
                        normalized_obj = {
                            "id": str(obj_id),
                            "mass": mass,
                            "position": pos,
                        }

                        # Preserve description if present and verbosity allows it
                        if (
                            verbosity != "minimal"
                            and "desc" in obj
                            and isinstance(obj["desc"], str)
                        ):
                            normalized_obj["desc"] = obj["desc"][
                                :200
                            ]  # Limit description length

                        state["objects"][obj_id] = normalized_obj
            else:
                logger.warning(f"Objects field is not a list: {type(objs)}")

            return state

        except Exception as e:
            logger.error(f"Error parsing LLM output: {e}", exc_info=True)
            return (
                state  # Return unchanged state rather than None to continue processing
            )
