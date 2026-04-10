from typing import Dict, Any
import time
import datetime
from langchain_core.runnables import RunnableConfig
from ..schemas import Status
from ..state import AgentState

def result_compiler_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    start_time = time.perf_counter()
    run_id = config.get("configurable", {}).get("run_id") if config else None
    if not run_id:
        run_id = config.get("run_id") if config else None
        
    results = state.get("results", [])
    error_count = state.get("error_count", 0)
    
    handoff_required = state.get("handoff_required", False) 
    review_message = state.get("review_message", "")
    fatal_error = ""

    for r in results:
        status = r.get("status")
        task_id = r.get("task_id")
        
        if status == Status.PARTIAL.value:
            handoff_required = True
        elif status == Status.FAILED.value:
            fatal_error = f"FATAL FAIL from Task ID: {task_id}"

    if error_count >= 3:
        fatal_error = "MAX_RETRIES_EXCEEDED"

    latency_ms = int((time.perf_counter() - start_time) * 1000)
    return {
        "handoff_required": handoff_required,
        "review_message": review_message,
        "fatal_error": fatal_error,
        "telemetry_logs": [{
            "node": "result_compiler",
            "timestamp": datetime.datetime.now().isoformat(),
            "event": "COMPILE_EVAL",
            "status": "error" if fatal_error else "success",
            "latency_ms": latency_ms,
            "importance": "secondary",
            "error_summary": fatal_error if fatal_error else None,
            "langsmith_run_id": str(run_id)
        }]
    }
