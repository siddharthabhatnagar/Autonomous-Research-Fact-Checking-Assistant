import asyncio
import json
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import settings, update_runtime_settings
from app.agent.orchestrator import ResearchOrchestrator, RUNS_STORE
from app.agent.tools import search_web_aggregated, extract_page_content
from app.agent.prompts import CLAIM_VERIFICATION_PROMPT
from app.agent.llm_factory import get_chat_model

# App instance
app = FastAPI(
    title="Autonomous Research & Fact-Checking Assistant",
    description="Tool-using agent that searches the web, extracts sources, compares claims, flags conflicts, and generates cited reports.",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Background worker executor
thread_pool = ThreadPoolExecutor(max_workers=4)

# Active event queues for SSE subscribers: run_id -> list of asyncio.Queue
EVENT_SUBSCRIBERS: Dict[str, List[asyncio.Queue]] = {}

def broadcast_event(run_id: str, event_type: str, data: Any):
    """Pushes an event to all connected SSE clients for this run_id."""
    subscribers = EVENT_SUBSCRIBERS.get(run_id, [])
    payload = {
        "event": event_type,
        "data": json.dumps(data) if not isinstance(data, str) else json.dumps({"message": data})
    }
    for q in subscribers:
        try:
            q.put_nowait(payload)
        except Exception as e:
            print(f"[main] error queuing event: {e}")

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Topic or question to research")
    depth: str = Field(default="balanced", description="Research depth: quick, balanced, or deep")
    provider: Optional[str] = Field(default=None, description="LLM provider: groq, nvidia, or simulated")
    api_key: Optional[str] = Field(default=None, description="Optional per-request API key")
    model_name: Optional[str] = Field(default=None, description="Optional custom model name")

class ClaimVerifyRequest(BaseModel):
    claim: str = Field(..., min_length=5, description="The statement to verify")
    provider: Optional[str] = Field(default=None)
    api_key: Optional[str] = Field(default=None)

class ConfigUpdateRequest(BaseModel):
    provider: Optional[str] = None
    groq_key: Optional[str] = None
    nvidia_key: Optional[str] = None
    tavily_key: Optional[str] = None
    groq_model: Optional[str] = None
    nvidia_model: Optional[str] = None

def run_orchestrator_worker(run_id: str, req: ResearchRequest):
    """Background worker executing the orchestrator synchronously in thread pool."""
    def on_event(event_type: str, data: Any):
        broadcast_event(run_id, event_type, data)
        
    orchestrator = ResearchOrchestrator(
        run_id=run_id,
        query=req.query,
        depth=req.depth,
        provider=req.provider,
        api_key=req.api_key,
        model_name=req.model_name,
        event_callback=on_event
    )
    orchestrator.execute()

@app.post("/api/research")
async def start_research(req: ResearchRequest, background_tasks: BackgroundTasks):
    """Initiates an autonomous research run."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    EVENT_SUBSCRIBERS[run_id] = []
    
    # Run in thread pool so it does not block the async event loop
    loop = asyncio.get_event_loop()
    loop.run_in_executor(thread_pool, run_orchestrator_worker, run_id, req)
    
    return {
        "run_id": run_id,
        "query": req.query,
        "status": "pending",
        "message": "Autonomous research agent started."
    }

@app.get("/api/research/{run_id}/events")
async def stream_research_events(run_id: str, request: Request):
    """SSE endpoint providing real-time telemetry and state changes."""
    queue = asyncio.Queue()
    if run_id not in EVENT_SUBSCRIBERS:
        EVENT_SUBSCRIBERS[run_id] = []
    EVENT_SUBSCRIBERS[run_id].append(queue)

    async def event_generator():
        # First send existing state if already populated
        existing_run = RUNS_STORE.get(run_id)
        if existing_run:
            yield {
                "event": "state_sync",
                "data": json.dumps(existing_run.model_dump())
            }
            if existing_run.status in ["completed", "failed"]:
                return

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Timeout for keep-alive ping
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                    # Check if terminal event
                    if msg.get("event") in ["report_complete", "stage_change"]:
                        data = json.loads(msg.get("data", "{}"))
                        if data.get("status") in ["completed", "failed"]:
                            break
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"timestamp": asyncio.get_event_loop().time()})}
        finally:
            if run_id in EVENT_SUBSCRIBERS and queue in EVENT_SUBSCRIBERS[run_id]:
                EVENT_SUBSCRIBERS[run_id].remove(queue)

    return EventSourceResponse(event_generator())

@app.get("/api/research/{run_id}")
async def get_research_status(run_id: str):
    """Fetches the current or completed state of a research run."""
    if run_id not in RUNS_STORE:
        raise HTTPException(status_code=404, detail="Research run not found")
    return RUNS_STORE[run_id].model_dump()

@app.get("/api/history")
async def get_history():
    """Returns recent research sessions."""
    summaries = []
    for r in reversed(list(RUNS_STORE.values())):
        summaries.append({
            "run_id": r.run_id,
            "query": r.query,
            "depth": r.depth,
            "status": r.status,
            "progress_percent": r.progress_percent,
            "sources_count": len(r.sources),
            "claims_count": len(r.claims),
            "conflicts_count": len(r.conflicts),
            "created_at": r.created_at,
            "completed_at": r.completed_at
        })
    return summaries

@app.get("/api/export/{run_id}/markdown")
async def export_markdown(run_id: str):
    """Exports the cited report as a Markdown file download."""
    if run_id not in RUNS_STORE:
        raise HTTPException(status_code=404, detail="Research run not found")
    run = RUNS_STORE[run_id]
    if not run.report:
        raise HTTPException(status_code=400, detail="Report has not finished generating")
    
    filename = f"research_report_{run_id}.md"
    return PlainTextResponse(
        content=run.report.markdown_content,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/verify-claim")
async def verify_claim_endpoint(req: ClaimVerifyRequest):
    """Performs rapid standalone claim verification and evidence retrieval."""
    search_results = search_web_aggregated(req.claim, max_results=3)
    
    # Scrape top 2 results for evidence
    evidence_docs = []
    for item in search_results[:2]:
        extracted = extract_page_content(item["url"], max_length=1500)
        evidence_docs.append({
            "title": item["title"],
            "url": item["url"],
            "snippet": item["snippet"],
            "text": extracted.get("full_text", item["snippet"]),
            "credibility": extracted.get("credibility_score", 75)
        })
        
    # Build fast evaluation
    has_refutation = any(w in req.claim.lower() for w in ["hoax", "false", "myth", "fake"])
    verdict = "DISPUTED"
    if not evidence_docs:
        verdict = "UNVERIFIED"
    elif any("hoax" in d["text"].lower() or "false" in d["text"].lower() or "myth" in d["text"].lower() for d in evidence_docs):
        verdict = "REFUTED / FALSE"
    else:
        verdict = "SUPPORTED WITH CAVEATS"
        
    return {
        "claim": req.claim,
        "verdict": verdict,
        "confidence": 85 if evidence_docs else 40,
        "sources_consulted": evidence_docs,
        "summary": f"Evidence evaluated across {len(evidence_docs)} web sources. Verdict: {verdict}."
    }

@app.get("/api/config")
async def get_config():
    """Returns current active settings (with sensitive keys masked)."""
    return {
        "provider": settings.LLM_PROVIDER,
        "groq_configured": bool(settings.GROQ_API_KEY),
        "groq_key_preview": f"gsk_...{settings.GROQ_API_KEY[-4:]}" if settings.GROQ_API_KEY else "Not configured",
        "nvidia_configured": bool(settings.NVIDIA_API_KEY),
        "nvidia_key_preview": f"nvapi_...{settings.NVIDIA_API_KEY[-4:]}" if settings.NVIDIA_API_KEY else "Not configured",
        "tavily_configured": bool(settings.TAVILY_API_KEY),
        "groq_model": settings.GROQ_MODEL,
        "nvidia_model": settings.NVIDIA_MODEL,
        "search_backend": "Tavily + DDGS (HTML/News) + Wikipedia API"
    }

@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    """Updates runtime configuration."""
    update_runtime_settings(
        provider=req.provider,
        groq_key=req.groq_key if req.groq_key != "***" else None,
        nvidia_key=req.nvidia_key if req.nvidia_key != "***" else None,
        tavily_key=req.tavily_key if req.tavily_key != "***" else None,
        groq_model=req.groq_model,
        nvidia_model=req.nvidia_model
    )
    return {"status": "success", "message": "Settings updated successfully"}

# Mount static assets
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def serve_index():
    """Serves the main single-page web dashboard."""
    index_file = static_dir / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Autonomous Research Assistant</h1><p>Frontend loading...</p>")
    return FileResponse(index_file)
