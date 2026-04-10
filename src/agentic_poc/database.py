from contextlib import asynccontextmanager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from .config import settings

@asynccontextmanager
async def get_checkpointer():
    """
    Factory function for yielding a LangGraph Checkpointer.
    Abstracts the concrete DB implementation (currently SQLite) 
    so it can easily be swapped out for Postgres based on settings.
    """
    # Later: if settings.CHECKPOINT_DB_URL.startswith("postgresql"): ... PostgresSaver
    async with AsyncSqliteSaver.from_conn_string(settings.CHECKPOINT_DB_PATH) as memory:
        yield memory
