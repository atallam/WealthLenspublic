"""
WealthLens OSS — Database Engine & Session Management (production-grade)

Scaling strategy:
  ┌────────────────────────────────────────────────────────────────────┐
  │  SQLite (dev)     │  PostgreSQL (prod)   │  PostgreSQL (scaled)   │
  │  0-50 families    │  50-2000 families    │  2000+ families        │
  │  Single file      │  Tuned pool + idx    │  + PgBouncer + replica │
  └────────────────────────────────────────────────────────────────────┘

Connection pooling:
  - SQLAlchemy QueuePool with configurable size
  - Pre-ping: detect stale connections
  - Overflow: burst capacity for price refresh spikes
  - Recycle: prevent connection aging issues

Indexes (for encrypted-data model):
  - user_id on every table (tenant isolation)
  - user_id + asset_type (holdings filter without decryption)
  - user_id + member_id (member filter without decryption)
  - holding_id (transaction/artifact lookup)
  - email UNIQUE (login lookup)
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

# ─── Engine configuration by DB type ───

connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,  # Detect dead connections before use
    "echo": settings.ENVIRONMENT == "development",
}

if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite: single-writer, fine for dev and small deployments
    connect_args = {"check_same_thread": False}
    engine_kwargs["pool_size"] = 1
    engine_kwargs["max_overflow"] = 0
else:
    # PostgreSQL: production pool settings
    engine_kwargs.update({
        "pool_size": int(getattr(settings, 'DB_POOL_SIZE', 10)),      # Steady-state connections
        "max_overflow": int(getattr(settings, 'DB_MAX_OVERFLOW', 20)), # Burst (price refresh spikes)
        "pool_timeout": 30,     # Wait max 30s for a connection
        "pool_recycle": 1800,   # Recycle connections after 30min (prevents stale)
    })

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)


# ─── SQLite performance tuning (WAL mode, pragmas) ───

@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Tune SQLite for concurrent reads (WAL mode)."""
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")       # Write-Ahead Logging: concurrent readers
        cursor.execute("PRAGMA synchronous=NORMAL")      # Faster writes, still crash-safe
        cursor.execute("PRAGMA cache_size=-64000")        # 64MB page cache
        cursor.execute("PRAGMA foreign_keys=ON")          # Enforce FK constraints
        cursor.execute("PRAGMA busy_timeout=5000")        # Wait 5s on lock instead of failing
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called on startup."""
    Base.metadata.create_all(bind=engine)

    # Log pool stats
    pool = engine.pool
    pool_info = f"pool_size={pool.size()}, overflow={pool.overflow()}" if hasattr(pool, 'size') else "SQLite (single)"
    print(f"   DB Pool: {pool_info}")


def get_pool_status() -> dict:
    """Return connection pool statistics (for /api/health)."""
    pool = engine.pool
    if hasattr(pool, 'size'):
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "max_overflow": engine_kwargs.get("max_overflow", 0),
        }
    return {"type": "sqlite", "pool_size": 1}
