"""
LLM service — DeepSeek API client (OpenAI-compatible format).

Hardening:
  - Transient-failure retry with exponential backoff (429 / 5xx / network / timeout)
  - Fixed 120s request timeout

Observability:
  - Every call records token usage into `llm_usage` (feature-tagged) unless
    `record_usage=False`.
"""
import json
import time
from typing import Optional

import httpx

from app.core.config import settings


def _record_usage(feature: str, usage: Optional[dict]) -> None:
    """Persist one LLM call's token usage. Never raises."""
    if not usage:
        return
    try:
        from app.core.database import SessionLocal
        from app.models.llm_usage import LLMUsage

        db = SessionLocal()
        try:
            db.add(LLMUsage(
                feature=feature,
                model=settings.LLM_MODEL,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            ))
            db.commit()
        finally:
            db.close()
    except Exception:
        # Observability must never break the request path
        pass


class LLMService:
    """Thin wrapper around DeepSeek chat completions API."""

    BASE_URL = settings.LLM_API_BASE.rstrip("/") + "/chat/completions"

    @classmethod
    def _headers(cls) -> dict:
        api_key = settings.DEEPSEEK_API_KEY
        if not api_key:
            raise RuntimeError(
                "DeepSeek API key not configured. "
                "Set DEEPSEEK_API_KEY in .env or environment variables."
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @classmethod
    def _payload(
        cls,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> dict:
        payload = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if stream:
            # Ask the server to append usage to the final streamed chunk
            payload["stream_options"] = {"include_usage": True}
        return payload

    @classmethod
    def _post_with_retry(
        cls,
        payload: dict,
        *,
        max_attempts: int = 3,
        backoff: float = 1.0,
    ) -> httpx.Response:
        """POST with exponential backoff on transient failures."""
        last_exc: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                resp = httpx.post(
                    cls.BASE_URL, headers=cls._headers(), json=payload, timeout=120
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = RuntimeError(f"LLM API transient error: HTTP {resp.status_code}")
                    if attempt < max_attempts - 1:
                        time.sleep(backoff)
                        backoff *= 2
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                if attempt < max_attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2
        raise last_exc  # type: ignore[misc]

    @classmethod
    def chat(
        cls,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        feature: str = "chat",
    ) -> str:
        """Send a chat request and return the response text."""
        payload = cls._payload(messages, temperature, max_tokens, False, tools, tool_choice)
        resp = cls._post_with_retry(payload)
        data = resp.json()
        _record_usage(feature, data.get("usage"))
        return data["choices"][0]["message"]["content"]

    @classmethod
    def chat_response(
        cls,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        feature: str = "agent",
    ) -> dict:
        """Non-streaming chat that returns the full assistant message.

        May include "tool_calls" when the model requests tools.
        """
        payload = cls._payload(messages, temperature, max_tokens, False, tools, tool_choice)
        resp = cls._post_with_retry(payload)
        data = resp.json()
        _record_usage(feature, data.get("usage"))
        return data["choices"][0]["message"]

    @classmethod
    def chat_stream(
        cls,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        feature: str = "chat",
    ):
        """Stream a chat response from DeepSeek (OpenAI-compatible).

        Yields dict events:
          {"content": str|None, "tool_calls": [fragments]|None, "finish_reason": str|None}
        Tool-call fragments carry a per-call "index" that the caller must
        accumulate across chunks.

        Transient failures before the first chunk are retried with backoff.
        """
        payload = cls._payload(messages, temperature, max_tokens, True, tools, tool_choice)
        last_exc: Optional[Exception] = None
        usage: Optional[dict] = None
        started = False  # True once the first event has been yielded

        for attempt in range(3):
            backoff = 1.0 * (2**attempt)
            try:
                with httpx.stream(
                    "POST", cls.BASE_URL, headers=cls._headers(), json=payload, timeout=120
                ) as resp:
                    if resp.status_code == 429 or resp.status_code >= 500:
                        resp.read()  # drain body before retrying
                        last_exc = RuntimeError(f"LLM API transient error: HTTP {resp.status_code}")
                        if attempt < 2:
                            time.sleep(backoff)
                        continue
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        chunk = json.loads(data_str)
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        if not chunk.get("choices"):
                            continue
                        choice = chunk["choices"][0]
                        delta = choice.get("delta", {})
                        started = True
                        yield {
                            "content": delta.get("content"),
                            "tool_calls": delta.get("tool_calls"),
                            "finish_reason": choice.get("finish_reason"),
                        }
                    _record_usage(feature, usage)
                    return
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # Only retry failures before any content was delivered — a
                # mid-stream error must not duplicate already-sent tokens.
                if started:
                    raise
                last_exc = e
                if attempt < 2:
                    time.sleep(backoff)

        _record_usage(feature, usage)
        raise last_exc  # type: ignore[misc]

    @classmethod
    def available(cls) -> bool:
        """Check if API key is configured."""
        return bool(settings.DEEPSEEK_API_KEY)
