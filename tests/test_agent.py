import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
from app.agent.tools import search_web_aggregated, extract_page_content, calculate_credibility
from app.agent.models import ResearchPlan, PlanStep, SourceDocument, Claim, Conflict, CitedReport
from app.agent.orchestrator import ResearchOrchestrator, RUNS_STORE

def test_calculate_credibility():
    score, rationale = calculate_credibility("https://www.nature.com/articles/d41586-024-00001", "Nature Article")
    assert score >= 90
    assert "Peer-reviewed" in rationale

    score_gov, rationale_gov = calculate_credibility("https://www.energy.gov/articles/fusion", "DOE Report")
    assert score_gov >= 95
    assert "government" in rationale_gov.lower()

def test_search_web():
    results = search_web_aggregated("Quantum computing breakthrough", max_results=3)
    assert len(results) > 0
    assert "url" in results[0]
    assert "title" in results[0]

def test_extract_page_content():
    extracted = extract_page_content("https://en.wikipedia.org/wiki/Artificial_intelligence", max_length=1000)
    assert extracted["status"] == "success"
    assert "Artificial intelligence" in extracted["title"]
    assert len(extracted["full_text"]) > 100

def test_orchestrator_execution():
    events_received = []
    def on_event(etype, data):
        events_received.append(etype)

    orchestrator = ResearchOrchestrator(
        run_id="test-run-001",
        query="Impact of Artificial Intelligence on Global Employment",
        depth="quick",
        event_callback=on_event
    )
    run = orchestrator.execute()

    assert run.status == "completed"
    assert run.plan is not None
    assert len(run.sources) > 0
    assert len(run.claims) > 0
    assert run.report is not None
    assert len(run.report.citations) > 0
    assert "stage_change" in events_received
    assert "report_complete" in events_received

if __name__ == "__main__":
    print("Running tests...")
    test_calculate_credibility()
    print("Credibility test passed!")
    test_search_web()
    print("Search web test passed!")
    test_extract_page_content()
    print("Extract page content test passed!")
    test_orchestrator_execution()
    print("Orchestrator end-to-end execution test passed!")
    print("\nALL AGENT TESTS PASSED!")
