from typing import Dict, Any, Optional, List
from ..schemas import HumanReviewAction
from ..registry import upsert_workflow, init_registry

async def sync_registry_state(app_graph, thread_id: str) -> None:
    """
    LangGraph의 내부 상태를 추출하여 가벼운 Registry DB에 동기화합니다.
    - 주요 변경(v5): process_family 와 input_request_summary (100자 헤드)를 병합하여 UI 품질을 향상합니다.
    """
    # Ensure initialized (prevents crash in CLI tests that skip fastapi lifecycle)
    await init_registry()
    
    state = await get_thread_state(app_graph, thread_id)
    vals = state["values"]
    
    status = "completed"
    if state["is_interrupted"]:
        status = "interrupted"
    elif vals.get("fatal_error"):
        status = "error"
        
    await upsert_workflow(
        thread_id=thread_id,
        owner_id=vals.get("owner_id", ""),
        status=status,
        workflow_id=vals.get("workflow_id", ""),
        next_task=state["next"][0] if state["next"] else "",
        process_family=vals.get("process_family", ""),
        input_request_summary=vals.get("input_request", "")[:100],
        last_error=vals.get("fatal_error", "")
    )

async def start_workflow(app_graph, input_request: str, thread_id: str, owner_id: str, source_file_ids: List[str] = None, **kwargs) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "input_request": input_request,
        "owner_id": owner_id,
        "workflow_id": "",
        "process_family": "",
        "submission_channel": "",
        "legal_owner": "",
        "source_file_ids": source_file_ids if source_file_ids is not None else [],
        "process_family_override": kwargs.get("process_family_override"),
        "tasks": [],
        "results": [],
        "error_count": 0,
        "handoff_required": False,
        "review_message": "",
        "fatal_error": "",
        "metrics": {},
        "telemetry_logs": [],
        "reviewed_task_ids": [],
        "human_action": None
    }
    
    # We can inject a specific run_id for LangSmith correlation
    import uuid
    run_id = str(uuid.uuid4())
    config["run_id"] = run_id
    
    await app_graph.ainvoke(initial_state, config=config)
    await sync_registry_state(app_graph, thread_id)

async def get_thread_state(app_graph, thread_id: str) -> Dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    state_tuple = await app_graph.aget_state(config)
    
    if not state_tuple:
        return {"is_interrupted": False, "values": {"results": []}, "next": []}
        
    res = {
        "is_interrupted": len(state_tuple.next) > 0 and "human_review" in state_tuple.next,
        "values": state_tuple.values,
        "next": state_tuple.next
    }
    return res

async def resume_workflow(app_graph, thread_id: str, action_data: Optional[Dict[str, Any]] = None) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    if action_data:
        # Strict Schema Boundary Validation
        validated_action = HumanReviewAction(**action_data)
        # Update thread state with pure JSON-safe dict representation
        await app_graph.aupdate_state(config, {"human_action": validated_action.model_dump(mode="json")})
        
    import uuid
    run_id = str(uuid.uuid4())
    config["run_id"] = run_id
    
    await app_graph.ainvoke(None, config=config)
    await sync_registry_state(app_graph, thread_id)
