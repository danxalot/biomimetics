#!/usr/bin/env python3
"""
ARCA Memory Maintainer - Lightweight Integration Module

This module provides a unified interface for agents to interact with
ARCA's memory systems (SDM, InfiniMemory, LongMemory, Accumulator, Hopfield).

Usage:
    from memory_maintainer import MemoryMaintainer, MemoryEvent
    
    maintainer = MemoryMaintainer(mcp_client)
    
    # Sync an event across memory systems
    await maintainer.sync_event(MemoryEvent(
        event_type="conversation_turn",
        content_hv=encoded_vector,
        importance=1.0,
        metadata={"session_id": "abc123"}
    ))
    
    # Intelligent retrieval
    context = await maintainer.retrieve(query_hv, strategy="cascaded")
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
import numpy as np

logger = logging.getLogger("MemoryMaintainer")


class AccumulatorChannel(Enum):
    CONTENT = "content"
    CONTEXT = "context"
    ACTIONS = "actions"
    FEEDBACK = "feedback"
    METADATA = "metadata"


class RetrievalStrategy(Enum):
    CASCADED = "cascaded"      # Hopfield → LongMem → Infini → SDM
    PARALLEL = "parallel"       # Query all, merge results
    FASTEST = "fastest"         # Hopfield only
    EPISODIC = "episodic"       # LongMem only
    COMPRESSIVE = "compressive" # InfiniMemory only


@dataclass
class MemoryEvent:
    """Event to be synchronized across memory systems."""
    event_type: str
    content_hv: np.ndarray  # HDC-encoded content
    importance: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    channel: AccumulatorChannel = AccumulatorChannel.CONTENT
    
    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "importance": self.importance,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "channel": self.channel.value
        }


@dataclass
class RetrievalResult:
    """Result from multi-system retrieval."""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    infini_relevance: float = 0.0
    hopfield_energy: float = 0.0
    total_matches: int = 0
    strategy_used: str = ""
    latency_ms: float = 0.0


class MemoryMaintainer:
    """
    Unified interface for ARCA memory system operations.
    
    This class wraps MCP tool calls and provides higher-level abstractions
    for memory synchronization, retrieval, and maintenance.
    """
    
    def __init__(self, mcp_call_tool: Callable = None, dimension: int = 4096):
        """
        Args:
            mcp_call_tool: Async function to call MCP tools, signature: (name, args) -> result
            dimension: HDC dimensionality (default 4096, matches neural_system defaults)
        """
        self._call_tool = mcp_call_tool
        self.dimension = dimension
        self._initialized = False
        
        # Event mapping to channels
        self._event_channel_map = {
            "conversation_turn": AccumulatorChannel.CONTENT,
            "conversation_end": AccumulatorChannel.CONTENT,
            "task_start": AccumulatorChannel.ACTIONS,
            "task_complete": AccumulatorChannel.ACTIONS,
            "user_feedback": AccumulatorChannel.FEEDBACK,
            "context_shift": AccumulatorChannel.CONTEXT,
            "anomaly_detected": AccumulatorChannel.METADATA,
            "repair_action": AccumulatorChannel.ACTIONS,
        }
        
        # Maintenance statistics
        self._stats = {
            "events_synced": 0,
            "retrievals": 0,
            "consolidations": 0,
            "last_maintenance": None
        }
    
    def set_mcp_client(self, call_tool: Callable):
        """Set or update the MCP tool calling function."""
        self._call_tool = call_tool
        self._initialized = True
    
    async def _tool(self, name: str, args: dict) -> dict:
        """Internal tool call wrapper with error handling."""
        if not self._call_tool:
            raise RuntimeError("MCP client not configured. Call set_mcp_client() first.")
        try:
            result = await self._call_tool(name, args)
            # Handle MCP CallToolResult objects
            if hasattr(result, 'content'):
                import json
                for item in result.content:
                    if hasattr(item, 'text'):
                        try:
                            return json.loads(item.text)
                        except:
                            return {"raw": item.text}
            return result
        except Exception as e:
            logger.error(f"Tool call failed: {name} - {e}")
            return {"error": str(e)}
    
    # ==================== Event Synchronization ====================
    
    async def sync_event(self, event: MemoryEvent) -> Dict[str, Any]:
        """
        Synchronize an event across all appropriate memory systems.
        
        This is the primary method agents should call after significant events.
        """
        results = {"systems_updated": [], "errors": []}
        
        # Ensure content_hv is a list for JSON serialization
        hv_list = event.content_hv.tolist() if isinstance(event.content_hv, np.ndarray) else event.content_hv
        
        # 1. Update InfiniMemory (always - compressive accumulation)
        try:
            infini_result = await self._tool("infini_update", {
                "content_hv": hv_list,
                "importance": event.importance
            })
            if "error" not in infini_result:
                results["systems_updated"].append("infini")
            else:
                results["errors"].append(f"infini: {infini_result['error']}")
        except Exception as e:
            results["errors"].append(f"infini: {e}")
        
        # 2. Store in LongMemory (for retrieval)
        try:
            longmem_result = await self._tool("longmem_store", {
                "key_hv": hv_list,
                "value": event.to_dict()
            })
            if "error" not in longmem_result:
                results["systems_updated"].append("longmem")
            else:
                results["errors"].append(f"longmem: {longmem_result['error']}")
        except Exception as e:
            results["errors"].append(f"longmem: {e}")
        
        # 3. Add to appropriate Accumulator channel
        channel = self._event_channel_map.get(event.event_type, event.channel)
        try:
            accum_result = await self._tool("accumulator_add", {
                "channel": channel.value,
                "content_hv": hv_list,
                "importance": event.importance
            })
            if "error" not in accum_result:
                results["systems_updated"].append(f"accumulator:{channel.value}")
            else:
                results["errors"].append(f"accumulator: {accum_result['error']}")
        except Exception as e:
            results["errors"].append(f"accumulator: {e}")
        
        # 4. For high-importance events, store as Hopfield attractor
        if event.importance >= 1.5:
            try:
                hopfield_result = await self._tool("hopfield_store", {
                    "patterns": [hv_list]
                })
                if "error" not in hopfield_result:
                    results["systems_updated"].append("hopfield")
            except Exception as e:
                results["errors"].append(f"hopfield: {e}")
        
        self._stats["events_synced"] += 1
        logger.info(f"Event synced: {event.event_type} → {results['systems_updated']}")
        
        return results
    
    # ==================== Intelligent Retrieval ====================
    
    async def retrieve(
        self, 
        query_hv: np.ndarray, 
        strategy: RetrievalStrategy = RetrievalStrategy.CASCADED,
        top_k: int = 5,
        recency_weight: float = 0.2
    ) -> RetrievalResult:
        """
        Retrieve relevant memories using specified strategy.
        
        Strategies:
        - CASCADED: Try Hopfield first, fall back to LongMem, then others
        - PARALLEL: Query all systems simultaneously, merge results
        - FASTEST: Hopfield only (good for known patterns)
        - EPISODIC: LongMemory only (good for conversational context)
        - COMPRESSIVE: InfiniMemory query (good for relevance check)
        """
        import time
        start = time.time()
        
        hv_list = query_hv.tolist() if isinstance(query_hv, np.ndarray) else query_hv
        result = RetrievalResult(strategy_used=strategy.value)
        
        if strategy == RetrievalStrategy.CASCADED:
            result = await self._cascaded_retrieval(hv_list, top_k, recency_weight)
        elif strategy == RetrievalStrategy.PARALLEL:
            result = await self._parallel_retrieval(hv_list, top_k, recency_weight)
        elif strategy == RetrievalStrategy.FASTEST:
            result = await self._hopfield_only(hv_list)
        elif strategy == RetrievalStrategy.EPISODIC:
            result = await self._longmem_only(hv_list, top_k, recency_weight)
        elif strategy == RetrievalStrategy.COMPRESSIVE:
            result = await self._infini_only(hv_list)
        
        result.latency_ms = (time.time() - start) * 1000
        result.strategy_used = strategy.value
        self._stats["retrievals"] += 1
        
        return result
    
    async def _cascaded_retrieval(self, hv_list: list, top_k: int, recency_weight: float) -> RetrievalResult:
        """Cascaded retrieval: Hopfield → LongMem → Infini → SDM."""
        result = RetrievalResult()
        
        # 1. Try Hopfield first (fast attractor match)
        hopfield = await self._tool("hopfield_retrieve", {
            "query": hv_list,
            "iterations": 2
        })
        if "error" not in hopfield:
            result.hopfield_energy = hopfield.get("energy", 0)
            if hopfield.get("energy", 0) < -0.5:  # Good match
                result.sources.append({
                    "system": "hopfield",
                    "confidence": abs(hopfield["energy"]),
                    "pattern_sample": hopfield.get("retrieved_sample", [])[:10]
                })
                result.total_matches = 1
                return result  # High-confidence match, return early
        
        # 2. Query LongMemory
        longmem = await self._tool("longmem_retrieve", {
            "query_hv": hv_list,
            "top_k": top_k,
            "recency_weight": recency_weight
        })
        if "error" not in longmem and longmem.get("memories"):
            result.sources.extend([
                {"system": "longmem", "memory": m} 
                for m in longmem["memories"]
            ])
            result.total_matches += len(longmem["memories"])
        
        # 3. Check InfiniMemory relevance
        infini = await self._tool("infini_query", {"query_hv": hv_list})
        if "error" not in infini:
            result.infini_relevance = infini.get("similarity", 0)
        
        # 4. If nothing found, try SDM cleanup
        if result.total_matches == 0:
            sdm = await self._tool("sdm_cleanup", {
                "pattern": hv_list,
                "iterations": 3
            })
            if "error" not in sdm and sdm.get("converged"):
                result.sources.append({
                    "system": "sdm",
                    "reconstructed_sample": sdm.get("cleaned_sample", [])[:10]
                })
                result.total_matches = 1
        
        return result
    
    async def _parallel_retrieval(self, hv_list: list, top_k: int, recency_weight: float) -> RetrievalResult:
        """Query all systems in parallel and merge results."""
        result = RetrievalResult()
        
        # Fire all queries concurrently
        hopfield_task = self._tool("hopfield_retrieve", {"query": hv_list, "iterations": 1})
        longmem_task = self._tool("longmem_retrieve", {"query_hv": hv_list, "top_k": top_k, "recency_weight": recency_weight})
        infini_task = self._tool("infini_query", {"query_hv": hv_list})
        
        hopfield, longmem, infini = await asyncio.gather(
            hopfield_task, longmem_task, infini_task,
            return_exceptions=True
        )
        
        # Merge results
        if isinstance(hopfield, dict) and "error" not in hopfield:
            result.hopfield_energy = hopfield.get("energy", 0)
            if hopfield.get("energy", 0) < -0.3:
                result.sources.append({"system": "hopfield", "data": hopfield})
                result.total_matches += 1
        
        if isinstance(longmem, dict) and "error" not in longmem:
            memories = longmem.get("memories", [])
            result.sources.extend([{"system": "longmem", "memory": m} for m in memories])
            result.total_matches += len(memories)
        
        if isinstance(infini, dict) and "error" not in infini:
            result.infini_relevance = infini.get("similarity", 0)
        
        return result
    
    async def _hopfield_only(self, hv_list: list) -> RetrievalResult:
        """Fastest retrieval - Hopfield only."""
        result = RetrievalResult()
        hopfield = await self._tool("hopfield_retrieve", {"query": hv_list, "iterations": 2})
        if "error" not in hopfield:
            result.hopfield_energy = hopfield.get("energy", 0)
            result.sources.append({"system": "hopfield", "data": hopfield})
            result.total_matches = 1
        return result
    
    async def _longmem_only(self, hv_list: list, top_k: int, recency_weight: float) -> RetrievalResult:
        """Episodic retrieval - LongMemory only."""
        result = RetrievalResult()
        longmem = await self._tool("longmem_retrieve", {
            "query_hv": hv_list, "top_k": top_k, "recency_weight": recency_weight
        })
        if "error" not in longmem:
            memories = longmem.get("memories", [])
            result.sources.extend([{"system": "longmem", "memory": m} for m in memories])
            result.total_matches = len(memories)
        return result
    
    async def _infini_only(self, hv_list: list) -> RetrievalResult:
        """Compressive retrieval - InfiniMemory relevance only."""
        result = RetrievalResult()
        infini = await self._tool("infini_query", {"query_hv": hv_list})
        if "error" not in infini:
            result.infini_relevance = infini.get("similarity", 0)
            result.total_matches = 1 if result.infini_relevance > 0.3 else 0
        return result
    
    # ==================== Maintenance Operations ====================
    
    async def run_consolidation(self) -> Dict[str, Any]:
        """
        Run memory consolidation (dreaming cycle).
        Call this during system idle time or on schedule.
        """
        results = {"actions": [], "stats": {}}
        
        # 1. Check InfiniMemory stats
        infini_stats = await self._tool("infini_stats", {})
        if "error" not in infini_stats:
            results["stats"]["infini"] = infini_stats
        
        # 2. Consolidate Accumulator channels
        accum_result = await self._tool("accumulator_consolidate", {})
        if "error" not in accum_result:
            results["actions"].append("accumulator_consolidated")
            
            # Store consolidated vector as Hopfield attractor
            if "consolidated_vector" in accum_result:
                await self._tool("hopfield_store", {
                    "patterns": [accum_result["consolidated_vector"][:100]]  # Truncate for safety
                })
                results["actions"].append("hopfield_attractor_stored")
        
        # 3. Get Accumulator stats
        accum_stats = await self._tool("accumulator_stats", {})
        if "error" not in accum_stats:
            results["stats"]["accumulator"] = accum_stats
        
        self._stats["consolidations"] += 1
        self._stats["last_maintenance"] = datetime.utcnow().isoformat()
        
        logger.info(f"Consolidation complete: {results['actions']}")
        return results
    
    async def health_check(self) -> Dict[str, Any]:
        """Get health status of all memory systems."""
        health = {}
        
        # SDM
        sdm = await self._tool("sdm_stats", {})
        health["sdm"] = {
            "status": "ok" if "error" not in sdm else "error",
            "data": sdm
        }
        
        # InfiniMemory
        infini = await self._tool("infini_stats", {})
        health["infini"] = {
            "status": "ok" if "error" not in infini else "error",
            "data": infini
        }
        
        # LongMemory
        longmem = await self._tool("longmem_stats", {})
        health["longmem"] = {
            "status": "ok" if "error" not in longmem else "error",
            "data": longmem
        }
        
        # Accumulator
        accum = await self._tool("accumulator_stats", {})
        health["accumulator"] = {
            "status": "ok" if "error" not in accum else "error",
            "data": accum
        }
        
        # Overall status
        all_ok = all(h["status"] == "ok" for h in health.values())
        health["overall"] = "healthy" if all_ok else "degraded"
        health["maintainer_stats"] = self._stats
        
        return health
    
    def get_stats(self) -> Dict[str, Any]:
        """Get maintainer statistics."""
        return self._stats.copy()

    def sync_ingest(self, hv: np.ndarray, importance: float = 1.0,
                    event_type: str = "concept_ingest") -> Dict[str, Any]:
        """
        Thread-safe synchronous wrapper around async sync_event().

        Allows PhenomenologicalCore (synchronous) to ingest a concept into the
        full memory cascade (SDM → InfiniMemory → LongMemory → Hopfield) without
        requiring an event loop to already be running.

        If no MCP client has been configured, this is a safe no-op.
        """
        if not self._call_tool:
            logger.debug("sync_ingest: MCP client not configured — skipping memory cascade")
            return {"skipped": True, "reason": "no_mcp_client"}

        event = MemoryEvent(
            event_type=event_type,
            content_hv=np.asarray(hv, dtype=np.float32),
            importance=importance,
        )

        try:
            # Try to get the running loop (FastAPI context has one)
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # We are inside an async context; schedule as a coroutine on the
                # existing loop's thread pool so we don't block the event thread.
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    self.sync_event(event), loop
                )
                return future.result(timeout=5.0)
            except RuntimeError:
                # No running loop — safe to call asyncio.run()
                return asyncio.run(self.sync_event(event))
        except Exception as exc:
            logger.warning("sync_ingest failed: %s", exc)
            return {"error": str(exc)}


# ==================== Factory Function ====================

def create_memory_maintainer(mcp_call_tool: Callable = None, dimension: int = 4096) -> MemoryMaintainer:
    """
    Factory function to create a MemoryMaintainer instance.
    
    Args:
        mcp_call_tool: Async function to call MCP tools
        dimension: HDC dimensionality
    
    Returns:
        Configured MemoryMaintainer instance
    """
    return MemoryMaintainer(mcp_call_tool=mcp_call_tool, dimension=dimension)


# ==================== Singleton for Global Access ====================

_global_maintainer: Optional[MemoryMaintainer] = None

def get_memory_maintainer() -> MemoryMaintainer:
    """Get or create the global MemoryMaintainer instance."""
    global _global_maintainer
    if _global_maintainer is None:
        _global_maintainer = MemoryMaintainer()
    return _global_maintainer

def set_memory_maintainer(maintainer: MemoryMaintainer):
    """Set the global MemoryMaintainer instance."""
    global _global_maintainer
    _global_maintainer = maintainer
