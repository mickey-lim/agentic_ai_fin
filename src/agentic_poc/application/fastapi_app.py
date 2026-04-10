import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import uuid
import jwt
import asyncio
import pathlib
import pandas as pd
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.agentic_poc.config import settings
from src.agentic_poc.database import get_checkpointer

from src.agentic_poc.graph import build_graph
from src.agentic_poc.application.api import start_workflow, get_thread_state, resume_workflow
from src.agentic_poc.schemas import HumanReviewAction
from src.agentic_poc.registry import init_registry, upsert_workflow, get_workflows

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

class StartRequest(BaseModel):
    input_request: str = Field(..., max_length=15000)

@app.post("/workflows/start", status_code=202)
@limiter.limit("5/minute")
async def api_start_workflow(req: StartRequest, request: Request, background_tasks: BackgroundTasks, user: str = Depends(verify_token)):
    try:
        thread_id = str(uuid.uuid4())
        # Pass user as owner_id
        await upsert_workflow(
            thread_id=thread_id,
            owner_id=user,
            status="running",
            input_request_summary=req.input_request[:100]
        )
        background_tasks.add_task(start_workflow, request.app.state.graph, req.input_request, thread_id, user)
        return {"job_id": thread_id, "status": "accepted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/workflows")
@limiter.limit("20/minute")
async def api_list_workflows(request: Request, status: Optional[str] = None, user: str = Depends(verify_token)):
    try:
        results = await get_workflows(user, status)
        return {"workflows": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error retrieving workflows")

@app.get("/workflows/{thread_id}/state")
@limiter.limit("10/minute")
async def api_get_state(thread_id: str, request: Request, user: str = Depends(verify_token)):
    try:
        state = await get_thread_state(request.app.state.graph, thread_id)
        # Enforce thread ownership
        if state.get("values", {}).get("owner_id") != user:
            raise HTTPException(status_code=403, detail="Forbidden: Thread ownership mismatch")
        return state
    except HTTPException:
        raise
    except Exception as e:
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
        if state.get("values", {}).get("owner_id") != user:
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
        raise HTTPException(status_code=500, detail="Internal Server Error retrieving package")

@app.post("/workflows/{thread_id}/resume", status_code=202)
@limiter.limit("5/minute")
async def api_resume_workflow(thread_id: str, action_data: HumanReviewAction, request: Request, background_tasks: BackgroundTasks, user: str = Depends(verify_token)):
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
        
        background_tasks.add_task(resume_workflow, request.app.state.graph, thread_id, action_dict)
        return {"job_id": thread_id, "status": "resume_accepted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Bad Request")
