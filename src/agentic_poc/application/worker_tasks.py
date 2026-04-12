from celery import shared_task
import asyncio
import datetime
import pathlib
import shutil
import nest_asyncio
from typing import List, Dict

# Apply nest_asyncio to support CELERY_TASK_ALWAYS_EAGER tests within asyncio environment
nest_asyncio.apply()

from src.agentic_poc.graph import build_graph
from src.agentic_poc.database import get_checkpointer
from src.agentic_poc.application.api import start_workflow, resume_workflow, get_thread_state
from src.agentic_poc.application.celery_app import app
from src.agentic_poc.registry import upsert_workflow
import aiosqlite
from src.agentic_poc.config import settings
from src.agentic_poc.utils.logger import get_logger

logger = get_logger(__name__)

# --- Lazy Singleton for Graph Factory ---
# We cache the uncompiled graph. The `compile` itself is O(1) and lightweight, 
# but binding the checkpointer connection safely per-async-event-loop is critical.
_uncompiled_graph = None

def get_cached_graph():
    global _uncompiled_graph
    if _uncompiled_graph is None:
        _uncompiled_graph = build_graph()
    return _uncompiled_graph

# --- Async Executors ---

async def async_start_workflow(input_request: str, thread_id: str, owner_id: str, source_file_id: str = None, process_family_override: str = None):
    # Idempotency Check
    async with aiosqlite.connect(settings.REGISTRY_DB_PATH) as db:
        async with db.execute("SELECT status FROM workflow_registry WHERE thread_id = ?", (thread_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                current_status = row[0]
                # If it's already completed or error, abort duplicated start
                if current_status in ["completed", "error"]:
                    # Already finished
                    return "ABORT_DUPLICATE_FINISHED"
                if current_status == "deleted":
                    return "ABORT_DELETED"
                if current_status == "running":
                    # Potentially currently processing by another worker. Wait, if acks_late=True, this might be a redelivery
                    # Need to check graph checkpoint to see if already passed START.
                    pass 

    async with get_checkpointer() as memory:
        graph = get_cached_graph().compile(checkpointer=memory, interrupt_before=["human_review"])
        
        # Double check checkpoint idempotency
        state = await get_thread_state(graph, thread_id)
        if state.get("values", {}).get("workflow_id"):
            # Graph already has history. This is a duplicate trigger for start.
            return "ABORT_DUPLICATE_STATE_EXISTS"

        await start_workflow(graph, input_request, thread_id, owner_id, source_file_id, process_family_override=process_family_override)
    return "SUCCESS"

async def async_resume_workflow(thread_id: str, action_data: dict, owner_id: str):
    async with get_checkpointer() as memory:
        graph = get_cached_graph().compile(checkpointer=memory, interrupt_before=["human_review"])
        
        # Idempotency Check
        state = await get_thread_state(graph, thread_id)
        
        async with aiosqlite.connect(settings.REGISTRY_DB_PATH) as db:
            async with db.execute("SELECT status FROM workflow_registry WHERE thread_id = ?", (thread_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == "deleted":
                    return "ABORT_DELETED"
        
        if not state.get("is_interrupted"):
            # Not in interrupted state. Duplicate or invalid resume.
            # The API may have preemptively set registry state to 'running', so we must revert it to true state.
            from src.agentic_poc.application.api import sync_registry_state
            await sync_registry_state(graph, thread_id)
            return "ABORT_NOT_INTERRUPTED"
            
        await resume_workflow(graph, thread_id, action_data)
    return "SUCCESS"

async def async_cleanup_artifacts():
    """
    Cleans up artifacts older than 7 days, BUT strictly limits to completed/error workflows.
    Never deletes running/interrupted workflows.
    """
    target_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
    target_iso = target_date.isoformat()
    
    deleted_count = 0
    
    async with aiosqlite.connect(settings.REGISTRY_DB_PATH) as db:
        # 1. Fetch eligible thread_ids
        async with db.execute(
            "SELECT workflow_id FROM workflow_registry WHERE status IN ('completed', 'error', 'deleted') AND updated_at < ?",
            (target_iso,)
        ) as cursor:
            rows = await cursor.fetchall()
            eligible_wids = [r[0] for r in rows if r[0]]
            
    # 2. Disk operation
    evidence_dir = pathlib.Path("./artifacts/evidence")
    package_dir = pathlib.Path("./artifacts/package")
    
    uploads_dir = pathlib.Path("./artifacts/uploads")
    
    for wid in eligible_wids:
        # evidence
        if evidence_dir.exists():
            for f in evidence_dir.glob(f"*_{wid}_*"):
                try:
                    f.unlink()
                    deleted_count += 1
                except Exception:
                    pass
            for f in evidence_dir.glob(f"report_{wid}.md"):
                try:
                    f.unlink()
                    deleted_count += 1
                except Exception:
                    pass
                    
        # package
        if package_dir.exists():
            for f in package_dir.glob(f"final_pkg_{wid}.zip"):
                try:
                    f.unlink()
                    deleted_count += 1
                except Exception:
                    pass
                    
    # 3. Clean up active file_registry records > 7 days that are not referenced in active states
    async with aiosqlite.connect(settings.REGISTRY_DB_PATH) as db:
        query = """
            SELECT file_id, stored_path 
            FROM file_registry 
            WHERE last_used_at < ? 
            AND file_id NOT IN (
                SELECT source_file_id 
                FROM workflow_registry 
                WHERE status IN ('running', 'interrupted') 
                AND source_file_id IS NOT NULL 
                AND source_file_id != ''
            )
        """
        async with db.execute(query, (target_iso,)) as cursor:
            old_files = await cursor.fetchall()
            
        for row in old_files:
            file_id, stored_path = row
            try:
                pathlib.Path(stored_path).unlink()
                deleted_count += 1
            except Exception:
                pass
            await db.execute("DELETE FROM file_registry WHERE file_id = ?", (file_id,))
        await db.commit()
                    
    return deleted_count

# --- Celery Task Wrappers ---

@app.task(bind=True, max_retries=3)
def task_start_workflow(self, input_request: str, thread_id: str, owner_id: str, source_file_id: str = None, process_family_override: str = None):
    """
    Celery task entrypoint to start a new LangGraph workflow execution.
    Runs asynchronously on Celery Worker daemon, detached from FastAPI blocking loop.
    Includes Idempotency checks to prevent duplicate graph initialization.
    """
    logger.info("Worker processing 'task_start_workflow'", extra={"thread_id": thread_id, "owner_id": owner_id, "event": "worker_start", "status": "running"})
    res = asyncio.run(async_start_workflow(input_request, thread_id, owner_id, source_file_id, process_family_override))
    logger.info("Worker completed 'task_start_workflow'", extra={"thread_id": thread_id, "owner_id": owner_id, "event": "worker_complete", "status": res})
    return res

@app.task(bind=True, max_retries=3)
def task_resume_workflow(self, thread_id: str, action_data: dict, owner_id: str):
    """
    Celery task entrypoint to resume an interrupted (HITL) workflow.
    Resolves human review actions (Approve/Reject) and pushes the graph forward.
    """
    logger.info("Worker processing 'task_resume_workflow'", extra={"thread_id": thread_id, "owner_id": owner_id, "event": "worker_resume", "status": "running"})
    res = asyncio.run(async_resume_workflow(thread_id, action_data, owner_id))
    logger.info("Worker completed 'task_resume_workflow'", extra={"thread_id": thread_id, "owner_id": owner_id, "event": "worker_complete", "status": res})
    return res

@app.task(bind=True)
def cleanup_artifacts_task(self):
    """
    Celery periodic task (Beat) for soft-triggering garbage collection.
    Removes old files that passed retention thresholds for completed/error workflows.
    """
    res = asyncio.run(async_cleanup_artifacts())
    return f"Deleted {res} stale artifacts."

async def async_purge_workflow_files(thread_ids: List[str]) -> int:
    evidence_dir = pathlib.Path("./artifacts/evidence")
    package_dir = pathlib.Path("./artifacts/package")
    deleted_count = 0
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    async with aiosqlite.connect(settings.REGISTRY_DB_PATH) as db:
        for tid in thread_ids:
            async with db.execute("SELECT workflow_id FROM workflow_registry WHERE thread_id = ?", (tid,)) as cursor:
                row = await cursor.fetchone()
                
            if row and row[0]:
                wid = row[0]
                if evidence_dir.exists():
                    for f in evidence_dir.glob(f"*_{wid}_*"):
                        try:
                            f.unlink()
                            deleted_count += 1
                        except Exception:
                            pass
                    for f in evidence_dir.glob(f"report_{wid}.md"):
                        try:
                            f.unlink()
                            deleted_count += 1
                        except Exception:
                            pass
                if package_dir.exists():
                    for f in package_dir.glob(f"final_pkg_{wid}.zip"):
                        try:
                            f.unlink()
                            deleted_count += 1
                        except Exception:
                            pass
                            
            # Update status to 'purged'
            await db.execute("""
                UPDATE workflow_registry 
                SET status = 'purged', purged_at = ? 
                WHERE thread_id = ?
            """, (now, tid))
        await db.commit()
    return deleted_count

@app.task(bind=True)
def purge_workflow_files_task(self, thread_ids: List[str]):
    """
    Celery task for executing 'Hard Purge'.
    Physically unlinks ZIP packages, evidence logs, and changes registry status to 'purged'.
    Executed completely asynchronously to prevent slow disk I/O in the frontend Batch Operations.
    """
    res = asyncio.run(async_purge_workflow_files(thread_ids))
    return f"Purged {len(thread_ids)} workflows, removed {res} files."
