import pytest
import jwt
import os
import asyncio
from httpx import AsyncClient, ASGITransport

from src.agentic_poc.application.fastapi_app import app
from src.agentic_poc.config import settings

# Ensure slowapi test overrides are considered if needed
@pytest.fixture
def token_alice():
    return jwt.encode({"sub": "alice"}, settings.JWT_SECRET, algorithm="HS256")

@pytest.fixture
def token_bob():
    return jwt.encode({"sub": "bob"}, settings.JWT_SECRET, algorithm="HS256")

@pytest.mark.asyncio
async def test_authz_missing_token_blocked():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # No auth header should fail 403 Forbidden (Depends behavior)
        res = await ac.get("/workflows/fake-thread-id/state")
    assert res.status_code == 401

@pytest.mark.asyncio
async def test_authz_invalid_token_blocked():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/workflows/fake-thread-id/state", headers={"Authorization": "Bearer bad_signature_token"})
    assert res.status_code == 401

@pytest.mark.asyncio
async def test_ownership_isolation(token_alice, token_bob):
    from src.agentic_poc.graph import build_graph
    from src.agentic_poc.database import get_checkpointer
    
    async with get_checkpointer() as memory:
        # Mock lifespan completion manually for test but use the SAME checkpoint DB as eager Celery
        app.state.graph = build_graph().compile(checkpointer=memory, interrupt_before=["human_review"])
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Start as Alice
            start_res = await ac.post(
                "/workflows/start",
                json={"input_request": "Isolation test"},
                headers={"Authorization": f"Bearer {token_alice}"}
            )
            assert start_res.status_code == 202, start_res.text
            thread_id = start_res.json()["job_id"]
            
            # Allow background task minimal time to start LangGraph execution
            await asyncio.sleep(1.0)
            
            # Bob attempts to read Alice's state
            bob_res = await ac.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {token_bob}"})
            assert bob_res.status_code == 403
            
            # Alice reads her own state
            alice_res = await ac.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {token_alice}"})
            assert alice_res.status_code == 200
            assert alice_res.json()["values"]["owner_id"] == "alice"
            
            # Fetch evidence payload parsing table endpoint
            alice_evidence = await ac.get(f"/workflows/{thread_id}/evidence", headers={"Authorization": f"Bearer {token_alice}"})
            # Workflow might take ~2s to reach collect and write evidence
            if alice_evidence.status_code == 404:
                await asyncio.sleep(2.0)
                alice_evidence = await ac.get(f"/workflows/{thread_id}/evidence", headers={"Authorization": f"Bearer {token_alice}"})
                
            assert alice_evidence.status_code == 200
            ev_data = alice_evidence.json()
            assert "filename" in ev_data
            assert "rows" in ev_data
            assert len(ev_data["rows"]) > 0

from src.agentic_poc.registry import upsert_workflow, init_registry
import uuid

@pytest.mark.asyncio
async def test_get_workflows_registry_endpoint(token_alice, token_bob):
    # Ensure initialized table
    await init_registry()

    thread_1 = str(uuid.uuid4())
    thread_2 = str(uuid.uuid4())
    
    await upsert_workflow(thread_id=thread_1, owner_id="alice", status="running", input_request_summary="Alice Request 1")
    await upsert_workflow(thread_id=thread_2, owner_id="alice", status="interrupted", input_request_summary="Alice Request 2")
    await upsert_workflow(thread_id="other-uuid", owner_id="bob", status="completed", input_request_summary="Bob Request")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/workflows", headers={"Authorization": f"Bearer {token_alice}"})
        
        assert res.status_code == 200
        data = res.json()["workflows"]
        
        # Should only see alice records
        assert len(data) >= 2
        thread_ids = [w["thread_id"] for w in data]
        assert thread_1 in thread_ids
        assert thread_2 in thread_ids
        assert "other-uuid" not in thread_ids
        
        # Test status filter
        res_interrupted = await ac.get("/workflows?status=interrupted", headers={"Authorization": f"Bearer {token_alice}"})
        data_filtered = res_interrupted.json()["workflows"]
        
        assert len(data_filtered) >= 1
        for row in data_filtered:
            assert row["status"] == "interrupted"
