"""Per-tenant custom anonymization rules fetched from the Hub.

The SDK fetches rules from ``GET /v1/anonymization-rules`` and applies them
on top of the baseline regex set before transmission. Rules are cached in
process memory with a TTL (default 300s) so the typical request path makes
zero network calls.

If the fetch has never succeeded, ``get()`` raises ``MonkAIAnonymizerNotReady``
so the upload pipeline can block instead of sending raw content. If the
fetch fails after at least one successful fetch, the cached value is
returned and a warning is logged — the SDK degrades to "stale rules" rather
than hard-failing for a transient Hub outage.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Dict, Optional

import requests

from monkai_trace.exceptions import MonkAIAnonymizerNotReady

logger = logging.getLogger(__name__)


_DEFAULT_TTL_SECONDS = 300


class RulesClient:
    """Fetches and caches per-tenant anonymization rules.

    Args:
        tracer_token: SDK tracer token (``tk_...``) used to authenticate the fetch.
        hub_url: Base URL of the Hub edge function exposing
            ``/v1/anonymization-rules`` (typically the same value as
            ``MonkAIClient.base_url``).
        ttl_seconds: How long a successful fetch is reused before a refetch
            is attempted. Defaults to 300s.
        timeout: Per-request timeout in seconds. Defaults to 5.
    """

    DEFAULT_RULES: Dict[str, Any] = {
        "version": 0,
        "rules": {"toggles": {}, "custom": []},
    }

    def __init__(
        self,
        tracer_token: str,
        hub_url: str,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        timeout: int = 5,
    ):
        self._tracer_token = tracer_token
        self._hub_url = hub_url.rstrip("/")
        self._ttl = ttl_seconds
        self._timeout = timeout
        self._cache: Optional[Dict[str, Any]] = None
        self._cached_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def endpoint(self) -> str:
        return f"{self._hub_url}/v1/anonymization-rules"

    def get(self) -> Dict[str, Any]:
        """Return current rules document, refetching when the cache is stale.

        Falls back to the last successful cache on transient failure. Raises
        ``MonkAIAnonymizerNotReady`` if no successful fetch has ever happened.
        """
        with self._lock:
            now = time.time()
            if self._cache is not None and (now - self._cached_at) < self._ttl:
                return self._cache

            try:
                payload = self._fetch_sync()
            except Exception:
                logger.exception(
                    "RulesClient: fetch from %s failed", self.endpoint
                )
                if self._cache is not None:
                    logger.warning(
                        "RulesClient: serving stale cache (age=%.1fs) — "
                        "Hub fetch failed",
                        now - self._cached_at,
                    )
                    return self._cache
                raise MonkAIAnonymizerNotReady(
                    f"Could not fetch anonymization rules from {self.endpoint}; "
                    "blocking upload to avoid sending raw content"
                )

            self._cache = payload
            self._cached_at = now
            return payload

    async def get_async(self) -> Dict[str, Any]:
        """Async variant of ``get()`` — runs the blocking fetch in a worker thread.

        Using a thread executor (instead of pulling in ``aiohttp`` here) keeps
        the rules-fetch path identical between sync and async clients and
        avoids cross-loop session reuse issues.
        """
        return await asyncio.to_thread(self.get)

    def invalidate(self) -> None:
        """Force the next call to ``get()`` to refetch."""
        with self._lock:
            self._cached_at = 0.0

    def _fetch_sync(self) -> Dict[str, Any]:
        response = requests.get(
            self.endpoint,
            headers={
                "tracer_token": self._tracer_token,
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return self._normalize(data)

    @staticmethod
    def _normalize(data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError(
                f"RulesClient: unexpected response type {type(data).__name__}"
            )
        version = data.get("version", 0)
        rules = data.get("rules") or {}
        toggles = rules.get("toggles") if isinstance(rules, dict) else None
        custom = rules.get("custom") if isinstance(rules, dict) else None
        return {
            "version": int(version) if isinstance(version, (int, float)) else 0,
            "rules": {
                "toggles": toggles if isinstance(toggles, dict) else {},
                "custom": custom if isinstance(custom, list) else [],
            },
        }
