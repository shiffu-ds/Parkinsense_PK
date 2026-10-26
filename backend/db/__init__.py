"""Database lifecycle and short transaction boundaries."""

from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import get_settings
from backend.db.models import Base

_engine = None
_factory = None
_lock = RLock()


def configure_db(database_url: str | None = None, *, allow_sqlite: bool = False):
    global _engine, _factory
    settings = get_settings()
    url = make_url(database_url or settings.database_url)
    if url.get_backend_name() not in {"postgresql", "sqlite"}:
        raise ValueError("Use PostgreSQL, or explicitly enable SQLite for development/tests.")
    options = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        if not (allow_sqlite or settings.allow_sqlite):
            raise ValueError("SQLite is development-only. Set PARKINSENSE_ALLOW_SQLITE=1 explicitly.")
        options["connect_args"] = {"check_same_thread": False}
        if url.database in {None, "", ":memory:"}:
            options["poolclass"] = StaticPool
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = create_engine(url, **options)
        if url.get_backend_name() == "sqlite":
            @event.listens_for(_engine, "connect")
            def _sqlite_foreign_keys(connection, _record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine():
    if _engine is None:
        configure_db()
    return _engine


def init_db() -> None:
    # Register additive workflow/security tables before create_all. Imports
    # stay here so service modules can safely import the transaction helper.
    from backend.db import pilot_models, production_models, validation_models, privacy_models, context_models  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite" and engine.url.database not in {None, "", ":memory:"}:
        Path(engine.url.database).chmod(0o600)


@contextmanager
def transaction():
    if _factory is None:
        configure_db()
    with _factory.begin() as session:
        yield session
