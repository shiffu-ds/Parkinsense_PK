"""Runtime configuration. Private values are never returned to the UI."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_root: Path
    max_upload_bytes: int
    allow_sqlite: bool


def get_settings() -> Settings:
    # Explicit env variables take precedence over the ignored local .env file.
    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env", override=False)
    max_upload_mb = int(os.getenv("PARKINSENSE_MAX_UPLOAD_MB", "100"))
    if not 1 <= max_upload_mb <= 500:
        raise ValueError("PARKINSENSE_MAX_UPLOAD_MB must be between 1 and 500.")
    storage = Path(os.getenv("PARKINSENSE_STORAGE_ROOT", str(project_root / "data" / "private"))).expanduser()
    if not storage.is_absolute():
        storage = project_root / storage
    return Settings(
        database_url=os.getenv(
            "PARKINSENSE_DATABASE_URL",
            "postgresql+psycopg://parkinsense@localhost:5432/parkinsense",
        ),
        storage_root=storage.absolute(),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        allow_sqlite=os.getenv("PARKINSENSE_ALLOW_SQLITE", "0") == "1",
    )
