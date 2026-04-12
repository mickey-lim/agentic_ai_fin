import pytest
from fastapi.testclient import TestClient
import jwt
import uuid
from src.agentic_poc.application.fastapi_app import app
from src.agentic_poc.config import settings
from src.agentic_poc.registry import init_registry, upsert_workflow
import aiosqlite

VALID_TOKEN = jwt.encode({"sub": "tester123", "role": "reviewer"}, settings.JWT_SECRET, algorithm="HS256")
OTHER_TOKEN = jwt.encode({"sub": "otheruser", "role": "reviewer"}, settings.JWT_SECRET, algorithm="HS256")

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

@pytest.mark.asyncio
async def test_soft_delete_and_hide_from_list(client: TestClient):
    await init_registry()
    
    thread_id = f"thread_to_delete_{uuid.uuid4()}"
    
    # 1. Insert mock workflow
    await upsert_workflow(thread_id, "tester123", "completed", workflow_id="wf_to_del")
    
    # 2. Check it appears
    res = client.get("/workflows", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res.status_code == 200
    wfs = res.json()["workflows"]
    assert any(w["thread_id"] == thread_id for w in wfs)
    
    # 3. Soft Delete it
    del_res = client.delete(f"/workflows/{thread_id}", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"
    
    # 4. Check it does NOT appear
    res2 = client.get("/workflows", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res2.status_code == 200
    wfs2 = res2.json()["workflows"]
    assert not any(w["thread_id"] == thread_id for w in wfs2)
    
@pytest.mark.asyncio
async def test_soft_delete_ownership_protection(client: TestClient):
    await init_registry()
    
    thread_id = f"thread_protected_{uuid.uuid4()}"
    await upsert_workflow(thread_id, "tester123", "completed", workflow_id="wf_prot")
    
    # Try deleting with other user's token
    del_res = client.delete(f"/workflows/{thread_id}", headers={"Authorization": f"Bearer {OTHER_TOKEN}"})
    
    # Should get 403 Forbidden because ownership mismatch
    assert del_res.status_code == 403
    
    # Verify it still exists for tester123
    res = client.get("/workflows", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert any(w["thread_id"] == thread_id for w in res.json()["workflows"])

@pytest.mark.asyncio
async def test_can_delete_running_workflow(client: TestClient):
    await init_registry()
    thread_id = f"thread_running_{uuid.uuid4()}"
    await upsert_workflow(thread_id, "tester123", "running", workflow_id="wf_run")
    
    del_res = client.delete(f"/workflows/{thread_id}", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    
    # We now allow deleting running workflows
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

class FakeStateTuple:
    def __init__(self, values, next_nodes):
        self.values = values
        self.next = next_nodes

class FakeGraph:
    def __init__(self, state_tuple=None):
        self._state_tuple = state_tuple
        
    async def aget_state(self, config):
        return self._state_tuple

@pytest.mark.asyncio
async def test_deleted_workflow_cannot_be_resurrected(client: TestClient):
    from src.agentic_poc.application.api import sync_registry_state
    
    await init_registry()
    thread_id = f"thread_zombie_{uuid.uuid4()}"
    
    # 1. Start a workflow
    await upsert_workflow(thread_id, "tester123", "running", workflow_id="wf_zom")
    
    # 2. Soft delete the workflow
    del_res = client.delete(f"/workflows/{thread_id}", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert del_res.status_code == 200
    
    # 3. Simulate background worker finishing execution and attempting to sync its final "completed" state
    fake_completed_state = FakeStateTuple(
        values={"owner_id": "tester123", "workflow_id": "wf_zom", "results": ["some result"]}, 
        next_nodes=[]
    )
    fake_graph = FakeGraph(fake_completed_state)
    
    await sync_registry_state(fake_graph, thread_id)
    
    # 4. Ensure it remains deleted and wasn't resurrected
    res = client.get("/workflows?status=deleted&include_deleted=true", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res.status_code == 200
    
    # Verify the item is still marked as deleted
    wfs = res.json()["workflows"]
    zombie_wf = next((w for w in wfs if w["thread_id"] == thread_id), None)
    
    assert zombie_wf is not None
    assert zombie_wf["status"] == "deleted"
    
    # Verify it doesn't leak into standard view
    res_std = client.get("/workflows", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert not any(w["thread_id"] == thread_id for w in res_std.json()["workflows"])

@pytest.mark.asyncio
async def test_restore_soft_deleted_workflow(client: TestClient):
    await init_registry()
    thread_id = f"thread_to_restore_{uuid.uuid4()}"
    await upsert_workflow(thread_id, "tester123", "interrupted", workflow_id="wf_res")
    
    # Soft delete it
    client.delete(f"/workflows/{thread_id}", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    
    # Verify it's not in standard queue
    res1 = client.get("/workflows", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert not any(w["thread_id"] == thread_id for w in res1.json()["workflows"])
    
    # Verify it IS in deleted queue
    res_del = client.get("/workflows?status=deleted&include_deleted=true", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_del.status_code == 200
    assert any(w["thread_id"] == thread_id for w in res_del.json()["workflows"])
    
    # Restore it
    restore_res = client.post(f"/workflows/{thread_id}/restore", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert restore_res.status_code == 200
    
    # Verify it's back in standard queue and status is back to interrupted
    res2 = client.get("/workflows", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    wfs2 = res2.json()["workflows"]
    restored_wf = next((w for w in wfs2 if w["thread_id"] == thread_id), None)
    assert restored_wf is not None
    assert restored_wf["status"] == "interrupted"
    assert restored_wf["previous_status"] is None
