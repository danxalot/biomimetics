"""
Research Augmentation Module
============================
Enhances document analysis by searching for related research based on extracted themes.

Pipeline:
1. Extract high-level themes from geometric model (3-5 key concepts)
2. Generate research-oriented search queries
3. Search via LangSearch web_search
4. Filter: Research/papers only, exclude raw mathematics
5. Create "Related Research" sidecar for ARCA discussion

This enables ARCA to say things like:
"This approach is similar to what the XYZ paper proposed, but adds the temporal dimension..."
"""

import json
import logging
import re
import httpx
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Configuration
MCP_SERVER_URL = "http://mcp_server:8086"
MAX_THEMES = 5
MAX_SEARCH_RESULTS = 5
RESEARCH_KEYWORDS = ["paper", "research", "study", "algorithm", "method", "approach", "framework", "architecture"]
MATH_FILTER_PATTERNS = [
    r'\$\$.*\$\$',  # LaTeX blocks
    r'\\frac\{',     # LaTeX fractions
    r'\\sum',        # Summations
    r'∫|∑|∏|∂',     # Math symbols
]


@dataclass
class ResearchResult:
    """A single research result."""
    title: str
    url: str
    summary: str
    relevance_score: float
    matched_theme: str


@dataclass
class ResearchSidecar:
    """Research context to accompany document analysis."""
    themes: List[str]
    research_results: List[ResearchResult]
    synthesis: str  # Brief synthesis of how research relates to document


class ResearchAugmentationEngine:
    """
    Augments document analysis with related research.
    
    Features:
    - Theme extraction from geometric models
    - Research-focused web search
    - Mathematics filtering (concept names, not formulas)
    - Synthesis generation for natural discussion
    """
    
    def __init__(self, mcp_url: str = MCP_SERVER_URL):
        self.mcp_url = mcp_url
    
    async def augment_with_research(self, geometric_model: Dict[str, Any], 
                                     document_title: str = "") -> ResearchSidecar:
        """
        Main entry point: augment a geometric model with related research.
        
        Args:
            geometric_model: The solar system from recursive ingestion
            document_title: Optional title for context
            
        Returns:
            ResearchSidecar with themes, results, and synthesis
        """
        # Step 1: Extract themes from geometric model
        themes = self._extract_themes(geometric_model)
        logger.info(f"Extracted {len(themes)} themes: {themes}")
        
        if not themes:
            return ResearchSidecar(
                themes=[],
                research_results=[],
                synthesis="No clear themes extracted for research augmentation."
            )
        
        # Step 2: Generate search queries
        queries = self._generate_research_queries(themes, document_title)
        
        # Step 3: Search for related research
        all_results = []
        for query, theme in queries:
            results = await self._search_research(query, theme)
            all_results.extend(results)
        
        # Step 4: Deduplicate and rank
        unique_results = self._deduplicate_results(all_results)
        
        # Step 5: Generate synthesis
        synthesis = self._generate_synthesis(themes, unique_results)
        
        return ResearchSidecar(
            themes=themes,
            research_results=unique_results[:MAX_SEARCH_RESULTS],
            synthesis=synthesis
        )
    
    def _extract_themes(self, geometric_model: Dict[str, Any]) -> List[str]:
        """
        Extract high-level themes from the geometric model.
        
        Looks at:
        - High-mass objects (important concepts)
        - Object clusters (related concepts)
        - The gravity well (central objective)
        """
        themes = []
        
        # 1. Get the central objective
        gravity_well = geometric_model.get("gravity_well", {})
        central_concept = gravity_well.get("concept", "")
        if central_concept:
            # Clean up for search
            central_concept = self._clean_theme(central_concept)
            if central_concept:
                themes.append(central_concept)
        
        # 2. Get high-mass objects
        objects = geometric_model.get("objects", [])
        
        # Sort by mass (importance)
        sorted_objects = sorted(
            objects, 
            key=lambda x: x.get("mass", 0), 
            reverse=True
        )
        
        # Extract top concepts
        for obj in sorted_objects[:10]:  # Check top 10
            obj_id = obj.get("id", "")
            if obj_id and len(themes) < MAX_THEMES:
                clean_id = self._clean_theme(obj_id)
                if clean_id and clean_id not in themes:
                    themes.append(clean_id)
        
        return themes[:MAX_THEMES]
    
    def _clean_theme(self, text: str) -> str:
        """Clean a theme for use in search queries."""
        # Remove special characters but keep spaces
        cleaned = re.sub(r'[^\w\s-]', '', text)
        # Remove numbers at start
        cleaned = re.sub(r'^\d+\s*', '', cleaned)
        # Collapse whitespace
        cleaned = ' '.join(cleaned.split())
        # Skip if too short or too long
        if len(cleaned) < 3 or len(cleaned) > 50:
            return ""
        return cleaned.strip()
    
    def _generate_research_queries(self, themes: List[str], 
                                    document_title: str) -> List[Tuple[str, str]]:
        """
        Generate research-oriented search queries from themes.
        
        Returns list of (query, source_theme) tuples.
        """
        queries = []
        
        for theme in themes:
            # Research-focused query
            query = f"{theme} research paper algorithm"
            queries.append((query, theme))
            
            # Architecture/framework query
            if "architecture" not in theme.lower():
                alt_query = f"{theme} system architecture design"
                queries.append((alt_query, theme))
        
        # Context-aware query using document title
        if document_title:
            context_query = f"{document_title} related work methods"
            queries.append((context_query, document_title))
        
        return queries
    
    async def _search_research(self, query: str, theme: str) -> List[ResearchResult]:
        """Search for research using LangSearch via MCP."""
        try:
            # Call MCP server's langsearch tool
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.mcp_url}/tools/langsearch",
                    json={
                        "query": query,
                        "count": 5,
                        "freshness": "noLimit",
                        "summary": True
                    }
                )
                
                if response.status_code != 200:
                    logger.warning(f"LangSearch returned {response.status_code}")
                    return []
                
                data = response.json()
                
        except Exception as e:
            logger.warning(f"Research search failed: {e}")
            # Fallback: try direct LangSearch if MCP fails
            return await self._fallback_search(query, theme)
        
        # Parse results
        results = []
        raw_results = data.get("results", [])
        
        for i, item in enumerate(raw_results):
            title = item.get("title", "")
            url = item.get("url", "")
            summary = item.get("summary", "")
            
            # Filter out math-heavy results
            if self._is_math_heavy(summary):
                continue
            
            # Check if it's research-oriented
            is_research = any(kw in summary.lower() for kw in RESEARCH_KEYWORDS)
            
            results.append(ResearchResult(
                title=title,
                url=url,
                summary=self._clean_summary(summary),
                relevance_score=1.0 - (i * 0.1) if is_research else 0.5 - (i * 0.1),
                matched_theme=theme
            ))
        
        return results
    
    async def _fallback_search(self, query: str, theme: str) -> List[ResearchResult]:
        """Fallback search if MCP is unavailable."""
        # Return empty - we don't want to fail the whole pipeline
        logger.info(f"Fallback search for: {query}")
        return []
    
    def _is_math_heavy(self, text: str) -> bool:
        """Check if text is heavily mathematical (should be filtered)."""
        for pattern in MATH_FILTER_PATTERNS:
            if re.search(pattern, text):
                return True
        return False
    
    def _clean_summary(self, summary: str) -> str:
        """Clean and truncate summary for readability."""
        # Remove LaTeX if any slipped through
        summary = re.sub(r'\$[^$]+\$', '[formula]', summary)
        # Truncate
        if len(summary) > 300:
            summary = summary[:297] + "..."
        return summary
    
    def _deduplicate_results(self, results: List[ResearchResult]) -> List[ResearchResult]:
        """Remove duplicate results, keeping highest relevance."""
        seen_urls = {}
        for result in results:
            if result.url not in seen_urls:
                seen_urls[result.url] = result
            elif result.relevance_score > seen_urls[result.url].relevance_score:
                seen_urls[result.url] = result
        
        # Sort by relevance
        return sorted(seen_urls.values(), key=lambda x: x.relevance_score, reverse=True)
    
    def _generate_synthesis(self, themes: List[str], 
                            results: List[ResearchResult]) -> str:
        """Generate a brief synthesis for ARCA to use in discussion."""
        if not results:
            return f"Themes identified: {', '.join(themes)}. No directly related research found."
        
        # Group by theme
        by_theme = {}
        for r in results:
            if r.matched_theme not in by_theme:
                by_theme[r.matched_theme] = []
            by_theme[r.matched_theme].append(r.title)
        
        parts = [f"Document themes: {', '.join(themes)}."]
        
        for theme, titles in by_theme.items():
            if titles:
                parts.append(f"Related to '{theme}': {', '.join(titles[:2])}.")
        
        return " ".join(parts)
    
    def format_for_context(self, sidecar: ResearchSidecar) -> str:
        """
        Format the research sidecar for injection into ARCA's context.
        
        This is what gets added to the prompt to enable natural discussion.
        """
        if not sidecar.research_results:
            return ""
        
        lines = [
            "## Related Research (for contextual discussion):",
            f"Themes identified: {', '.join(sidecar.themes)}",
            ""
        ]
        
        for r in sidecar.research_results[:3]:  # Top 3 only
            lines.append(f"- **{r.title}**")
            lines.append(f"  {r.summary[:150]}...")
            lines.append("")
        
        lines.append("Use this research context naturally in discussion - don't list it explicitly.")
        
        return "\n".join(lines)


# Convenience function
async def augment_document_with_research(geometric_model: Dict, 
                                          document_title: str = "") -> Dict[str, Any]:
    """
    Convenience function to augment a geometric model with research.
    
    Returns a dict with:
    - themes: List of extracted themes
    - research: List of research results
    - synthesis: Brief synthesis
    - context_injection: Formatted string for prompt injection
    """
    engine = ResearchAugmentationEngine()
    sidecar = await engine.augment_with_research(geometric_model, document_title)
    
    return {
        "themes": sidecar.themes,
        "research": [
            {
                "title": r.title,
                "url": r.url,
                "summary": r.summary,
                "relevance": r.relevance_score,
                "theme": r.matched_theme
            }
            for r in sidecar.research_results
        ],
        "synthesis": sidecar.synthesis,
        "context_injection": engine.format_for_context(sidecar)
    }
