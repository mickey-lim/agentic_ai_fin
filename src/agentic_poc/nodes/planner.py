import uuid
import os
import time
import datetime
from typing import Dict, Any
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnableConfig

from ..schemas import ProcessFamily, SubmissionChannel, LegalOwner, AIType, TargetTier, WorkflowEnvelope
from ..state import AgentState
from ..config import settings
from src.agentic_poc.utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv()

def planner_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    start_time = time.perf_counter()
    run_id = config.get("configurable", {}).get("run_id") if config else None
    if not run_id:
        run_id = config.get("run_id") if config else None
        
    raw_req = state.get("input_request", "")
    from .middleware import pii_middleware
    req = pii_middleware.invoke(raw_req)
    workflow_id = str(uuid.uuid4())
    
    telemetry_logs = []
    
    override = state.get("process_family_override")
    
    if override and (settings.GOOGLE_API_KEY is not None):
        # Even if overriden, we can attempt to use LLM for tasks decomposition by injecting the override constraint
        pass # Wait, the requirement says "planner가 가장 먼저 override를 확인. override가 있으면 LLM/regex보다 우선 적용." 
        # But if we completely bypass LLM, we must use regex logic block to build tasks, or just let regex block use `override` instead of substring matching.
        try:
            llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
            structured_llm = llm.with_structured_output(WorkflowEnvelope)
            prompt = f"""
            You are an expert SME financial orchestrator in South Korea.
            Analyze the following user request and decompose it into exactly 4 tasks.
            
            Request: {req}
            
            Output a WorkflowEnvelope explicitly filled with tasks.
            CRITICAL ENUM CONSTRAINTS:
            - ProcessFamily: MUST BE EXACTLY ONE OF [vat, withholding, payroll, social_insurance, expense, treasury, corporate_tax, grant]
            - SubmissionChannel: MUST BE EXACTLY ONE OF [hometax, nps_edi, 4insure, tax_agent, manual]
            - LegalOwner: MUST BE EXACTLY ONE OF [manager, team_leader, ceo, tax_agent]
            - ApprovalMode: MUST BE EXACTLY ONE OF [auto_bypass, human_review, external_handoff]
            Do not invent your own values. If the request involves grants or subsidies, use ProcessFamily 'grant' and SubmissionChannel 'manual'. If payroll, use 'payroll' and 'hometax'.
            
            Always output exactly 4 tasks with the following literal task_ids:
            1. task_id: 'collect_1', task_type: 'collect', depends_on: [], ai_type: 'AI_주도', target_tier: 'low', goal: 'Gather data'
            2. task_id: 'normalize_1', task_type: 'normalize', depends_on: ['collect_1'], ai_type: 'AI_주도', target_tier: 'low', goal: 'Clean data'
            3. task_id: 'draft_1', task_type: 'draft', depends_on: ['collect_1', 'normalize_1'], target_tier: 'high', goal: 'Draft report'
               - For the draft task, set ai_type strictly: 
                 If request implies budget/treasury ("자금일정", "예산"): 'AI_보조'
                 If request implies corporate tax or tax agent ("법인세", "세무대리인"): '사람_전담'
                 Otherwise: 'AI_주도'
            4. task_id: 'package_1', task_type: 'package', depends_on: ['draft_1'], ai_type: 'AI_보조', target_tier: 'low', goal: 'Package submission'
            """
            envelope: WorkflowEnvelope = structured_llm.invoke(prompt)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            telemetry_logs.append({
                "node": "planner",
                "timestamp": datetime.datetime.now().isoformat(),
                "event": "LLM_CALL",
                "status": "success",
                "latency_ms": latency_ms,
                "importance": "primary",
                "langsmith_run_id": str(run_id)
            })
            
            return {
                "workflow_id": workflow_id,
                "tasks": [t.model_dump(mode="json") for t in envelope.tasks],
                "process_family": override if override else envelope.process_family.value,
                "submission_channel": envelope.submission_channel.value,
                "legal_owner": envelope.legal_owner.value,
                "telemetry_logs": telemetry_logs
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            err_type = type(e).__name__
            err_msg = str(e)[:250]
            
            v_errors = []
            if hasattr(e, "errors") and callable(getattr(e, "errors")):
                try:
                    for err in e.errors():
                        v_errors.append(f"{err.get('loc', [])}: {err.get('msg', '')}")
                except Exception:
                    pass
            
            telemetry_logs.append({
                "node": "planner",
                "timestamp": datetime.datetime.now().isoformat(),
                "event": "LLM_CALL",
                "status": "error",
                "latency_ms": latency_ms,
                "importance": "primary",
                "error_summary": f"[{err_type}] {err_msg}",
                "provider_status": "failed",
                "validation_path": "; ".join(v_errors)[:200],
                "langsmith_run_id": str(run_id)
            })
            
            log_ctx = {
                "owner_id": state.get("owner_id", "unknown"),
                "thread_id": config.get("configurable", {}).get("thread_id", "unknown"),
                "status": "error"
            }
            if "Validation" in err_type:
                logger.error(f"[ValidationError] Gemini Schema Validation Failed: {err_msg}", extra=log_ctx)
            elif "Quota" in err_type or "Timeout" in err_type or "API" in err_type or "Service" in err_type:
                logger.error(f"[{err_type}] Provider API Network/Quota Error: {err_msg}", extra=log_ctx)
            else:
                logger.error(f"[{err_type}] Unknown Planning Error: {err_msg}", extra=log_ctx)
            # Fallback to local regex heuristic logic below
            pass

    tasks = []
    
    t1_id = f"collect_{uuid.uuid4().hex[:8]}"
    t2_id = f"normalize_{uuid.uuid4().hex[:8]}"
    t3_id = f"draft_{uuid.uuid4().hex[:8]}"
    t4_id = f"package_{uuid.uuid4().hex[:8]}"
    
    if "WF-004" in req or "자금일정" in req:
        pf = ProcessFamily.TREASURY
        sc = SubmissionChannel.MANUAL
        lo = LegalOwner.MANAGER
        ai_t = AIType.AI_ASSISTED
    elif "원천세" in req:
        pf = ProcessFamily.WITHHOLDING
        sc = SubmissionChannel.HOMETAX
        lo = LegalOwner.MANAGER
        ai_t = AIType.AI_LED
    elif "법인세" in req:
        pf = ProcessFamily.CORPORATE_TAX
        sc = SubmissionChannel.TAX_AGENT
        lo = LegalOwner.TAX_AGENT
        ai_t = AIType.HUMAN_ONLY
    elif "자격상실" in req or "4insure" in req or "4대보험" in req:
        pf = ProcessFamily.SOCIAL_INSURANCE
        sc = SubmissionChannel.FOUR_INSURE
        lo = LegalOwner.TEAM_LEADER
        ai_t = AIType.AI_ASSISTED
    elif "지원금" in req or "보조금" in req:
        pf = ProcessFamily.GRANT
        sc = SubmissionChannel.MANUAL
        lo = LegalOwner.CEO
        ai_t = AIType.AI_ASSISTED
    elif "급여" in req or "payroll" in req:
        pf = ProcessFamily.PAYROLL
        sc = SubmissionChannel.HOMETAX
        lo = LegalOwner.MANAGER
        ai_t = AIType.AI_ASSISTED
    elif any(k in req for k in ["비용", "expense", "지출의결", "지출결의서", "영수증", "receipt", "영수"]):
        pf = ProcessFamily.EXPENSE
        sc = SubmissionChannel.MANUAL
        lo = LegalOwner.MANAGER
        ai_t = AIType.AI_ASSISTED
    else:
        pf = ProcessFamily.VAT
        sc = SubmissionChannel.HOMETAX
        lo = LegalOwner.MANAGER
        ai_t = AIType.AI_ASSISTED


    tasks.append({
        "task_id": t1_id,
        "task_type": "collect",
        "depends_on": [],
        "ai_type": AIType.AI_LED.value,
        "target_tier": TargetTier.LOW.value,
        "goal": "Gather raw data"
    })
    tasks.append({
        "task_id": t2_id,
        "task_type": "normalize",
        "depends_on": [t1_id],
        "ai_type": AIType.AI_LED.value,
        "target_tier": TargetTier.LOW.value,
        "goal": "Clean format"
    })
    tasks.append({
        "task_id": t3_id,
        "task_type": "draft",
        "depends_on": [t1_id, t2_id],
        "ai_type": ai_t.value,
        "target_tier": TargetTier.HIGH.value,
        "goal": "Reconcile and draft report"
    })
    tasks.append({
        "task_id": t4_id,
        "task_type": "package",
        "depends_on": [t3_id],
        "ai_type": ai_t.value,
        "target_tier": TargetTier.LOW.value,
        "goal": "Package for submission"
    })

    latency_ms = int((time.perf_counter() - start_time) * 1000)
    telemetry_logs.append({
        "node": "planner",
        "timestamp": datetime.datetime.now().isoformat(),
        "event": "FALLBACK_ROUTE",
        "status": "success",
        "latency_ms": latency_ms,
        "importance": "primary",
        "error_summary": None,
        "langsmith_run_id": str(run_id)
    })

    return {
        "workflow_id": workflow_id,
        "tasks": tasks,
        "process_family": override if override else pf.value,
        "submission_channel": sc.value,
        "legal_owner": lo.value,
        "telemetry_logs": telemetry_logs
    }
