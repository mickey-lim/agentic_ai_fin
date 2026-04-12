import pytest
import jwt
import uuid
from starlette.testclient import TestClient
from src.agentic_poc.registry import init_registry, upsert_workflow, get_workflows, soft_delete_workflow
from src.agentic_poc.application.fastapi_app import app
from src.agentic_poc.config import settings

VALID_TOKEN = jwt.encode({"sub": "tester123", "role": "reviewer"}, settings.JWT_SECRET, algorithm="HS256")

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

@pytest.mark.asyncio
async def test_batch_operations_and_purge(client: TestClient):
    await init_registry()
    
    thread_1 = f"batch_thread_{uuid.uuid4()}"
    thread_2 = f"batch_thread_{uuid.uuid4()}"
    thread_3 = f"batch_thread_{uuid.uuid4()}"
    
    # 1. Setup multiple workflows
    await upsert_workflow(thread_1, "tester123", "completed", workflow_id="w1")
    await upsert_workflow(thread_2, "tester123", "interrupted", workflow_id="w2")
    await upsert_workflow(thread_3, "tester123", "running", workflow_id="w3") # Now CAN be deleted
    
    # 2. Batch Delete
    res_del = client.post("/workflows/batch", json={
        "action": "delete",
        "thread_ids": [thread_1, thread_2, thread_3]
    }, headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    
    assert res_del.status_code == 200
    results = res_del.json()["results"]
    assert len(results) == 3
    
    # Check outcomes
    r1 = next(r for r in results if r["thread_id"] == thread_1)
    r2 = next(r for r in results if r["thread_id"] == thread_2)
    r3 = next(r for r in results if r["thread_id"] == thread_3)
    
    assert r1["status"] == "ok"
    assert r2["status"] == "ok"
    assert r3["status"] == "ok"
    
    # 3. Batch Restore
    res_res = client.post("/workflows/batch", json={
        "action": "restore",
        "thread_ids": [thread_1]
    }, headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_res.status_code == 200
    assert res_res.json()["results"][0]["status"] == "ok"
    
    # Verify state via GET
    res_get = client.get("/workflows", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    all_wfs = res_get.json()["workflows"]
    # t1 should be completed
    t1 = next((w for w in all_wfs if w["thread_id"] == thread_1), None)
    assert t1 is not None and t1["status"] == "completed"
    
    # 4. Purge the deleted ones
    # Only thread_2 and thread_3 are deleted now
    res_purge = client.post("/workflows/batch", json={
        "action": "purge",
        "thread_ids": [thread_1, thread_2, thread_3]
    }, headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    
    p_results = res_purge.json()["results"]
    p1 = next(r for r in p_results if r["thread_id"] == thread_1) # completed -> skipped
    p2 = next(r for r in p_results if r["thread_id"] == thread_2) # deleted -> ok
    p3 = next(r for r in p_results if r["thread_id"] == thread_3) # deleted -> ok
    
    assert p1["status"] == "skipped"
    assert p2["status"] == "ok"
    assert p3["status"] == "ok"
