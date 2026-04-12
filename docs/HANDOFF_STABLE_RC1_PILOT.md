# 🤝 HANDOFF: Stable Release Candidate (Pilot)

## 1. Scope and Goal
- **목표:** 재무부서(Treasury, Grant, Payroll, Withholding) 코어 워크플로우를 관통하는 백엔드 파이프라인(Agentic + FastAPI)의 성공적인 완료 후 파일럿 이관.
- **상태:** `v1.0-RC1` 도달. 실 환경(E2E) 제약사항을 만족하고 동의어 정규분포 테스트(Real-PDF) 검증까지 결함 없이 완료되었으나 디자인 및 UI/UX를 붙이지 않은 로직 엔지니어링 최적화 상태입니다.

## 2. Operational Caveats (운영자 주의 사항)

파일럿 운영 시 관리자가 반드시 숙지해야 하는 환경 및 실행 정책입니다.

### 🌐 환경 / 포트 설정
- 도커 에코시스템과의 완전 호환을 위해 프론트 API 기준 포트는 **`3001` (프론트/Next) $\leftrightarrow$ `8001` (백엔드/FastAPI)** 경로를 표준으로 삼습니다. (마지막 점검에서 `frontend/.env.local`의 혼합 환경 버그(8002포트 분리현상)가 완전 치유되었습니다.)

### 📑 PDF 지원 범위 (초기 파일럿 기대 모델)
- 본 릴리스의 어댑터(`pdf_parser`)는 전방위 범용 PDF 처리를 지원하지 않습니다. 
- 오직 **마우스로 텍스트 드래그가 정상적으로 되며, 표(Table) 헤더 구조가 문서상 명시적으로 살아있는 텍스트 레이아웃 PDF**에 한해서만 요약값을 추출합니다.
- 이미지 파일, 표 레이아웃이 뭉개진 스캔본은 작동 불가를 반환합니다. 현업에게 해당 제약을 명시하십시오.

### ♻️ 삭제 및 복구 행동 정책
- 워크플로 목록에서 **`running` 상태인 문서를 강제 삭제할 수 있습니다(`deleted` 전환)**. 단, 삭제된 문서의 작업 내역은 폐기되므로 복구(`restore`) 시 `running` 상태의 백그라운드 Worker 상태로 이어지지 않고 `interrupted` 상태로 안전하게 떨어집니다. 이는 백엔드 상태를 좀비화 시키지 않기 위함입니다.

### 🧑‍💻 Human-in-the-loop (HITL) Behavior
- 아키텍처에 정의된 바에 따라 개별 도메인 파이프라인은 AI가 결론을 도출하지 않거나, 보안결재 라인의 개입(`사람_전담`)이 들어간 경우 노드 통과를 보류하고 `interrupted`(`human_review`) 단계로 전환됩니다. 유저는 `WorkflowConsolePanel` 또는 이벤트를 통해 개입해 징검다리를 연결해 주어야 패키지 발행이 작동합니다.

## 3. Current State & Tests
- **현재 브랜치**: `main`
- **최신 커밋**: `e8c5cd6 (docs(phase5): finalize v1.0-rc.1 documentation and hardening)`
- **테스트 커버리지**: PyTest 기반 전체 유닛 테스트 및 Real-PDF 기반 무결성 E2E 100% 정상 통과

## 4. Next-Agent Prompt (다음 담당자 지시 사항)
당신의 목표는 이 시스템을 기반으로 **UI/UX 디자인 및 렌더링 시스템 최적화**를 구축하는 것입니다.
- 현 `v1.0-RC1` 백엔드 로직 코드는 극도로 안정화된 상태이므로 `FastAPI`나 `LangGraph` 어댑터 등 핵심 백엔드 계층(`*.py`)은 수정하지 **마십시오**. 파일럿 피드백이 누적되기 전까지 아키텍처 로직 건드리는 것은 금지됩니다.
- 본 저장소의 `PILOT_SCENARIO_CHECKLIST.md`와 피드백 문서를 참고하여, 사용자가 시각적으로 에러나 대기 상황(Skeleton, Error boundary)을 인지할 수 있는 React 클라이언트 보강을 진행하십시오.
