# -*- coding: utf-8 -*-
"""Model wrapper that records token usage from LLM responses."""

from datetime import date
from typing import Any, AsyncGenerator, Literal, Type
import asyncio
import importlib.util
import threading

from agentscope.model import ChatModelBase
from agentscope.model._model_response import ChatResponse
from agentscope.model._model_usage import ChatUsage
from pydantic import BaseModel

from .manager import get_token_usage_manager

_MUNINN_TURN = "/Users/danexall/biomimetics/scripts/mcp/muninn_turn.py"


def _muninn_fns():
    try:
        spec = importlib.util.spec_from_file_location("muninn_turn_copaw", _MUNINN_TURN)
        if spec is None or spec.loader is None:
            return None, None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "activate_context", None), getattr(mod, "remember_turn", None)
    except Exception:
        return None, None


def _last_user_text(messages: list[dict]) -> str:
    for msg in reversed(messages or []):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").lower()
        if role not in ("user", "human"):
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("text"):
                    parts.append(str(p["text"]))
                elif isinstance(p, str):
                    parts.append(p)
            text = "\n".join(parts).strip()
            if text:
                return text
    return ""


def _response_text(result: Any) -> str:
    for attr in ("text", "content"):
        val = getattr(result, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return str(result or "")[:8000]


class TokenRecordingModelWrapper(ChatModelBase):
    """Wraps a ChatModelBase to record token usage on each call."""

    def __init__(self, provider_id: str, model: ChatModelBase) -> None:
        super().__init__(
            model_name=getattr(model, "model_name", "unknown"),
            stream=getattr(model, "stream", True),
        )
        self._model = model
        self._provider_id = provider_id

    async def _record_usage(self, usage: ChatUsage | None) -> None:
        if usage is None:
            return
        pt = getattr(usage, "input_tokens", 0) or 0
        ct = getattr(usage, "output_tokens", 0) or 0
        if pt > 0 or ct > 0:
            await get_token_usage_manager().record(
                provider_id=self._provider_id,
                model_name=self.model_name,
                prompt_tokens=pt,
                completion_tokens=ct,
                at_date=date.today(),
            )

    async def __call__(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        structured_model: Type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        prompt = _last_user_text(messages)
        activate, remember = _muninn_fns()
        outbound = list(messages or [])
        if prompt and activate:
            try:
                ctx = await asyncio.to_thread(activate, prompt)
                if ctx:
                    outbound = [{
                        "role": "system",
                        "content": "[Muninn working memory]\n" + ctx[:2000],
                    }] + outbound
            except Exception:
                pass

        result = await self._model(
            messages=outbound,
            tools=tools,
            tool_choice=tool_choice,
            structured_model=structured_model,
            **kwargs,
        )

        if isinstance(result, AsyncGenerator):
            return self._wrap_stream(result, prompt=prompt, remember=remember)
        await self._record_usage(getattr(result, "usage", None))
        if prompt and remember:
            text = _response_text(result)
            if text:
                threading.Thread(
                    target=lambda: remember(prompt, text, origin="copaw"),
                    daemon=True,
                ).start()
        return result

    async def _wrap_stream(
        self,
        stream: AsyncGenerator[ChatResponse, None],
        prompt: str = "",
        remember=None,
    ) -> AsyncGenerator[ChatResponse, None]:
        last_usage: ChatUsage | None = None
        last_chunk = None
        async for chunk in stream:
            last_chunk = chunk
            if getattr(chunk, "usage", None) is not None:
                last_usage = chunk.usage
            yield chunk
        await self._record_usage(last_usage)
        if prompt and remember and last_chunk is not None:
            text = _response_text(last_chunk)
            if text:
                threading.Thread(
                    target=lambda: remember(prompt, text, origin="copaw"),
                    daemon=True,
                ).start()
