"""
V2 Geometry Kernel - Embedding Queue Worker

Processes the embedding queue during system downtime.
Embeds cached content when the system is idle.

Uses Qwen3-Embedding for text embeddings.
"""

import os
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    """Item from the embedding queue."""
    id: int
    content: str
    source: str
    priority: int
    created_at: str


class EmbeddingQueueWorker:
    """
    Background worker that processes the embedding queue.
    
    Runs during idle periods to embed cached content
    that was queued during busy periods.
    """
    
    def __init__(
        self,
        db_path: str = "working_memory.db",
        embedding_service_url: str = "http://localhost:8005",
        batch_size: int = 10,
        idle_threshold_seconds: float = 5.0
    ):
        """
        Initialize the embedding queue worker.
        
        Args:
            db_path: Path to SQLite database
            embedding_service_url: URL of embedding service
            batch_size: Number of items to process per batch
            idle_threshold_seconds: Minimum idle time before processing
        """
        self.db_path = db_path
        self.embedding_service_url = embedding_service_url
        self.batch_size = batch_size
        self.idle_threshold = idle_threshold_seconds
        
        self._last_activity = time.time()
        self._running = False
        self._processed_count = 0
        
        logger.info(f"EmbeddingQueueWorker initialized (batch={batch_size})")
    
    def record_activity(self):
        """Record activity to reset idle timer."""
        self._last_activity = time.time()
    
    def is_idle(self) -> bool:
        """Check if system is idle enough for background processing."""
        elapsed = time.time() - self._last_activity
        return elapsed >= self.idle_threshold
    
    async def add_to_queue(
        self, 
        content: str, 
        source: str = "unknown",
        priority: int = 0
    ) -> int:
        """
        Add content to the embedding queue.
        
        Args:
            content: Text content to embed
            source: Source identifier
            priority: Higher priority items processed first
            
        Returns:
            Queue item ID
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO embedding_queue (content, source, priority)
                VALUES (?, ?, ?)
            """, (content, source, priority))
            await db.commit()
            
            item_id = cursor.lastrowid
            logger.debug(f"Added to embedding queue: id={item_id}, source={source}")
            return item_id
    
    async def get_pending_items(self, limit: int = None) -> List[QueueItem]:
        """Get pending items from the queue."""
        limit = limit or self.batch_size
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id, content, source, priority, created_at
                FROM embedding_queue
                WHERE embedded = FALSE
                ORDER BY priority DESC, created_at ASC
                LIMIT ?
            """, (limit,))
            
            rows = await cursor.fetchall()
            
            return [
                QueueItem(
                    id=row[0],
                    content=row[1],
                    source=row[2],
                    priority=row[3],
                    created_at=row[4]
                )
                for row in rows
            ]
    
    async def mark_embedded(self, item_id: int):
        """Mark an item as embedded."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE embedding_queue
                SET embedded = TRUE, embedded_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (item_id,))
            await db.commit()
    
    async def _embed_content(self, content: str) -> Optional[List[float]]:
        """Get embedding from service."""
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.embedding_service_url}/embed/text",
                    json={"texts": [content]},
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()["embeddings"][0]
        except Exception as e:
            logger.error(f"Embedding service error: {e}")
            return None
    
    async def process_batch(self) -> int:
        """
        Process a batch of pending items.
        
        Returns:
            Number of items processed
        """
        items = await self.get_pending_items()
        
        if not items:
            return 0
        
        processed = 0
        for item in items:
            try:
                # Get embedding
                embedding = await self._embed_content(item.content)
                
                if embedding:
                    # TODO: Store embedding in episodic memory
                    # For now, just mark as processed
                    await self.mark_embedded(item.id)
                    processed += 1
                    self._processed_count += 1
                    
                    logger.debug(
                        f"Embedded item {item.id} from {item.source}"
                    )
            except Exception as e:
                logger.error(f"Error processing item {item.id}: {e}")
        
        if processed > 0:
            logger.info(f"Processed {processed} embeddings from queue")
        
        return processed
    
    async def run_worker_cycle(self):
        """Run a single worker cycle if idle."""
        if not self.is_idle():
            return 0
        
        return await self.process_batch()
    
    async def start_background_worker(self, check_interval: float = 1.0):
        """
        Start the background worker loop.
        
        Args:
            check_interval: Seconds between idle checks
        """
        self._running = True
        logger.info("Embedding queue worker started")
        
        while self._running:
            try:
                await self.run_worker_cycle()
            except Exception as e:
                logger.error(f"Worker error: {e}")
            
            await asyncio.sleep(check_interval)
        
        logger.info("Embedding queue worker stopped")
    
    def stop(self):
        """Stop the background worker."""
        self._running = False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        return {
            "processed_total": self._processed_count,
            "is_idle": self.is_idle(),
            "idle_threshold": self.idle_threshold,
            "running": self._running
        }


async def main():
    """Test the embedding queue worker."""
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    # Initialize with test database
    db_path = "test_embedding_queue.db"
    
    # Create tables first
    async with aiosqlite.connect(db_path) as db:
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
    
    worker = EmbeddingQueueWorker(
        db_path=db_path,
        idle_threshold_seconds=1.0
    )
    
    # Add test items
    print("Adding test items to queue...")
    await worker.add_to_queue("This is a test message", "test", priority=1)
    await worker.add_to_queue("Another test message", "test", priority=2)
    await worker.add_to_queue("Low priority message", "test", priority=0)
    
    # Check pending
    pending = await worker.get_pending_items()
    print(f"Pending items: {len(pending)}")
    
    # Wait for idle
    print("Waiting for idle period...")
    await asyncio.sleep(2)
    
    # Process (will fail without embedding service, but shows the flow)
    processed = await worker.process_batch()
    print(f"Processed: {processed}")
    
    print(f"Stats: {worker.get_stats()}")
    
    # Cleanup
    os.unlink(db_path)


if __name__ == "__main__":
    asyncio.run(main())
