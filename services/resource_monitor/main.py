from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import docker
import requests_unixsocket
import psutil
import json
import asyncio
import logging
import time
import logging
import time
from datetime import datetime
import requests
from fastapi.responses import RedirectResponse, FileResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

app.mount("/monitor", StaticFiles(directory="static", html=True), name="static")

client = None
# previous counters for rate calculations
_prev_system = {
    "ts": None,
    "net_bytes_sent": None,
    "net_bytes_recv": None,
    "disk_read_bytes": None,
    "disk_write_bytes": None,
}

# store previous per-container network/blkio counters by id
_prev_container = {}

def get_docker_client():
    """Return a docker client. Try APIClient over unix socket first, then DockerClient.from_env()."""
    global client
    if client is not None:
        return client

    import os
    import os
    # Try explicit socket path first as it's most reliable in this container setup
    if os.path.exists("/var/run/docker.sock"):
        try:
            client = docker.APIClient(base_url="unix:///var/run/docker.sock")
            # Quick check
            _ = client.version()
            return client
        except Exception as e:
            logging.debug(f"Docker socket explicit init failed: {e}")
            
    try:
        # Fallback to env
        client = docker.from_env()
        return client
    except Exception as e:
        logging.debug(f"Docker env init failed: {e}")
        client = None
        return None

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_system_metrics():
    """Get current system metrics (non-blocking)"""
    import asyncio
    return await asyncio.to_thread(_get_system_metrics_sync)

def _get_system_metrics_sync():
    # CPU sample (blocking for 1s to get a meaningful percent)
    cpu = psutil.cpu_percent(interval=1)
    vm = psutil.virtual_memory()

    # network counters (bytes)
    net = psutil.net_io_counters()
    disk = psutil.disk_io_counters()
    now = time.time()

    # calculate rates (bytes/sec) using previous snapshot
    net_sent_rate = None
    net_recv_rate = None
    disk_read_rate = None
    disk_write_rate = None

    if _prev_system["ts"] is not None:
        dt = max(0.001, now - _prev_system["ts"])
        try:
            net_sent_rate = (net.bytes_sent - (_prev_system["net_bytes_sent"] or 0)) / dt
            net_recv_rate = (net.bytes_recv - (_prev_system["net_bytes_recv"] or 0)) / dt
            disk_read_rate = (disk.read_bytes - (_prev_system["disk_read_bytes"] or 0)) / dt
            disk_write_rate = (disk.write_bytes - (_prev_system["disk_write_bytes"] or 0)) / dt
        except Exception:
            net_sent_rate = net_recv_rate = disk_read_rate = disk_write_rate = None

    # update snapshot
    _prev_system["ts"] = now
    _prev_system["net_bytes_sent"] = net.bytes_sent
    _prev_system["net_bytes_recv"] = net.bytes_recv
    _prev_system["disk_read_bytes"] = getattr(disk, "read_bytes", 0)
    _prev_system["disk_write_bytes"] = getattr(disk, "write_bytes", 0)

    return {
        "timestamp": datetime.now().isoformat(),
        "cpu_percent": cpu,
        "memory_percent": vm.percent,
        "memory_available": vm.available / (1024 * 1024 * 1024),  # GB
        "memory_total": vm.total / (1024 * 1024 * 1024),  # GB
        "net_bytes_sent_per_sec": net_sent_rate,
        "net_bytes_recv_per_sec": net_recv_rate,
        "disk_read_bytes_per_sec": disk_read_rate,
        "disk_write_bytes_per_sec": disk_write_rate,
    }

async def get_all_container_metrics():
    """Get metrics for ALL containers"""
    metrics_list = []
    
    # Try docker helper HTTP API first
    try:
        helper_url = 'http://docker_helper:8082'
        r = requests.get(f"{helper_url}/containers?all=1", timeout=1)
        if r.status_code == 200:
            containers = r.json()
            for target in containers:
                try:
                    cid = target.get('Id')
                    if not cid: continue
                    
                    cont_id = cid[:12]
                    status = target.get('State', 'unknown')
                    name = (target.get('Names') or ['unknown'])[0].lstrip('/')

                    stats_r = requests.get(f"{helper_url}/containers/{cid}/stats", timeout=1)
                    if stats_r.status_code == 200:
                        stats = stats_r.json()
                        metrics = _process_stats(stats, cont_id, name, status)
                        metrics_list.append(metrics)
                except Exception:
                    continue
            
            if metrics_list:
                return metrics_list
    except Exception:
        pass

    # Fallback: Try docker-py client
    c = get_docker_client()
    if c is not None:
        try:
            if hasattr(c, 'containers'):
                # High-level
                for container in c.containers.list(all=True):
                    try:
                        stats = container.stats(stream=False)
                        metrics = _process_stats(stats, container.id[:12], container.name, container.status)
                        metrics_list.append(metrics)
                    except Exception:
                        pass
            else:
                # APIClient
                for cont in c.containers(all=True):
                    try:
                        cid = cont.get('Id')
                        cont_id = cid[:12]
                        status = cont.get('State', 'unknown')
                        name = (cont.get('Names') or ['unknown'])[0].lstrip('/')
                        stats = c.stats(cid, stream=False)
                        if isinstance(stats, bytes): stats = json.loads(stats)
                        
                        metrics = _process_stats(stats, cont_id, name, status)
                        metrics_list.append(metrics)
                    except Exception:
                        pass
            return metrics_list
        except Exception as e:
            logging.error(f"Docker client fallback failed: {e}")

    # Final Fallback: use curl with --unix-socket (robust)
    if not metrics_list:
        try:
            import subprocess
            # list containers
            out = subprocess.check_output([
                'curl', '--silent', '--unix-socket', '/var/run/docker.sock',
                'http://localhost/containers/json?all=1'
            ], text=True, timeout=2)
            containers = json.loads(out)
            
            for target in containers:
                try:
                    cid = target.get('Id')
                    if not cid: continue
                    cont_id = cid[:12]
                    status = target.get('State', 'unknown')
                    name = (target.get('Names') or ['unknown'])[0].lstrip('/')
                    
                    # Fetch stats
                    out = subprocess.check_output([
                        'curl', '--silent', '--unix-socket', '/var/run/docker.sock',
                        f'http://localhost/containers/{cid}/stats?stream=false'
                    ], text=True, timeout=2)
                    stats = json.loads(out)
                    
                    metrics = _process_stats(stats, cont_id, name, status)
                    metrics_list.append(metrics)
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"Curl fallback failed: {e}")
             
    return metrics_list

def _process_stats(stats, cont_id, name, status):
    """Helper to process raw docker stats into metrics dict"""
    try:
        # CPU
        cpu_usage = stats["cpu_stats"]["cpu_usage"]["total_usage"]
        precpu_usage = stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
        system_cpu = stats["cpu_stats"].get("system_cpu_usage", 0)
        system_precpu = stats.get("precpu_stats", {}).get("system_cpu_usage", 0)
        
        cpu_delta = cpu_usage - precpu_usage
        system_delta = system_cpu - system_precpu
        
        cpu_percent = 0.0
        if system_delta > 0 and cpu_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * 100.0 * psutil.cpu_count()

        # Memory
        memory_usage = stats.get("memory_stats", {}).get("usage", 0) / (1024**3)
        memory_limit = stats.get("memory_stats", {}).get("limit", 1) / (1024**3)
        memory_percent = (memory_usage / memory_limit) * 100 if memory_limit else 0.0

        # Network
        net_rx = 0
        net_tx = 0
        for v in (stats.get('networks') or {}).values():
            net_rx += v.get('rx_bytes', 0)
            net_tx += v.get('tx_bytes', 0)
            
        # Block IO
        blk_read = 0
        blk_write = 0
        for entry in stats.get('blkio_stats', {}).get('io_service_bytes_recursive', []) or []:
            op = entry.get('op', '').lower()
            if op == 'read': blk_read += entry.get('value', 0)
            elif op == 'write': blk_write += entry.get('value', 0)

        # Rates
        now = time.time()
        prev = _prev_container.get(cont_id, {})
        net_rx_rate = 0.0
        net_tx_rate = 0.0
        blk_read_rate = 0.0
        blk_write_rate = 0.0
        
        if prev.get('ts') and (now - prev['ts']) < 5.0:
            dt = max(0.001, now - prev['ts'])
            net_rx_rate = (net_rx - prev.get('net_rx', 0)) / dt
            net_tx_rate = (net_tx - prev.get('net_tx', 0)) / dt
            blk_read_rate = (blk_read - prev.get('blk_read', 0)) / dt
            blk_write_rate = (blk_write - prev.get('blk_write', 0)) / dt

        _prev_container[cont_id] = {
            'ts': now, 'net_rx': net_rx, 'net_tx': net_tx,
            'blk_read': blk_read, 'blk_write': blk_write
        }

        return {
            "container_id": cont_id,
            "name": name,
            "status": status,
            "cpu_percent": cpu_percent,
            "memory_usage_gb": memory_usage,
            "memory_limit_gb": memory_limit,
            "memory_percent": memory_percent,
            "net": {"rx_bytes_per_sec": net_rx_rate, "tx_bytes_per_sec": net_tx_rate},
            "io": {"read_bytes_per_sec": blk_read_rate, "write_bytes_per_sec": blk_write_rate}
        }
    except Exception as e:
        return {"container_id": cont_id, "name": name, "status": status, "error": str(e)}


@app.get("/logs")
async def get_container_logs(lines: int = 200):
    """Return the last N log lines for the qwen_server container using curl + unix-socket."""
    try:
        # try docker_helper service first
        try:
            helper_url = 'http://docker_helper:8082'
            # find by listing
            hr = requests.get(f"{helper_url}/containers?all=1", timeout=2)
            if hr.status_code == 200:
                conts = hr.json()
                target = None
                for c in conts:
                    if any('qwen_server' in n for n in (c.get('Names') or [])):
                        target = c
                        break
                if not target:
                    return {"error": "qwen_server container not found"}
                cid = target.get('Id')
                lr = requests.get(f"{helper_url}/containers/{cid}/logs?tail={lines}", timeout=5)
                if lr.status_code == 200:
                    return {"container_id": cid[:12], "logs": lr.text}
                else:
                    logging.error(f"docker_helper logs returned {lr.status_code}")
            else:
                logging.debug(f"docker_helper containers list failed: {hr.status_code}")
        except Exception as e:
            logging.debug(f"docker_helper logs fetch failed: {e}")

        # fallback to curl unix-socket if helper isn't available
        import subprocess
        # find container id via curl
        out = subprocess.check_output([
            'curl', '--silent', '--unix-socket', '/var/run/docker.sock',
            'http://localhost/containers/json?all=1'
        ], text=True, timeout=3)
        conts = json.loads(out)
        target = None
        for c in conts:
            if any('qwen_server' in n for n in (c.get('Names') or [])):
                target = c
                break
        if not target:
            return {"error": "qwen_server container not found"}

        cid = target.get('Id')
        logs = subprocess.check_output([
            'curl', '--silent', '--unix-socket', '/var/run/docker.sock',
            f'http://localhost/containers/{cid}/logs?stdout=1&stderr=1&tail={lines}'
        ], text=True, timeout=5)

        return {"container_id": cid[:12], "logs": logs}
    except Exception as e:
        logging.error(f"Failed to fetch container logs: {e}")
        return {"error": str(e)}

@app.get("/metrics")
async def get_metrics():
    """One-shot metrics endpoint"""
    system = await get_system_metrics()
    containers = await get_all_container_metrics()
    
    return {
        "system": system,
        "containers": containers
    }

@app.get("/history")
async def get_history():
    """Aggregate historical metrics from shared storage for the graph"""
    import asyncio
    return await asyncio.to_thread(_get_history_sync)

def _get_history_sync():
    import os
    import json
    from pathlib import Path
    
    data_points = []
    # Telemetry path from telemetry_cleaner.py
    telemetry_dir = Path("/app/shared_storage/tmp_dev_records/telemetry")
    
    if telemetry_dir.exists():
        try:
            # List all json files
            files = sorted(telemetry_dir.glob("*.json"))
            # Limit to last 200 points (approx 100 mins at 30s interval) to prevent timeouts
            for f in files[-200:]:
                try:
                    with open(f, 'r') as fd:
                        record = json.load(fd)
                        # Extract key metrics
                        ts = record.get("timestamp")
                        # Support legacy format (just system) and new format (system + containers)
                        sys_cpu = record.get("system", {}).get("cpu_percent")
                        sys_mem = record.get("system", {}).get("memory_percent")
                        
                        containers = record.get("containers", [])
                        
                        if ts and sys_cpu is not None:
                            point = {
                                "timestamp": ts,
                                "cpu": sys_cpu,
                                "memory": sys_mem,
                                "containers": []
                            }
                            # Extract minimal container data for graph
                            for c in containers:
                                point["containers"].append({
                                    "name": c.get("name"),
                                    "cpu": c.get("cpu_percent", 0),
                                    "memory": c.get("memory_percent", 0)
                                })
                            data_points.append(point)
                except Exception:
                    continue
        except Exception as e:
            logging.error(f"Failed to read history: {e}")
            
    return {"history": data_points}


@app.get("/")
async def root_redirect():
    """Redirect root to the mounted static UI at /monitor/"""
    return RedirectResponse(url="/monitor/")


@app.head("/")
async def root_head_redirect():
    """Respond to HEAD on root with a redirect (no body)."""
    return RedirectResponse(url="/monitor/")

@app.get("/ws-test")
async def ws_test_page():
    """Serve a minimal WebSocket diagnostics page to test /ws/metrics from a browser."""
    return FileResponse("static/ws-test.html")

@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    """Streaming metrics endpoint"""
    await websocket.accept()
    
    try:
        while True:
            system = await get_system_metrics()
            containers = await get_all_container_metrics()
            
            await websocket.send_json({
                "system": system,
                "containers": containers
            })
            
            await asyncio.sleep(1)  # Update every second
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()

@app.on_event("startup")
async def startup_event():
    """Start background tasks on startup"""
    asyncio.create_task(run_telemetry_cleaner_task())
    asyncio.create_task(run_telemetry_writer_task())

async def run_telemetry_cleaner_task():
    """Background task for 72h telemetry retention"""
    import asyncio
    from telemetry_cleaner import cleanup_telemetry
    
    logger.info("Telemetry Cleaner: Starting background service (72h retention)")
    while True:
        try:
            # Run in thread pool to avoid blocking event loop
            await asyncio.to_thread(cleanup_telemetry)
        except Exception as e:
            logger.error(f"Telemetry Cleaner: Error: {e}")
        
        # Run every hour
        await asyncio.sleep(3600)

async def run_telemetry_writer_task():
    """Background task to persist FULL telemetry (system + containers) for history graph"""
    import json
    import time
    from pathlib import Path
    
    # Ensure dir exists
    telemetry_dir = Path("/app/shared_storage/tmp_dev_records/telemetry")
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Telemetry Writer: Starting background service (30s interval)")
    
    while True:
        try:
            # Re-use existing async functions to get full data
            # These functions are already defined in this file
            system_metrics = await get_system_metrics()
            container_metrics = await get_all_container_metrics()
            
            data = {
                "timestamp": datetime.now().isoformat(),
                "system": system_metrics,
                "containers": container_metrics
            }
            
            # Write file
            fname = f"telemetry_{int(time.time())}.json"
            # Write in thread pool
            await asyncio.to_thread(_write_telemetry_file, telemetry_dir / fname, data)
                
        except Exception as e:
            logger.error(f"Telemetry Writer error: {e}")
            
        await asyncio.sleep(30)

def _write_telemetry_file(path, data):
    import json
    with open(path, 'w') as f:
        json.dump(data, f)

if __name__ == "__main__":
    import os
    import uvicorn
    
    # Tasks are started in startup_event
    port = int(os.getenv("PORT", "9090"))
    uvicorn.run(app, host="0.0.0.0", port=port)