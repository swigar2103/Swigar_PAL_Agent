"""Normalize SQLAlchemy / asyncpg database URLs (Neon sslmode, etc.)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalize_async_database_url(url: str) -> str:
    """Use SQLAlchemy async engine with PostgreSQL (Neon, etc.)."""
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def _strip_scheme(url: str) -> tuple[str, str]:
    for prefix in (
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
        "postgresql://",
        "postgres://",
    ):
        if url.startswith(prefix):
            return prefix, url[len(prefix) :]
    return "", url


def prepare_postgres_urls(url: str) -> tuple[str, dict, str, bool | None]:
    """
    Returns:
      - sqlalchemy_async_url (sslmode removed from query)
      - connect_args for create_async_engine (e.g. ssl=True)
      - asyncpg DSN (postgresql://… without sslmode)
      - ssl flag for asyncpg.connect
    """
    async_url = normalize_async_database_url(url)
    scheme, rest = _strip_scheme(async_url)
    if not scheme:
        return async_url, {}, url, None

    parsed = urlparse(f"postgresql://{rest}")
    qs = parse_qs(parsed.query, keep_blank_values=False)
    sslmode = (qs.pop("sslmode", ["prefer"])[0] or "prefer").lower()
    qs.pop("channel_binding", None)

    ssl: bool | None
    if sslmode in ("require", "verify-ca", "verify-full"):
        ssl = True
    elif sslmode == "disable":
        ssl = False
    else:
        ssl = None

    flat = {k: v[0] for k, v in qs.items()}
    clean_rest = urlunparse(
        parsed._replace(query=urlencode(flat) if flat else "")
    ).replace("postgresql://", "", 1)
    clean_async = f"{scheme}{clean_rest}"
    asyncpg_dsn = f"postgresql://{clean_rest}"
    connect_args: dict = {"timeout": 20}
    if ssl is True:
        connect_args["ssl"] = True
    elif ssl is False:
        connect_args["ssl"] = False

    return clean_async, connect_args, asyncpg_dsn, ssl


def to_asyncpg_dsn(url: str) -> str:
    """Plain postgresql:// DSN for asyncpg.connect (sslmode stripped)."""
    _, _, dsn, _ = prepare_postgres_urls(url)
    return dsn
