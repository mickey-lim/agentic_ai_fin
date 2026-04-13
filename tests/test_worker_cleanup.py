import pytest
import datetime
import pathlib
import aiosqlite
from src.agentic_poc.config import settings
from src.agentic_poc.registry import init_registry, touch_file_last_used
from src.agentic_poc.application.worker_tasks import async_cleanup_artifacts

@pytest.mark.asyncio
async def test_garbage_collection_protects_recent_used_old_files():
    await init_registry()
    
    old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=8)
    old_iso = old_time.isoformat()
    
    test_file_id = "upl_gc_test"
    test_path = pathlib.Path("./artifacts/uploads/gc_test.xlsx")
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.touch()
    
    async with aiosqlite.connect(settings.REGISTRY_DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO file_registry
            (file_id, owner_id, stored_path, original_filename, size_bytes, content_type, created_at, file_hash, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (test_file_id, "test_owner", str(test_path), "fake.xlsx", 0, "text/csv", old_iso, "hash123", old_iso))
        await db.commit()
    
    await touch_file_last_used(test_file_id)
    
    deleted_count = await async_cleanup_artifacts()
    
    assert test_path.exists()
    
    async with aiosqlite.connect(settings.REGISTRY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM file_registry WHERE file_id = ?", (test_file_id,)) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            
    test_path.unlink(missing_ok=True)

@pytest.mark.asyncio
async def test_garbage_collection_protects_multi_files():
    await init_registry()
    
    old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=8)
    old_iso = old_time.isoformat()
    
    test_file_id = "upl_gc_multi_test"
    test_path = pathlib.Path("./artifacts/uploads/gc_multi_test.xlsx")
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.touch()
    
    thread_id = "thread_active_multi"
    
    async with aiosqlite.connect(settings.REGISTRY_DB_PATH) as db:
        # 1. Insert old file
        await db.execute("""
            INSERT OR REPLACE INTO file_registry
            (file_id, owner_id, stored_path, original_filename, size_bytes, content_type, created_at, file_hash, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (test_file_id, "test_owner", str(test_path), "fake.xlsx", 0, "text/csv", old_iso, "hash123", old_iso))
        
        # 2. Insert active workflow
        await db.execute("""
            INSERT OR REPLACE INTO workflow_registry
            (thread_id, owner_id, status, updated_at)
            VALUES (?, ?, ?, ?)
        """, (thread_id, "test_owner", "running", old_iso))
        
        # 3. Associate file via workflow_source_files (Multi-file schema!)
        await db.execute("DELETE FROM workflow_source_files WHERE thread_id = ?", (thread_id,))
        await db.execute("INSERT INTO workflow_source_files (thread_id, file_id, sort_order) VALUES (?, ?, 0)", (thread_id, test_file_id))
        
        await db.commit()
        
    deleted_count = await async_cleanup_artifacts()
    
    assert test_path.exists(), "The file should be protected because it's referenced in an active workflow's source_files."
    
    test_path.unlink(missing_ok=True)
