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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workflow_registry (
                thread_id TEXT PRIMARY KEY,
                workflow_id TEXT,
                owner_id TEXT,
                status TEXT,
                next_task TEXT,
                process_family TEXT,
                input_request_summary TEXT,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_registry_owner_status_time 
            ON workflow_registry (owner_id, status, updated_at DESC)
        """)
        await db.commit()

async def upsert_workflow(
    thread_id: str,
    owner_id: str,
    status: str,
    workflow_id: str = "",
    next_task: str = "",
    process_family: str = "",
    input_request_summary: str = "",
    last_error: str = ""
) -> None:
    """
    워크플로우의 상태와 메타데이터를 UI/조회용 데이터베이스에 병합(Upsert)합니다.
    - 주요 변경(v5): process_family 및 input_request_summary가 함께 동기화되어 메타데이터 품질을 보증합니다.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        # Check if exists
        async with db.execute("SELECT thread_id, created_at FROM workflow_registry WHERE thread_id = ?", (thread_id,)) as cursor:
            row = await cursor.fetchone()
            
        if row is None:
            # Insert
            await db.execute("""
                INSERT INTO workflow_registry 
                (thread_id, workflow_id, owner_id, status, next_task, process_family, input_request_summary, last_error, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                thread_id, workflow_id, owner_id, status, next_task, 
                process_family, input_request_summary, last_error, now, now
            ))
        else:
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
            if last_error or last_error == "":
                updates.append("last_error = ?")
                params.append(last_error)
                
            params.append(thread_id)
            query = f"UPDATE workflow_registry SET {', '.join(updates)} WHERE thread_id = ?"
            await db.execute(query, params)
            
        await db.commit()

async def get_workflows(owner_id: str, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        query = "SELECT * FROM workflow_registry WHERE owner_id = ?"
        params = [owner_id]
        
        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)
            
        query += " ORDER BY updated_at DESC"
        
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
