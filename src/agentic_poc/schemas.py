from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# Core AI Enums
class AIType(str, Enum):
    AI_LED = "AI_주도"
    AI_ASSISTED = "AI_보조"
    HUMAN_ONLY = "사람_전담"

class TargetTier(str, Enum):
    HIGH = "high"
    LOW = "low"
    HUMAN = "human"

class WorkflowTemplate(str, Enum):
    TEMPLATE_A = "AI_자동집계_승인"       
    TEMPLATE_B = "AI_누락탐지_보정"       
    TEMPLATE_C = "담당자_직접처리_보고"   
    TEMPLATE_D = "담당자_수집처리_보고"   

# Korean SME specific Operational Enums
class ProcessFamily(str, Enum):
    VAT = "vat"
    WITHHOLDING = "withholding"
    PAYROLL = "payroll"
    SOCIAL_INSURANCE = "social_insurance"
    EXPENSE = "expense"
    TREASURY = "treasury"
    CORPORATE_TAX = "corporate_tax"
    GRANT = "grant"
    UNKNOWN = "unknown"

class SubmissionChannel(str, Enum):
    HOMETAX = "hometax"
    NPS_EDI = "nps_edi"
    FOUR_INSURE = "4insure"
    TAX_AGENT = "tax_agent"
    MANUAL = "manual"

class LegalOwner(str, Enum):
    MANAGER = "manager"
    TEAM_LEADER = "team_leader"
    CEO = "ceo"
    TAX_AGENT = "tax_agent"

class ApprovalMode(str, Enum):
    AUTO_BYPASS = "auto_bypass"
    HUMAN_REVIEW = "human_review"
    EXTERNAL_HANDOFF = "external_handoff"

class Status(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"

class TaskEnvelope(BaseModel):
    task_id: str
    task_type: str = Field(description="collect|normalize|draft|package|compute")
    depends_on: List[str] = Field(default_factory=list)
    ai_type: AIType
    target_tier: TargetTier
    goal: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    tools_allowed: List[str] = Field(default_factory=list)

class WorkflowEnvelope(BaseModel):
    workflow_id: str
    process_family: ProcessFamily
    submission_channel: SubmissionChannel
    legal_owner: LegalOwner
    approval_mode: ApprovalMode
    evidence_bundle_required: bool = True
    sensitivity_level: TargetTier = TargetTier.HIGH
    tasks: List[TaskEnvelope]

class Cost(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0

class ErrorDetail(BaseModel):
    code: str
    message: str

class ResultEnvelope(BaseModel):
    task_id: str
    status: Status
    output: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[str] = Field(default_factory=list)
    cost: Cost = Field(default_factory=Cost)
    latency_ms: int = 0
    error: Optional[ErrorDetail] = None

class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    HANDOFF = "handoff"
    
class HumanReviewAction(BaseModel):
    """External Boundary Validation for Human Injection Payload"""
    decision: ReviewDecision
    comment: str
    reviewer: str
    reviewed_at: str 
    reviewed_task_ids: List[str]
