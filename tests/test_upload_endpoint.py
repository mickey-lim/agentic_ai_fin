import pytest
from fastapi.testclient import TestClient
from src.agentic_poc.application.fastapi_app import app
from src.agentic_poc.config import settings
import jwt
from io import BytesIO

# Test data
VALID_TOKEN = jwt.encode({"sub": "tester123", "role": "reviewer"}, settings.JWT_SECRET, algorithm="HS256")

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

def test_upload_success_excel(client: TestClient):
    file_content = b"fake excel content"
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("test_file.xlsx", BytesIO(file_content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res.status_code == 201
    data = res.json()
    assert "file_id" in data
    assert data["filename"] == "test_file.xlsx"

def test_upload_success_csv(client: TestClient):
    file_content = b"a,b,c\n1,2,3"
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("test_data.csv", BytesIO(file_content), "text/csv")}
    )
    assert res.status_code == 201
    data = res.json()
    assert "file_id" in data
    assert data["filename"] == "test_data.csv"

def test_upload_invalid_mime_type(client: TestClient):
    file_content = b"print('hello')"
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("test.py", BytesIO(file_content), "text/x-python")}
    )
    assert res.status_code == 400
    assert "Invalid MIME type" in res.json()["detail"]

def test_upload_invalid_extension_with_valid_mime(client: TestClient):
    # Testing someone pushing valid mime type but bad string extension
    file_content = b"fake excel content"
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("test_file.exe", BytesIO(file_content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res.status_code == 400
    assert "Invalid extension" in res.json()["detail"]

def test_upload_path_traversal_prevention(client: TestClient):
    file_content = b"fake traversal content"
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("../../../evil.xlsx", BytesIO(file_content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res.status_code == 201
    
    # Needs to check if file isn't uploaded outside.
    data = res.json()
    assert "file_id" in data
    
    # We shouldn't see any ../../
    # Let's ensure evil.xlsx wasn't written to project root
    import pathlib
    assert not pathlib.Path("evil.xlsx").exists()
    assert not pathlib.Path("../../evil.xlsx").exists()

def test_upload_success_image(client: TestClient):
    file_content = b"fake jpeg bytes"
    res = client.post(
        "/workflows/upload",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        files={"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}
    )
    assert res.status_code == 201
    data = res.json()
    assert "file_id" in data
    assert data["filename"] == "receipt.jpg"
