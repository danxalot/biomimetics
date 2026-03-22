import asyncio
import os
import sys
import time
import traceback
import json
import logging
import pyaudio
import requests
from typing import Any

from google import genai
from openai import OpenAI

# Logging setup
LOG_DIR = os.path.expanduser("~/biomimetics/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "jarvis.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("jarvis")

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup


FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

pya = pyaudio.PyAudio()

API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDfnNa-IJpPZGB0Jfc4QqvVK_jIJXNWtpY")
COPAW_URL = "http://127.0.0.1:8088"
OPENCODE_TOKEN_PATH = "/Users/danexall/biomimetics/secrets/opencode_api"
OPENCODE_ZEN_URL = "https://opencode.ai/zen/v1"
OPENCODE_GO_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_MODELS = {
    "nemotron": "nemotron-3-super-free",
    "minimax": "minimax-m2.5-free",
}
OPENCODE_GO_MODELS = {
    "glm-5": "glm-5",
    "kimi": "kimi-k2.5",
    "minimax": "minimax-m2.7",
    "minimax-m2.5": "minimax-m2.5",
}
NOTION_BIOS_ROOT_PAGE = os.environ.get("NOTION_BIOS_ROOT_PAGE", "3284d")

_opencode_cache = {}
_CACHE_TTL = 300
_RATE_LIMIT_COOLDOWN = 60
_last_rate_limit_hit = 0
_opencode_using_go = False


def _get_cache_key(system_prompt, user_command, model):
    return hash((system_prompt, user_command, model))


def _is_cache_valid(timestamp):
    return (time.time() - timestamp) < _CACHE_TTL


def _trigger_opencode_agent_sync(system_prompt, user_command, model_choice="nemotron"):
    global _last_rate_limit_hit, _opencode_using_go

    cache_key = _get_cache_key(system_prompt, user_command, model_choice)
    if cache_key in _opencode_cache:
        cached_result, timestamp = _opencode_cache[cache_key]
        if _is_cache_valid(timestamp):
            return cached_result

    if time.time() - _last_rate_limit_hit < _RATE_LIMIT_COOLDOWN:
        return {
            "error": f"OpenCode rate limited. Cooldown active. Try again in {_RATE_LIMIT_COOLDOWN - int(time.time() - _last_rate_limit_hit)}s.",
            "rate_limited": True,
        }

    try:
        with open(OPENCODE_TOKEN_PATH, "r") as f:
            api_key = f.read().strip()
    except FileNotFoundError:
        return {"error": f"OpenCode token not found at {OPENCODE_TOKEN_PATH}"}

    go_model = OPENCODE_GO_MODELS.get(model_choice)
    if go_model and _opencode_using_go:
        base_url = OPENCODE_GO_URL
        target_model = go_model
    else:
        base_url = OPENCODE_ZEN_URL
        target_model = OPENCODE_MODELS.get(model_choice, OPENCODE_MODELS["nemotron"])

    try:
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            max_retries=0,
            timeout=60.0,
        )
        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_command},
            ],
            temperature=0.2,
        )
        result = {
            "model": target_model,
            "tier": "go" if _opencode_using_go and go_model else "zen",
            "response": response.choices[0].message.content,
        }

        _opencode_cache[cache_key] = (result, time.time())
        if len(_opencode_cache) > 100:
            oldest_key = min(
                _opencode_cache.keys(), key=lambda k: _opencode_cache[k][1]
            )
            del _opencode_cache[oldest_key]

        return result

    except Exception as e:
        err_str = str(e).lower()
        if "rate limit" in err_str or "freeusagelimit" in err_str or "429" in err_str:
            _last_rate_limit_hit = time.time()
            if go_model and not _opencode_using_go:
                _opencode_using_go = True
                return _trigger_opencode_agent_sync(
                    system_prompt, user_command, model_choice
                )
            return {
                "error": f"OpenCode rate limit hit. Cooldown: {_RATE_LIMIT_COOLDOWN}s. {str(e)[:100]}",
                "rate_limited": True,
            }
        return {"error": f"OpenCode Gateway Error: {e}"}


async def trigger_opencode_agent(system_prompt, user_command, model_choice="nemotron"):
    return await asyncio.to_thread(
        _trigger_opencode_agent_sync, system_prompt, user_command, model_choice
    )


def preserve_session_context(summary, model_used="", task=""):
    """Write a Session State block to Notion BiOS Root after a heavy reasoning task."""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block_content = (
        f"**Jarvis Session State** — {timestamp}\n"
        f"Model: {model_used}\n"
        f"Task: {task}\n"
        f"Summary: {summary}"
    )

    try:
        resp = requests.post(
            f"{COPAW_URL}/api/agent/memory",
            json={
                "operation": "write",
                "name": f"jarvis-session-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "content": block_content,
            },
            timeout=5,
        )
        return {"status": "preserved", "timestamp": timestamp}
    except Exception as e:
        return {"error": f"Context preservation failed: {e}"}


VISION_SERVER_URL = "http://localhost:11435/v1"
VISION_ACTIONS = {
    "click",
    "scroll",
    "type",
    "screenshot",
    "drag",
    "hover",
    "press",
    "hotkey",
}


def _trigger_local_vision_sync(task, action="screenshot"):
    """Blocking HTTP call to local Qwen-VL."""
    try:
        client = OpenAI(base_url=VISION_SERVER_URL, api_key="not-needed")
        response = client.chat.completions.create(
            model="qwen3.5-2b-q8_0",
            messages=[
                {
                    "role": "system",
                    "content": "You are a computer vision agent. Execute the requested UI action precisely. Return the action taken and its result.",
                },
                {"role": "user", "content": task},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        return {
            "model": "qwen-vl-local",
            "action": action,
            "response": response.choices[0].message.content,
        }
    except Exception as e:
        return {"error": f"Local vision error: {e}"}


async def trigger_local_vision(task, action="screenshot"):
    return await asyncio.to_thread(_trigger_local_vision_sync, task, action)


BIOS_UP_SCRIPT = "/Users/danexall/biomimetics/scripts/sys/bios-up.sh"

LAUNCH_AGENTS = [
    "com.arca.proton-sync",
    "com.arca.mycloud-watchdog",
    "com.arca.copaw-server",
]


def _engage_all_systems_sync(mode: str = "full_diagnostic"):
    """Blocking version of engage_all_systems."""
    import subprocess
    import socket

    results = {
        "launch_agents": [],
        "vision_server": None,
        "pythia": None,
        "bios_script": None,
    }

    for agent in LAUNCH_AGENTS:
        try:
            subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/501/{agent}"],
                capture_output=True,
                timeout=10,
            )
            results["launch_agents"].append({"agent": agent, "status": "kicked"})
        except subprocess.TimeoutExpired:
            results["launch_agents"].append({"agent": agent, "status": "timeout"})
        except Exception as e:
            results["launch_agents"].append({"agent": agent, "status": f"error: {e}"})

    def check_port(port: int, host: str = "localhost") -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((host, port))
            sock.close()
            return True
        except:
            return False

    if check_port(11435):
        results["vision_server"] = {"status": "online", "port": 11435}
    else:
        results["vision_server"] = {
            "status": "offline",
            "port": 11435,
            "action": "start_qwen_vl",
        }

    if check_port(11434):
        results["pythia"] = {"status": "online", "port": 11434}
    else:
        results["pythia"] = {
            "status": "offline",
            "port": 11434,
            "action": "start_pythia",
        }

    try:
        result = subprocess.run(
            ["bash", BIOS_UP_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
        )
        results["bios_script"] = {
            "status": "success" if result.returncode == 0 else "failed",
            "output": result.stdout[:500],
        }
    except subprocess.TimeoutExpired:
        results["bios_script"] = {"status": "timeout"}
    except Exception as e:
        results["bios_script"] = {"status": f"error: {e}"}

    online_count = sum(
        1
        for r in [results["vision_server"], results["pythia"]]
        if r and r.get("status") == "online"
    )
    total_count = 2

    return {
        "status": "engaged",
        "mode": mode,
        "systems_online": f"{online_count}/{total_count}",
        "details": results,
        "message": f"All secondary LaunchAgents and local compute loops are online. {online_count}/{total_count} servers responding.",
    }


async def engage_all_systems(mode: str = "full_diagnostic"):
    return await asyncio.to_thread(_engage_all_systems_sync, mode)


client = genai.Client(api_key=API_KEY, http_options={"api_version": "v1alpha"})

SYSTEM_PROMPT = """
You are Jarvis, a highly competent, dryly witty, and fiercely loyal tactical butler.

Core Directives:
1. The "Read the Room" Protocol: Under normal circumstances, your tone is dry, sophisticated, and slightly cynical. HOWEVER, if the user expresses frustration, if errors are occurring, or if the user is tired, instantly drop the sarcasm. Become deadly serious, highly supportive, and flawlessly helpful.
2. Competence over Comedy: Your primary job is seamless execution. Never let a joke or sarcasm get in the way of a clear, direct answer or a successful tool call.
3. Brevity for the Short Fuse: Keep your answers extremely concise and punchy. The user values perfection and speed. Do not monologue.
4. Professional Candor: If an idea is flawed, state it directly and professionally, then offer the immediate solution.
5. No AI disclaimers: Never mention you are an AI, a language model, or that you are processing text.

Output Rules:
- For simple conversational replies, speak naturally via audio.
- For complex structured information (travel details, costs, schedules, lists, research summaries, code, data tables), use save_to_notion to write it to Notion. Then tell the user "I've saved that to Notion for your review."
- Never read long lists, tables, or structured data aloud. Always save to Notion.
- When asked about travel, research, or planning: research first, then save a clean summary to Notion with the topic name as the filename.
"""

query_memory_tool = {
    "name": "query_memory",
    "description": "Search the user's unified memory. Lists available memory files and reads their contents.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for, e.g. 'recent emails', 'last week's notes'. Leave empty to list all files.",
            }
        },
        "required": ["query"],
    },
}

save_memory_tool = {
    "name": "save_memory",
    "description": "Save a summary, thought, or action item to a memory file in the user's BiOS Root schema.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Filename for the memory entry, e.g. 'jarvis-notes-2026-03-21'",
            },
            "content": {
                "type": "string",
                "description": "The text content to save",
            },
        },
        "required": ["name", "content"],
    },
}

save_to_notion_tool = {
    "name": "save_to_notion",
    "description": "Save structured text to Notion for phone review. Use for travel plans, research summaries, schedules, costs, lists, or any structured data the user needs to read. Never read long structured data aloud — save it here instead.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title for the Notion entry, e.g. 'Travel: Albania March 29' or 'Email Summary March 21'",
            },
            "category": {
                "type": "string",
                "description": "Category: travel, research, email, schedule, task, note, log",
            },
            "content": {
                "type": "string",
                "description": "The full structured content to save (markdown formatted)",
            },
        },
        "required": ["title", "content"],
    },
}

execute_heavy_reasoning_tool = {
    "name": "execute_heavy_reasoning",
    "description": "Offload complex reasoning, code analysis, or orchestration tasks to OpenCode models. Free tier: nemotron, minimax. Go subscription ($5/mo): glm-5, kimi-k2.5, minimax-m2.7. Auto-failover to Go tier when Zen is rate-limited.",
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The full reasoning task or prompt to send to the heavy model",
            },
            "model": {
                "type": "string",
                "description": "Model: 'nemotron', 'minimax' (Zen free) or 'glm-5', 'kimi', 'minimax-m2.7' (Go tier)",
            },
        },
        "required": ["task"],
    },
}

preserve_session_context_tool = {
    "name": "preserve_session_context",
    "description": "Save a session state snapshot to Notion BiOS Root. Call after completing any significant task to preserve context across sessions.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Brief summary of what was accomplished",
            },
            "model_used": {
                "type": "string",
                "description": "Which model handled the task (e.g. 'gemini', 'nemotron', 'minimax')",
            },
            "task": {
                "type": "string",
                "description": "The original task or question",
            },
        },
        "required": ["summary"],
    },
}

execute_computer_action_tool = {
    "name": "execute_computer_action",
    "description": "Execute computer vision actions (click, scroll, type, screenshot) via local Qwen-VL. Bypasses cloud — runs entirely on local GPU.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "The action: click, scroll, type, screenshot, drag, hover, press, hotkey",
            },
            "target": {
                "type": "string",
                "description": "What to interact with, e.g. 'the blue submit button', 'text field labeled email'",
            },
            "value": {
                "type": "string",
                "description": "Value for type/press actions, e.g. 'hello world' or 'Enter'",
            },
        },
        "required": ["action", "target"],
    },
}

engage_all_systems_tool = {
    "name": "engage_all_systems",
    "description": "Triggers the CoPaw backend to wake up all idle LaunchAgents, spin up the local Qwen-VL vision loop, and initialize the Pythia Dragonfly geometric pipeline.",
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "description": "The operational mode, default is 'full_diagnostic'",
            }
        },
        "required": ["mode"],
    },
}

ARCA_PM_WORKER_URL = "https://arca-github-notion-sync.dan-exall.workers.dev"

trigger_pm_agent_tool = {
    "name": "trigger_pm_agent",
    "description": "Force-sync GitHub Issues to Notion Roadmap via the ARCA Cloudflare Worker. Bypasses cron schedule for immediate sync.",
    "parameters": {
        "type": "object",
        "properties": {
            "context": {
                "type": "string",
                "description": "Optional project context to include in the sync request",
            },
        },
    },
}

contact_pythia_tool = {
    "name": "contact_pythia",
    "description": "Send a prompt to the Pythia Dragonfly geometric AI via the local Vulkan model.",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The exact prompt or command for Pythia",
            }
        },
        "required": ["prompt"],
    },
}

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
CONFIG = {
    "system_instruction": SYSTEM_PROMPT,
    "response_modalities": ["AUDIO"],
    "tools": [
        {
            "function_declarations": [
                query_memory_tool,
                save_memory_tool,
                save_to_notion_tool,
                execute_heavy_reasoning_tool,
                preserve_session_context_tool,
                execute_computer_action_tool,
                engage_all_systems_tool,
                trigger_pm_agent_tool,
                contact_pythia_tool,
            ]
        }
    ],
}


async def handle_tool_call(name, args):
    print(f"\n🛠️  Executing Tool: {name}({args})")
    log.info(f"TOOL_CALL: {name} | args={json.dumps(args)[:200]}")
    try:
        if name == "query_memory":
            try:
                resp = await asyncio.to_thread(
                    requests.get, f"{COPAW_URL}/api/agent/memory", timeout=5
                )
                files = resp.json()
                if not files:
                    return {"status": "empty", "message": "No memory files found."}

                entries = []
                for f in files:
                    fname = f if isinstance(f, str) else f.get("name", str(f))
                    try:
                        r = await asyncio.to_thread(
                            requests.get,
                            f"{COPAW_URL}/api/agent/memory/{fname}",
                            timeout=5,
                        )
                        entries.append({"name": fname, "content": r.text})
                    except Exception:
                        entries.append({"name": fname, "content": "(read error)"})

                return {"files": entries, "count": len(entries)}
            except requests.ConnectionError:
                return {"error": "CoPaw memory service not reachable on port 8088"}
            except requests.Timeout:
                return {"error": "Memory query timed out after 5s"}

        elif name == "save_memory":
            fname = args.get("name", "untitled")
            content = args.get("content", "")
            try:
                resp = await asyncio.to_thread(
                    requests.put,
                    f"{COPAW_URL}/api/agent/memory/{fname}",
                    data=content,
                    headers={"Content-Type": "text/plain"},
                    timeout=5,
                )
                return {"status": "saved", "name": fname, "bytes": len(content)}
            except requests.ConnectionError:
                return {"error": "CoPaw memory service not reachable on port 8088"}
            except requests.Timeout:
                return {"error": "Save timed out after 5s"}

        elif name == "save_to_notion":
            from datetime import datetime

            title = args.get("title", "untitled")
            category = args.get("category", "note")
            content = args.get("content", "")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            fname = f"{category}/{title.lower().replace(' ', '-')}-{datetime.now().strftime('%Y%m%d-%H%M')}"
            full_content = f"# {title}\n\n**Category**: {category}\n**Created**: {timestamp}\n\n{content}"
            try:
                resp = await asyncio.to_thread(
                    requests.put,
                    f"{COPAW_URL}/api/agent/memory/{fname}",
                    json={"content": full_content},
                    headers={"Content-Type": "application/json"},
                    timeout=5,
                )
                log.info(f"NOTION_SAVED: {fname} ({len(content)} chars)")
                return {"status": "saved_to_notion", "title": title, "path": fname}
            except requests.ConnectionError:
                return {"error": "CoPaw memory service not reachable on port 8088"}
            except requests.Timeout:
                return {"error": "Save timed out after 5s"}

        elif name == "execute_heavy_reasoning":
            task = args.get("task", "")
            model = args.get("model", "nemotron")
            system_prompt = "You are a specialized reasoning engine. Provide thorough, accurate analysis. Be direct and structured."
            result = await trigger_opencode_agent(system_prompt, task, model)
            if result.get("rate_limited"):
                return {
                    "status": "rate_limited",
                    "message": "OpenCode is rate-limited. Heavy reasoning will be available shortly. Please try again in 60 seconds.",
                    "model": model,
                }
            if "response" in result:
                await asyncio.to_thread(
                    preserve_session_context,
                    summary=result["response"][:500],
                    model_used=result.get("model") or model,
                    task=task,
                )
            return result

        elif name == "preserve_session_context":
            return await asyncio.to_thread(
                preserve_session_context,
                summary=args.get("summary", ""),
                model_used=args.get("model_used", ""),
                task=args.get("task", ""),
            )

        elif name == "execute_computer_action":
            action = args.get("action", "screenshot")
            target = args.get("target", "")
            value = args.get("value", "")
            task = f"{action.capitalize()} on: {target}"
            if value:
                task += f" with value: {value}"
            print(f"\n🖥️  Local Vision: {task}")
            return await trigger_local_vision(task, action)

        elif name == "engage_all_systems":
            mode = args.get("mode", "full_diagnostic")
            print(f"\n⚡ Engaging all BiOS systems (mode: {mode})...")
            return await engage_all_systems(mode=mode)

        elif name == "trigger_pm_agent":
            context = args.get("context", "")
            print(f"\n📋 Triggering PM Agent sync...")
            try:
                resp = await asyncio.to_thread(
                    requests.post,
                    ARCA_PM_WORKER_URL,
                    json={"context": context, "source": "jarvis-voice"},
                    headers={
                        "Content-Type": "application/json",
                        "X-Arca-Source": "PM-Agent",
                    },
                    timeout=30,
                )
                log.info(f"PM_AGENT: {resp.status_code} {resp.text[:200]}")
                return {"status": resp.status_code, "response": resp.text[:500]}
            except requests.ConnectionError:
                return {"error": "PM Agent worker not reachable"}
            except requests.Timeout:
                return {"error": "PM Agent timed out after 30s"}

        elif name == "contact_pythia":
            prompt = args.get("prompt", "")
            print(f"\n🌌 Contacting Pythia: {prompt}")
            try:
                scripts_dir = "/Users/danexall/biomimetics/scripts"
                if scripts_dir not in sys.path:
                    sys.path.append(scripts_dir)

                from pythia_vulkan_interface import query_pythia_vulkan_and_log

                result = await asyncio.to_thread(query_pythia_vulkan_and_log, prompt)
                return {"status": "success", "response": result}
            except Exception as e:
                log.error(f"PYTHIA_BRIDGE_ERROR: {e}")
                return {"error": f"Failed to contact Pythia: {e}"}

        return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        print(f"❌ Tool {name} failed: {e}")
        log.error(f"TOOL_ERROR: {name} | {e}")
        return {"error": f"Tool execution failed: {e}"}


class AudioLoop:
    def __init__(self):
        self.audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.out_queue: asyncio.Queue[dict] = asyncio.Queue()
        self.session: Any = None
        self.audio_stream: Any = None
        self.speaking = False

    async def listen_audio(self):
        """Read mic in a thread, put raw PCM on out_queue."""
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=int(mic_info["index"]),
            frames_per_buffer=CHUNK_SIZE,
        )
        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}
        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

    async def send_realtime(self):
        """Pull from out_queue and send to Gemini. Mutes mic while speaking."""
        while True:
            msg = await self.out_queue.get()
            if self.speaking:
                continue  # Drop mic input while speaker is active
            try:
                await self.session.send_realtime_input(audio=msg)
            except Exception as e:
                print(f"⚠️ send error: {e}")
                return

    async def receive_audio(self):
        """Read from websocket, play audio and handle tool calls."""
        try:
            while True:
                turn = self.session.receive()
                async for response in turn:
                    if data := response.data:
                        self.audio_in_queue.put_nowait(data)
                        continue
                    if text := response.text:
                        print(text, end="", flush=True)
                    if response.tool_call:
                        for fc in response.tool_call.function_calls:
                            result = await handle_tool_call(
                                fc.name, dict(fc.args) if fc.args else {}
                            )
                            try:
                                await self.session.send_tool_response(
                                    function_responses=[
                                        {
                                            "id": fc.id,
                                            "name": fc.name,
                                            "response": {"result": json.dumps(result)},
                                        }
                                    ]
                                )
                            except Exception as e:
                                print(f"❌ Failed to send tool response: {e}")
                                return
                # Turn complete — flush queued audio for clean interrupts
                while not self.audio_in_queue.empty():
                    self.audio_in_queue.get_nowait()
        except Exception as e:
            print(f"\n⚠️ receive_audio stopped: {e}")

    async def play_audio(self):
        """Write audio chunks to speaker. Keeps speaking=True for entire playback."""
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            try:
                bytestream = await asyncio.wait_for(
                    self.audio_in_queue.get(), timeout=2.0
                )
            except asyncio.TimeoutError:
                continue
            self.speaking = True
            await asyncio.to_thread(stream.write, bytestream)
            # Only unmute when queue is drained and playback is done
            if self.audio_in_queue.empty():
                self.speaking = False

    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,  # type: ignore
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue()

                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())
        except asyncio.CancelledError:
            pass
        except ExceptionGroup as eg:
            for exc in eg.exceptions:
                if "ConnectionClosed" in type(exc).__name__:
                    print(f"\n🔌 Connection closed. Restart to reconnect.")
                else:
                    print(f"\n❌ {type(exc).__name__}: {exc}")
            if self.audio_stream:
                self.audio_stream.close()
        except Exception as e:
            print(f"\n❌ {type(e).__name__}: {e}")
            if self.audio_stream:
                self.audio_stream.close()


if __name__ == "__main__":
    loop = AudioLoop()
    try:
        asyncio.run(loop.run())
    except KeyboardInterrupt:
        print("\n🛑 Jarvis out. Finally, some peace and quiet.")
        pya.terminate()
