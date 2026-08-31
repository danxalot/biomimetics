"""
MCP Project Context Tool

Provides agents with access to project documentation and context.
Enables agents to read wiki docs, cite sources, and understand project structure.

Author: ARCA System
Date: March 12, 2026
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# MCP FastMCP
try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("mcp.server.fastmcp not available")

logger = logging.getLogger(__name__)

# Initialize FastMCP if available
if MCP_AVAILABLE:
    mcp = FastMCP("mcp-project-context")
else:
    mcp = None


# ============================================================================
# Configuration
# ============================================================================

# ARCA root directory
ARCA_ROOT = Path(__file__).parent.parent.parent.parent

# Wiki directory
WIKI_DIR = ARCA_ROOT / "shared_storage" / "wiki"

# Project planning documents
PLANNING_DIR = ARCA_ROOT / "project_planning_documents"

# System documentation
SYSTEM_AS_IS = PLANNING_DIR / "ARCA_SYSTEM_AS_IS.md"
SYSTEM_TO_BE = PLANNING_DIR / "ARCA_SYSTEM_TO_BE.md"


# ============================================================================
# Project Context Functions
# ============================================================================


def get_wiki_index() -> Dict[str, Any]:
    """
    Get wiki index with all available documentation.

    Returns:
        Dict with wiki structure and document list
    """
    index = {
        "timestamp": datetime.now().isoformat(),
        "wiki_root": str(WIKI_DIR),
        "sections": {},
        "total_documents": 0,
    }

    if not WIKI_DIR.exists():
        index["error"] = f"Wiki directory not found: {WIKI_DIR}"
        return index

    # Scan wiki sections
    for section_dir in sorted(WIKI_DIR.iterdir()):
        if not section_dir.is_dir():
            continue

        section_name = section_dir.name
        section_docs = []

        # Scan markdown files in section
        for md_file in sorted(section_dir.glob("*.md")):
            section_docs.append(
                {
                    "name": md_file.stem,
                    "path": str(md_file.relative_to(ARCA_ROOT)),
                    "size_kb": round(md_file.stat().st_size / 1024, 2),
                }
            )
            index["total_documents"] += 1

        index["sections"][section_name] = section_docs

    return index


def get_document_content(doc_path: str) -> Dict[str, Any]:
    """
    Get content of a specific document.

    Args:
        doc_path: Relative path to document (e.g., "shared_storage/wiki/01_core_architecture/ARCHITECTURE_OVERVIEW.md")

    Returns:
        Dict with document content and metadata
    """
    full_path = ARCA_ROOT / doc_path

    if not full_path.exists():
        return {"error": f"Document not found: {doc_path}", "path": str(full_path)}

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract title (first H1)
        title = "Unknown"
        for line in content.split("\n")[:10]:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        return {
            "path": doc_path,
            "full_path": str(full_path),
            "title": title,
            "size_kb": round(full_path.stat().st_size / 1024, 2),
            "modified": datetime.fromtimestamp(full_path.stat().st_mtime).isoformat(),
            "content": content,
        }

    except Exception as e:
        return {"error": f"Failed to read document: {e}", "path": doc_path}


def get_system_summary() -> Dict[str, Any]:
    """
    Get summary of current system state (AS-IS).

    Returns:
        Dict with system summary
    """
    summary = {"timestamp": datetime.now().isoformat(), "components": {}}

    # Read AS-IS document if available
    if SYSTEM_AS_IS.exists():
        try:
            with open(SYSTEM_AS_IS, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract key sections
            summary["as_is_available"] = True
            summary["as_is_path"] = str(SYSTEM_AS_IS.relative_to(ARCA_ROOT))

        except Exception as e:
            summary["as_is_available"] = False
            summary["error"] = str(e)
    else:
        summary["as_is_available"] = False
        summary["error"] = "AS-IS document not found"

    # Read TO-BE document if available
    if SYSTEM_TO_BE.exists():
        summary["to_be_available"] = True
        summary["to_be_path"] = str(SYSTEM_TO_BE.relative_to(ARCA_ROOT))
    else:
        summary["to_be_available"] = False

    return summary


def search_documents(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Search documents by keyword.

    Args:
        query: Search query (case-insensitive)
        max_results: Maximum number of results

    Returns:
        List of matching documents with context
    """
    results = []
    query_lower = query.lower()

    if not WIKI_DIR.exists():
        return results

    # Scan all markdown files
    for md_file in WIKI_DIR.rglob("*.md"):
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check for query match
            if query_lower in content.lower():
                # Find context around first match
                idx = content.lower().find(query_lower)
                start = max(0, idx - 100)
                end = min(len(content), idx + len(query) + 100)
                context = content[start:end].replace("\n", " ")

                results.append(
                    {
                        "path": str(md_file.relative_to(ARCA_ROOT)),
                        "title": md_file.stem,
                        "context": f"...{context}...",
                        "relevance": 1.0,  # Simple binary relevance for now
                    }
                )

                if len(results) >= max_results:
                    break

        except Exception as e:
            logger.debug(f"Error scanning {md_file}: {e}")

    return results


# ============================================================================
# MCP Tool Definitions
# ============================================================================

if MCP_AVAILABLE:

    @mcp.tool()
    async def project_context() -> Dict[str, Any]:
        """
        Get project context index and summary.

        Returns wiki index, system summary, and available documentation.
        Use this to understand project structure and available resources.

        Returns:
            Dict with:
            - wiki_index: List of all wiki documents by section
            - system_summary: AS-IS/TO-BE availability
            - total_documents: Count of available documents
        """
        return {"wiki_index": get_wiki_index(), "system_summary": get_system_summary()}

    @mcp.tool()
    async def get_wiki_document(path: str) -> Dict[str, Any]:
        """
        Get content of a specific wiki document.

        Args:
            path: Relative path to document (e.g., "shared_storage/wiki/01_core_architecture/ARCHITECTURE_OVERVIEW.md")

        Returns:
            Dict with document content, title, and metadata
        """
        return get_document_content(path)

    @mcp.tool()
    async def search_project_docs(
        query: str, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search project documentation by keyword.

        Args:
            query: Search query (case-insensitive)
            max_results: Maximum number of results (default: 10)

        Returns:
            List of matching documents with context snippets
        """
        return search_documents(query, max_results)

    @mcp.tool()
    async def list_wiki_sections() -> Dict[str, Any]:
        """
        List all wiki sections and their document counts.

        Returns:
            Dict with section names and document counts
        """
        index = get_wiki_index()

        sections = {}
        for section_name, docs in index.get("sections", {}).items():
            sections[section_name] = {
                "document_count": len(docs),
                "documents": [doc["name"] for doc in docs],
            }

        return {
            "total_sections": len(sections),
            "total_documents": index.get("total_documents", 0),
            "sections": sections,
        }


# ============================================================================
# Tool Registry Integration
# ============================================================================


def register_with_tool_registry():
    """Register project context tools with ToolRegistry"""
    try:
        from tool_registry import ToolCategory, get_tool_registry, register_tool

        registry = get_tool_registry()

        @register_tool(
            category="intelligence",
            description="Get project context index and summary",
            parameters={},
            returns="Dict with wiki_index, system_summary, total_documents",
        )
        def project_context_registry() -> Dict[str, Any]:
            return {
                "wiki_index": get_wiki_index(),
                "system_summary": get_system_summary(),
            }

        logger.info("✅ Project Context tools registered with ToolRegistry")

    except ImportError as e:
        logger.warning(f"Could not register Project Context with ToolRegistry: {e}")
    except Exception as e:
        logger.error(f"Error registering Project Context: {e}")


# Auto-register on import
register_with_tool_registry()
