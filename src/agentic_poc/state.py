from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

def keep_last_50_logs(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not a: a = []
    if not b: b = []
    return (a + b)[-50:]


class AgentState(TypedDict):
    """
    Standardizes on pure Py-native Dicts for inner task tracking 
    to bypass arbitrary MemorySaver pydantic deserialization issues.
    """
    input_request: str
    owner_id: str
    workflow_id: str
    process_family: str
    submission_channel: str
    legal_owner: str
    tasks: List[Dict[str, Any]]
    results: Annotated[List[Dict[str, Any]], operator.add]
    error_count: int
    handoff_required: bool
    review_message: str
    fatal_error: str
    
    # Telemetry
    metrics: Dict[str, Any]
    telemetry_logs: Annotated[List[Dict[str, Any]], keep_last_50_logs]
    reviewed_task_ids: List[str]
    human_action: Optional[Dict[str, Any]]
