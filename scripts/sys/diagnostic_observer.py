#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BiOS Diagnostic Observer - Autonomous Sidecar for System Anomalies
Tails the session logs, detects errors, and pushes payloads to Notion.
"""

import os
import time
import json
import httpx
import logging
from pathlib import Path

# --- Configuration ---
LOG_FILE = Path("logs/bios_session.log")
BACKEND_URL = "http://localhost:8090/mcp/call"
NOTION_DB_ID = "3284d2d9-fc7c-81f3-8ceb-ded2ff235c9e"
POLL_INTERVAL = 1.0  # seconds
DEBOUNCE_SEC = 5.0    # Don't report the same error within 5s

# --- Setup logging for the sidecar itself ---
logging.basicConfig(level=logging.INFO, format="[DIAGNOSTIC] %(message)s")
logger = logging.getLogger(__name__)

class DiagnosticObserver:
    def __init__(self):
        self.last_seen_pos = 0
        self.last_report_time = 0
        self.client = httpx.Client(timeout=10.0)

    def _push_to_notion(self, error_text: str):
        """Proxy call through CoPaw backend to reach Notion MCP."""
        payload = {
            "server_name": "notion",
            "tool_name": "API-post-page",
            "arguments": {
                "parent": {"database_id": NOTION_DB_ID},
                "properties": {
                    "Name": {"title": [{"text": {"content": f"System Anomaly: {time.strftime('%Y-%m-%d %H:%M:%S')}"}}]},
                    "Status": {"select": {"name": "Critical"}},
                    "Tag": {"select": {"name": "System Anomalies"}}
                },
                "children": [
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": [{"type": "text", "text": {"content": error_text[:2000]}}],
                            "language": "plain text"
                        }
                    }
                ]
            }
        }
        
        try:
            resp = self.client.post(BACKEND_URL, json=payload)
            if resp.status_code == 200:
                logger.info("Successfully pushed anomaly to Notion.")
            else:
                logger.warning(f"Failed to push to Notion (HTTP {resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Error pushing to backend bridge: {e}")

    def run(self):
        logger.info(f"Starting observer on {LOG_FILE}")
        
        # Ensure log exists
        if not LOG_FILE.exists():
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            LOG_FILE.touch()

        # Start at the end of the file
        self.last_seen_pos = LOG_FILE.stat().st_size

        while True:
            try:
                curr_size = LOG_FILE.stat().st_size
                if curr_size < self.last_seen_pos:
                    # Log truncated
                    self.last_seen_pos = 0

                if curr_size > self.last_seen_pos:
                    with open(LOG_FILE, "r") as f:
                        f.seek(self.last_seen_pos)
                        lines = f.readlines()
                        self.last_seen_pos = f.tell()

                        # Detect anomaly
                        error_batch = []
                        for line in lines:
                            if any(trigger in line.upper() for trigger in ["ERROR", "CRITICAL", "TRACEBACK"]):
                                error_batch.append(line.strip())

                        if error_batch:
                            now = time.time()
                            if now - self.last_report_time > DEBOUNCE_SEC:
                                combined_errors = "\n".join(error_batch)
                                logger.error(f"Anomaly detected! Reporting to Notion...")
                                self._push_to_notion(combined_errors)
                                self.last_report_time = now

            except Exception as e:
                logger.error(f"Observer loop error: {e}")

            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    observer = DiagnosticObserver()
    observer.run()
