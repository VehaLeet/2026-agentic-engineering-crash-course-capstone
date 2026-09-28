"""Database connection configuration; secrets come only from the environment."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return url


def make_engine(url: str | None = None):
    return create_async_engine(url or database_url())


def make_session_factory(engine=None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine or make_engine(), expire_on_commit=False)
