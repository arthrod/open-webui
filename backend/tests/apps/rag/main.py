import pytest
from fastapi.testclient import TestClient
from backend.apps.rag.main import app, store_doc, store_text, TextRAGForm

client = TestClient(app)

def test_store_doc():
    with open("backend/tests/apps/rag/HR email Contacts 1.pdf", "rb") as file:
        response = client.post(
            "/doc",
            files={"file": ("HR email Contacts 1.pdf", file, "application/pdf")},
            data={"collection_name": "test_collection"}
        )
    assert response.status_code == 200
    assert response.json()["status"] == True
    assert response.json()["collection_name"] == "test_collection"
    assert response.json()["filename"] == "test.pdf"

def test_store_text():
    form_data = {
        "name": "test_name",
        "content": "test_content",
        "collection_name": "test_collection"
    }
    response = client.post("/text", json=form_data)
    assert response.status_code == 200
    assert response.json()["status"] == True
    assert response.json()["collection_name"] == "test_collection"
