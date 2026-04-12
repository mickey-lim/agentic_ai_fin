# Pilot Deployment Guide

운영팀 및 파일럿 테스터들이 로컬 머신에서 독립적으로 시스템을 기동하고 E2E 시나리오를 검증할 수 있도록 돕는 최소 셋업 가이드입니다.

## 1. 런타임 환경 구성 (.env)

모든 컨테이너가 정상적으로 기동되려면 루트 디렉토리(`.`)에 `.env` 파일이 필수적으로 세팅되어 있어야 합니다. **누락 시 컨테이너가 종료되거나 백엔드 기능이 막힙니다.**

```env
# 1. 인증 시크릿 (임의의 문자열 가능, JWT 토큰 서명용)
JWT_SECRET=super_secret_for_pilot_test

# 2. Google AI API 주입 (Gemini-2.5-flash 추론을 위함)
# 실제 GCP나 AI Studio 발급 키 사용 필수
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY_HERE

# 3. 운영 모드 설정 (prod로 전환 시 JSON 로깅으로 스위칭)
APP_ENV=local

# 4. CORS 설정 (Front-end 도메인 접근 허용)
ALLOWED_ORIGINS=["http://localhost:3001","http://127.0.0.1:3001"]
```

## 2. Docker Compose 기동 (Healthcheck)

불필요한 설정 파일(`.dockerignore` 반영 완료)이 배제된 클린한 상태의 Docker 스택을 빌드합니다. 터미널을 열고 다음 명령어를 순차적으로 구동하십시오.

```bash
# 1. 컨테이너 일괄 빌드 및 백그라운드 기동
docker compose up --build -d

# 2. 프로세스 헬스체크 구동 상태 확인 (Up / healthy 검증)
docker compose ps
```
> [!IMPORTANT]  
> 헬스체크 의존성(`condition: service_healthy`) 덕분에, 만약 Redis 상태가 `healthy`가 되지 않았다면 Backend 및 Worker는 대기열에서 기다립니다. 정상 부팅 후 `backend`, `frontend`, `redis`, `celery_worker`, `celery_beat` 총 5개의 컨테이너가 `Up` 상태여야 합니다.

## 3. 포트별 런타임 검증 확인 노드

모든 스택이 올라왔다면, 아래 로컬호스트 주소를 통해 실제 컴포넌트 접근을 테스트합니다.

- **[Backend / OpenAPI]** http://localhost:8001/docs
  - FastAPI Swagger UI가 정상 표출되는지 확인.
- **[Frontend / 관제 보드]** http://localhost:3001/board
  - Next.js Admin UI 접속. (더미 JWT 로그인 과정을 거쳐 `Queue Dashboard`가 나오는지 확인)

## 4. E2E 파일럿 테스트 케이스 가이드

콘솔 환경이 준비되었다면 아래의 프로세스대로 진행해 보십시오.
1. **업로드 (Ingestion)**: 임의의 `Excel/CSV` 재무/품의 내역 파일을 프론트엔드의 Workflow 구동 화면에 업로드합니다.
2. **비동기 접수 확인 (Observability)**: Queue Dashboard에서 `status: running` 상태인 카드로 뜨는지 실시간(`Polling`) 확인합니다.
3. **인터럽트 검수 (HITL)**: Workflow가 Draft를 생성하고 `status: interrupted` 상태로 대기하는지 확인한 뒤, 패널의 [Draft Summary]를 읽고 **승인 (Approve)** 버튼을 클릭합니다.
4. **결과 다운로드 확인 (Conclusion)**: 상태가 `completed`로 떨어지고, 파일럿 결과물(Zip 다운로드) 버튼이 정상적으로 활성화되는지 확인합니다.
