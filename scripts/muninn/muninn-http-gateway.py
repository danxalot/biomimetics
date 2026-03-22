#!/usr/bin/env python3
"""
MuninnDB HTTP Gateway - Wraps Go MCP binary with HTTP API
Listens on 0.0.0.0:8097 for Cloud Function Gateway compatibility
"""
import json
import os
import hashlib
import sqlite3
import math
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib import request

PORT = 8097
MCP_URL = os.environ.get('MUNINN_MCP_URL', 'http://127.0.0.1:8750/mcp')
DB_PATH = '/home/danexall/muninn/data/muninn.db'

# ACT-R parameters
DECAY_RATE = 0.01
RETRIEVAL_THRESHOLD = 0.3

working_memories = []

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, content TEXT, metadata TEXT, confidence REAL DEFAULT 0.5, created_at TEXT)')
    conn.commit()
    cursor = conn.execute('SELECT * FROM memories ORDER BY created_at DESC LIMIT 100')
    for row in cursor:
        working_memories.append({
            'id': row['id'],
            'content': row['content'],
            'metadata': json.loads(row['metadata']) if row['metadata'] else {},
            'confidence': row['confidence'],
            'created': row['created_at']
        })
    conn.close()
    print(f'Loaded {len(working_memories)} memories from persistent storage')

def apply_decay(confidence: float, hours: float) -> float:
    return confidence * math.exp(-DECAY_RATE * hours)

def call_mcp(method: str, params: dict) -> dict:
    """Call MCP endpoint"""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        data = json.dumps(payload).encode('utf-8')
        req = request.Request(MCP_URL, data=data, headers={'Content-Type': 'application/json'})
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, f, *a): print(f'[{datetime.now()}] {a[0]}')
    def send_json(self, d, s=200):
        self.send_response(s)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())
    def do_GET(self):
        if self.path == '/health':
            self.send_json({'status': 'healthy', 'service': 'muninndb', 'type': 'working_memory', 'persistent': True, 'go_binary': True})
        elif self.path == '/Activate':
            self.send_json({'status': 'ok', 'endpoint': 'ACT-R activation'})
        elif self.path == '/memories':
            self.send_json({'memories': working_memories[-50:]})
        else:
            self.send_json({'error': 'not found'}, 404)
    def do_POST(self):
        l = int(self.headers.get('Content-Length', 0))
        b = self.rfile.read(l).decode()
        p = json.loads(b) if b else {}
        
        if '/search' in self.path or '/Activate' in self.path:
            q = p.get('query', '')
            now = datetime.now()
            results = []
            for m in working_memories:
                created = datetime.fromisoformat(m['created'])
                hours = (now - created).total_seconds() / 3600
                confidence = apply_decay(m.get('confidence', 0.5), hours)
                if q.lower() in m['content'].lower():
                    if confidence >= RETRIEVAL_THRESHOLD:
                        results.append({
                            'id': m['id'],
                            'content': m['content'],
                            'metadata': m.get('metadata', {}),
                            'confidence': confidence,
                            'source': 'muninn_working'
                        })
            results.sort(key=lambda x: x['confidence'], reverse=True)
            self.send_json({'status': 'success', 'query': q, 'results': results[:10]})
        
        elif '/memorize' in self.path:
            c = p.get('content', '')
            if not c:
                return self.send_json({'error': 'content required'}, 400)
            m = {
                'id': hashlib.md5(c.encode()).hexdigest()[:8],
                'content': c,
                'metadata': p.get('metadata', {}),
                'confidence': 0.9,
                'created': datetime.now().isoformat()
            }
            working_memories.append(m)
            try:
                conn = get_db()
                conn.execute('INSERT OR REPLACE INTO memories (id, content, metadata, confidence, created_at) VALUES (?, ?, ?, ?, ?)',
                           (m['id'], c, json.dumps(m['metadata']), m['confidence'], m['created']))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f'DB error: {e}')
            self.send_json({'status': 'success', 'id': m['id'], 'confidence': m['confidence']})
        else:
            self.send_json({'error': 'not found'}, 404)

if __name__ == '__main__':
    init_db()
    print(f'MuninnDB HTTP Gateway on :{PORT}')
    print(f'MCP URL: {MCP_URL}')
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
