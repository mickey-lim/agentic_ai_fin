# Agentic Financial Console - Release Notes (v1.0 RC)

본 릴리스 노트는 Agentic AI 기반 재무 Orchestration 시스템의 첫 번째 릴리스 후보(v1.0 Release Candidate) 배포 구성을 안내합니다.

## 핵심 성과 요약 (Executive Summary)
v1.0 RC는 기존의 선형적인 데이터 처리 시스템에서 벗어나 **LangGraph 기반의 ReAct 에이전트**와 **Celery/Redis 비동기 큐**를 융합한 엔터프라이즈 하이브리드 워크플로우 엔진입니다. AI가 자율적으로 업무를 기획하고(Decomposition) 문서를 처리하는 동안, 작업자가 개입하여 검토하고(Human-in-the-Loop) 승인할 수 있는 모던 Next.js 관제 뷰를 제공합니다.

---

## 🚀 지원 범위 (Supported Scope)

1. **파일 기반 재무 데이터 파이프라인 (Upload-Based Automation)**
   - 수동으로 추출한 Excel/CSV 포맷의 재무 내역, 세금계산서, 은행 입출금 데이터 업로드 및 파싱.
2. **비동기 큐 및 탄력적 워커 (Celery/Redis)**
   - Redis Broker를 활용한 Celery 비동기 워커.
   - 단일 트랜잭션당 최대 50개의 자식 태스크 제한(`max-tasks-per-child=50`)을 둔 안정적인 메모리 워크플로우 환경 구축.
3. **HITL (Human-in-the-Loop) 통제 콘솔**
   - 워크플로우 Interrupt 상태 감지 및 Draft Summary 제공.
   - 운영자의 명시적 판단(승인/반려/수동완료) 후 다음 Graph Node로 롤백 또는 포워딩하는 관측성 패널.
4. **멀티모달 비전 문서 처리 (VLM OCR/Image Parser)**
   - Gemini 2.5 Flash 기반의 이미지/스캔본 영수증 병합 처리 (오직 **비용/자금(Expense/Treasury)** 도메인 문서에 한정됨).
   - 영수증, 지출결의서 위주로 단가/수량/금액 등의 세부 라인 아이템 파싱, 식별 실패 시 Fail-Closed(인적 개입 요망)를 유도하는 구조적 안전망 검증 완료. 범용 재무 스캔 문서는 지원하지 않습니다.

4. **배치 운영 체계 (Batch Ops)**
   - 다중 노드에 대한 일괄 승인/보류(Batch API), Soft Delete(휴지통 모드) 적용.
   - SQLite 동시성 로킹을 회피하는 물리적 `WAL(Write-Ahead Logging)` 적용.

---

## 🚫 비지원 범위 (Unsupported Scope)

프로덕션 단계에서 다음과 같은 영역은 **현재 v1.0 릴리스 대상에서 제외**되어 있으며, 향후 Phase에서 논의될 수 있습니다.

1. **ERP / 코어뱅킹 직접 연동 (Direct Integration)**
   - 사내 그룹웨어 전자결재 API나 외부 은행망(Firmbanking/Open API)과의 직접 통신은 제외. 현재는 파일 추출-결과물 ZIP 떨구기 형태의 Air-gapped 운영으로 제한됩니다.
2. **대규모 Postgres Scale-out**
   - SQLite `WAL` 프라그마를 통해 병렬 Lock 현상을 해결했으나, 멀티 서버(다중 EC2 인스턴스) 간의 분산 DB 노리킹(Clustering)을 타겟으로 한 PostgreSQL/PGPool 마이그레이션은 제외되어 있습니다.

---

## Technical Hardening & Observability
- 환경에 따라 유연하게 분기되는 `APP_ENV` 기반 구조적 로깅 채택 (`JSON` for Prod, `Pretty` for Local).
- Docker Compose 레이어에 엄격한 Redis `healthcheck` 체인이 걸리며 런타임 Race-Condition이 완전 차단됨.
