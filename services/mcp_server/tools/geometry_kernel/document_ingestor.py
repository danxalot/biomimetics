import os
import logging
from typing import Dict, Any, List
import torch
from pathlib import Path

# Adjust imports based on your actual structure
# Assuming geometry_kernel is available in python path or relatively imported
try:
    from geometry_kernel.context_memory import ManifoldContext, CelestialBody
    # Placeholder for recursive_context_walker if it exists, or we implement simple logic here
    # from some.path import recursive_context_walker 
except ImportError:
    # Fallback for dev/test without full environment
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
    from geometry_kernel.context_memory import ManifoldContext, CelestialBody

logger = logging.getLogger("arca.tools.document_ingestor")

class DocumentIngestor:
    """
    Ingests documents into the Geometry Kernel as 'Solar Systems'.
    Star = Document, Planet = Chapter/Section, Moon = Paragraph.
    """
    def __init__(self, manifold: ManifoldContext, embedding_service=None):
        self.manifold = manifold
        self.embedding_service = embedding_service # Interface to get vectors

    async def ingest_document(self, file_path: str) -> Dict[str, Any]:
        """
        Parses a document and creates the corresponding celestial bodies.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        doc_content = path.read_text(errors='ignore') # Simple text read for now
        doc_title = path.name

        # 1. Create the STAR (Document Root)
        # Position depends on the semantic embedding of the title/summary
        star_vector = await self._get_embedding(doc_title + ": " + doc_content[:500])
        star_id = f"DOC_{doc_title}"
        
        self.manifold.add_body(
            body_id=star_id,
            type="STAR",
            mass=100.0,
            position=star_vector,
            content_ref=str(path)
        )

        # 2. Parse and Create PLANETS (Sections)
        # Simple heuristic split by markdown headers for now
        sections = self._simple_markdown_split(doc_content)
        
        for i, section in enumerate(sections):
            header = section['header']
            content = section['content']
            
            planet_vector = await self._get_embedding(header + ": " + content[:200])
            planet_id = f"{star_id}_SEC_{i}"
            
            self.manifold.add_body(
                body_id=planet_id,
                type="PLANET",
                mass=50.0,
                position=planet_vector,
                content_ref=f"{path}#{header}",
                parent_id=star_id
            )
            
            # 3. Create MOONS (Paragraphs)
            paragraphs = [p for p in content.split('\n\n') if len(p.strip()) > 50]
            for j, para in enumerate(paragraphs):
                moon_vector = await self._get_embedding(para)
                moon_id = f"{planet_id}_PARA_{j}"
                
                self.manifold.add_body(
                    body_id=moon_id,
                    type="MOON",
                    mass=10.0,
                    position=moon_vector,
                    content_ref=f"{path}#{header}:para{j}",
                    parent_id=planet_id
                )

        return {"status": "success", "doc_id": star_id, "bodies_created": len(self.manifold.celestial_bodies)}

    async def _get_embedding(self, text: str) -> torch.Tensor:
        """
        Helper to get embedding vector.
        If actual service is missing, returns random for mocked testing.
        """
        if self.embedding_service:
            # Assuming embedding service returns list or tensor
            return await self.embedding_service.embed(text)
        else:
            # Mock
            return torch.randn(768) # Default dim

    def _simple_markdown_split(self, text: str) -> List[Dict[str, str]]:
        """
        Rudimentary markdown splitter. 
        """
        lines = text.split('\n')
        sections = []
        current_header = "Intro"
        current_content = []
        
        for line in lines:
            if line.startswith('#'):
                if current_content:
                    sections.append({"header": current_header, "content": "\n".join(current_content)})
                current_header = line.strip('# ').strip()
                current_content = []
            else:
                current_content.append(line)
        
        if current_content:
            sections.append({"header": current_header, "content": "\n".join(current_content)})
            
        return sections
