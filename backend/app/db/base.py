from __future__ import annotations

from contextlib import contextmanager
import time
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from app.core.config import Settings
from app.db.models import Base

_ENGINE: Engine | None = None
_SessionFactory: scoped_session[Session] | None = None


def init_engine(settings: Settings) -> Engine:
    global _ENGINE, _SessionFactory
    _ENGINE = create_engine(
        settings.sqlalchemy_database_uri, pool_pre_ping=True, future=True, hide_parameters=True,
        connect_args={"connect_timeout": 10, "options": "-c statement_timeout=30000"},
    )
    _SessionFactory = scoped_session(
        sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)
    )
    return _ENGINE


def create_all_tables(max_retries: int = 10, retry_delay_seconds: int = 2) -> None:
    if _ENGINE is None:
        raise RuntimeError("Engine was not initialized")
    for attempt in range(1, max_retries + 1):
        try:
            Base.metadata.create_all(bind=_ENGINE)
            return
        except OperationalError:
            if attempt == max_retries:
                raise
            time.sleep(retry_delay_seconds)


def get_session_factory() -> scoped_session[Session]:
    if _SessionFactory is None:
        raise RuntimeError("Session factory is not initialized")
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
