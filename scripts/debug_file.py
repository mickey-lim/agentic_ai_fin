import sqlite3
import os
def check():
    db_path = "test_agentic_poc.db"
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        return
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, stored_path FROM file_registry")
        rows = cursor.fetchall()
        print("file_registry rows:", rows)
check()
