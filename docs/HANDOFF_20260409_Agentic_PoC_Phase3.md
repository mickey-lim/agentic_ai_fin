# [Historical] Agentic AI Orchestration PoC - Phase 3 Handoff

> [!WARNING]
> **해당 문서는 Phase 3 종료 시점(2026-04-09)의 과거 기록(Historical Archive)입니다.**
> 이 문서에 서술된 상태(MemorySaver, 테스트 4개 통과 등)는 현재(Phase 5)의 데이터 영속성 메커니즘, 15개 테스트 스위트 구조 및 FastAPI 연동 구조와 일치하지 않습니다. **현행 시스템의 상태 확인을 위해서는 이 문서를 참조하지 마십시오.**

## 1. Project Background (Context)
- **완료된 목표 (Phase 1/2)**: 순수 `dict/TypedDict` 기반의 LangGraph 상태 머신, Gemini 2.5 Flash 기반의 `Structured Output` 라우터, Human-in-the-Loop 중단/재개 승인 루프, 그리고 FastAPI 기반의 제어 평면(API) 구성 및 더미 엑셀(IO) 파싱/압축 증빙 수집 동작 검증. 모든 벤치마크 테스트(4 Pass) 통과.
- **다음 목표 (Phase 3)**: 단순 설계 검증을 넘어선 "Production-ready" 엔터프라이즈 환경 구축. 메모리에 의존하던 상태 머신을 영구 데이터베이스에 이관하고, 외부에 노출할 API 인프라에 접근 제어 및 로깅을 접목시키며, 단순 시드 파일 생성을 넘어 실제 재무 도메인에 특화된 데이터 구조 로더(Excel/CSV)를 체결.

## 📍 Current State
- **저장소 위치**: `/Users/mickey/AI/12_agentic-ai`
- **Git 상태**: Git이 초기화되지 않은 상태 (Local files directly created)
- **핵심 모듈 상태**:
  - `planner.py` (Gemini 2.5 Flash 적용, 제약조건 프롬프트 완전 동작)
  - `worker.py` (pandas & zipfile 연동 IO 패키징 적용 완료)
  - `fastapi_app.py` (Endpoints 생성 완료 & 작동 확인)
  - `graph.py` (단순 MemorySaver 구성 중)
- **최신 테스트 결과**: `pytest tests/test_benchmark_pipeline.py -v` (4 passed, 100% 성공)

## 📂 Changed Files (최종 확정 스코프 기준)
- `pyproject.toml` (FastAPi, Gemini, pandas, openpyxl 의존성 주입)
- `.gitignore` (artifacts, scratch, pycache, .env 보호)
- `src/agentic_poc/application/fastapi_app.py` `[NEW]`
- `src/agentic_poc/nodes/planner.py` `[MODIFIED]`
- `src/agentic_poc/nodes/worker.py` `[MODIFIED]`
- `src/agentic_poc/nodes/aggregator.py` `[DELETED]`

## 🧪 Tests
- **Test Command**: `source venv_313/bin/activate && PYTHONPATH=./src pytest tests/ -v`
- **Result**: PASSED (4 tests, 소요시간 약 29초, Serde Warning 직렬화 이슈 완전히 해소됨)

## ⚠️ Open Issues and Risks
1. **MemorySaver 휘발성 리스크** (`graph.py`): 현 구조는 `uvicorn` 프로세스가 다운되는 동시 모든 진행 중인 워크플로우(HITL 대기열 포함)가 소실됨. Phase 3에서 즉시 `AsyncSqliteSaver` 도입 요망.
2. **API 개방 리스크** (`fastapi_app.py`): 토큰 릴레이나 IP 검증, Rate Limiter 없이 Endpoints가 전면 개방되어 있어, 프로덕션 배포 시 인젝션 및 Denial of Service에 매우 취약함.
3. **Fallback 시 Task ID 동적 참조 필요**: Gemini Structured Output 실패 시 정적 라우터 분기로 Fallback이 발생하는데, 이때 생성되는 `task_id`가 랜덤 UUID를 갖게 됩니다. 다음 단계에서 API 연동 시 하드코딩된 ID(`draft_1`) 대신 반드시 동적으로 추출된 Task ID를 참조해야 합니다.

## 🚀 Next Steps (Phase 3 Hardening Backlog Priorities)
1. **AsyncSqliteSaver & Postgres 기반 체크포인트**: 
   - `AsyncSqliteSaver` 마이그레이션 및 장기적으로 Postgres 전향을 통한 **Durable Execution** 확립.
2. **API 생명주기 및 202 Accepted 기반 분리**: 
   - `FastAPI`의 동기 처리 단절. 1차적으로 `BackgroundTasks` 분리 도입 후, 2차적으로 `Celery/ARQ` 큐 적용. 응답으로 `202 Accepted`와 `job_id(thread_id)` 분리 전송.
3. **Observability & PII Redaction (데이터 통제)**: 
   - `LangSmith` Tracing 및 `OpenTelemetry` 알림 구성. 금융 데이터 특성을 감안해 가장 앞단에 **LangChain PII Middleware**를 통한 민감정보(Redaction) 정책 즉시 반영.
4. **인증/인가 + Thread Ownership**: 
   - 서버 측에서 `thread_id` 발급 후 소유자와 토큰 바인딩 처리 (JWT). Rate Limit 설정으로 `[P1]` 보안 공백 해결.
5. **Next.js 16 기반 승인 제어 평면 (Frontend)**: 
   - UI 스택: **Next.js 16 (Active LTS) + Tailwind CSS v4 + shadcn/ui**.
   - 장식적 글래스모피즘 최소화, **통제와 감사(Audit)** 우선 설계. 비교 패널과 승인 로그(누가, 언제, 변경점) 중심으로 한 평면적 F-Pattern 형태 화면 구축.

## 🤖 Next-Agent Prompt (복사용 템플릿)
```markdown
당신은 백엔드 및 인프라 보안 최적화 전문가이자 프론트엔드 아키텍트입니다.
지금까지의 Agentic AI Financial PoC(FastAPI + Gemini)는 성공적으로 설계 검증이 끝났으나, Production Level 진입을 위해 아래 하드닝 백로그를 해소해야 합니다. 기능 확장 이전에 다음 순서를 엄격히 따라주세요.

[실행 순서 우선순위]
1. `graph.py` 를 수정하여 `AsyncSqliteSaver` 기반으로 체크포인트를 확보하세요.
2. `fastapi_app.py` 의 `/workflows/start` 엔드포인트를 `202 Accepted` 비동기 실행(`BackgroundTasks`)으로 전환하고 서버 측에서 `thread_id`를 발급하도록 구조를 변경하세요.
3. LangSmith/OpenTelemetry를 연결하고 최우선으로 LangChain PII Redaction Middleware를 끼워 넣으세요.
4. JWT 인증 및 Rate limit, 그리고 `HumanReviewAction` Pydantic 정식 스키마 바인딩(422)을 추가하세요.
5. `tests/` 파이프라인 무결성을 통과시킨 후, 해당 백엔드 위에 올라갈 Next.js 16 + Tailwind v4 + shadcn/ui 기반의 Dashboard 스캐폴딩(감사 로그, 데이터 비교 패널 중심)을 기획하세요.
```
