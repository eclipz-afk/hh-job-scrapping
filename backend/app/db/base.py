import logging
import time
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from app.core.config import Settings
from app.db.models import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: scoped_session[Session] | None = None


def init_engine(settings: Settings) -> Engine:
    global _engine, _session_factory
    _engine = create_engine(
        settings.sqlalchemy_database_uri,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 10, "options": "-c statement_timeout=30000"},
    )
    _session_factory = scoped_session(
        sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    )
    return _engine


def create_all_tables(max_retries: int = 10, retry_delay_seconds: int = 2) -> None:
    if _engine is None:
        raise RuntimeError("Engine was not initialized")
    for attempt in range(1, max_retries + 1):
        try:
            Base.metadata.create_all(bind=_engine)
            return
        except OperationalError:
            if attempt == max_retries:
                raise
            logger.warning("Database unavailable; retry %s/%s", attempt, max_retries)
            time.sleep(retry_delay_seconds)


def get_session_factory() -> scoped_session[Session]:
    if _session_factory is None:
        raise RuntimeError("Session factory is not initialized")
    return _session_factory


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
