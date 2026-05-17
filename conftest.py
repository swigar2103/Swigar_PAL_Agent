import os

os.environ.setdefault("SWIGAR_MEMORY_DISABLED", "1")
os.environ.setdefault("SWIGAR_LLM_ENABLED", "false")
# Tests use local SQLite + builtin bank; do not hit remote Neon during pytest
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./.pytest_swigar.db"
os.environ["SWIGAR_QUESTION_BANK_SOURCE"] = "builtin"
