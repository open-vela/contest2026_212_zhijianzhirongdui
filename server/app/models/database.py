"""Async database engine and session management with SQLAlchemy 2.0 + aiosqlite."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Create all tables and seed default data."""
    sqlite_prefix = "sqlite+aiosqlite:///"
    if settings.DATABASE_URL.startswith(sqlite_prefix):
        database_path = settings.DATABASE_URL.removeprefix(sqlite_prefix)
        if database_path and database_path != ":memory:":
            Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    from app.models.models import (  # noqa: F401  — ensure models are loaded
        Alert,
        AuditLog,
        CloudTransferEvent,
        CloudTransferAttempt,
        DemoMetricSnapshot,
        DemoTelemetry,
        Device,
        EnergyLog,
        Event,
        Face,
        Permission,
        Person,
        Role,
        RolePermission,
        Rule,
        Space,
        Tenant,
        User,
        UserRole,
        Visitor,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
            await _upgrade_sqlite_schema(conn)

    # Seed default data
    from app.services.auth_service import seed_default_data

    async with async_session_factory() as session:
        await seed_default_data(session)
        await session.commit()


async def _upgrade_sqlite_schema(conn) -> None:
    """Apply additive SQLite upgrades for portable databases created pre-OPE-86.

    SQLAlchemy's ``create_all`` creates new tables but deliberately does not add
    columns to an existing table. These idempotent additions keep a copied demo
    database usable without introducing a separate migration dependency.
    """

    async def columns(table: str) -> set[str]:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {str(row[1]) for row in result.fetchall()}

    telemetry_columns = await columns("demo_telemetry")
    if "provenance" not in telemetry_columns:
        await conn.execute(text(
            "ALTER TABLE demo_telemetry ADD COLUMN provenance VARCHAR(32) "
            "NOT NULL DEFAULT 'real'"
        ))

    cloud_columns = await columns("cloud_transfer_events")
    additions = {
        "idempotency_key": "VARCHAR(128)",
        "provider": "VARCHAR(32) NOT NULL DEFAULT 'disabled'",
        "transport": "VARCHAR(32) NOT NULL DEFAULT 'none'",
        "provenance": "VARCHAR(32) NOT NULL DEFAULT 'reserved'",
        "error_message": "TEXT",
        "response_status": "INTEGER",
        "max_retries": "INTEGER NOT NULL DEFAULT 5",
        "next_attempt_at": "DATETIME",
        "last_attempt_at": "DATETIME",
        "delivered_at": "DATETIME",
        "receipt_json": "JSON DEFAULT '{}'",
    }
    for name, ddl in additions.items():
        if name not in cloud_columns:
            await conn.execute(text(f"ALTER TABLE cloud_transfer_events ADD COLUMN {name} {ddl}"))

    await conn.execute(text(
        "UPDATE cloud_transfer_events SET status = 'pending' WHERE status = 'queued_local'"
    ))
    # Older OPE-86 previews scoped this key across both directions. A cloud
    # receiver may legitimately acknowledge an upload with the same key, so
    # idempotency is enforced independently for upload and receive.
    await conn.execute(text("DROP INDEX IF EXISTS ux_cloud_transfer_tenant_idempotency"))
    await conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_cloud_transfer_tenant_direction_idempotency "
        "ON cloud_transfer_events (tenant_id, direction, idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    ))
