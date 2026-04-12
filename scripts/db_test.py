import sqlite3
from src.agentic_poc.config import settings

with sqlite3.connect(settings.REGISTRY_DB_PATH) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM file_registry")
    print(cursor.fetchall())
