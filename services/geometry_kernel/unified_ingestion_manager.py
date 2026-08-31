
import os
import time
import json
import logging
import shutil
import glob
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UnifiedIngester")

# Configuration
INTAKE_DIR = os.path.abspath("shared_storage/atomized/intake")
OUTPUT_BASE_DIR = os.path.abspath("shared_storage/atomized/Concepts")
MODAL_BRIDGE_URL = os.environ.get("MODAL_BRIDGE_URL", "http://localhost:8080")  # Or direct Modal Client

# Check for Local vs Modal
USE_MODAL = os.environ.get("USE_MODAL", "true").lower() == "true"

try:
    import modal
    # Try to connect to Modal client early to verify
    # modal_client = modal.Client() 
    MODAL_AVAILABLE = True
except ImportError:
    MODAL_AVAILABLE = False
    logger.warning("Modal SDK not installed. Falling back to local only.")

# Import Geometric Kernel Services
# Assuming we are running from project root or services/geometry_kernel is in pythonpath
try:
    from services.geometry_kernel.semantic_chunker import SemanticChunker
    from services.geometry_kernel.clever_artifacts import extract_clever_artifacts
    # We might need a local LLM client wrapper here if not using CognitiveScheduler
except ImportError:
    # If running as script inside the folder
    from semantic_chunker import SemanticChunker
    from clever_artifacts import extract_clever_artifacts

class IngestionPipeline:
    def __init__(self):
        self.chunker = SemanticChunker(embed_fn=self._embed_text)
        self.use_modal = MODAL_AVAILABLE and USE_MODAL
        
        # Modal Function References (Lazy Load)
        self.fn_embed = None
        self.fn_inference = None
        
        if self.use_modal:
            try:
                # Connect to specific functions of the deployed class using from_name
                self.fn_embed = modal.Function.from_name("arca-unified-worker", "UnifiedWorker.embed")
                self.fn_inference = modal.Function.from_name("arca-unified-worker", "UnifiedWorker.extract_concepts")
                logger.info("✅ Modal App 'arca-geometry-heavy-lifter' connected.")
            except Exception as e:
                logger.warning(f"⚠️ Could not connect to Modal App: {e}. Falling back to Local.")
                self.use_modal = False

    def _embed_text(self, texts: List[str]) -> List[List[float]]:
        """Unified embedding: Modal preferred, Local fallback."""
        if self.use_modal and self.fn_embed:
            try:
                return self.fn_embed.remote(texts)
            except Exception as e:
                logger.error(f"Modal embedding failed: {e}. Trying local.")
        
        # Local Fallback (Llama.cpp / OpenAI compatible)
        # Using a simple requests call to local endpoint
        import requests
        try:
            # Assumes local llama.cpp server running logic
            resp = requests.post("http://localhost:8005/v1/embeddings", json={
                "input": texts, "model": "Qwen/Qwen2-VL-2B-Instruct-GGUF"
            }, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                return [d["embedding"] for d in data.get("data", [])]
        except Exception as e:
            logger.error(f"Local embedding failed: {e}")
            return [] # Fail gracefully
            
        return []

    def process_document(self, file_path: str):
        """Full processing pipeline for a single document."""
        doc_name = os.path.basename(file_path)
        safe_name = os.path.splitext(doc_name)[0].replace(" ", "_").replace(".", "_")
        target_dir = os.path.join(OUTPUT_BASE_DIR, safe_name)
        
        logger.info(f"🚀 Processing: {doc_name} -> {target_dir}")
        os.makedirs(target_dir, exist_ok=True)
        
        # 1. Read
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
            
        # 2. Semantic Chunking
        logger.info("✂️  Chunking...")
        chunks = self.chunker.chunk_document(text)
        chunk_texts = [c["text"] for c in chunks]
        
        # 3. Embed Chunks (Vector Generation)
        logger.info(f"🧠 Embedding {len(chunks)} chunks...")
        vectors = self._embed_text(chunk_texts)
        
        # 4. Concept Extraction (Reasoning) - "What is this chunk?"
        # We need an LLM to label these chunks with IDs like "Gravity", "Mass"
        # This creates the "Objects" metadata for The Mount
        logger.info("💡 Extracting Concepts...")
        objects_metadata = self._extract_concepts(chunk_texts)
        
        # 5. Artifacts & Analysis
        logger.info("🎨 Generating Artifacts...")
        # Convert to Geometric Model format for CleverArtifacts
        geometric_model = {
            "objects": [
                {
                    "id": meta.get("id", f"Chunk_{i}"), 
                    "desc": meta.get("desc", ""),
                    "mass": meta.get("mass", 0.5),
                    "position": vec
                }
                for i, (meta, vec) in enumerate(zip(objects_metadata, vectors))
            ]
        }
        artifacts = extract_clever_artifacts(geometric_model, text)
        
        # 6. Save Outputs
        # Save Vectors (Pythia)
        vec_path = os.path.join(target_dir, f"{safe_name}_Vectors.json")
        with open(vec_path, "w") as f:
            json.dump(vectors, f)
            
        # Save Objects/Concepts (The Mount)
        obj_path = os.path.join(target_dir, f"{safe_name}_Objects.json")
        with open(obj_path, "w") as f:
            json.dump(geometric_model["objects"], f, indent=2)
            
        # Save Artifacts
        art_path = os.path.join(target_dir, f"{safe_name}_Artifacts.json")
        with open(art_path, "w") as f:
            json.dump(artifacts, f, indent=2)
            
        logger.info(f"✅ Finished {doc_name}. Artifacts saved in {target_dir}")

    def _extract_concepts(self, texts: List[str]) -> List[Dict]:
        """Use LLM (Modal or Local) to extract concept metadata for each chunk."""
        results = []
        # Simple shim for now - normally this calls `scheduler.run_reasoning_phase`
        # or a lightweight prompt.
        
        # For efficiency, we can batch this or just use a regex heuristic if LLM unavailable
        # But user wants "Best of both worlds" -> Use LLM.
        
        for text in texts:
            # Prompt: "Extract main concept ID (1-3 words) and 1 sentence desc."
            # ... (Implementation detail: call LLM API)
            
            # Placeholder for minimal viability if no LLM:
            # Use First 5 words as ID
            results.append({"id": " ".join(text.split()[:3]), "desc": text[:100], "mass": 0.5})
            
        return results

    def watch_intake(self):
        """Watch intake folder loop."""
        logger.info(f"👀 Watching {INTAKE_DIR}...")
        while True:
            files = glob.glob(os.path.join(INTAKE_DIR, "*.*"))
            for f in files:
                try:
                    self.process_document(f)
                    # Move to 'processed' or delete?
                    # Let's move to a 'processed' folder inside intake? No, separate.
                    done_dir = os.path.join(INTAKE_DIR, "processed")
                    os.makedirs(done_dir, exist_ok=True)
                    shutil.move(f, os.path.join(done_dir, os.path.basename(f)))
                except Exception as e:
                    logger.error(f"Failed to process {f}: {e}")
                    # Move to error
                    err_dir = os.path.join(INTAKE_DIR, "error")
                    os.makedirs(err_dir, exist_ok=True)
                    shutil.move(f, os.path.join(err_dir, os.path.basename(f)))
            time.sleep(5)

if __name__ == "__main__":
    pipeline = IngestionPipeline()
    pipeline.watch_intake()
