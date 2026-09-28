from pathlib import Path
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from app.storage.database import make_engine, make_session_factory
from app.storage.repository import DamRepository

FIXTURES = Path(__file__).parent / "fixtures"
BACKEND = Path(__file__).parent.parent
ROOT = BACKEND.parent


def postgres_env_file() -> Path:
    env_file = ROOT / ".env"
    if not env_file.exists():
        env_file = ROOT / ".env.example"
    return env_file


def postgres_image() -> str:
    env_file = postgres_env_file()
    values = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if line and not line.startswith("#"))
    return os.getenv("POSTGRES_IMAGE", values["POSTGRES_IMAGE"])


@pytest.fixture(scope="session")
def database_url():
    with PostgresContainer(postgres_image(), driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def alembic_config(database_url):
    config = Config(str(BACKEND / "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
        yield config
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture
async def engine(database_url, alembic_config):
    engine = make_engine(database_url)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(
                "TRUNCATE dam_prices, dam_days, dam_raw_snapshots, collection_runs RESTART IDENTITY"
            ))
        await engine.dispose()


@pytest.fixture
def sessions(engine):
    return make_session_factory(engine)


@pytest.fixture
def repository(sessions):
    return DamRepository(sessions)


@pytest.fixture
def fixture_bytes():
    def load(name: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    return load
