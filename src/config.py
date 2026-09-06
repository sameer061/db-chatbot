from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    model_name: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    max_rows: int = int(os.getenv("MAX_ROWS", "100"))
    max_repair_attempts: int = int(os.getenv("MAX_REPAIR_ATTEMPTS", "2"))
    query_timeout_seconds: int = int(os.getenv("QUERY_TIMEOUT_SECONDS", "10"))

settings = Settings()

ALLOWED_SUFFIXES = {".db", ".sqlite", ".sqlite3"}

DESTRUCTIVE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "ATTACH", "DETACH", "REINDEX", "VACUUM", "PRAGMA", "REPLACE",
}
