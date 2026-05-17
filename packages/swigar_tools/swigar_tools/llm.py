"""OpenAI-compatible LLM client (阿里云百炼 DashScope)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


class DashScopeLLMClient:
    """Calls DashScope compatible-mode API via OpenAI Python SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        enabled: bool | None = None,
        fallback_on_error: bool | None = None,
    ):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.base_url = base_url or os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.environ.get("DASHSCOPE_MODEL", DEFAULT_MODEL)
        self.timeout = float(os.environ.get("DASHSCOPE_TIMEOUT", str(timeout)))
        self.enabled = _env_bool("SWIGAR_LLM_ENABLED", True) if enabled is None else enabled
        self.fallback_on_error = (
            _env_bool("SWIGAR_LLM_FALLBACK_ON_ERROR", True)
            if fallback_on_error is None
            else fallback_on_error
        )
        self._client = None
        workers = int(os.environ.get("SWIGAR_LLM_THREAD_WORKERS", "4"))
        self._executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="swigar-llm")
        prefetch_workers = int(os.environ.get("SWIGAR_LLM_PREFETCH_WORKERS", "2"))
        self._prefetch_executor = ThreadPoolExecutor(
            max_workers=max(1, prefetch_workers),
            thread_name_prefix="swigar-llm-prefetch",
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.api_key and self.api_key != "sk-your-dashscope-api-key-here")

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url.rstrip("/"),
                timeout=self.timeout,
            )
        return self._client

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        """Return parsed JSON object from model, or None on failure."""
        if not self.is_configured:
            return None

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if trace:
            try:
                trace("llm_request", {"model": self.model, "messages": messages})
            except Exception:
                logger.debug("llm trace callback failed on request", exc_info=True)

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            raw = response.choices[0].message.content or "{}"
            if trace:
                try:
                    trace(
                        "llm_response",
                        {
                            "model": self.model,
                            "raw": raw,
                            "usage": getattr(response, "usage", None),
                        },
                    )
                except Exception:
                    logger.debug("llm trace callback failed on response", exc_info=True)
            return _parse_json_object(raw)
        except Exception as exc:
            logger.exception("DashScope LLM call failed: %s", exc)
            if trace:
                try:
                    trace("llm_error", {"error": str(exc)})
                except Exception:
                    pass
            return None

    async def complete_json_async(
        self,
        *,
        system: str,
        user: str,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
        priority: str = "active",
    ) -> dict[str, Any] | None:
        """Run complete_json in a thread pool so asyncio handlers stay responsive."""
        loop = asyncio.get_running_loop()
        pool = self._prefetch_executor if priority == "prefetch" else self._executor
        return await loop.run_in_executor(
            pool,
            lambda: self.complete_json(system=system, user=user, trace=trace),
        )


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise


_llm_singleton: DashScopeLLMClient | None = None


def reset_llm_client() -> None:
    """Drop cached client so the next get_llm_client() reads fresh env (after .env sync)."""
    global _llm_singleton
    _llm_singleton = None


def get_llm_client() -> DashScopeLLMClient:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = DashScopeLLMClient()
    return _llm_singleton
