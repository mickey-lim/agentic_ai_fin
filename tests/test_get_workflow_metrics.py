import pytest
import sqlite3
import jwt
from fastapi.testclient import TestClient
from src.agentic_poc.registry import REGISTRY_DB_PATH, get_workflow_metrics
from src.agentic_poc.application.fastapi_app import app
from src.agentic_poc.config import settings

def seed_workflows(owner_id: str, counts: dict):
    with sqlite3.connect(REGISTRY_DB_PATH) as conn:
        idx = 0
        for status, count in counts.items():
            for _ in range(count):
                thread_id = f"test_metric_{idx}"
                conn.execute("""
                    INSERT INTO workflow_registry 
                    (thread_id, workflow_id, owner_id, status, process_family, created_at, updated_at)
                    VALUES (?, 'wf', ?, ?, 'test', '2026', '2026')
                """, (thread_id, owner_id, status))
                idx += 1
        conn.commit()

def cleanup_workflows(owner_id: str):
    with sqlite3.connect(REGISTRY_DB_PATH) as conn:
        conn.execute("DELETE FROM workflow_registry WHERE owner_id = ?", (owner_id,))
        conn.commit()

@pytest.fixture
def test_data():
    owner = "tester_metrics"
    counts = {
        "running": 2,
        "interrupted": 3,
        "completed": 5,
        "error": 1,
        "queue_error": 1,
        "deleted": 4,
        "purged": 10
    }
    cleanup_workflows(owner)
    seed_workflows(owner, counts)
    yield owner, counts
    cleanup_workflows(owner)

@pytest.mark.asyncio
async def test_get_workflow_metrics_logic(test_data):
    owner, counts = test_data
    metrics = await get_workflow_metrics(owner)
    
    assert metrics["total"] == 12
    assert metrics["running"] == 2
    assert metrics["interrupted"] == 3
    assert metrics["completed"] == 5
    assert metrics["error"] == 2  # error + queue_error
    assert metrics["deleted"] == 4

def test_api_workflow_metrics(test_data):
    owner, _ = test_data
    client = TestClient(app)
    
    VALID_TOKEN = jwt.encode({"sub": owner, "role": "reviewer"}, settings.JWT_SECRET, algorithm="HS256")
    headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
    
    response = client.get("/workflows/metrics", headers=headers)
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["total"] == 12
    assert metrics["running"] == 2
    assert metrics["error"] == 2
