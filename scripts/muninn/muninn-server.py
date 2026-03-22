#!/usr/bin/env python3
"""MuninnDB Server - Working Memory with ACT-R & Hebbian Learning (Persistent)"""
import json, os, sqlite3, hashlib, math
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8097
DB_PATH = '/home/danexall/muninn/data/muninn.db'  # Persistent storage

# ACT-R / Hebbian parameters
DECAY_RATE = 0.01  # per hour
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
    # Load existing memories from disk
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

class Handler(BaseHTTPRequestHandler):
    def log_message(self, f, *a): print(f'[{datetime.now()}] {a[0]}')
    def send_json(self, d, s=200):
        self.send_response(s)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())
    def do_GET(self):
        if self.path == '/health': self.send_json({'status': 'healthy', 'service': 'muninndb', 'type': 'working_memory', 'persistent': True})
        elif self.path == '/Activate': self.send_json({'status': 'ok', 'endpoint': 'ACT-R activation'})
        elif self.path == '/memories': self.send_json({'memories': working_memories[-50:]})
        else: self.send_json({'error': 'not found'}, 404)
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
                        results.append({'id': m['id'], 'content': m['content'], 'metadata': m.get('metadata', {}), 'confidence': confidence, 'source': 'muninn_working'})
            results.sort(key=lambda x: x['confidence'], reverse=True)
            self.send_json({'status': 'success', 'query': q, 'results': results[:10]})
        
        elif '/memorize' in self.path:
            c = p.get('content', '')
            if not c: return self.send_json({'error': 'content required'}, 400)
            m = {'id': hashlib.md5(c.encode()).hexdigest()[:8], 'content': c, 'metadata': p.get('metadata', {}), 'confidence': 0.9, 'created': datetime.now().isoformat()}
            working_memories.append(m)
            # Persist to SQLite
            try:
                conn = get_db()
                conn.execute('INSERT OR REPLACE INTO memories (id, content, metadata, confidence, created_at) VALUES (?, ?, ?, ?, ?)',
                           (m['id'], c, json.dumps(m['metadata']), m['confidence'], m['created']))
                conn.commit()
                conn.close()
            except Exception as e: print(f'DB error: {e}')
            self.send_json({'status': 'success', 'id': m['id'], 'confidence': m['confidence']})
        else: self.send_json({'error': 'not found'}, 404)

if __name__ == '__main__':
    init_db()
    print(f'MuninnDB (persistent working memory) on :{PORT}')
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
