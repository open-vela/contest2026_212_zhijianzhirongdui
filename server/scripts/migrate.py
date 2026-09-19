#!/usr/bin/env python3
"""Database migration script for VelaMesh (枢络).

Usage:
    PYTHONPATH=. python scripts/migrate.py          # Show pending migrations
    PYTHONPATH=. python scripts/migrate.py --up     # Apply all pending
    PYTHONPATH=. python scripts/migrate.py --down   # Rollback last batch

Migrations are tracked in a `_migrations` table. Each migration is a
Python callable in the MIGRATIONS dict with an upgrade/downgrade pair.
"""

import asyncio
import sys
import time
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, select

from app.models.database import Base, async_session_factory, engine

# ── Migration tracking table ──────────────────────────────────────────


class Migration(Base):
    __tablename__ = "_migrations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, unique=True)
    applied_at = Column(DateTime, default=datetime.utcnow)
    batch = Column(Integer, nullable=False)


# ── Migration definitions ─────────────────────────────────────────────
# Each function receives (db_session) and should call db.add()/db.execute()
# as needed. Return True on success.

MIGRATIONS: dict[str, dict] = {}


def migration(name: str, description: str = ""):
    """Decorator to register a migration."""
    def wrapper(func):
        async def upgrade(session):
            return await func(session)
        upgrade.down = None  # type: ignore
        MIGRATIONS[name] = {
            "up": upgrade,
            "description": description or name,
        }
        return func
    return wrapper


def migration_pair(name: str, description: str = ""):
    """Decorator for a migration with upgrade and downgrade functions."""
    def wrapper(func):
        async def upgrade(session):
            return await func(session)

        async def downgrade(session):
            if hasattr(func, "down"):
                return await func.down(session)
            return False

        upgrade.down = downgrade  # type: ignore
        MIGRATIONS[name] = {
            "up": upgrade,
            "down": downgrade,
            "description": description or name,
        }
        return func
    return wrapper


# ── Example migrations (add yours below) ──────────────────────────────

@migration("v001_initial_tables", "Initial schema (tracked by ORM create_all)")
async def v001_initial_tables(session):
    """Initial tables are created by ORM Base.metadata.create_all().
    This migration just records that the initial schema was applied.
    """
    return True


@migration("v002_add_device_config_index", "Add index on device config")
async def v002_add_device_config_index(session):
    """Example: add an index on devices.config_json for faster queries."""
    from sqlalchemy import text
    try:
        await session.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_devices_config ON devices(config_json)"
        ))
        return True
    except Exception:
        return False


# ── Migration runner ──────────────────────────────────────────────────


async def ensure_table():
    """Create the _migrations table if it doesn't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Migration.__table__.create, checkfirst=True)


async def get_applied() -> dict[str, int]:
    """Return {migration_name: batch_id} for applied migrations."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(Migration.name, Migration.batch).order_by(Migration.id)
        )
        return {row[0]: row[1] for row in result.fetchall()}


async def show_status():
    """Show migration status."""
    await ensure_table()
    applied = await get_applied()
    print(f"{'Migration':<45} {'Status':<10} {'Batch':<6}")
    print("-" * 65)
    for name, mig in MIGRATIONS.items():
        if name in applied:
            batch = applied[name]
            print(f"{name:<45} {'✅ Applied':<10} {batch:<6}")
        else:
            print(f"{name:<45} {'⬜ Pending':<10}")


async def run_up():
    """Apply all pending migrations in a single batch."""
    await ensure_table()
    applied = await get_applied()
    pending = [n for n in MIGRATIONS if n not in applied]

    if not pending:
        print("No pending migrations.")
        return

    # Determine batch number
    max_batch = max(applied.values()) if applied else 0
    batch = max_batch + 1

    async with async_session_factory() as db:
        for name in pending:
            mig = MIGRATIONS[name]
            print(f"Applying: {name}...", end=" ")
            try:
                result = await mig["up"](db)
                if result:
                    db.add(Migration(name=name, batch=batch))
                    await db.flush()
                    print("✅")
                else:
                    print("⚠️  No-op")
            except Exception as e:
                await db.rollback()
                print(f"❌ Failed: {e}")
                return
        await db.commit()
    print(f"\n✅ Applied {len(pending)} migrations (batch #{batch})")


async def run_down():
    """Rollback the last batch of migrations."""
    await ensure_table()
    applied = await get_applied()
    if not applied:
        print("No migrations to rollback.")
        return

    max_batch = max(applied.values())
    to_rollback = [n for n, b in applied.items() if b == max_batch]

    async with async_session_factory() as db:
        for name in reversed(to_rollback):
            mig = MIGRATIONS.get(name)
            down = mig.get("down") if mig else None
            if down:
                print(f"Rolling back: {name}...", end=" ")
                try:
                    await down(db)
                    await db.execute(
                        Migration.__table__.delete().where(Migration.name == name)
                    )
                    await db.flush()
                    print("✅")
                except Exception as e:
                    await db.rollback()
                    print(f"❌ Failed: {e}")
                    return
            else:
                print(f"Skipping: {name} (no downgrade)")

        await db.commit()
    print(f"\n✅ Rolled back {len(to_rollback)} migrations (batch #{max_batch})")


if __name__ == "__main__":
    if "--up" in sys.argv:
        asyncio.run(run_up())
    elif "--down" in sys.argv:
        asyncio.run(run_down())
    else:
        asyncio.run(show_status())
