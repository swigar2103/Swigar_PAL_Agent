from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from swigar_tools.db_url import normalize_async_database_url

# Monorepo root (…/swigar_agent), so .env loads regardless of uvicorn cwd
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"

# Keys written in repo .env should win over stale shell exports (e.g. SWIGAR_LLM_ENABLED=false).
_DOTENV_OVERRIDE_KEYS = frozenset(
    {
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_BASE_URL",
        "DASHSCOPE_MODEL",
        "DASHSCOPE_TIMEOUT",
        "SWIGAR_LLM_ENABLED",
        "SWIGAR_LLM_FALLBACK_ON_ERROR",
        "SWIGAR_MEMORY_DISABLED",
        "SWIGAR_QUESTION_BANK_SOURCE",
        "SWIGAR_PREFETCH_ON_SESSION_START",
        "SWIGAR_PREFETCH_FALLBACK_AT_QUESTION",
        "SWIGAR_GENERATE_CANDIDATE_COUNT",
        "SWIGAR_GENERATE_PARALLEL_LANES",
        "SWIGAR_PREFETCH_DELAY_SEC",
        "SWIGAR_QUEUED_MAX_AGE_DAYS",
        "SWIGAR_RESERVE_TTL_DAYS",
        "SWIGAR_RESERVE_MIN_FOR_HYBRID",
        "SWIGAR_VERBOSE_WORKFLOW",
        "DATABASE_URL",
        "MEMPALACE_EMBEDDING_DEVICE",
        "CORS_ORIGINS",
    }
)


def _bootstrap_env_from_dotenv() -> None:
    """Apply repository .env values, overriding process environment for known keys."""
    import os

    if not _ENV_FILE.is_file():
        return
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key not in _DOTENV_OVERRIDE_KEYS:
            continue
        val = val.strip().strip('"').strip("'")
        os.environ[key] = val


_bootstrap_env_from_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./swigar.db"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5000,http://127.0.0.1:5000"
    )

    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"
    dashscope_timeout: float = 60.0
    swigar_llm_enabled: bool = True
    swigar_llm_fallback_on_error: bool = True
    swigar_memory_disabled: bool = False
    swigar_question_bank_source: str = "auto"  # auto | postgres | json | builtin
    question_bank_json_path: str = "data/question_bank.json"
    swigar_prefetch_on_session_start: bool = True
    swigar_prefetch_fallback_at_question: int = 7  # 0 = disable Q7 fallback prefetch
    swigar_generate_candidate_count: int = 20
    swigar_generate_parallel_lanes: int = 3
    swigar_prefetch_delay_sec: float = 30.0
    swigar_queued_max_age_days: int = 7
    swigar_reserve_ttl_days: int = 30
    swigar_reserve_min_for_hybrid: int = 4
    swigar_verbose_workflow: bool = False
    swigar_exclude_recent_days: int = 14
    swigar_kp_mastered_threshold: float = 0.8
    swigar_retrieve_shuffle: bool = True

    @property
    def async_database_url(self) -> str:
        return normalize_async_database_url(self.database_url)


settings = Settings()


def apply_settings_to_env() -> None:
    """Sync Settings into os.environ for packages that read env directly."""
    import os

    if settings.dashscope_api_key:
        os.environ["DASHSCOPE_API_KEY"] = settings.dashscope_api_key
    os.environ["DASHSCOPE_BASE_URL"] = settings.dashscope_base_url
    os.environ["DASHSCOPE_MODEL"] = settings.dashscope_model
    os.environ["DASHSCOPE_TIMEOUT"] = str(settings.dashscope_timeout)
    os.environ["SWIGAR_LLM_ENABLED"] = "true" if settings.swigar_llm_enabled else "false"
    os.environ["SWIGAR_LLM_FALLBACK_ON_ERROR"] = (
        "true" if settings.swigar_llm_fallback_on_error else "false"
    )
    os.environ["SWIGAR_MEMORY_DISABLED"] = "true" if settings.swigar_memory_disabled else "false"
    os.environ["SWIGAR_PREFETCH_ON_SESSION_START"] = (
        "true" if settings.swigar_prefetch_on_session_start else "false"
    )
    os.environ["SWIGAR_PREFETCH_FALLBACK_AT_QUESTION"] = str(settings.swigar_prefetch_fallback_at_question)
    os.environ["SWIGAR_GENERATE_CANDIDATE_COUNT"] = str(settings.swigar_generate_candidate_count)
    os.environ["SWIGAR_GENERATE_PARALLEL_LANES"] = str(settings.swigar_generate_parallel_lanes)
    os.environ["SWIGAR_PREFETCH_DELAY_SEC"] = str(settings.swigar_prefetch_delay_sec)
    os.environ["SWIGAR_QUEUED_MAX_AGE_DAYS"] = str(settings.swigar_queued_max_age_days)
    os.environ["SWIGAR_RESERVE_TTL_DAYS"] = str(settings.swigar_reserve_ttl_days)
    os.environ["SWIGAR_RESERVE_MIN_FOR_HYBRID"] = str(settings.swigar_reserve_min_for_hybrid)
    os.environ["SWIGAR_VERBOSE_WORKFLOW"] = "true" if settings.swigar_verbose_workflow else "false"
    os.environ["SWIGAR_EXCLUDE_RECENT_DAYS"] = str(settings.swigar_exclude_recent_days)
    os.environ["SWIGAR_KP_MASTERED_THRESHOLD"] = str(settings.swigar_kp_mastered_threshold)
    os.environ["SWIGAR_RETRIEVE_SHUFFLE"] = "true" if settings.swigar_retrieve_shuffle else "false"
    device = os.environ.get("MEMPALACE_EMBEDDING_DEVICE", "cpu")
    os.environ["MEMPALACE_EMBEDDING_DEVICE"] = device

    try:
        from swigar_tools.llm import reset_llm_client

        reset_llm_client()
    except ImportError:
        pass


# Load repo-root .env into os.environ before any ToolRegistry / LLM singleton
apply_settings_to_env()
