import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    claude_bin: str = os.getenv("CLAUDE_BIN", "claude")
    workers: int = max(1, int(os.getenv("WORKERS", "1")))
    max_retries: int = max(0, int(os.getenv("MAX_RETRIES", "2")))
    db_path: Path = Path(os.getenv("DB_PATH", "./data/tasks.db"))
    workspace_root: Path = Path(os.getenv("WORKSPACE_ROOT", "./workspace"))
    log_root: Path = Path(os.getenv("LOG_ROOT", "./logs"))


settings = Settings()
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
settings.workspace_root.mkdir(parents=True, exist_ok=True)
settings.log_root.mkdir(parents=True, exist_ok=True)
