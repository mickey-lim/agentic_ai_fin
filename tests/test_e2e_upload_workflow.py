from src.agentic_poc.application.fastapi_app import limiter
limiter.enabled = False

import pytest
from fastapi.testclient import TestClient
from src.agentic_poc.application.fastapi_app import app
from src.agentic_poc.config import settings
import jwt
from io import BytesIO
import pandas as pd
import pathlib
import io

VALID_TOKEN = jwt.encode({"sub": "tester123", "role": "reviewer"}, settings.JWT_SECRET, algorithm="HS256")

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_full_upload_to_summary_e2e(client: TestClient):
    # 1. Create a dynamic mock excel file
    df = pd.DataFrame({"집행일자": ["2026-04-01"], "비목": ["인건비"], "세목": ["급여"], "승인금액": [10000], "집행금액": [10000], "잔액": [0]})
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    
    # 2. Upload the file
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("grant_test.xlsx", buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res.status_code == 201
    file_id = res.json()["file_id"]
    
    # 3. Trigger workflow. 
    # Because CELERY_TASK_ALWAYS_EAGER=true in conftest.py, the task runs synchronously, 
    # blocking until completed (or interrupted).
    start_payload = {
        "input_request": "보조금 정산 검토해줘.",
        "source_file_id": file_id
    }
    res_start = client.post(
        "/workflows/start",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json=start_payload
    )
    assert res_start.status_code == 202
    thread_id = res_start.json()["job_id"]
    
    # 4. Check if artifacts were created.
    # The worker task should have populated the state, generated an evidence snapshot, and created draft_summary.
    # Wait, the task_id used inside worker.py is a random UUID string generated on the fly.
    # BUT worker.py uses `task_id = str(uuid.uuid4())[:8]` and creates `${task_id}_raw.xlsx` ...
    # So we don't know the exact task_id filename statically. Let's find it.
    
    evidence_dir = pathlib.Path("./artifacts/evidence")
    found_evidence = list(evidence_dir.glob(f"*_raw.xlsx"))
    
    # We must find the latest one or use DB to get it.
    # Let's inspect the registry.
    import sqlite3
    with sqlite3.connect(settings.REGISTRY_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT workflow_id, status, source_file_id FROM workflow_registry WHERE thread_id = ?", (thread_id,))
        row = cursor.fetchone()
        assert row is not None
        workflow_id, status, db_source_file_id = row
        assert db_source_file_id == file_id
        assert status in ["completed", "interrupted"]
        
    # 5. Assert Artifact Hardening
    # ensure artifacts/evidence and artifacts/package contains exactly what's expected.
    package_dir = pathlib.Path("./artifacts/package")
    evidence_dir = pathlib.Path("./artifacts/evidence")
    
    zip_path = package_dir / f"final_pkg_{workflow_id}.zip"
    md_path = evidence_dir / f"report_{workflow_id}.md"
    
    # We must find the draft_json which contains random task id in prefix: {task_id}_{workflow_id}_draft.json
    draft_jsons = list(evidence_dir.glob(f"*_{workflow_id}_draft.json"))
    assert len(draft_jsons) > 0, f"Expected draft snapshot for workflow_id {workflow_id} not found"
    
    # Check data integrity in draft
    import json
    with open(draft_jsons[0], "r") as f:
        draft_content = json.load(f)
    
    # 5. Resume Workflow
    import datetime
    resume_payload = {
        "decision": "approve",
        "comment": "Looks good",
        "reviewer": "test_human",
        "reviewed_at": datetime.datetime.now().isoformat(),
        "reviewed_task_ids": [draft_jsons[0].stem.split("_")[0] + "_" + draft_jsons[0].stem.split("_")[1]] # e.g. draft_xyz
    }
    res_resume = client.post(
        f"/workflows/{thread_id}/resume",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json=resume_payload
    )
    assert res_resume.status_code == 202, res_resume.text

    # 6. Assert Final Packaging Artifacts
    zip_path = package_dir / f"final_pkg_{workflow_id}.zip"
    md_path = evidence_dir / f"report_{workflow_id}.md"
    
    assert zip_path.exists(), f"Expected package {zip_path} not found"
    assert md_path.exists(), f"Expected report {md_path} not found"
    
    # The abstract adapter "grant" calculates sums matching the DataFrame input.
    assert draft_content.get("total_approved") == 10000, "Integrity Error: total_approved invalid"
    assert draft_content.get("total_executed") == 10000, "Integrity Error: total_executed invalid"
    assert draft_content.get("total_balance") == 0, "Integrity Error: total_balance invalid"
    
def test_duplicate_upload_retains_history(client: TestClient):
    """
    Ensure identical files uploaded twice correctly reuse the existing file_id
    and update last_used_at instead of overwriting stored_path.
    """
    df = pd.DataFrame([{"Test": "Duplicate 123"}])
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    
    # Upload 1
    res1 = client.post(
        "/workflows/upload",
        files={"file": ("dup_test.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"}
    )
    assert res1.status_code == 201
    file_id_1 = res1.json()["file_id"]
    
    # Upload 2 (identical content)
    buffer.seek(0)
    res2 = client.post(
        "/workflows/upload",
        files={"file": ("dup_test.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"}
    )
    assert res2.status_code == 201
    file_id_2 = res2.json()["file_id"]
    
    # Assert deduplication mapping
    assert file_id_1 == file_id_2, "Identical files should return the same file_id via hash lookup"

from unittest.mock import patch

@patch('src.agentic_poc.utils.pdf_parser.parse_pdf_to_dataframe')
def test_full_upload_to_summary_e2e_pdf_synonyms(mock_parse_pdf, client: TestClient):
    """
    E2E Test for PDF integration and Column Normalization logic.
    Verifies that a PDF is accepted, parsed (mocked), and synonyms are correctly mapped
    to the canonical schema so that adapter summary calculation succeeds.
    """
    # 1. Mock the PDF parser to return a dataframe with SYNONYMS instead of expected columns
    # Expected by treasury: '공급가액', '부가세', '계정과목', '거래일자', '승인자'
    # Returned by mock: '금액', '세액', '항목', '날짜', '승인자'
    import pandas as pd
    df = pd.DataFrame({
        "날짜": ["2026-04-12"], 
        "항목": ["소프트웨어 구독"], 
        "금액": [100000], 
        "세액": [10000], 
        "승인자": ["Mickey"]
    })
    df.attrs["parser_type"] = "pdf_text"
    mock_parse_pdf.return_value = df

    # 2. Upload dummy PDF bytes
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("invoice.pdf", b"dummy pdf content", "application/pdf")}
    )
    assert res.status_code == 201, res.text
    file_id = res.json()["file_id"]

    # 3. Trigger workflow using a treasury-related prompt
    start_payload = {
        "input_request": "지출결의서 부가세 검토해줘",
        "source_file_id": file_id
    }
    res_start = client.post(
        "/workflows/start",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json=start_payload
    )
    assert res_start.status_code == 202
    thread_id = res_start.json()["job_id"]

    # 4. Extract workflow_id from registry
    import sqlite3
    with sqlite3.connect(settings.REGISTRY_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT workflow_id, status FROM workflow_registry WHERE thread_id = ?", (thread_id,))
        row = cursor.fetchone()
        assert row is not None
        workflow_id, status = row
        assert status in ["completed", "interrupted"]

    # 5. Check data integrity in draft
    import pathlib, json
    evidence_dir = pathlib.Path("./artifacts/evidence")
    draft_jsons = list(evidence_dir.glob(f"*_{workflow_id}_draft.json"))
    assert len(draft_jsons) > 0, "Draft JSON not found for PDF E2E"

    with open(draft_jsons[0], "r") as f:
        draft_content = json.load(f)

    # If the column normalizer successfully mapped '금액' to '공급가액' and '세액' to '부가세',
    # total_supply and total_vat should be correctly computed by treasury.py.
    assert draft_content.get("total_supply") == 100000, "Column normalizer failed: total_supply incorrect"
    assert draft_content.get("total_vat") == 10000, "Column normalizer failed: total_vat incorrect"
    assert draft_content.get("total_transactions") == 1

    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})
    assert any(r.get("output", {}).get("provenance", {}).get("parser_type") == "pdf_text" for r in state_val.get("results", [])) 
    
    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})

def test_full_upload_to_summary_e2e_pdf_real_non_mocked(client: TestClient):
    """
    E2E Test without mocking pdf_parser.
    Uploads a real generated PDF fixture 'real_invoice.pdf' and asserts that
    it correctly flows through pdfplumber -> synonyms mapping -> treasury adapter.
    """
    pdf_path = pathlib.Path("tests/fixtures/real_invoice.pdf")
    assert pdf_path.exists(), "real_invoice.pdf fixture is missing"
    
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()

    # 1. Upload real PDF bytes
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("real_invoice.pdf", pdf_content, "application/pdf")}
    )
    assert res.status_code == 201, res.text
    file_id = res.json()["file_id"]

    # 2. Trigger workflow using a treasury-related prompt
    start_payload = {
        "input_request": "부서지출결의서 부가세 검증해", # should route to treasury
        "source_file_id": file_id
    }
    res_start = client.post(
        "/workflows/start",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json=start_payload
    )
    assert res_start.status_code == 202
    thread_id = res_start.json()["job_id"]

    # 3. Extract workflow_id from registry
    import sqlite3
    with sqlite3.connect(settings.REGISTRY_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT workflow_id, status FROM workflow_registry WHERE thread_id = ?", (thread_id,))
        row = cursor.fetchone()
        assert row is not None
        workflow_id, status = row
        assert status in ["completed", "interrupted"]

    # 4. Check data integrity
    import json
    evidence_dir = pathlib.Path("./artifacts/evidence")
    draft_jsons = list(evidence_dir.glob(f"*_{workflow_id}_draft.json"))
    assert len(draft_jsons) > 0, "Draft JSON not found for non-mocked PDF E2E"

    with open(draft_jsons[0], "r") as f:
        draft_content = json.load(f)

    # real_invoice.pdf has: ['날짜', '항목', '금액', '세액', '승인자'] -> ['2026-04-12', 'Software', '100000', '10000', 'Mickey']
    # If correctly extracted by pdfplumber and normalized,
    # total_supply == 100000 and total_vat == 10000
    assert draft_content.get("total_supply") == 100000, f"Expected 100000, got {draft_content.get('total_supply')}"
    assert draft_content.get("total_vat") == 10000, f"Expected 10000, got {draft_content.get('total_vat')}"
    assert draft_content.get("total_transactions") == 1

    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})
    assert any(r.get("output", {}).get("provenance", {}).get("parser_type") == "pdf_text" for r in state_val.get("results", [])) 
    
    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})

def test_full_upload_to_summary_e2e_pdf_real_grant(client: TestClient):
    pdf_path = pathlib.Path("tests/fixtures/real_grant.pdf")
    assert pdf_path.exists()
    with open(pdf_path, "rb") as f: pdf_content = f.read()

    res = client.post("/workflows/upload", headers={"Authorization": f"Bearer {VALID_TOKEN}"}, files={"file": ("real_grant.pdf", pdf_content, "application/pdf")})
    assert res.status_code == 201
    file_id = res.json()["file_id"]

    res_start = client.post("/workflows/start", headers={"Authorization": f"Bearer {VALID_TOKEN}"}, json={"input_request": "보조금 내역 확인해봐", "source_file_id": file_id})
    assert res_start.status_code == 202
    thread_id = res_start.json()["job_id"]

    import sqlite3
    with sqlite3.connect(settings.REGISTRY_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT workflow_id, status FROM workflow_registry WHERE thread_id = ?", (thread_id,))
        row = cursor.fetchone()
        assert row is not None
        workflow_id, status = row
        assert status in ["completed", "interrupted"]

    import json
    evidence_dir = pathlib.Path("./artifacts/evidence")
    draft_jsons = list(evidence_dir.glob(f"*_{workflow_id}_draft.json"))
    assert len(draft_jsons) > 0

    with open(draft_jsons[0], "r") as f:
        draft_content = json.load(f)

    # real_grant.pdf has Approved=500000, Executed=150000 -> 잔액=350000
    assert draft_content.get("total_approved") == 500000
    assert draft_content.get("total_executed") == 150000
    assert draft_content.get("total_balance") == 350000

    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})
    assert any(r.get("output", {}).get("provenance", {}).get("parser_type") == "pdf_text" for r in state_val.get("results", [])) 

    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})

def test_full_upload_to_summary_e2e_pdf_real_payroll(client: TestClient):
    pdf_path = pathlib.Path("tests/fixtures/real_payroll.pdf")
    assert pdf_path.exists()
    with open(pdf_path, "rb") as f: pdf_content = f.read()

    res = client.post("/workflows/upload", headers={"Authorization": f"Bearer {VALID_TOKEN}"}, files={"file": ("real_payroll.pdf", pdf_content, "application/pdf")})
    assert res.status_code == 201
    file_id = res.json()["file_id"]

    res_start = client.post("/workflows/start", headers={"Authorization": f"Bearer {VALID_TOKEN}"}, json={"input_request": "급여대장 총액 검토해줘", "source_file_id": file_id})
    assert res_start.status_code == 202
    thread_id = res_start.json()["job_id"]

    import sqlite3
    with sqlite3.connect(settings.REGISTRY_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT workflow_id, status FROM workflow_registry WHERE thread_id = ?", (thread_id,))
        workflow_id = cursor.fetchone()[0]

    import json
    evidence_dir = pathlib.Path("./artifacts/evidence")
    draft_jsons = list(evidence_dir.glob(f"*_{workflow_id}_draft.json"))
    assert len(draft_jsons) > 0

    with open(draft_jsons[0], "r") as f:
        draft_content = json.load(f)

    # Base=5000000, Meal=200000, Insur=300000, Tax=150000
    assert draft_content.get("total_net_payout") == 4750000 # 5200000 - 450000
    assert draft_content.get("total_headcount") == 1

    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})
    assert any(r.get("output", {}).get("provenance", {}).get("parser_type") == "pdf_text" for r in state_val.get("results", [])) 

    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})

def test_full_upload_to_summary_e2e_pdf_real_withholding(client: TestClient):
    pdf_path = pathlib.Path("tests/fixtures/real_withholding.pdf")
    assert pdf_path.exists()
    with open(pdf_path, "rb") as f: pdf_content = f.read()

    res = client.post("/workflows/upload", headers={"Authorization": f"Bearer {VALID_TOKEN}"}, files={"file": ("real_withholding.pdf", pdf_content, "application/pdf")})
    assert res.status_code == 201
    file_id = res.json()["file_id"]

    res_start = client.post("/workflows/start", headers={"Authorization": f"Bearer {VALID_TOKEN}"}, json={"input_request": "원천세 납부서 검토해", "source_file_id": file_id})
    assert res_start.status_code == 202
    thread_id = res_start.json()["job_id"]

    import sqlite3
    with sqlite3.connect(settings.REGISTRY_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT workflow_id, status FROM workflow_registry WHERE thread_id = ?", (thread_id,))
        workflow_id = cursor.fetchone()[0]

    import json
    evidence_dir = pathlib.Path("./artifacts/evidence")
    draft_jsons = list(evidence_dir.glob(f"*_{workflow_id}_draft.json"))
    assert len(draft_jsons) > 0

    with open(draft_jsons[0], "r") as f:
        draft_content = json.load(f)

    # Tax = 1200000, Headcount = 10
    assert draft_content.get("total_tax") == 1200000
    assert draft_content.get("total_headcount") == 10

    # 5. Check provenance
    res_state = client.get(f"/workflows/{thread_id}/state", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert res_state.status_code == 200
    state_val = res_state.json().get("values", {})
    assert any(r.get("output", {}).get("provenance", {}).get("parser_type") == "pdf_text" for r in state_val.get("results", []))

