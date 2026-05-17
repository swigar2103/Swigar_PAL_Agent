"""Database readiness flag — avoids circular imports between main and routes."""

from __future__ import annotations

import asyncio
import logging

from swigar_api.db import init_db

log = logging.getLogger(__name__)
_db_ready: bool = False


def is_db_ready() -> bool:
    return _db_ready


def set_db_ready(value: bool) -> None:
    global _db_ready
    _db_ready = value


async def ensure_db_ready() -> bool:
    """Retry init_db if startup timed out (common with cold Neon)."""
    global _db_ready
    if _db_ready:
        return True
    for attempt in range(1, 4):
        try:
            await asyncio.wait_for(init_db(), timeout=90.0)
            _db_ready = True
            log.info("init_db succeeded on retry attempt %s", attempt)
            try:
                from swigar_api.main import _refresh_health_snapshot

                _refresh_health_snapshot(db_ready=True, question_bank_loading=False)
            except Exception:
                pass
            return True
        except asyncio.TimeoutError:
            log.warning("init_db retry %s timed out (90s)", attempt)
        except Exception:
            log.exception("init_db retry %s failed", attempt)
        await asyncio.sleep(2.0 * attempt)
    return False
