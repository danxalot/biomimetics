#!/bin/bash
# MuninnDB Complete Setup - Go Binary + HTTP Gateway

set -e

echo "=== MuninnDB Complete Setup ==="
date

# Stop all existing services
systemctl stop muninndb 2>/dev/null || true
systemctl stop muninn-gateway 2>/dev/null || true
pkill -9 -f muninn-server.py 2>/dev/null || true
pkill -9 -f 'python.*8097' 2>/dev/null || true
pkill -9 -f 'python.*http-gateway' 2>/dev/null || true

# Create directories
mkdir -p /home/danexall/muninn/data

# Download Go binary if needed
if [ ! -f /usr/local/bin/muninn ]; then
    echo "Downloading MuninnDB Go binary..."
    curl -sL 'https://github.com/scrypster/muninndb/releases/download/v0.4.2-alpha/muninn_v0.4.2-alpha_linux_amd64.tar.gz' -o /tmp/muninn.tar.gz
    tar -xzf /tmp/muninn.tar.gz -C /tmp/
    mv /tmp/muninn /usr/local/bin/muninn
    chmod +x /usr/local/bin/muninn
fi

echo "MuninnDB version:"
muninn --version

# Initialize MuninnDB (non-interactive, no token for simplicity)
echo "Initializing MuninnDB..."
muninn init --yes --no-token --no-start 2>&1 || echo "Init completed or skipped"

# Create HTTP Gateway script (port 8097 for Cloud Function compatibility)
cat > /home/danexall/muninn-http-gateway.py << 'PYEOF'
#!/usr/bin/env python3
import json, os, sqlite3, hashlib, math
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8097
DB_PATH = '/home/danexall/muninn/data/muninn.db'
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
        working_memories.append({'id': row['id'], 'content': row['content'], 'metadata': json.loads(row['metadata']) if row['metadata'] else {}, 'confidence': row['confidence'], 'created': row['created_at']})
    conn.close()

def apply_decay(conf, hours): return conf * math.exp(-DECAY_RATE * hours)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send_json(self, d, s=200):
        self.send_response(s)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())
    def do_GET(self):
        if self.path == '/health': self.send_json({'status': 'healthy', 'service': 'muninndb', 'type': 'working_memory', 'persistent': True})
        elif self.path == '/Activate': self.send_json({'status': 'ok'})
        else: self.send_json({'memories': working_memories[-50:]} if self.path == '/memories' else {'error': 'not found'}, 200 if self.path == '/memories' else 404)
    def do_POST(self):
        l = int(self.headers.get('Content-Length', 0))
        p = json.loads(self.rfile.read(l).decode()) if l else {}
        if '/search' in self.path or '/Activate' in self.path:
            q = p.get('query', '')
            now = datetime.now()
            results = [{'id': m['id'], 'content': m['content'], 'metadata': m.get('metadata', {}), 'confidence': apply_decay(m.get('confidence', 0.5), (now - datetime.fromisoformat(m['created'])).total_seconds() / 3600), 'source': 'muninn_working'} for m in working_memories if q.lower() in m['content'].lower() and apply_decay(m.get('confidence', 0.5), (now - datetime.fromisoformat(m['created'])).total_seconds() / 3600) >= RETRIEVAL_THRESHOLD]
            results.sort(key=lambda x: x['confidence'], reverse=True)
            self.send_json({'status': 'success', 'query': q, 'results': results[:10]})
        elif '/memorize' in self.path:
            c = p.get('content', '')
            if not c: return self.send_json({'error': 'content required'}, 400)
            m = {'id': hashlib.md5(c.encode()).hexdigest()[:8], 'content': c, 'metadata': p.get('metadata', {}), 'confidence': 0.9, 'created': datetime.now().isoformat()}
            working_memories.append(m)
            conn = get_db()
            conn.execute('INSERT OR REPLACE INTO memories (id, content, metadata, confidence, created_at) VALUES (?, ?, ?, ?, ?)', (m['id'], c, json.dumps(m['metadata']), m['confidence'], m['created']))
            conn.commit()
            conn.close()
            self.send_json({'status': 'success', 'id': m['id']})
        else: self.send_json({'error': 'not found'}, 404)

if __name__ == '__main__':
    init_db()
    print(f'MuninnDB HTTP Gateway on :{PORT}')
    HTTPServer(('0.0.0.0', PORT), H).serve_forever()
PYEOF

chmod +x /home/danexall/muninn-http-gateway.py

# Create systemd service for Go binary (internal MCP)
cat > /etc/systemd/system/muninndb.service << 'EOF'
[Unit]
Description=MuninnDB Go Service (MCP)
After=network.target

[Service]
Type=simple
User=danexall
Group=danexall
WorkingDirectory=/home/danexall/muninn
Environment=HOME=/home/danexall
Environment=MUNINNDB_DATA=/home/danexall/muninn/data
ExecStart=/usr/local/bin/muninn start --data /home/danexall/muninn/data
Restart=always
RestartSec=30
LimitNOFILE=65536
MemoryMax=512M
TimeoutStartSec=60

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for HTTP Gateway (port 8097)
cat > /etc/systemd/system/muninn-gateway.service << 'EOF'
[Unit]
Description=MuninnDB HTTP Gateway
After=network.target muninndb.service

[Service]
Type=simple
User=danexall
Group=danexall
WorkingDirectory=/home/danexall
Environment=HOME=/home/danexall
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /home/danexall/muninn-http-gateway.py
Restart=always
RestartSec=10
LimitNOFILE=65536
MemoryMax=256M

[Install]
WantedBy=multi-user.target
EOF

# Enable and start services
systemctl daemon-reload
systemctl enable muninndb muninn-gateway
systemctl restart muninndb
sleep 5
systemctl restart muninn-gateway

sleep 5

echo ""
echo "=== Service Status ==="
echo "Go Binary (MCP):"
systemctl status muninndb --no-pager | head -8
echo ""
echo "HTTP Gateway (8097):"
systemctl status muninn-gateway --no-pager | head -8

echo ""
echo "=== Test HTTP Gateway ==="
curl -s http://localhost:8097/health || echo "Gateway not responding"

echo ""
echo "=== Setup Complete ==="
