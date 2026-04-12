import aiosqlite
import pathlib
import datetime
import os
from typing import List, Dict, Any, Optional
from src.agentic_poc.config import settings

REGISTRY_DB_PATH = settings.REGISTRY_DB_PATH

async def init_registry() -> None:
    """
    Registry 데이터베이스 스키마를 초기화합니다.
    - 테이블: workflow_registry
    - 특징: docker volume 마운트로 상태 영속성을 보장하며, 복합 인덱싱을 지원합니다.
    """
    # Ensure the DB space is initialized
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workflow_registry (
                thread_id TEXT PRIMARY KEY,
                workflow_id TEXT,
                owner_id TEXT,
                status TEXT,
                next_task TEXT,
                process_family TEXT,
                input_request_summary TEXT,
                source_file_id TEXT,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_registry_owner_status_time 
            ON workflow_registry (owner_id, status, updated_at DESC)
        """)
        
        # File Source Registry (Phase 7)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_registry (
                file_id TEXT PRIMARY KEY,
                owner_id TEXT,
                stored_path TEXT,
                original_filename TEXT,
                size_bytes INTEGER,
                content_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_hash TEXT,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Backward compatibility for existing DBs
        try:
            await db.execute("ALTER TABLE workflow_registry ADD COLUMN source_file_id TEXT")
        except aiosqlite.OperationalError:
            pass # Column already exists
            
        try:
            await db.execute("ALTER TABLE file_registry ADD COLUMN file_hash TEXT")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE file_registry ADD COLUMN last_used_at TIMESTAMP")
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE workflow_registry ADD COLUMN deleted_at TIMESTAMP")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE workflow_registry ADD COLUMN deleted_by TEXT")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE workflow_registry ADD COLUMN delete_reason TEXT")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE workflow_registry ADD COLUMN previous_status TEXT")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE workflow_registry ADD COLUMN purged_at TIMESTAMP")
        except aiosqlite.OperationalError:
            pass
            
        await db.commit()

async def upsert_workflow(
    thread_id: str,
    owner_id: str,
    status: str,
    workflow_id: str = "",
    next_task: str = "",
    process_family: str = "",
    input_request_summary: str = "",
    source_file_id: str = "",
    last_error: str = ""
) -> None:
    """
    워크플로우의 상태와 메타데이터를 UI/조회용 데이터베이스에 병합(Upsert)합니다.
    - 주요 변경(v5): process_family 및 input_request_summary가 함께 동기화되어 메타데이터 품질을 보증합니다.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        # Check if exists and get current status
        async with db.execute("SELECT status, created_at FROM workflow_registry WHERE thread_id = ?", (thread_id,)) as cursor:
            row = await cursor.fetchone()
            
        if row is None:
            # Insert
            await db.execute("""
                INSERT INTO workflow_registry 
                (thread_id, workflow_id, owner_id, status, next_task, process_family, input_request_summary, source_file_id, last_error, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                thread_id, workflow_id, owner_id, status, next_task, 
                process_family, input_request_summary, source_file_id, last_error, now, now
            ))
        else:
            current_status = row[0]
            if current_status in ('deleted', 'purging', 'purged'):
                # User requested deletion/purging, so freeze the row. Do not process background worker updates.
                return

            # Update only provided non-empty fields or vital ones
            # For simplicity, coalesce or overwrite based on inputs.
            # To avoid overwriting with empty defaults on partial updates, we build dynamic query.
            updates = []
            params = []
            
            updates.append("status = ?")
            params.append(status)
            
            updates.append("updated_at = ?")
            params.append(now)
            
            if workflow_id:
                updates.append("workflow_id = ?")
                params.append(workflow_id)
            if next_task or next_task == "":  # Allow clearing next_task
                updates.append("next_task = ?")
                params.append(next_task)
            if process_family:
                updates.append("process_family = ?")
                params.append(process_family)
            if input_request_summary:
                updates.append("input_request_summary = ?")
                params.append(input_request_summary)
            if source_file_id:
                updates.append("source_file_id = ?")
                params.append(source_file_id)
            if last_error or last_error == "":
                updates.append("last_error = ?")
                params.append(last_error)
                
            params.append(thread_id)
            query = f"UPDATE workflow_registry SET {', '.join(updates)} WHERE thread_id = ?"
            await db.execute(query, params)
            
        await db.commit()

async def get_workflow_metrics(owner_id: str) -> Dict[str, int]:
    """Retrieve summarized counts of workflows for the dashboard KPI bar."""
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        query = "SELECT status, COUNT(*) as count FROM workflow_registry WHERE owner_id = ? AND status NOT IN ('purged', 'purging') GROUP BY status"
        async with db.execute(query, (owner_id,)) as cursor:
            rows = await cursor.fetchall()
            
        metrics = {
            "total": 0,
            "running": 0,
            "interrupted": 0,
            "completed": 0,
            "error": 0,
            "deleted": 0
        }
        
        for row in rows:
            status, count = row[0], row[1]
            if status == "deleted":
                metrics["deleted"] += count
            else:
                metrics["total"] += count
                if status == "running":
                    metrics["running"] += count
                elif status == "interrupted":
                    metrics["interrupted"] += count
                elif status == "completed":
                    metrics["completed"] += count
                elif status in ("error", "queue_error"):
                    metrics["error"] += count
                    
        return metrics

async def get_workflows(owner_id: str, status_filter: Optional[str] = None, limit: int = 50, cursor: Optional[str] = None, include_deleted: bool = False) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        query = "SELECT * FROM workflow_registry WHERE owner_id = ?"
        params = [owner_id]
        
        if not include_deleted:
            query += " AND status NOT IN ('deleted', 'purging', 'purged')"
            
        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)
            
        if cursor:
            # Decode cursor (format: 'updated_at_iso|thread_id')
            parts = cursor.split('|', 1)
            if len(parts) == 2:
                c_updated_at, c_thread_id = parts
                query += " AND (updated_at < ? OR (updated_at = ? AND thread_id < ?))"
                params.extend([c_updated_at, c_updated_at, c_thread_id])
                
        query += " ORDER BY updated_at DESC, thread_id DESC LIMIT ?"
        params.append(limit)
        
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def soft_delete_workflow(thread_id: str, owner_id: str, reason: str = "User deleted via UI") -> bool:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        # Enforce ownership explicitly before updating because we need to check 'running' status
        async with db.execute("SELECT status FROM workflow_registry WHERE thread_id = ? AND owner_id = ?", (thread_id, owner_id)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            if row[0] == 'running':
                # Allow deletion even if running to clear stuck items
                pass

        # Set status = 'deleted' and previous_status = current status
        cursor = await db.execute("""
            UPDATE workflow_registry
            SET previous_status = status, status = 'deleted', deleted_at = ?, deleted_by = ?, delete_reason = ?, updated_at = ?
            WHERE thread_id = ? AND owner_id = ?
        """, (now, owner_id, reason, now, thread_id, owner_id))
        await db.commit()
        return cursor.rowcount > 0

async def restore_workflow(thread_id: str, owner_id: str) -> bool:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE workflow_registry
            SET status = CASE WHEN previous_status = 'running' THEN 'interrupted' ELSE COALESCE(previous_status, 'completed') END, 
                previous_status = NULL, 
                deleted_at = NULL, 
                deleted_by = NULL, 
                delete_reason = NULL, 
                updated_at = ?
            WHERE thread_id = ? AND owner_id = ? AND status = 'deleted'
        """, (now, thread_id, owner_id))
        await db.commit()
        return cursor.rowcount > 0

async def batch_operate_workflows(thread_ids: List[str], owner_id: str, action: str) -> List[Dict[str, str]]:
    """
    배치 작업을 실행합니다.
    action: 'delete' | 'restore' | 'purge'
    결과 반환: [{"thread_id": "...", "status": "ok" | "skipped" | "forbidden", "reason": "..."}, ...]
    """
    if not thread_ids:
        return []

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    results = []
    
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        for tid in thread_ids:
            # 1. Fetch current status & ownership
            async with db.execute("SELECT status FROM workflow_registry WHERE thread_id = ? AND owner_id = ?", (tid, owner_id)) as cursor:
                row = await cursor.fetchone()
                
            if not row:
                results.append({"thread_id": tid, "status": "forbidden", "reason": "Not found or ownership mismatch"})
                continue
                
            current_status = row[0]
            
            if action == 'delete':
                if current_status in ('deleted', 'purging', 'purged'):
                    results.append({"thread_id": tid, "status": "skipped", "reason": f"Already {current_status}"})
                else:
                    await db.execute("""
                        UPDATE workflow_registry
                        SET previous_status = status, status = 'deleted', deleted_at = ?, deleted_by = ?, updated_at = ?
                        WHERE thread_id = ?
                    """, (now, owner_id, now, tid))
                    results.append({"thread_id": tid, "status": "ok"})
                    
            elif action == 'restore':
                if current_status != 'deleted':
                    results.append({"thread_id": tid, "status": "skipped", "reason": f"Cannot restore from {current_status}"})
                else:
                    await db.execute("""
                        UPDATE workflow_registry
                        SET status = CASE WHEN previous_status = 'running' THEN 'interrupted' ELSE COALESCE(previous_status, 'completed') END, 
                            previous_status = NULL, deleted_at = NULL, deleted_by = NULL, delete_reason = NULL, updated_at = ?
                        WHERE thread_id = ?
                    """, (now, tid))
                    results.append({"thread_id": tid, "status": "ok"})
                    
            elif action == 'purge':
                if current_status != 'deleted':
                    results.append({"thread_id": tid, "status": "skipped", "reason": f"Only deleted workflows can be purged (current: {current_status})"})
                else:
                    await db.execute("""
                        UPDATE workflow_registry
                        SET status = 'purging', updated_at = ?
                        WHERE thread_id = ?
                    """, (now, tid))
                    results.append({"thread_id": tid, "status": "ok"})
            else:
                results.append({"thread_id": tid, "status": "skipped", "reason": "Unknown action"})
                
        await db.commit()
    return results

async def register_file_metadata(
    file_id: str,
    owner_id: str,
    stored_path: str,
    original_filename: str,
    size_bytes: int,
    content_type: str,
    file_hash: str
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        await db.execute("""
            INSERT INTO file_registry
            (file_id, owner_id, stored_path, original_filename, size_bytes, content_type, created_at, file_hash, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (file_id, owner_id, stored_path, original_filename, size_bytes, content_type, now, file_hash, now))
        await db.commit()

async def get_file_by_hash(owner_id: str, file_hash: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM file_registry WHERE owner_id = ? AND file_hash = ? ORDER BY created_at DESC LIMIT 1", (owner_id, file_hash)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

async def touch_file_last_used(file_id: str) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        await db.execute("UPDATE file_registry SET last_used_at = ? WHERE file_id = ?", (now, file_id))
        await db.commit()

async def get_recent_uploads(owner_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Omitting stored_path in the projection
        query = """
            SELECT file_id, original_filename, size_bytes, content_type, created_at, last_used_at 
            FROM file_registry 
            WHERE owner_id = ? 
            ORDER BY last_used_at DESC 
            LIMIT ?
        """
        async with db.execute(query, (owner_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_file_metadata(file_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM file_registry WHERE file_id = ?", (file_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
