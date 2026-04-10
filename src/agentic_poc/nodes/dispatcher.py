from typing import Dict, Any, Literal
import time
import datetime
from langchain_core.runnables import RunnableConfig
from ..state import AgentState
from ..schemas import Status

def dispatcher_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    start_time = time.perf_counter()
    run_id = config.get("configurable", {}).get("run_id") if config else None
    if not run_id:
        run_id = config.get("run_id") if config else None
        
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    return {
        "telemetry_logs": [{
            "node": "dispatcher",
            "timestamp": datetime.datetime.now().isoformat(),
            "event": "ROUTE_EVAL",
            "status": "success",
            "latency_ms": latency_ms,
            "importance": "secondary",
            "langsmith_run_id": str(run_id)
        }]
    }

def route_dispatcher(state: AgentState) -> Literal["worker", "human_review", "result_compiler"]:
    error_count = state.get("error_count", 0)
    if error_count >= 3:
        return "result_compiler"
        
    tasks = state.get("tasks", [])
    results = state.get("results", [])
    completed = {r["task_id"]: r["status"] for r in results}
    
    # Are there any new partial results waiting for review?
    reviewed_ids = state.get("reviewed_task_ids", [])
    for r in results:
        if r["status"] == Status.PARTIAL.value and r["task_id"] not in reviewed_ids:
            return "human_review"
            
    if any(st == Status.FAILED.value for st in completed.values()):
        return "result_compiler"
        
    for task in tasks:
        if task["task_id"] not in completed:
            deps_met = True
            for d in task.get("depends_on", []):
                dep_status = completed.get(d)
                
                # Exceptions logic
                if task["task_type"] == "package" and dep_status == Status.PARTIAL.value:
                    pass 
                elif dep_status != Status.SUCCESS.value:
                    deps_met = False
                    break
            
            if deps_met:
                return "worker"
                
    return "result_compiler"
