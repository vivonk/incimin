"""Postgres connection pool and schema application.

psycopg3 is the single driver for this project. `langgraph-checkpoint-postgres`
requires it, so using anything else here (asyncpg) would mean two pools against
one database once phase 11 wires up the checkpointer.
"""
from __future__ import annotations

import logging
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.api.settings import settings

log = logging.getLogger("incimin.api.db")

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_pool: AsyncConnectionPool | None = None


async def open_pool() -> AsyncConnectionPool:
    """Create and open the shared pool. Idempotent."""
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            settings.database_url,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            open=False,
            kwargs={"row_factory": dict_row},
        )
        await _pool.open(wait=True, timeout=30)
        log.info("postgres pool open (%s)", _redact(settings.database_url))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("pool not open — call open_pool() in the app lifespan first")
    return _pool


async def apply_schema() -> None:
    """Apply schema.sql. Idempotent — every statement is CREATE ... IF NOT EXISTS.

    A fresh `docker compose up` plus a start of this app must produce a working
    database with zero manual steps.
    """
    ddl = SCHEMA_PATH.read_text()
    async with pool().connection() as conn:
        await conn.execute(ddl)
    log.info("schema applied")


_checkpointer = None


async def setup_checkpointer() -> None:
    """Create the LangGraph checkpointer tables and build the shared saver.

    `AsyncPostgresSaver.setup()` does not run automatically, and a connection built
    outside the pool needs autocommit or the DDL silently commits nothing — the
    tables simply never appear and the first pause fails.

    The saver itself is held for the process lifetime and shares the application
    pool. Building one per run would mean a second pool against the same database,
    and — worse — a pause written by one saver and resumed by another.
    """
    global _checkpointer
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError:  # pragma: no cover - dependency is declared
        log.warning("langgraph-checkpoint-postgres not installed; gates will be unavailable")
        return

    async with await _autocommit_connection() as conn:
        await AsyncPostgresSaver(conn).setup()

    _checkpointer = AsyncPostgresSaver(pool())
    log.info("checkpointer ready")


def checkpointer():
    if _checkpointer is None:
        raise RuntimeError("checkpointer not initialised — call setup_checkpointer() in lifespan")
    return _checkpointer


async def _autocommit_connection():
    from psycopg import AsyncConnection

    return await AsyncConnection.connect(
        settings.database_url, autocommit=True, row_factory=dict_row
    )


def _redact(url: str) -> str:
    """Strip credentials before logging a connection string."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.rpartition('@')[2]}"
