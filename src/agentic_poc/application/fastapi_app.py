import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Response, Depends, UploadFile, File, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import uuid
import jwt
import asyncio
import aiosqlite
import pathlib
import pandas as pd
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.agentic_poc.config import settings
from src.agentic_poc.database import get_checkpointer

from src.agentic_poc.graph import build_graph
from src.agentic_poc.application.api import get_thread_state
from src.agentic_poc.schemas import HumanReviewAction
from src.agentic_poc.registry import init_registry, upsert_workflow, get_workflows, register_file_metadata, get_file_metadata, get_file_by_hash, touch_file_last_used

import traceback
from src.agentic_poc.utils.logger import get_logger

logger = get_logger(__name__)
# SECURITY
JWT_SECRET = settings.JWT_SECRET
if not JWT_SECRET:
    raise RuntimeError("CRITICAL: JWT_SECRET environment variable is not set. Refusing to start.")

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize separate workflow registry index
    await init_registry()
    
    # Setup Checkpointer via Factory
    async with get_checkpointer() as memory:
        uncompiled_graph = build_graph()
        app.state.graph = uncompiled_graph.compile(
            checkpointer=memory,
            interrupt_before=["human_review"]
        )
        yield
    # connection auto-closes on yield exit

app = FastAPI(title="Agentic PoC Control Plane API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from pydantic import BaseModel, Field

class ResumeRequest(BaseModel):
    user_review: str
    approved: bool

class BatchActionRequest(BaseModel):
    action: str  # 'delete', 'restore', 'purge'
    thread_ids: List[str]

router = APIRouter()

class StartRequest(BaseModel):
    input_request: str = Field(..., max_length=15000)
    source_file_ids: Optional[List[str]] = Field(default_factory=list, description="Opaque identifier of uploaded file")
    process_family_override: Optional[str] = Field(None, description="Manual domain override")

class FileUploadResponse(BaseModel):
    file_id: str
    filename: str

ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
    "text/csv",
    "application/pdf",
    "image/jpeg",
    "image/png"
}
MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB

@app.post("/workflows/upload", response_model=FileUploadResponse, status_code=201)
@limiter.limit("10/minute")
async def api_upload_file(request: Request, file: UploadFile = File(...), user: str = Depends(verify_token)):
    ext = file.filename.lower()
    
    logger.info(f"UPLOAD RECEIVED: filename={file.filename}, content_type={file.content_type}")
    
    if file.content_type not in ALLOWED_MIME_TYPES:
        logger.error(f"Invalid MIME type: {file.content_type} for file {file.filename}")
        raise HTTPException(status_code=400, detail=f"Invalid MIME type: {file.content_type}. Excel, CSV, PDF and Image receipts (.jpg, .png) are allowed.")
        
    if not (ext.endswith(".xlsx") or ext.endswith(".csv") or ext.endswith(".pdf") or ext.endswith(".jpg") or ext.endswith(".jpeg") or ext.endswith(".png")):
        logger.error(f"Invalid extension for file {file.filename}")
        raise HTTPException(status_code=400, detail=f"Invalid extension. Only .xlsx, .csv, .pdf, .jpg, .jpeg, .png are allowed.")
    
    file_id = f"upl_{uuid.uuid4()}"
    uploads_dir = pathlib.Path("./artifacts/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    import re
    safe_name = pathlib.Path(file.filename).name
    safe_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', safe_name)
    stored_path = uploads_dir / f"{file_id}_{safe_name}"
    size_bytes = 0
    
    import hashlib
    hasher = hashlib.sha256()

    with open(stored_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            size_bytes += len(chunk)
            if size_bytes > MAX_FILE_SIZE:
                stored_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large (Max 10MB)")
            hasher.update(chunk)
            buffer.write(chunk)
            
    file_hash = hasher.hexdigest()
    
    # Duplicate Verification Cache Layer
    existing_file = await get_file_by_hash(user, file_hash)
    if existing_file:
        stored_path.unlink(missing_ok=True)
        await touch_file_last_used(existing_file["file_id"])
        return {"file_id": existing_file["file_id"], "filename": existing_file["original_filename"]}
            
    # Register metadata for ownership and processing
    await register_file_metadata(
        file_id=file_id,
        owner_id=user,
        stored_path=str(stored_path),
        original_filename=file.filename,
        size_bytes=size_bytes,
        content_type=file.content_type,
        file_hash=file_hash
    )
    
    return {"file_id": file_id, "filename": file.filename}

@app.get("/workflows/uploads", status_code=200)
@limiter.limit("20/minute")
async def api_get_uploads(response: Response, request: Request, user: str = Depends(verify_token)):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    try:
        from src.agentic_poc.registry import get_recent_uploads
        uploads = await get_recent_uploads(user)
        return {"uploads": uploads}
    except Exception as e:
        import traceback; traceback.print_exc()
        logger.error("UPLOAD ERROR", exc_info=True, extra={"owner_id": user, "status": "error"})
        raise HTTPException(status_code=500, detail="Internal Server Error retrieving uploads")

@app.post("/workflows/start", status_code=202)
@limiter.limit("5/minute")
async def api_start_workflow(req: StartRequest, request: Request, user: str = Depends(verify_token)):
    try:
        # Validate file ownership if source_file_id provided
        if req.source_file_ids:
            f_metas = [await get_file_metadata(fid) for fid in req.source_file_ids]
            if not all(f_metas):
                 raise HTTPException(status_code=404, detail="Source file not found")
            if any(f["owner_id"] != user for f in f_metas if f):
                 raise HTTPException(status_code=403, detail="Forbidden: File ownership mismatch")
            
            # UX Patch: Update last_used_at when explicitely starting a workflow with an existing file
            for fid in req.source_file_ids:
                await touch_file_last_used(fid)
                 
        thread_id = str(uuid.uuid4())
        # Pass user as owner_id
        await upsert_workflow(
            thread_id=thread_id,
            owner_id=user,
            status="running",
            input_request_summary=req.input_request[:100],
            source_file_ids=req.source_file_ids if req.source_file_ids else []
        )
        # Dispatch via Celery
        try:
            from src.agentic_poc.application.worker_tasks import task_start_workflow
            task_start_workflow.delay(req.input_request, thread_id, user, req.source_file_ids, req.process_family_override)
        except Exception as queue_err:
            await upsert_workflow(
                thread_id=thread_id,
                owner_id=user,
                status="queue_error",
                last_error=f"Queue fallback: {str(queue_err)}"
            )
            # Re-raise so the API explicitly returns 500
            raise HTTPException(status_code=500, detail="Failed to enqueue workflow")

        return {"job_id": thread_id, "status": "accepted"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/workflows", status_code=200)
@limiter.limit("20/minute")
async def api_list_workflows(
    response: Response,
    request: Request, 
    status: Optional[str] = None, 
    limit: int = 50, 
    cursor: Optional[str] = None, 
    include_deleted: bool = False,
    user: str = Depends(verify_token)
):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    try:
        results = await get_workflows(user, status, limit, cursor, include_deleted=include_deleted)
        
        # Determine next cursor
        next_cursor = None
        if len(results) == limit:
            last_item = results[-1]
            next_cursor = f"{last_item['updated_at']}|{last_item['thread_id']}"
            
        return {"workflows": results, "next_cursor": next_cursor}
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error retrieving workflows")

@app.get("/workflows/metrics", status_code=200)
@limiter.limit("20/minute")
async def api_get_workflow_metrics(request: Request, response: Response, user: str = Depends(verify_token)):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    try:
        from src.agentic_poc.registry import get_workflow_metrics
        metrics = await get_workflow_metrics(user)
        return metrics
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error retrieving workflow metrics")

@app.delete("/workflows/{thread_id}", status_code=200)
@limiter.limit("10/minute")
async def api_delete_workflow(thread_id: str, request: Request, user: str = Depends(verify_token)):
    try:
        from src.agentic_poc.registry import soft_delete_workflow
        # Fast path check via SQLite ownership implicit update
        success = await soft_delete_workflow(thread_id, user, "User deleted via UI")
        if not success:
            raise HTTPException(status_code=403, detail="Forbidden or Not Found: Thread ownership mismatch")
            
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        logger.error("DELETE ERROR", exc_info=True, extra={"thread_id": thread_id, "owner_id": user, "status": "error"})
        raise HTTPException(status_code=500, detail="Internal Server Error during deletion")

@app.post("/workflows/{thread_id}/restore", status_code=200)
@limiter.limit("10/minute")
async def api_restore_workflow(thread_id: str, request: Request, user: str = Depends(verify_token)):
    try:
        from src.agentic_poc.registry import restore_workflow
        
        success = await restore_workflow(thread_id, user)
        if not success:
            raise HTTPException(status_code=403, detail="Forbidden or Not Found: Thread ownership mismatch or not deleted")
            
        return {"status": "restored"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        logger.error("RESTORE ERROR", exc_info=True, extra={"thread_id": thread_id, "owner_id": user, "status": "error"})
        raise HTTPException(status_code=500, detail="Internal Server Error during restore")

@app.post("/workflows/batch", status_code=200)
@limiter.limit("5/minute")
async def api_batch_operations(req: BatchActionRequest, request: Request, user: str = Depends(verify_token)):
    """
    Unified Batch API for 'delete', 'restore', and 'purge' actions. 
    Handles maximum 100 threads per call. Relegates physical file removal for 'purge' to Celery workers.
    """
    if len(req.thread_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 thread_ids allowed per batch")
    if req.action not in ("delete", "restore", "purge"):
        raise HTTPException(status_code=400, detail="Invalid action")
        
    try:
        from src.agentic_poc.registry import batch_operate_workflows
        from src.agentic_poc.application.worker_tasks import purge_workflow_files_task
        
        results = await batch_operate_workflows(req.thread_ids, user, req.action)
        
        # If purge action, we must trigger asynchronous cleanup for successfully transitioned items
        if req.action == 'purge':
            purging_ids = [res["thread_id"] for res in results if res["status"] == "ok"]
            if purging_ids:
                purge_workflow_files_task.delay(purging_ids)
                
        return {"results": results}
    except Exception as e:
        import traceback; traceback.print_exc()
        logger.error("BATCH ERROR", exc_info=True, extra={"owner_id": user, "status": "error"})
        raise HTTPException(status_code=500, detail="Internal Server Error during batch operation")

@app.get("/workflows/{thread_id}/state")
@limiter.limit("10/minute")
async def api_get_state(thread_id: str, request: Request, response: Response, user: str = Depends(verify_token)):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    try:
        state = await get_thread_state(request.app.state.graph, thread_id)
        # Enforce thread ownership
        current_owner = state.get("values", {}).get("owner_id")
        if not current_owner:
            from src.agentic_poc.registry import REGISTRY_DB_PATH
            import aiosqlite
            async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
                async with db.execute("SELECT owner_id FROM workflow_registry WHERE thread_id = ?", (thread_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        current_owner = row[0]
                        
        if current_owner != user:
            raise HTTPException(status_code=403, detail="Forbidden: Thread ownership mismatch")
        return state
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=404, detail="State not found")

@app.get("/workflows/{thread_id}/evidence")
@limiter.limit("20/minute")
async def api_get_evidence(thread_id: str, request: Request, user: str = Depends(verify_token)):
    """
    현재 워크플로우 과정에서 수집/정규화된 엑셀 데이터의 프리뷰를 반환합니다.
    - 성능 및 방어: asyncio.to_thread로 I/O 병목을 제거하며, 최대 100행(head)만 반환하여 
      가벼운 JSON 응답과 프론트엔드 OOM을 방지합니다. 원본은 별도 ZIP으로 제공됩니다.
    """
    try:
        # Enforce thread ownership
        state = await get_thread_state(request.app.state.graph, thread_id)
        current_owner = state.get("values", {}).get("owner_id")
        if not current_owner:
            from src.agentic_poc.registry import REGISTRY_DB_PATH
            import aiosqlite
            async with aiosqlite.connect(REGISTRY_DB_PATH) as db:
                async with db.execute("SELECT owner_id FROM workflow_registry WHERE thread_id = ?", (thread_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        current_owner = row[0]
                        
        if current_owner != user:
            raise HTTPException(status_code=403, detail="Forbidden: Thread ownership mismatch")
        
        workflow_id = state.get("values", {}).get("workflow_id")
        if not workflow_id:
            raise HTTPException(status_code=400, detail="Workflow ID missing in state")

        evidence_dir = pathlib.Path("./artifacts/evidence")
        matches = list(evidence_dir.glob(f"*_{workflow_id}_norm.xlsx"))
        if not matches:
             matches = list(evidence_dir.glob(f"*_{workflow_id}_raw.xlsx"))

        if not matches:
             raise HTTPException(status_code=404, detail="No evidence artifact found for this workflow")
        
        target = matches[-1] # if multiple generated, get the newest logic
        df = await asyncio.to_thread(pd.read_excel, target)
        df.fillna("", inplace=True) # Ensure JSON safety for NaN
        
        # Security/Perf: Preview row limit to prevent excessive JSON bloating
        data = df.head(100).to_dict(orient="records")
        res = {"filename": target.name, "rows": data}
        
        drafts = list(evidence_dir.glob(f"*_{workflow_id}_draft.json"))
        if drafts:
            import json
            with open(drafts[-1], "r") as f:
                res["draft_summary"] = json.load(f)
                
        reports = list(evidence_dir.glob(f"report_{workflow_id}.md"))
        if reports:
            with open(reports[-1], "r") as f:
                res["report_md"] = f.read()

        return res

    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error retrieving evidence")

from fastapi.responses import FileResponse
@app.get("/workflows/{thread_id}/download")
@limiter.limit("5/minute")
async def api_download_package(thread_id: str, request: Request, user: str = Depends(verify_token)):
    try:
        state = await get_thread_state(request.app.state.graph, thread_id)
        if state.get("values", {}).get("owner_id") != user:
            raise HTTPException(status_code=403, detail="Forbidden: Thread ownership mismatch")
            
        workflow_id = state.get("values", {}).get("workflow_id")
        package_dir = pathlib.Path("./artifacts/package")
        package_file = package_dir / f"final_pkg_{workflow_id}.zip"
        
        if not package_file.exists():
            raise HTTPException(status_code=404, detail="Package zip not found")
            
        return FileResponse(path=package_file, filename=package_file.name, media_type="application/zip")
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error retrieving package")

@app.post("/workflows/{thread_id}/resume", status_code=202)
@limiter.limit("5/minute")
async def api_resume_workflow(thread_id: str, action_data: HumanReviewAction, request: Request, user: str = Depends(verify_token)):
    try:
        # Check ownership before queueing
        state = await get_thread_state(request.app.state.graph, thread_id)
        if state.get("values", {}).get("owner_id") != user:
            raise HTTPException(status_code=403, detail="Forbidden: Thread ownership mismatch")
            
        action_dict = action_data.model_dump()
        
        # Pre-update status before background execution
        await upsert_workflow(
            thread_id=thread_id,
            owner_id=user,
            status="running"
        )
        
        # Dispatch via Celery
        try:
            from src.agentic_poc.application.worker_tasks import task_resume_workflow
            task_resume_workflow.delay(thread_id, action_dict, user)
        except Exception as queue_err:
            await upsert_workflow(
                thread_id=thread_id,
                owner_id=user,
                status="queue_error",
                last_error=f"Queue fallback: {str(queue_err)}"
            )
            raise HTTPException(status_code=500, detail="Failed to enqueue resume task")
        
        return {"job_id": thread_id, "status": "resume_accepted"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        logger.error("RESUME ERROR", exc_info=True, extra={"thread_id": thread_id, "owner_id": user, "status": "error"})
        raise HTTPException(status_code=400, detail=f"Bad Request: {str(e)}")
