from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.engine import URL, make_url
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import Settings

engine = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


async def init_db(settings: Settings) -> None:
    global engine, AsyncSessionLocal
    from app.db.models import Base

    db_url = normalize_database_url(_resolve_database_url(settings))
    if db_url.get_backend_name() == "sqlite":
        db_path = db_url.database
        if db_path:
            if not Path(db_path).expanduser().is_absolute():
                db_path = str(settings.project_root / db_path)
                db_url = db_url.set(database=db_path)
            Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        db_url,
        echo=settings.database_echo,
        future=True,
    )
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_owner_user_columns)


async def close_db() -> None:
    global engine, AsyncSessionLocal
    if engine:
        await engine.dispose()
    engine = None
    AsyncSessionLocal = None


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized.")
    return AsyncSessionLocal


def normalize_database_url(value: str) -> URL:
    url = make_url(value)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+asyncpg")
    if url.drivername == "postgresql+asyncpg":
        url = _normalize_asyncpg_ssl(url)
        url = _normalize_supabase_pooler(url)
    return url


def _ensure_owner_user_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)
    table_names = set(inspector.get_table_names())
    for table in [
        "vedic_sessions",
        "vedic_artifacts",
        "vedic_exports",
        "vedic_core_jobs",
        "vedic_core_job_nodes",
    ]:
        if table not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "owner_user_id" not in columns:
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN owner_user_id VARCHAR(160)"))


def database_diagnostic_context(settings: Settings | None = None) -> dict[str, object]:
    try:
        db_url = normalize_database_url(_resolve_database_url(settings) if settings else "")
    except Exception as exc:
        return {
            "initialized": AsyncSessionLocal is not None,
            "urlValid": False,
            "urlErrorType": type(exc).__name__,
            "urlError": str(exc),
            "render": bool(os.getenv("RENDER")),
        }
    host = db_url.host or "local"
    return {
        "initialized": AsyncSessionLocal is not None,
        "source": _database_source(settings),
        "driver": db_url.drivername,
        "host": host,
        "port": db_url.port,
        "database": db_url.database or "",
        "render": bool(os.getenv("RENDER")),
        "supabasePooler": host.endswith(".pooler.supabase.com"),
        "supabaseDirect": host.startswith("db.") and host.endswith(".supabase.co"),
    }


def _resolve_database_url(settings: Settings) -> str:
    resolver = getattr(settings, "resolved_database_url", None)
    if callable(resolver):
        return str(resolver())
    return str(settings.database_url)


def _database_source(settings: Settings | None) -> str:
    if not settings:
        return "unknown"
    resolver = getattr(settings, "database_source", None)
    if callable(resolver):
        return str(resolver())
    return "database_url"


def _normalize_asyncpg_ssl(url: URL) -> URL:
    if "sslmode" in url.query and "ssl" not in url.query:
        sslmode = _query_value_to_string(url.query["sslmode"])
        url = url.difference_update_query(["sslmode"]).update_query_dict({"ssl": sslmode})
    elif "sslmode" in url.query:
        url = url.difference_update_query(["sslmode"])
    elif "ssl" not in url.query:
        url = url.update_query_dict({"ssl": "require"})
    return url


def _query_value_to_string(value: tuple[str, ...] | str) -> str:
    if isinstance(value, tuple):
        return value[-1] if value else ""
    return value


def _normalize_supabase_pooler(url: URL) -> URL:
    if "pgbouncer" in url.query:
        url = url.difference_update_query(["pgbouncer"])
    if (
        url.host
        and url.host.endswith(".pooler.supabase.com")
        and url.port == 6543
        and "prepared_statement_cache_size" not in url.query
    ):
        return url.update_query_dict({"prepared_statement_cache_size": "0"})
    return url
