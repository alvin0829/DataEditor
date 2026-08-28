"""Database configuration and session management."""

from os import environ
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


def _database_url():
    explicit_url = environ.get("DATABASE_URL")
    if explicit_url:
        return explicit_url

    host = environ.get("POSTGRES_HOST")
    if host:
        return URL.create(
            "postgresql+asyncpg",
            username=environ.get("POSTGRES_USER", "appuser"),
            password=environ.get("POSTGRES_PASSWORD", ""),
            host=host,
            port=int(environ.get("POSTGRES_PORT", "5432")),
            database=environ.get("POSTGRES_DB", "appdb"),
        )

    return "sqlite+aiosqlite:///./dev.db"


DATABASE_URL = _database_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Yield a database session, auto-closing after use."""
    async with async_session() as session:
        yield session


async def init_db():
    """Create all tables at startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all intentionally does not alter existing PostgreSQL tables.
        # Keep the original local deployment compatible while moving RBQ No. to
        # a database-enforced unique identifier.
        if conn.dialect.name == "postgresql":
            await conn.execute(
                text("ALTER TABLE contract_services ADD COLUMN IF NOT EXISTS rbq_no VARCHAR(128)")
            )
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_contract_services_rbq_no "
                    "ON contract_services (rbq_no) WHERE rbq_no IS NOT NULL"
                )
            )
