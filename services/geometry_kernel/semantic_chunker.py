"""
Semantic Chunking Module
========================
Implements intelligent document chunking based on semantic boundaries.

Instead of fixed-size or delimiter-based chunking, this module:
1. Embeds sentences/paragraphs locally
2. Detects topic boundaries via embedding similarity drop
3. Preserves structural elements (headings, code blocks)
4. Produces chunks aligned with natural topic transitions
"""

import re
import logging
from typing import List, Dict, Callable, Tuple, Optional, Any
import numpy as np

logger = logging.getLogger(__name__)

# Configuration
SIMILARITY_THRESHOLD = 0.6  # Below this = topic boundary
MIN_CHUNK_SIZE = 200  # Characters - don't create tiny chunks
MAX_CHUNK_SIZE = 3000  # Characters - split if too large


class ChunkingFailure(Exception):
    """Raised when semantic chunking fails and fallback is not allowed."""

    pass


class SemanticChunker:
    """
    Intelligent document chunking using semantic similarity.

    Features:
    - Embedding-based topic boundary detection
    - Heading-aware chunking (respects H1/H2/H3)
    - Code block preservation (never split mid-block)
    - Fallback to paragraph-based chunking if embedding fails
    """

    def __init__(self, embed_fn: Callable[[List[str]], List[List[float]]]):
        if embed_fn is None:
            raise TypeError("SemanticChunker requires an embed_fn callable.")
        self._embedding_cache: Dict[str, List[float]] = {}
        self.embed_fn = embed_fn

    def chunk_document(
        self, text: str, preserve_structure: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Split document into semantically coherent chunks.

        Args:
            text: Full document text
            preserve_structure: If True, respect headings and code blocks

        Returns:
            List of chunks with metadata:
            [
                {
                    "text": "chunk content",
                    "chunk_index": 0,
                    "start_char": 0,
                    "end_char": 500,
                    "chunk_type": "narrative" | "code" | "heading",
                    "heading_context": "Current section heading if any"
                }
            ]
        """
        if not text or not text.strip():
            return []

        # Step 1: Extract and protect special elements
        protected_elements = []
        working_text = text

        if preserve_structure:
            # Extract code blocks (preserve intact)
            working_text, code_blocks = self._extract_code_blocks(text)
            protected_elements.extend(code_blocks)

        # Step 2: Split into sentences/paragraphs for analysis
        units = self._split_into_units(working_text)

        if len(units) < 3:
            # Too few units for semantic analysis, return as single chunk
            return [self._create_chunk(text, 0, 0, len(text), "narrative")]

        # Step 3: Get embeddings for each unit
        embeddings = self._get_embeddings([u["text"] for u in units])

        if embeddings is None:
            # STOP: Fallback is denied by user policy to ensure semantic quality
            msg = "Semantic chunking failed: Embedding service returned no data. Stopping ingestion to prevent low-quality paragraph fallback."
            logger.error(msg)
            raise ChunkingFailure(msg)

        # Step 4: Detect topic boundaries via similarity
        boundaries = self._detect_boundaries(embeddings, units)

        # Step 5: Create chunks from boundaries
        chunks = self._create_chunks_from_boundaries(
            units, boundaries, protected_elements
        )

        return chunks

    def _extract_code_blocks(self, text: str) -> Tuple[str, List[Dict]]:
        """Extract code blocks and replace with placeholders."""
        code_blocks = []
        placeholder_text = text

        # Match fenced code blocks
        pattern = r"```[\w]*\n[\s\S]*?```"
        matches = list(re.finditer(pattern, text))

        for i, match in enumerate(reversed(matches)):  # Reverse to maintain positions
            placeholder = f"__CODE_BLOCK_{len(matches) - i - 1}__"
            code_blocks.insert(
                0,
                {
                    "placeholder": placeholder,
                    "content": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                },
            )
            placeholder_text = (
                placeholder_text[: match.start()]
                + placeholder
                + placeholder_text[match.end() :]
            )

        return placeholder_text, code_blocks

    def _split_into_units(self, text: str) -> List[Dict]:
        """Split text into analyzable units (sentences/paragraphs)."""
        units = []

        # First split by paragraphs (double newline)
        paragraphs = re.split(r"\n\s*\n", text)

        char_offset = 0
        for para in paragraphs:
            para = para.strip()
            if not para:
                char_offset += 2  # For the \n\n
                continue

            # Check if it's a heading
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", para)
            if heading_match:
                unit_type = "heading"
                heading_level = len(heading_match.group(1))
            else:
                unit_type = "paragraph"
                heading_level = 0

            units.append(
                {
                    "text": para,
                    "type": unit_type,
                    "heading_level": heading_level,
                    "start_char": char_offset,
                    "end_char": char_offset + len(para),
                }
            )

            char_offset += len(para) + 2  # +2 for paragraph breaks

        return units

    def _get_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """Get embeddings for a list of texts from embedding service."""
        if not texts:
            return None

        try:
            # Check cache first
            uncached = [
                (i, t) for i, t in enumerate(texts) if t not in self._embedding_cache
            ]

            if uncached:
                # Batch embed uncached texts
                indices, to_embed = zip(*uncached) if uncached else ([], [])

                # Use the provided embed_fn callable (e.g. vLLM llm.embed wrapper)
                embeddings_list = self.embed_fn(list(to_embed))

                # Cache results
                if embeddings_list:
                    for idx, emb in zip(indices, embeddings_list):
                        self._embedding_cache[texts[idx]] = emb

            # Build result array from cache
            # Default to 2048 dims for Qwen3-VL Embedding
            embeddings = [self._embedding_cache.get(t, [0.0] * 2048) for t in texts]
            return np.array(embeddings)

        except Exception as e:
            logger.warning(f"Failed to get embeddings: {e}")
            return None

    def _detect_boundaries(
        self, embeddings: np.ndarray, units: List[Dict]
    ) -> List[int]:
        """
        Detect topic boundaries by finding drops in similarity between consecutive units.

        Returns list of indices where new topics start.
        """
        boundaries = [0]  # First unit always starts a chunk

        for i in range(1, len(embeddings)):
            # Cosine similarity between consecutive embeddings
            similarity = self._cosine_similarity(embeddings[i - 1], embeddings[i])

            # Check for topic boundary
            is_boundary = False

            # Low similarity indicates topic change
            if similarity < SIMILARITY_THRESHOLD:
                is_boundary = True

            # Headings always start new chunks
            if units[i]["type"] == "heading":
                is_boundary = True

            # High-level headings (H1, H2) definitely start new sections
            if units[i].get("heading_level", 0) <= 2:
                is_boundary = True

            if is_boundary:
                boundaries.append(i)

        return boundaries

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    def _create_chunks_from_boundaries(
        self, units: List[Dict], boundaries: List[int], protected_elements: List[Dict]
    ) -> List[Dict]:
        """Create final chunks from detected boundaries."""
        chunks = []
        current_heading = ""

        for i, boundary_start in enumerate(boundaries):
            # Determine chunk end
            if i + 1 < len(boundaries):
                boundary_end = boundaries[i + 1]
            else:
                boundary_end = len(units)

            # Collect units in this chunk
            chunk_units = units[boundary_start:boundary_end]

            if not chunk_units:
                continue

            # Build chunk text
            chunk_text = "\n\n".join(u["text"] for u in chunk_units)

            # Update heading context
            for u in chunk_units:
                if u["type"] == "heading":
                    current_heading = u["text"].lstrip("#").strip()

            # Determine chunk type
            if chunk_units[0]["type"] == "heading":
                chunk_type = "heading"
            else:
                chunk_type = "narrative"

            # Check if chunk is too large, split if needed
            if len(chunk_text) > MAX_CHUNK_SIZE:
                sub_chunks = self._split_large_chunk(
                    chunk_text, chunk_type, current_heading, len(chunks)
                )
                chunks.extend(sub_chunks)
            elif len(chunk_text) >= MIN_CHUNK_SIZE:
                chunks.append(
                    self._create_chunk(
                        chunk_text,
                        len(chunks),
                        chunk_units[0]["start_char"],
                        chunk_units[-1]["end_char"],
                        chunk_type,
                        current_heading,
                    )
                )
            else:
                # Chunk too small - merge with previous if possible
                if chunks:
                    chunks[-1]["text"] += "\n\n" + chunk_text
                    chunks[-1]["end_char"] = chunk_units[-1]["end_char"]
                else:
                    chunks.append(
                        self._create_chunk(
                            chunk_text,
                            0,
                            chunk_units[0]["start_char"],
                            chunk_units[-1]["end_char"],
                            chunk_type,
                            current_heading,
                        )
                    )

        # Restore protected code blocks
        for chunk in chunks:
            for code_block in protected_elements:
                if code_block["placeholder"] in chunk["text"]:
                    chunk["text"] = chunk["text"].replace(
                        code_block["placeholder"], code_block["content"]
                    )
                    chunk["chunk_type"] = "mixed"  # Contains code

        return chunks

    def _split_large_chunk(
        self, text: str, chunk_type: str, heading: str, start_index: int
    ) -> List[Dict]:
        """Split a chunk that exceeds MAX_CHUNK_SIZE."""
        chunks = []

        # Split by sentences for narrative, or by lines for other content
        if chunk_type == "narrative":
            # Split by sentences
            sentences = re.split(r"(?<=[.!?])\s+", text)
            current = ""

            for sentence in sentences:
                if len(current) + len(sentence) > MAX_CHUNK_SIZE and current:
                    chunks.append(
                        self._create_chunk(
                            current.strip(),
                            start_index + len(chunks),
                            0,
                            0,
                            chunk_type,
                            heading,
                        )
                    )
                    current = sentence
                else:
                    current += " " + sentence if current else sentence

            if current.strip():
                chunks.append(
                    self._create_chunk(
                        current.strip(),
                        start_index + len(chunks),
                        0,
                        0,
                        chunk_type,
                        heading,
                    )
                )
        else:
            # Simple character-based split for non-narrative
            for i in range(0, len(text), MAX_CHUNK_SIZE):
                chunk_text = text[i : i + MAX_CHUNK_SIZE]
                chunks.append(
                    self._create_chunk(
                        chunk_text,
                        start_index + len(chunks),
                        i,
                        i + len(chunk_text),
                        chunk_type,
                        heading,
                    )
                )

        return chunks

    def _create_chunk(
        self,
        text: str,
        index: int,
        start: int,
        end: int,
        chunk_type: str,
        heading: str = "",
    ) -> Dict:
        """Create a chunk dictionary."""
        return {
            "text": text,
            "chunk_index": index,
            "start_char": start,
            "end_char": end,
            "chunk_type": chunk_type,
            "heading_context": heading,
            "char_count": len(text),
        }

    def _fallback_chunk(self, text: str) -> List[Dict]:
        """Fallback to simple paragraph-based chunking."""
        chunks = []
        paragraphs = text.split("\n\n")

        current_chunk = ""
        current_heading = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Check for heading
            if para.startswith("#"):
                current_heading = para.lstrip("#").strip()

            # Accumulate until MAX_CHUNK_SIZE
            if len(current_chunk) + len(para) > MAX_CHUNK_SIZE and current_chunk:
                chunks.append(
                    self._create_chunk(
                        current_chunk, len(chunks), 0, 0, "narrative", current_heading
                    )
                )
                current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        if current_chunk.strip():
            chunks.append(
                self._create_chunk(
                    current_chunk, len(chunks), 0, 0, "narrative", current_heading
                )
            )

        return chunks


# Convenience function
def chunk_semantically(text: str, preserve_structure: bool = True) -> List[Dict]:
    """Chunk a document using semantic boundaries."""
    chunker = SemanticChunker()
    return chunker.chunk_document(text, preserve_structure)
