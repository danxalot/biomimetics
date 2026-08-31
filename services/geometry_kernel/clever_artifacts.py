"""
Clever Artifacts Module
=======================
Provides enriched analytical artifacts from geometric models to enhance ARCA's discussion.

Artifacts:
1. Theme Vectors - High-level conceptual themes with direction
2. Dependency Graph - Which concepts reference/depend on which
3. Contradiction Markers - Points of internal friction or evolution
4. Novelty Scores - How unique a concept is vs. common knowledge
5. Implementation Density - Code-to-theory ratio per section
"""

import json
import logging
import re
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ThemeVector:
    """A high-level theme with directional emphasis."""
    name: str
    direction: List[float]  # 3D vector showing conceptual direction
    strength: float  # 0-1 importance
    related_objects: List[str]  # Object IDs that contribute to this theme


@dataclass
class DependencyEdge:
    """A dependency relationship between concepts."""
    source: str  # Concept that depends
    target: str  # Concept depended upon
    strength: float  # Dependency strength
    type: str  # "requires", "extends", "contradicts", "relates"


@dataclass
class ContradictionMarker:
    """Marks a point of conceptual tension or contradiction."""
    concept_a: str
    concept_b: str
    tension_type: str  # "semantic", "structural", "temporal"
    description: str


@dataclass
class ConceptNovelty:
    """Novelty score for a concept."""
    concept_id: str
    novelty_score: float  # 0 = common, 1 = highly novel
    familiarity_indicators: List[str]  # Why it's familiar
    novelty_indicators: List[str]  # Why it's novel


@dataclass 
class CleverArtifacts:
    """Collection of clever artifacts for rich discussion."""
    theme_vectors: List[ThemeVector]
    dependencies: List[DependencyEdge]
    contradictions: List[ContradictionMarker]
    novelty_scores: List[ConceptNovelty]
    implementation_density: float  # Overall code-to-theory ratio
    
    def to_dict(self) -> Dict:
        return {
            "theme_vectors": [asdict(t) for t in self.theme_vectors],
            "dependencies": [asdict(d) for d in self.dependencies],
            "contradictions": [asdict(c) for c in self.contradictions],
            "novelty_scores": [asdict(n) for n in self.novelty_scores],
            "implementation_density": self.implementation_density
        }


class CleverArtifactExtractor:
    """
    Extracts clever artifacts from geometric models.
    
    These artifacts enable richer, more insightful discussion by ARCA.
    """
    
    # Common computing/AI terms (for novelty detection)
    COMMON_TERMS = {
        "api", "database", "server", "client", "model", "data", "system",
        "function", "method", "class", "object", "interface", "module",
        "architecture", "design", "pattern", "framework", "library",
        "neural network", "machine learning", "deep learning", "ai",
        "algorithm", "optimization", "training", "inference"
    }
    
    def extract_all(self, geometric_model: Dict[str, Any], 
                    document_text: str = "") -> CleverArtifacts:
        """
        Extract all clever artifacts from a geometric model.
        
        Args:
            geometric_model: Solar system from recursive ingestion
            document_text: Optional original document for deeper analysis
        """
        objects = geometric_model.get("objects", [])
        
        # Extract each artifact type
        theme_vectors = self._extract_theme_vectors(objects, geometric_model)
        dependencies = self._extract_dependencies(objects)
        contradictions = self._detect_contradictions(objects)
        novelty_scores = self._score_novelty(objects)
        impl_density = self._calculate_implementation_density(document_text)
        
        return CleverArtifacts(
            theme_vectors=theme_vectors,
            dependencies=dependencies,
            contradictions=contradictions,
            novelty_scores=novelty_scores,
            implementation_density=impl_density
        )
    
    def _extract_theme_vectors(self, objects: List[Dict], 
                                model: Dict) -> List[ThemeVector]:
        """
        Extract high-level themes by clustering objects by position.
        
        Objects close together in 3D space share a theme.
        """
        themes = []
        
        if not objects:
            return themes
        
        # Group objects by quadrant (simplified clustering)
        quadrants = defaultdict(list)
        
        for obj in objects:
            pos = obj.get("position", [0, 0, 0])
            if not isinstance(pos, list) or len(pos) < 3:
                pos = [0, 0, 0]
            
            # Determine quadrant by sign of coordinates
            quadrant = (
                "+" if pos[0] >= 0 else "-",
                "+" if pos[1] >= 0 else "-", 
                "+" if pos[2] >= 0 else "-"
            )
            quadrants[quadrant].append(obj)
        
        # For each quadrant with multiple objects, create a theme
        quadrant_names = {
            ('+',' +', '+'): "Core Systems",
            ('+', '+', '-'): "Extensions",
            ('+', '-', '+'): "Infrastructure",
            ('+', '-', '-'): "Tooling",
            ('-', '+', '+'): "Concepts",
            ('-', '+', '-'): "Theory",
            ('-', '-', '+'): "Methodology",
            ('-', '-', '-'): "Foundations"
        }
        
        for quadrant, objs in quadrants.items():
            if len(objs) >= 2:  # Only if multiple objects cluster here
                # Calculate centroid
                positions = [obj.get("position", [0,0,0]) for obj in objs]
                centroid = np.mean(positions, axis=0).tolist()
                
                # Calculate total mass
                total_mass = sum(obj.get("mass", 0.5) for obj in objs)
                
                # Get object IDs
                obj_ids = [obj.get("id", "unknown") for obj in objs]
                
                # Create theme name from highest-mass object or quadrant default
                if objs:
                    top_obj = max(objs, key=lambda x: x.get("mass", 0))
                    theme_name = top_obj.get("id", quadrant_names.get(quadrant, "Cluster"))
                else:
                    theme_name = quadrant_names.get(quadrant, "Cluster")
                
                themes.append(ThemeVector(
                    name=theme_name,
                    direction=centroid,
                    strength=min(1.0, total_mass / 5.0),  # Normalize
                    related_objects=obj_ids[:5]  # Top 5
                ))
        
        # Sort by strength
        themes.sort(key=lambda x: x.strength, reverse=True)
        return themes[:5]  # Top 5 themes
    
    def _extract_dependencies(self, objects: List[Dict]) -> List[DependencyEdge]:
        """
        Infer dependencies between concepts based on position and mass.
        
        - Objects close together likely relate
        - Higher mass objects are depended upon
        """
        dependencies = []
        
        if len(objects) < 2:
            return dependencies
        
        # Check each pair
        for i, obj_a in enumerate(objects):
            pos_a = np.array(obj_a.get("position", [0,0,0]))
            mass_a = obj_a.get("mass", 0.5)
            id_a = obj_a.get("id", f"obj_{i}")
            
            for j, obj_b in enumerate(objects):
                if i >= j:
                    continue
                    
                pos_b = np.array(obj_b.get("position", [0,0,0]))
                mass_b = obj_b.get("mass", 0.5)
                id_b = obj_b.get("id", f"obj_{j}")
                
                # Calculate distance
                distance = float(np.linalg.norm(pos_a - pos_b))
                
                # Close objects are related
                if distance < 2.0:  # Threshold
                    # Higher mass is depended upon
                    if mass_a > mass_b * 1.5:
                        dependencies.append(DependencyEdge(
                            source=id_b,
                            target=id_a,
                            strength=1.0 - (distance / 2.0),
                            type="requires"
                        ))
                    elif mass_b > mass_a * 1.5:
                        dependencies.append(DependencyEdge(
                            source=id_a,
                            target=id_b,
                            strength=1.0 - (distance / 2.0),
                            type="requires"
                        ))
                    else:
                        # Similar mass = relates
                        dependencies.append(DependencyEdge(
                            source=id_a,
                            target=id_b,
                            strength=1.0 - (distance / 2.0),
                            type="relates"
                        ))
        
        # Sort by strength
        dependencies.sort(key=lambda x: x.strength, reverse=True)
        return dependencies[:10]  # Top 10
    
    def _detect_contradictions(self, objects: List[Dict]) -> List[ContradictionMarker]:
        """
        Detect potential contradictions or tensions between concepts.
        
        - Opposite positions but similar descriptions
        - High mass objects at opposite ends
        """
        contradictions = []
        
        if len(objects) < 2:
            return contradictions
        
        for i, obj_a in enumerate(objects):
            pos_a = np.array(obj_a.get("position", [0,0,0]))
            id_a = obj_a.get("id", f"obj_{i}")
            desc_a = obj_a.get("desc", "").lower()
            
            for j, obj_b in enumerate(objects):
                if i >= j:
                    continue
                    
                pos_b = np.array(obj_b.get("position", [0,0,0]))
                id_b = obj_b.get("id", f"obj_{j}")
                desc_b = obj_b.get("desc", "").lower()
                
                # Check for opposite positions
                dot_product = float(np.dot(pos_a, pos_b))
                
                if dot_product < -0.5:  # Opposite directions
                    # Check if they share keywords (potential tension)
                    words_a = set(desc_a.split())
                    words_b = set(desc_b.split())
                    overlap = words_a & words_b
                    
                    if len(overlap) >= 2:  # Shared vocabulary but opposite positions
                        contradictions.append(ContradictionMarker(
                            concept_a=id_a,
                            concept_b=id_b,
                            tension_type="structural",
                            description=f"'{id_a}' and '{id_b}' share vocabulary but occupy opposite conceptual positions"
                        ))
        
        return contradictions[:5]  # Top 5 contradictions
    
    def _score_novelty(self, objects: List[Dict]) -> List[ConceptNovelty]:
        """
        Score how novel each concept is.
        
        Common computing terms = low novelty
        Unique/specific terms = high novelty
        """
        novelty_scores = []
        
        for obj in objects:
            obj_id = obj.get("id", "unknown")
            desc = obj.get("desc", "")
            
            # Check against common terms
            id_lower = obj_id.lower()
            desc_lower = desc.lower()
            
            familiarity = []
            novelty = []
            
            for common in self.COMMON_TERMS:
                if common in id_lower or common in desc_lower:
                    familiarity.append(common)
            
            # Check for specific/novel indicators
            novel_patterns = [
                r"[A-Z]{2,}",  # Acronyms
                r"\d+[.]\d+",  # Version numbers
                r"hyper|meta|neo|quantum",  # Novel prefixes
            ]
            
            for pattern in novel_patterns:
                if re.search(pattern, obj_id) or re.search(pattern, desc):
                    novelty.append(f"Contains '{pattern}'")
            
            # Calculate score
            if len(familiarity) == 0 and len(novelty) > 0:
                score = 0.9
            elif len(familiarity) == 0:
                score = 0.7
            elif len(novelty) > len(familiarity):
                score = 0.6
            elif len(novelty) == len(familiarity):
                score = 0.5
            else:
                score = 0.3
            
            novelty_scores.append(ConceptNovelty(
                concept_id=obj_id,
                novelty_score=score,
                familiarity_indicators=familiarity[:3],
                novelty_indicators=novelty[:3]
            ))
        
        # Sort by novelty (most novel first)
        novelty_scores.sort(key=lambda x: x.novelty_score, reverse=True)
        return novelty_scores[:10]
    
    def _calculate_implementation_density(self, document_text: str) -> float:
        """
        Calculate the ratio of code to theory in the document.
        
        High density = practical/implementation focused
        Low density = theoretical/conceptual
        """
        if not document_text:
            return 0.5  # Unknown
        
        # Count code blocks
        code_pattern = r'```[\w]*\n[\s\S]*?```'
        code_blocks = re.findall(code_pattern, document_text)
        code_chars = sum(len(block) for block in code_blocks)
        
        # Total chars
        total_chars = len(document_text)
        
        if total_chars == 0:
            return 0.5
        
        # Ratio
        density = code_chars / total_chars
        return min(1.0, density * 2)  # Scale up since code is usually < 50%
    
    def format_for_context(self, artifacts: CleverArtifacts) -> str:
        """Format artifacts for injection into ARCA's context."""
        lines = ["## Document Analysis Artifacts:"]
        
        # Theme vectors
        if artifacts.theme_vectors:
            lines.append("\n### Key Themes:")
            for t in artifacts.theme_vectors[:3]:
                lines.append(f"- **{t.name}** (strength: {t.strength:.1f}): {', '.join(t.related_objects[:3])}")
        
        # Contradictions (interesting for discussion)
        if artifacts.contradictions:
            lines.append("\n### Points of Tension:")
            for c in artifacts.contradictions[:2]:
                lines.append(f"- {c.description}")
        
        # Novelty
        novel = [n for n in artifacts.novelty_scores if n.novelty_score > 0.6]
        if novel:
            lines.append("\n### Novel Concepts:")
            for n in novel[:3]:
                lines.append(f"- {n.concept_id} (novelty: {n.novelty_score:.1f})")
        
        # Implementation density
        if artifacts.implementation_density > 0.6:
            lines.append(f"\n*This document is implementation-heavy ({artifacts.implementation_density:.0%} code)*")
        elif artifacts.implementation_density < 0.3:
            lines.append(f"\n*This document is theory-heavy ({1-artifacts.implementation_density:.0%} conceptual)*")
        
        return "\n".join(lines)


# Convenience function
def extract_clever_artifacts(geometric_model: Dict, document_text: str = "") -> Dict:
    """Extract clever artifacts from a geometric model."""
    extractor = CleverArtifactExtractor()
    artifacts = extractor.extract_all(geometric_model, document_text)
    return {
        **artifacts.to_dict(),
        "context_injection": extractor.format_for_context(artifacts)
    }
