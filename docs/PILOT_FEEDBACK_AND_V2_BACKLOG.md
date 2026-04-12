# 📝 Pilot Feedback & V2 Backlog

본 문서는 파일럿 운영 기간 중 사용자로부터 수집된 피드백을 기록하고, 차기 릴리스(V2)를 위한 기술 백로그(Backlog)로 승격시키기 위한 관리 문서입니다.

## 📊 1. 사용자 피드백 (현장 수집 내용)

| 일자 | 도메인 | 이슈 분류 | 내용 | 심각도 | 상태 |
| :-- | :--- | :--- | :--- | :--- | :-- |
| (예시) | 공통 | UI/UX | 업로드 진행률 표시 바(Progress Bar) 부재 | Minor | Backlog |
| (예시) | Payroll | Data | 급여 명세 PDF의 컬럼 헤더가 어댑터 스키마와 다를 경우 오류 발생 | Major | Review Needed |

*(파일럿 진행 중 위 테이블을 채워주세요)*

---

## 🚀 2. V2 기술 백로그 (Architecture Roadmap)

현 버전에선 시스템 안정성과 보안을 담보하기 위해 보수적으로 닫아두었으나, 피드백을 바탕으로 다음 Phase(V2)에서 진화시킬 핵심 설계 영역입니다.

#### A. 비정형 문서 & 이미지 스캔본 대응 (스캔/이미지 영수증 VLM)
- 성능과 환각 최소화 방어를 위해 현재는 순수 Text-Table 형태의 제한적 PDF 파싱(`pdfplumber` 기반)만을 허용하고 있습니다.
- V2에서는 Gemini 1.5 Pro 혹은 타 Vision Language Model(VLM)을 이용한 **이미지 스캔 기반 영수증/증빙 인식 파이프라인**을 개척하여 하이브리드 Fallback 아키텍처를 전면 도입할 예정입니다.

#### B. 상태 라이프사이클 명확화 (`cancel_requested` / `cancelled`)
- 파일럿 과정에서 사용중인 레지스트리 삭제(`deleted` 상태 플래그) 기능에 더해, 더 명시적인 시스템 이관 종료 트리거인 `cancel_requested`와 `cancelled` 상태를 도입합니다.
- 사용자가 진행 중인 처리를 직관적으로 종료하고 좀비 연산을 원천 방지하는 큐(Queue) 통제 기술을 개발합니다.

#### C. 다중 파일 통합 리포트 UX (Frontend)
- 다건의 영수증과 증빙을 업로드할 경우 사용자가 통합적인 맥락(Context)을 이해할 수 있는 통합 리포트 UX를 제공합니다.
- 다운로드(`blob` 추출)나 데이터 테이블 렌더 시, 어떤 파일에서 온 데이터인지 Provenance(출처)를 시각적으로 매핑하는 UI/스트리밍 스켈레톤을 고도화합니다.

#### D. 인프라 확장성 (PostgreSQL Migration)
- 현재 단일 SQLite3(`agentic_registry.db`) 구조를 벗어나, 실제 트래픽과 다중 서버 인스턴스(Scale-out)를 지원하기 위해 PostgreSQL로 확장/마이그레이션(Migration)하는 아키텍처를 도입합니다.
