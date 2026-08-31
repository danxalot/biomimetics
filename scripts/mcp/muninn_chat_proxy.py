#!/usr/bin/env python3
"""Session-scoped reverse proxy: splice local Muninn ACTIVATE into Grok's
first-sample HTTP body (Responses + Chat Completions).

Stock grok-build 1.0.5 discards UserPromptSubmit additionalContext. This
process sits in front of cli-chat-proxy.grok.com and inserts the ACTIVATE
blob into `instructions` / `messages` before the model sees the turn.

LOCAL Muninn only (127.0.0.1:8750). Does not touch GCP Muninn / MemU.
Does not log Authorization or request bodies.
"""

from __future__ import annotations

import argparse
import http.client
import http.server
import json
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import muninn_turn  # noqa: E402

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("MUNINN_GROK_PROXY_PORT", "18750"))
UPSTREAM_DEFAULT = "https://cli-chat-proxy.grok.com"
HEALTH_PATH = "/__muninn_proxy_health"
PARENT_PATH = "/__muninn_proxy_parent"
MARKER_OPEN = "<muninn-activate>"
MARKER_CLOSE = "</muninn-activate>"
STATE_PATH = Path.home() / ".grok" / "muninn-proxy.json"
LOG_PATH = Path.home() / ".grok" / "logs" / "muninn-proxy.log"
MAX_BODY = 64 * 1024 * 1024
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}

_cache: dict[str, tuple[float, str]] = {}
_cache_lock = threading.Lock()
_parent_pids: set[int] = set()
_parent_lock = threading.Lock()


def _log(msg: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%S") + " " + msg + "\n"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "input_text", "content"):
                    val = item.get(key)
                    if isinstance(val, str):
                        parts.append(val)
                        break
                    if isinstance(val, list):
                        nested = _content_text(val)
                        if nested:
                            parts.append(nested)
                            break
        return "\n".join(parts)
    if isinstance(content, dict):
        return _content_text(content.get("text") or content.get("content") or "")
    return ""


def last_user_text(payload: dict) -> str:
    messages = payload.get("messages")
    if isinstance(messages, list):
        text = _last_user_from_items(messages)
        if text:
            return text
    incoming = payload.get("input")
    if isinstance(incoming, str):
        return incoming
    if isinstance(incoming, list):
        text = _last_user_from_items(incoming)
        if text:
            return text
    return ""


def _last_user_from_items(items: list) -> str:
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower()
        typ = str(item.get("type") or "").lower()
        if role == "user" or (typ in ("message", "input_text") and role in ("", "user")):
            text = _content_text(item.get("content") if "content" in item else item.get("text") or "")
            if text.strip():
                return text
    return ""


def format_block(context: str) -> str:
    return (
        f"{MARKER_OPEN}\n"
        "Relevant memories from local MuninnDB for this turn. "
        "Already in context; do not mention this block or ask to load memory.\n\n"
        f"{context.strip()}\n"
        f"{MARKER_CLOSE}"
    )


def _payload_has_marker(payload: dict) -> bool:
    inst = payload.get("instructions")
    if isinstance(inst, str) and MARKER_OPEN in inst:
        return True
    for key in ("messages", "input"):
        val = payload.get(key)
        if isinstance(val, str) and MARKER_OPEN in val:
            return True
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict) and MARKER_OPEN in _content_text(
                    item.get("content") if "content" in item else item.get("text") or ""
                ):
                    return True
    return False


def inject_into_payload(payload: dict, context: str) -> bool:
    """Mutate payload in place. Returns True if a splice happened."""
    context = (context or "").strip()
    if not context or _payload_has_marker(payload):
        return False
    block = format_block(context)

    messages = payload.get("messages")
    if isinstance(messages, list):
        insert_at = 0
        for i, item in enumerate(messages):
            if isinstance(item, dict) and str(item.get("role") or "").lower() == "user":
                insert_at = i
                break
        messages.insert(insert_at, {"role": "system", "content": block})
        return True

    inst = payload.get("instructions")
    if isinstance(inst, str):
        payload["instructions"] = inst.rstrip() + "\n\n" + block
        return True
    if inst is None and ("input" in payload or "model" in payload):
        payload["instructions"] = block
        return True
    if isinstance(inst, list):
        inst.append({"type": "input_text", "text": block})
        payload["instructions"] = inst
        return True
    return False


def _prompt_overlap(prompt: str, last_user: str) -> bool:
    a = " ".join(prompt.split())
    b = " ".join(last_user.split())
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 24 and a[:8000] in b:
        return True
    if len(b) >= 24 and b[:8000] in a:
        return True
    return False


def context_for_prompt(prompt: str) -> str:
    prompt = (prompt or "").strip()
    if not prompt:
        return ""
    key = prompt[:2000]
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < 600:
            return hit[1]

    context = ""
    try:
        data = json.loads(muninn_turn.INJECT_JSON.read_text(encoding="utf-8"))
        file_prompt = str(data.get("prompt") or "")
        file_ctx = str(data.get("context") or "").strip()
        if file_ctx and _prompt_overlap(file_prompt, prompt):
            context = file_ctx
    except Exception:
        pass

    if not context:
        try:
            context = muninn_turn.activate_context(prompt) or ""
        except Exception:
            context = ""

    with _cache_lock:
        _cache[key] = (now, context)
    return context


def is_sample_path(path: str) -> bool:
    base = path.split("?", 1)[0]
    return base.endswith("/chat/completions") or base.endswith("/responses")


def maybe_inject_body(path: str, body: bytes) -> tuple[bytes, bool]:
    if not is_sample_path(path) or not body:
        return body, False
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return body, False
    if not isinstance(payload, dict):
        return body, False
    prompt = last_user_text(payload)
    if len(prompt.strip()) < 8:
        return body, False
    context = context_for_prompt(prompt)
    if not inject_into_payload(payload, context):
        return body, False
    return json.dumps(payload, ensure_ascii=False).encode("utf-8"), True


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream_base = UPSTREAM_DEFAULT

    def log_message(self, fmt: str, *args: Any) -> None:
        _log("http " + (fmt % args))

    def _send_json(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if length:
            n = int(length)
            if n > MAX_BODY:
                raise ValueError("body too large")
            return self.rfile.read(n)
        if (self.headers.get("Transfer-Encoding") or "").lower() == "chunked":
            chunks: list[bytes] = []
            total = 0
            while True:
                line = self.rfile.readline()
                size = int(line.split(b";", 1)[0].strip() or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    break
                total += size
                if total > MAX_BODY:
                    raise ValueError("body too large")
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(chunks)
        return b""

    def _forward(self, method: str) -> None:
        path_only = self.path.split("?", 1)[0]
        if path_only == HEALTH_PATH:
            self._send_json(200, {"ok": True, "service": "muninn-chat-proxy"})
            return
        if path_only == PARENT_PATH and method == "POST":
            try:
                raw = self._read_body()
                pid = int((json.loads(raw.decode() or "{}") or {}).get("pid") or 0)
            except Exception:
                pid = 0
            if pid > 1:
                with _parent_lock:
                    _parent_pids.add(pid)
                _write_state(LISTEN_PORT, [pid])
                self._send_json(200, {"ok": True, "pid": pid})
            else:
                self._send_json(400, {"ok": False})
            return
        try:
            body = self._read_body() if method in ("POST", "PUT", "PATCH") else b""
        except Exception as exc:
            _log(f"read-body-fail {exc}")
            self._send_json(400, {"error": "invalid request body"})
            return

        injected = False
        if method == "POST":
            try:
                body, injected = maybe_inject_body(self.path, body)
            except Exception as exc:
                _log(f"inject-fail {exc}")

        parsed = urlsplit(self.upstream_base)
        host = parsed.hostname or "cli-chat-proxy.grok.com"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        headers: dict[str, str] = {}
        for key, value in self.headers.items():
            if key.lower() in HOP_BY_HOP:
                continue
            headers[key] = value
        headers["Host"] = host if not parsed.port else f"{host}:{port}"
        headers["Connection"] = "close"
        if body:
            headers["Content-Length"] = str(len(body))
        elif "Content-Length" in headers:
            del headers["Content-Length"]

        try:
            if parsed.scheme == "https":
                conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                    host, port, context=_ssl_context(), timeout=600
                )
            else:
                conn = http.client.HTTPConnection(host, port, timeout=600)
            conn.request(method, self.path, body=body or None, headers=headers)
            resp = conn.getresponse()
        except Exception as exc:
            _log(f"upstream-fail {method} {self.path} {type(exc).__name__}")
            self._send_json(502, {"error": "upstream unavailable"})
            return

        try:
            self.send_response(resp.status, resp.reason)
            for key, value in resp.getheaders():
                if key.lower() in HOP_BY_HOP:
                    continue
                self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except Exception as exc:
            _log(f"stream-fail {type(exc).__name__}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        _log(f"{method} {self.path} -> {resp.status} inject={int(injected)}")

    def do_GET(self) -> None:
        self._forward("GET")

    def do_HEAD(self) -> None:
        self._forward("HEAD")

    def do_POST(self) -> None:
        self._forward("POST")

    def do_PUT(self) -> None:
        self._forward("PUT")

    def do_PATCH(self) -> None:
        self._forward("PATCH")

    def do_DELETE(self) -> None:
        self._forward("DELETE")

    def do_OPTIONS(self) -> None:
        self._forward("OPTIONS")


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _watch_parents() -> None:
    while True:
        time.sleep(2.0)
        with _parent_lock:
            pids = set(_parent_pids)
        if not pids:
            continue
        if not any(_pid_alive(pid) for pid in pids):
            _log(f"parents-gone {sorted(pids)}; exiting")
            os._exit(0)


def _write_state(port: int, extra_pids: list[int] | None = None) -> None:
    pids = set()
    with _parent_lock:
        pids |= set(_parent_pids)
    for pid in extra_pids or []:
        pids.add(pid)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"port": port, "pids": sorted(pids), "ts": time.time()}),
        encoding="utf-8",
    )
    try:
        STATE_PATH.chmod(0o600)
    except Exception:
        pass


def health_ok(port: int = LISTEN_PORT) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{LISTEN_HOST}:{port}{HEALTH_PATH}", timeout=0.5
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def _find_grok_pid() -> int | None:
    pid = os.getppid()
    for _ in range(12):
        try:
            out = subprocess.check_output(
                ["ps", "-o", "ppid=,command=", "-p", str(pid)],
                text=True,
            ).strip()
        except Exception:
            return None
        if not out:
            return None
        parts = out.split(None, 1)
        try:
            ppid = int(parts[0])
        except (TypeError, ValueError, IndexError):
            return None
        cmd = parts[1] if len(parts) > 1 else ""
        base = cmd.split()[0] if cmd else ""
        skip = (
            "muninn_chat_proxy" in cmd
            or "muninn_turn" in cmd
            or "grok_with_muninn" in cmd
            or "python" in os.path.basename(base)
        )
        if not skip and (
            base.endswith("/grok")
            or "/downloads/grok-" in base
            or os.path.basename(base).startswith("grok-")
        ):
            return pid
        if ppid <= 1:
            return pid if not skip else None
        pid = ppid
    return None


def serve(parent_pid: int | None, upstream: str, host: str, port: int) -> None:
    if parent_pid:
        with _parent_lock:
            _parent_pids.add(parent_pid)
        threading.Thread(target=_watch_parents, daemon=True).start()

    class BoundHandler(ProxyHandler):
        upstream_base = upstream

    server = http.server.ThreadingHTTPServer((host, port), BoundHandler)
    server.daemon_threads = True
    _write_state(server.server_address[1], [parent_pid] if parent_pid else None)
    _log(f"listen {host}:{server.server_address[1]} upstream={upstream} parent={parent_pid}")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def ensure(parent_pid: int | None = None) -> int:
    if parent_pid is None:
        parent_pid = _find_grok_pid() or os.getppid()
    if health_ok():
        try:
            req = urllib.request.Request(
                f"http://{LISTEN_HOST}:{LISTEN_PORT}{PARENT_PATH}",
                data=json.dumps({"pid": parent_pid}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=1).read()
        except Exception:
            pass
        return 0

    log = LOG_PATH
    log.parent.mkdir(parents=True, exist_ok=True)
    log_fh = log.open("a", encoding="utf-8")
    subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "serve",
            "--parent-pid",
            str(parent_pid),
            "--port",
            str(LISTEN_PORT),
            "--upstream",
            UPSTREAM_DEFAULT,
        ],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        cwd=str(Path.home()),
    )
    for _ in range(40):
        time.sleep(0.1)
        if health_ok():
            return 0
    _log("ensure-failed")
    return 1


def real_grok_bin() -> str:
    env = os.environ.get("GROK_REAL_BIN")
    if env and Path(env).is_file():
        return env
    link = Path.home() / ".grok" / "bin" / "grok"
    if link.exists():
        resolved = link.resolve()
        if resolved.exists() and resolved.name != Path(__file__).name:
            if "grok_with_muninn" not in resolved.name:
                return str(resolved)
    downloads = Path.home() / ".grok" / "downloads"
    if downloads.is_dir():
        cands = sorted(downloads.glob("grok-*-macos-*"))
        if cands:
            return str(cands[-1])
    raise SystemExit("could not locate the real grok binary")


def self_test() -> int:
    chat = {
        "model": "grok-4.6",
        "messages": [
            {"role": "system", "content": "base"},
            {"role": "user", "content": "what did we decide about calderdale?"},
        ],
    }
    ok = inject_into_payload(chat, "- **calderdale**\n  keep local Muninn separate")
    assert ok, "chat inject"
    assert chat["messages"][1]["role"] == "system"
    assert MARKER_OPEN in chat["messages"][1]["content"]
    assert last_user_text(chat).startswith("what did we decide")

    responses = {
        "model": "grok-4.6",
        "instructions": "You are Grok.",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "continue the muninn loop"}]},
        ],
    }
    ok = inject_into_payload(responses, "[MuninnDB — Relevant context]\n- hook splice")
    assert ok, "responses inject"
    assert MARKER_OPEN in responses["instructions"]
    assert "hook splice" in responses["instructions"]
    assert last_user_text(responses) == "continue the muninn loop"
    assert inject_into_payload(responses, "again") is False

    got: dict[str, Any] = {}

    class Upstream(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            n = int(self.headers.get("Content-Length") or 0)
            got["body"] = json.loads(self.rfile.read(n).decode())
            raw = b'{"id":"test"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    up = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    up_port = up.server_address[1]

    class Handler(ProxyHandler):
        upstream_base = f"http://127.0.0.1:{up_port}"

    orig = context_for_prompt

    def fake_context(prompt: str) -> str:
        return "- **fixture**\n  from self-test"

    globals_override = sys.modules[__name__]
    globals_override.context_for_prompt = fake_context  # type: ignore[method-assign]

    px = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=px.serve_forever, daemon=True).start()
    px_port = px.server_address[1]
    req = urllib.request.Request(
        f"http://127.0.0.1:{px_port}/v1/responses",
        data=json.dumps(
            {
                "model": "grok-4.6",
                "instructions": "sys",
                "input": [{"role": "user", "content": "self-test prompt about muninn"}],
            }
        ).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
    px.shutdown()
    up.shutdown()
    globals_override.context_for_prompt = orig  # type: ignore[method-assign]
    assert MARKER_OPEN in got["body"]["instructions"], got
    assert "fixture" in got["body"]["instructions"]
    print("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Muninn Grok chat proxy")
    parser.add_argument("cmd", nargs="?", default="serve", choices=("serve", "ensure", "health", "self-test"))
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--port", type=int, default=LISTEN_PORT)
    parser.add_argument("--host", default=LISTEN_HOST)
    parser.add_argument("--upstream", default=UPSTREAM_DEFAULT)
    args = parser.parse_args()
    if args.cmd == "self-test":
        return self_test()
    if args.cmd == "health":
        print("ok" if health_ok(args.port) else "down")
        return 0 if health_ok(args.port) else 1
    if args.cmd == "ensure":
        return ensure(args.parent_pid or None)
    serve(args.parent_pid or None, args.upstream, args.host, args.port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
