"""Test fixtures for the prompt registry.

Integration tests need a real Postgres (pgvector + JSONB). The `registry`
fixture is auto-skipped when DATABASE_URL is not reachable, so `make test`
still passes on a laptop without docker running.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from meridian_db import Base
from meridian_prompt_registry import PromptRegistry
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://meridian:meridian@localhost:5432/meridian",
    )


@pytest.fixture(scope="session")
def engine() -> Iterator[object]:
    url = _database_url()
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"postgres unavailable at {url}: {exc}", allow_module_level=False)
    # Ensure every ORM table exists. In CI, alembic will have run; locally we
    # fall back to create_all so developers don't need to run migrations first.
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: object) -> sessionmaker[Session]:  # type: ignore[type-arg]
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)  # type: ignore[arg-type]


@pytest.fixture()
def registry(session_factory: sessionmaker[Session]) -> Iterator[PromptRegistry]:  # type: ignore[type-arg]
    # Each test gets a clean slate — wipe the registry tables.
    with session_factory() as session:
        for table in (
            "prompt_audit_log",
            "prompt_activations",
            "prompt_templates",
        ):
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()
    yield PromptRegistry(session_factory)
