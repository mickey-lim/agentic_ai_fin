import time
import json
import uuid
import datetime
import urllib.request
import urllib.error

API_BASE_URL = "http://127.0.0.1:8000"

def post_json(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'))
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode()}")
        raise

def get_json(url):
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode()}")
        raise

def main():
    print("=" * 60)
    print("🚀 Agentic PoC (v7) E2E 시나리오 테스트를 시작합니다.")
    print("=" * 60)

    # 1. Start Workflow
    thread_id = str(uuid.uuid4())
    print(f"\n[1] 새로운 워크플로우를 시작합니다. (Thread ID: {thread_id[:8]}...)")
    
    # "자금일정" / "예산" 키워드가 포함되면 Gemini가 ai_type을 'AI_보조'로 할당하여 
    # Draft 단계에서 파이프라인이 멈추고(HITL) Human Review 인터럽트를 걸도록 유도합니다.
    start_payload = {
        "input_request": "[WF-004] 다음 달 사업기획 부서 예산 작성 및 자금일정을 구성해서 검토 올려줘.",
        "thread_id": thread_id
    }
    
    start_resp = post_json(f"{API_BASE_URL}/workflows/start", start_payload)
    print(f"✅ 워크플로우 Trigger 완료: {start_resp}")

    dynamic_draft_task_id = "draft_1"
    
    # 2. Polling for HITL (Human-Index-The-Loop) or Completion
    print("\n[2] Agent의 실행(Collect -> Normalize -> Draft)을 모니터링합니다...")
    while True:
        state_resp = get_json(f"{API_BASE_URL}/workflows/{thread_id}/state")
        next_nodes = state_resp.get("next", [])
        wf_status = "completed" if len(next_nodes) == 0 else "started"
        awaiting_human = "human_review" in next_nodes
        
        print(f"  👉 현재 상태: [{'진행중' if wf_status == 'started' else '완료'}] | HITL 대기: {awaiting_human}")
        
        if awaiting_human:
            print("\n🚨 Agent가 실행을 일시 중단하고 'Human Review'를 대기 중입니다! (Draft 준비 완료)")
            
            # Print current results to review
            results = state_resp.get("values", {}).get("results", [])
            draft_res = next((r for r in results if r["task_id"].startswith("draft")), None)
            if draft_res:
                dynamic_draft_task_id = draft_res["task_id"]
                print(f"  📎 Draft Task 결과물 요약: {draft_res.get('output')}")
            
            break
            
        if wf_status in ["completed", "failed"]:
            print(f"Workflow Finished unexpectedly with status: {wf_status}")
            return
            
        time.sleep(3)

    # 3. 인간의 승인 이관 (HITL Inject)
    print("\n[3] '관리자(Human)'가 검토를 완료하고 승인(Approve) 결정을 내립니다...")
    time.sleep(2)
    
    resume_payload = {
        "decision": "approve",
        "comment": "자금일정 및 예산 초안이 기준에 부합합니다. 최종 승인하니 패키징 진행하세요.",
        "reviewer": "CFO_Mickey",
        "reviewed_at": datetime.datetime.now().isoformat(),
        "reviewed_task_ids": [dynamic_draft_task_id]
    }
    
    resume_resp = post_json(f"{API_BASE_URL}/workflows/{thread_id}/resume", resume_payload)
    print(f"✅ 승인 제출 완료. Agent가 패키징(Resume)을 재가동합니다.")

    # 4. Polling for final completion
    print("\n[4] Agent의 재실행(Draft 승인 -> Package 빌드 -> End)을 모니터링합니다...")
    while True:
        state_resp = get_json(f"{API_BASE_URL}/workflows/{thread_id}/state")
        next_nodes = state_resp.get("next", [])
        wf_status = "completed" if len(next_nodes) == 0 else "started"
        
        print(f"  👉 현재 상태: [{'진행중' if wf_status == 'started' else '완료'}]")
        
        if wf_status == "completed":
            print("\n🎉 워크플로우가 모두 성공적으로 완료되었습니다!")
            
            # Print Package paths
            results = state_resp.get("values", {}).get("results", [])
            for res in results:
                if res["task_id"].startswith("package"):
                    print(f"  📦 최종 병합 패키지(ZIP) 경로: {res.get('output', {}).get('package_path')}")
            break
            
        time.sleep(3)
        
if __name__ == "__main__":
    main()
