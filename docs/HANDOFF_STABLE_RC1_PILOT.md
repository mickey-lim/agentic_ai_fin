# 🤝 HANDOFF: Stable Release Candidate (Pilot)

## 1. Scope and Goal
- **목표:** 재무부서(Treasury, Grant, Payroll, Withholding) 코어 워크플로우를 관통하는 백엔드 파이프라인(Agentic + FastAPI)의 성공적인 완료 후 파일럿 이관.
- **상태:** `v1.0-RC1` 도달. 실 환경(E2E) 제약사항을 만족하고 동의어 정규분포 테스트(Real-PDF) 검증까지 결함 없이 완료되었으나 디자인 및 UI/UX를 붙이지 않은 로직 엔지니어링 최적화 상태입니다.

## 2. Operational Caveats (운영자 주의 사항)

파일럿 운영 시 관리자가 반드시 숙지해야 하는 환경 및 실행 정책입니다.

### 🌐 환경 / 포트 설정
- 도커 에코시스템과의 완전 호환을 위해 프론트 API 기준 포트는 **`3001` (프론트/Next) $\leftrightarrow$ `8001` (백엔드/FastAPI)** 경로를 표준으로 삼습니다. (마지막 점검에서 `frontend/.env.local`의 혼합 환경 버그(8002포트 분리현상)가 완전 치유되었습니다.)

### 📑 VLM/OCR 지원 범위 (멀티모달 파일럿 기대 모델)
- 본 릴리스의 어댑터(`vlm_extractor`)는 기존의 텍스트 레이아웃 PDF뿐만 아니라 **비용/자금(Expense/Treasury) 도메인에 한정하여 이미지 영수증(.jpg, .png) 및 지출결의서 스캔본의 파싱**을 공식 지원합니다. 범용 재무 스캔 문서는 분석 대상에서 제외됩니다.
- Gemini 2.5 Flash를 통한 멀티모달 비전 인식을 통해 단가, 수량, 금액, 판매처 등을 추출하며, 식별/판독 불가 시 억지 통과(Silent Pass) 대신 `Fail-closed`(인적 개입 요망)를 유도하도록 강력하게 보호되어 있습니다.
- 단일 워크플로우에 여러 장의 영수증을 동시에 첨부하는 멀티-파일(Multi-file Drop) 인식을 지원합니다.

### ♻️ 삭제 및 복구 행동 정책
- 워크플로 목록에서 **`running` 상태인 문서를 강제 삭제할 수 있습니다(`deleted` 전환)**. 단, 삭제된 문서의 작업 내역은 폐기되므로 복구(`restore`) 시 `running` 상태의 백그라운드 Worker 상태로 이어지지 않고 `interrupted` 상태로 안전하게 떨어집니다. 이는 백엔드 상태를 좀비화 시키지 않기 위함입니다.

### 🧑‍💻 Human-in-the-loop (HITL) Behavior
- 아키텍처에 정의된 바에 따라 개별 도메인 파이프라인은 AI가 결론을 도출하지 않거나, 보안결재 라인의 개입(`사람_전담`)이 들어간 경우 노드 통과를 보류하고 `interrupted`(`human_review`) 단계로 전환됩니다. 유저는 `WorkflowConsolePanel` 또는 이벤트를 통해 개입해 징검다리를 연결해 주어야 패키지 발행이 작동합니다.

## 3. Current State & Tests
- **현재 브랜치**: `main`
- **최신 커밋**: `01e2248` (docs: finalize v1 handoff document formatting and hash synchronization)
- **테스트 커버리지**: PyTest 기반 전체 유닛 테스트 및 Real-PDF 기반 무결성 E2E 100% 정상 통과

## 4. Next-Agent Prompt (다음 담당자 지시 사항)
당신의 목표는 이 시스템을 기반으로 **UI/UX 디자인 및 렌더링 시스템 최적화**를 구축하는 것입니다.
- 현 `v1.0-RC1` 백엔드 로직 코드는 극도로 안정화된 상태이므로 `FastAPI`나 `LangGraph` 어댑터 등 핵심 백엔드 계층(`*.py`)은 수정하지 **마십시오**. 파일럿 피드백이 누적되기 전까지 아키텍처 로직 건드리는 것은 금지됩니다.
- 본 저장소의 `PILOT_SCENARIO_CHECKLIST.md`와 피드백 문서를 참고하여, 사용자가 시각적으로 에러나 대기 상황(Skeleton, Error boundary)을 인지할 수 있는 React 클라이언트 보강을 진행하십시오.
