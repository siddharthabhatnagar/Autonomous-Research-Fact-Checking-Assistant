import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_home_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Autonomous Research & Fact-Checking" in response.text
    print("Test home page: PASS")

def test_get_config():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert "groq_model" in data
    print("Test get config: PASS")

def test_quick_claim_verify():
    response = client.post("/api/verify-claim", json={"claim": "Bananas contain potassium-40 and are radioactive"})
    assert response.status_code == 200
    data = response.json()
    assert "verdict" in data
    assert "confidence" in data
    assert len(data["sources_consulted"]) >= 0
    print(f"Test quick claim verify: PASS (Verdict: {data['verdict']})")

def test_start_research_api():
    response = client.post("/api/research", json={
        "query": "Quantum computing timeline",
        "depth": "quick"
    })
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "pending"
    print(f"Test start research API: PASS (Run ID: {data['run_id']})")

if __name__ == "__main__":
    print("Running FastAPI endpoint tests...")
    test_home_page()
    test_get_config()
    test_quick_claim_verify()
    test_start_research_api()
    print("\nALL API TESTS PASSED!")
