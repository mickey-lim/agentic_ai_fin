from typing import Dict, Any
import time
import datetime
from langchain_core.runnables import RunnableConfig
from ..state import AgentState

def human_review_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Node acting as the designated checkpoint interrupt target.
    Extracts the externally validated interaction parameter and commits edits to state context.
    """
    start_time = time.perf_counter()
    run_id = config.get("configurable", {}).get("run_id") if config else None
    if not run_id:
        run_id = config.get("run_id") if config else None
        
    action = state.get("human_action")
    
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    telemetry = [{
        "node": "human_review",
        "timestamp": datetime.datetime.now().isoformat(),
        "event": "PROCESS_ACTION" if action else "AWAIT_ACTION",
        "status": "success",
        "latency_ms": latency_ms,
        "importance": "secondary",
        "langsmith_run_id": str(run_id)
    }]
    
    if not action:
        return {"telemetry_logs": telemetry}
        
    current_ids = state.get("reviewed_task_ids", [])
    new_ids = action.get("reviewed_task_ids", [])
    
    combined_ids = list(set(current_ids + new_ids))

    return {
        "review_message": action.get("comment", ""),
        "reviewed_task_ids": combined_ids,
        "handoff_required": action.get("decision") == "handoff",
        "telemetry_logs": telemetry
    }
