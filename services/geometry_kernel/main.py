"""
V2 Geometry Kernel - Main Runtime

Orchestrates the complete Cognitive Tick loop:
1. Visual Spike Detection (SigLIP) - 310ms
2. Qwen VL Description (on spike only)
3. DeepSeek R1 Reasoning
4. Guardian Safety Screening
5. Background Embedding (during idle)

Usage:
    python -m geometry_kernel.main

Or as a library:
    from geometry_kernel.main import V2GeometryKernel
    kernel = V2GeometryKernel()
    await kernel.start()
"""

import os
import sys
import time
import asyncio
import logging
from typing import Optional, Callable, Any
from dataclasses import dataclass
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from geometry_kernel.visual_spike import VisualSpikeDetector
from geometry_kernel.cognitive_scheduler import CognitiveScheduler, CognitiveTickResult
from geometry_kernel.embedding_worker import EmbeddingQueueWorker

logger = logging.getLogger(__name__)


@dataclass
class KernelConfig:
    """Configuration for V2 Geometry Kernel."""
    # Spike detection
    spike_threshold: float = 0.95
    
    # Tick timing
    tick_interval_ms: float = 100.0  # 10 Hz check rate
    
    # Servers
    gpu_port: int = 11434
    vl_port: int = 11435
    guardian_port: int = 11436
    
    # Safety
    enable_safety: bool = True
    
    # Embedding
    embedding_idle_seconds: float = 5.0
    
    # Database
    db_path: str = "working_memory.db"


class V2GeometryKernel:
    """
    V2 Geometry Kernel Runtime
    
    Orchestrates visual perception, reasoning, and safety
    with optimized spike detection for efficient processing.
    
    Example:
        kernel = V2GeometryKernel()
        
        # Process a single frame
        result = await kernel.process_frame(image)
        
        # Or run continuous loop
        await kernel.run(frame_source=camera_feed)
    """
    
    def __init__(self, config: Optional[KernelConfig] = None):
        """Initialize the V2 Geometry Kernel."""
        self.config = config or KernelConfig()
        
        # Core components
        self.scheduler = CognitiveScheduler(
            spike_threshold=self.config.spike_threshold,
            enable_safety=self.config.enable_safety
        )
        
        self.embedding_worker = EmbeddingQueueWorker(
            db_path=self.config.db_path,
            idle_threshold_seconds=self.config.embedding_idle_seconds
        )
        
        # Flag to track initialization
        self._initialized = False
        
        # State
        self._running = False
        self._tick_count = 0
        self._last_tick_time = 0.0
        
        # Callbacks
        self._on_spike: Optional[Callable[[CognitiveTickResult], Any]] = None
        self._on_tick: Optional[Callable[[CognitiveTickResult], Any]] = None
        
        logger.info(
            f"V2GeometryKernel initialized "
            f"(threshold={self.config.spike_threshold}, "
            f"interval={self.config.tick_interval_ms}ms)"
        )
    
    def on_spike(self, callback: Callable[[CognitiveTickResult], Any]):
        """Register callback for visual spike events."""
        self._on_spike = callback
    
    def on_tick(self, callback: Callable[[CognitiveTickResult], Any]):
        """Register callback for every tick."""
        self._on_tick = callback
    
    async def process_frame(self, image) -> CognitiveTickResult:
        """
        Process a single frame through the cognitive pipeline.
        
        Args:
            image: Image to process (PIL, numpy, or path)
            
        Returns:
            CognitiveTickResult with all outputs
        """
        # Record activity for embedding worker
        self.embedding_worker.record_activity()
        
        # Run cognitive tick
        result = self.scheduler.tick(image)
        
        # Fire callbacks
        if self._on_tick:
            try:
                await self._maybe_await(self._on_tick(result))
            except Exception as e:
                logger.error(f"on_tick callback error: {e}")
        
        if result.visual_spike and self._on_spike:
            try:
                await self._maybe_await(self._on_spike(result))
            except Exception as e:
                logger.error(f"on_spike callback error: {e}")
        
        # Queue description for embedding if we got a new one
        if result.visual_spike and result.visual_description:
            await self.embedding_worker.add_to_queue(
                content=result.visual_description,
                source="visual_spike",
                priority=1
            )
        
        if result.reasoning_output:
            await self.embedding_worker.add_to_queue(
                content=result.reasoning_output,
                source="reasoning",
                priority=2
            )
        
        self._tick_count += 1
        self._last_tick_time = time.time()
        
        return result
    
    async def _maybe_await(self, result):
        """Await if result is a coroutine."""
        if asyncio.iscoroutine(result):
            await result
    
    async def run(
        self, 
        frame_source: Callable[[], Any],
        max_ticks: Optional[int] = None
    ):
        """
        Run the continuous cognitive tick loop.
        
        Args:
            frame_source: Callable that returns the next frame
            max_ticks: Maximum ticks to run (None for infinite)
        """
        self._running = True
        tick_interval_sec = self.config.tick_interval_ms / 1000.0
        
        logger.info("V2 Geometry Kernel starting tick loop...")
        
        # Initialize database tables if needed
        import aiosqlite
        async with aiosqlite.connect(self.config.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS embedding_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    priority INTEGER DEFAULT 0,
                    embedded BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embedded_at TIMESTAMP
                )
            """)
            await db.commit()
        
        # Start embedding worker in background
        embedding_task = asyncio.create_task(
            self.embedding_worker.start_background_worker()
        )
        
        try:
            tick_num = 0
            while self._running:
                loop_start = time.time()
                
                # Get frame
                frame = frame_source()
                if frame is None:
                    logger.warning("Frame source returned None, stopping")
                    break
                
                # Process
                result = await self.process_frame(frame)
                
                # Rate limiting
                elapsed = time.time() - loop_start
                sleep_time = max(0, tick_interval_sec - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
                tick_num += 1
                if max_ticks and tick_num >= max_ticks:
                    logger.info(f"Reached max ticks: {max_ticks}")
                    break
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self._running = False
            self.embedding_worker.stop()
            embedding_task.cancel()
            
            logger.info(
                f"V2 Geometry Kernel stopped after {tick_num} ticks"
            )
    
    def stop(self):
        """Stop the kernel."""
        self._running = False
        self.embedding_worker.stop()
    
    def get_stats(self) -> dict:
        """Get kernel statistics."""
        return {
            "ticks": self._tick_count,
            "running": self._running,
            "scheduler": self.scheduler.get_stats(),
            "embedding_worker": self.embedding_worker.get_stats()
        }


async def demo():
    """Demo the V2 Geometry Kernel."""
    from PIL import Image
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    print("=" * 60)
    print("V2 Geometry Kernel Demo")
    print("=" * 60)
    
    # Initialize kernel
    kernel = V2GeometryKernel(
        KernelConfig(
            spike_threshold=0.95,
            enable_safety=False  # Disable for demo
        )
    )
    
    # Register callbacks
    def on_spike(result: CognitiveTickResult):
        print(f"🔴 SPIKE at tick {result.frame_id}!")
        print(f"   Description: {result.visual_description[:50]}...")
    
    kernel.on_spike(on_spike)
    
    # Create test frames
    frames = [
        Image.new("RGB", (224, 224), "red"),    # Frame 1
        Image.new("RGB", (224, 224), "red"),    # Frame 2 (same)
        Image.new("RGB", (224, 224), "red"),    # Frame 3 (same)
        Image.new("RGB", (224, 224), "blue"),   # Frame 4 (SPIKE!)
        Image.new("RGB", (224, 224), "blue"),   # Frame 5 (same)
        Image.new("RGB", (224, 224), "green"),  # Frame 6 (SPIKE!)
    ]
    frame_iter = iter(frames)
    
    def get_next_frame():
        try:
            return next(frame_iter)
        except StopIteration:
            return None
    
    print("\nProcessing 6 test frames...")
    print("-" * 60)
    
    await kernel.run(
        frame_source=get_next_frame,
        max_ticks=6
    )
    
    print("-" * 60)
    print("\nFinal Stats:")
    stats = kernel.get_stats()
    print(f"  Ticks: {stats['ticks']}")
    print(f"  Spike Rate: {stats['scheduler']['spike_rate']:.1%}")
    print(f"  Reuse Rate: {stats['scheduler']['reuse_rate']:.1%}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
