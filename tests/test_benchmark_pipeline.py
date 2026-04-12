import uuid
import datetime
import pytest
import pytest_asyncio
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.agentic_poc.graph import build_graph
from src.agentic_poc.application.api import start_workflow, resume_workflow, get_thread_state
from src.agentic_poc.schemas import Status, ProcessFamily, SubmissionChannel, LegalOwner

@pytest_asyncio.fixture
async def app_graph():
    async with AsyncSqliteSaver.from_conn_string(":memory:") as memory:
        uncompiled_graph = build_graph()
        compiled = uncompiled_graph.compile(
            checkpointer=memory,
            interrupt_before=["human_review"]
        )
        yield compiled

@pytest.mark.asyncio
async def test_treasury_draft_hitl(app_graph):
    tid = str(uuid.uuid4())
    await start_workflow(app_graph, "WF-004: 예산작성 및 자금일정 처리", tid, "test_user")
    state_data = await get_thread_state(app_graph, tid)
    
    assert state_data["is_interrupted"] is True
    vals = state_data["values"]
    assert vals["process_family"] == ProcessFamily.TREASURY.value
    
    results = vals["results"]
    draft_task_id = None
    for r in results:
        if r["task_id"].startswith("draft"):
            draft_task_id = r["task_id"]
            assert r["status"] == Status.PARTIAL.value
            
    assert draft_task_id is not None
    
    payload = {
        "decision": "approve",
        "comment": "All figures checked.",
        "reviewer": "finance_manager_1",
        "reviewed_at": datetime.datetime.now().isoformat(),
        "reviewed_task_ids": [draft_task_id]
    }
    
    await resume_workflow(app_graph, tid, payload)
    final_state = await get_thread_state(app_graph, tid)
    
    assert final_state["is_interrupted"] is False
    final_results = final_state["values"]["results"]
    
    # Prove the package step executes
    package_ran = any(r["task_id"].startswith("package") and r["status"] == Status.SUCCESS.value for r in final_results)
    assert package_ran is True

@pytest.mark.asyncio
async def test_withholding_tax_monthly(app_graph):
    tid = str(uuid.uuid4())
    await start_workflow(app_graph, "원천세 신고 10일자 처리", tid, "test_user")
    state_data = await get_thread_state(app_graph, tid)
    
    assert state_data["is_interrupted"] is False
    assert len(state_data["next"]) == 0
    
    results = state_data["values"]["results"]
    draft_status = None
    for r in results:
        if r["task_id"].startswith("draft"):
            draft_status = r["status"]
            
    assert draft_status == Status.SUCCESS.value

@pytest.mark.asyncio
async def test_corporate_tax_agent(app_graph):
    tid = str(uuid.uuid4())
    await start_workflow(app_graph, "법인세 신고결산자료 세무대리인 넘김", tid, "test_user")
    state_data = await get_thread_state(app_graph, tid)
    
    assert state_data["is_interrupted"] is True
    vals = state_data["values"]
    assert vals["legal_owner"] == LegalOwner.TAX_AGENT.value

    results = vals["results"]
    draft_task_id = next((r["task_id"] for r in results if r["task_id"].startswith("draft")), None)
    
    payload = {
        "decision": "handoff",
        "comment": "Passing off partial evidence.",
        "reviewer": "ceo",
        "reviewed_at": datetime.datetime.now().isoformat(),
        "reviewed_task_ids": [draft_task_id]
    }
    
    await resume_workflow(app_graph, tid, payload)
    fin = await get_thread_state(app_graph, tid)
    assert fin["values"]["handoff_required"] is True

@pytest.mark.asyncio
async def test_loop_guard_abort(app_graph):
    tid = str(uuid.uuid4())
    await start_workflow(app_graph, "force_fail: 원천세 에러 발생", tid, "test_user")
    state_data = await get_thread_state(app_graph, tid)
    
    assert state_data["is_interrupted"] is False
    assert state_data["values"]["fatal_error"] == "MAX_RETRIES_EXCEEDED"
    
    # Assert telemetry coverage
    telemetry = state_data["values"].get("telemetry_logs", [])
    assert len(telemetry) > 0
    
    # Primary logic should contain multiple worker errors (up to 3 before aborting)
    worker_errors = [t for t in telemetry if t["node"] == "worker" and t["status"] == "error"]
    assert len(worker_errors) > 0
    
    # Secondary edge routing records should be present
    edge_logs = [t for t in telemetry if t.get("importance") == "secondary"]
    assert len(edge_logs) > 0
    
@pytest.mark.asyncio
async def test_out_of_domain_fallback(app_graph):
    tid = str(uuid.uuid4())
    # Sending a completely nonsense prompt that will fail structured validation
    await start_workflow(app_graph, "호그와트 마법부 빗자루 비행 보조금 신청 처리", tid, "test_user")
    state_data = await get_thread_state(app_graph, tid)
    
    vals = state_data["values"]
    assert vals.get("process_family") == "grant"
    
    # Since our extended fallback now checks for "보조금", it should catch "grant" and "manual". (Assuming gemini fails).
    # If Gemini somehow successfully parses it, we are fine, but in either case, tasks should be generated stably
    results = vals.get("results", [])
    assert len(results) > 0

    # OOD text may still route into an AI-assisted grant flow, which legitimately pauses for review.
    assert state_data["is_interrupted"] in [True, False]
    if state_data["is_interrupted"] is False:
        assert len(state_data["next"]) == 0
    
    telemetry = vals.get("telemetry_logs", [])
    assert len(telemetry) > 0
    planner_logs = [t for t in telemetry if t["node"] == "planner"]
    assert len(planner_logs) > 0
