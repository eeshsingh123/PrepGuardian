import os
import aiosqlite

from app.config import settings
from app.logger import logger


_connection: aiosqlite.Connection | None = None


async def connect_sqlite():
    global _connection
    db_path = settings.SQLITE_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _connection = await aiosqlite.connect(db_path)
    _connection.row_factory = aiosqlite.Row
    await _connection.execute("PRAGMA journal_mode=WAL")
    logger.info(f"SQLite initialized at '{db_path}'.")


async def close_sqlite():
    global _connection
    if _connection:
        await _connection.close()
        _connection = None
        logger.info("SQLite connection closed.")


def get_sqlite_db() -> aiosqlite.Connection:
    """
    Returns the active SQLite connection. Must be called after connect_sqlite()
    has been awaited during application startup.

    Raises:
        RuntimeError: If called before the database has been initialized.
    """
    if _connection is None:
        raise RuntimeError("SQLite is not initialized. Call connect_sqlite() first.")
    return _connection
