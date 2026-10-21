from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class PlanStep(BaseModel):
    step_id: str = Field(description="Unique identifier for the step e.g. STEP-1")
    title: str = Field(description="Descriptive title of what this step investigates")
    rationale: str = Field(description="Why this angle or perspective is crucial to investigate")
    search_queries: List[str] = Field(description="Specific, targeted search queries for this step")

class ResearchPlan(BaseModel):
    objective: str = Field(description="The primary research objective and scope")
    focus_areas: List[str] = Field(description="Key dimensions or themes to explore")
    search_plan: List[PlanStep] = Field(description="Step-by-step breakdown of search queries to execute")
    initial_hypotheses: List[str] = Field(description="Plausible competing hypotheses or viewpoints to test")
    required_perspectives: List[str] = Field(default_factory=list, description="Different viewpoints needed (e.g., industry, academic, consumer, regulator)")

class SourceDocument(BaseModel):
    source_id: str = Field(description="Short unique ID e.g. SRC-1")
    url: str = Field(description="Source URL")
    title: str = Field(description="Title of the webpage or document")
    domain: str = Field(description="Domain name e.g. nature.com, bbc.com")
    snippet: str = Field(description="Brief summary or search snippet")
    full_text: Optional[str] = Field(default="", description="Clean extracted main text")
    published_date: Optional[str] = Field(default="Unknown", description="Publication date if available")
    credibility_score: int = Field(default=80, description="Credibility score 0-100 based on source authority and neutrality")
    credibility_rationale: str = Field(default="Standard web publication", description="Reasoning for credibility score")

class Claim(BaseModel):
    claim_id: str = Field(description="Unique claim ID e.g. CLM-1")
    topic: str = Field(description="Topic or subtopic category")
    statement: str = Field(description="Clear, atomic factual assertion")
    source_id: str = Field(description="ID of the source asserting this claim (e.g. SRC-1)")
    source_url: Optional[str] = Field(default="", description="URL of the source")
    quote: str = Field(description="Exact verbatim or near-verbatim quote from the source supporting the claim")
    stance: Literal["supports", "refutes", "neutral", "conditional"] = Field(
        description="Whether this source supports, refutes, stays neutral, or puts heavy conditions on the core topic"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        default="high",
        description="Confidence level in the accuracy and rigor of this specific claim"
    )
    metrics_mentioned: List[str] = Field(
        default_factory=list,
        description="Quantitative figures, percentages, dates, or dollar amounts mentioned in the claim"
    )

class ClaimExtractionResult(BaseModel):
    claims: List[Claim] = Field(description="List of discrete atomic claims extracted from the source text")

class Conflict(BaseModel):
    conflict_id: str = Field(description="Unique conflict ID e.g. CONF-1")
    topic: str = Field(description="Subject matter of the disagreement")
    conflicting_point: str = Field(description="Detailed explanation of the exact point of contradiction or divergence")
    source_a_id: str = Field(description="Source ID for perspective A")
    source_a_title: Optional[str] = Field(default="", description="Title of Source A")
    claim_a: str = Field(description="Claim or data asserted by perspective A")
    source_b_id: str = Field(description="Source ID for perspective B")
    source_b_title: Optional[str] = Field(default="", description="Title of Source B")
    claim_b: str = Field(description="Opposing or divergent claim asserted by perspective B")
    conflict_type: Literal[
        "metric_discrepancy",
        "timeline_disagreement",
        "causality_dispute",
        "methodology_difference",
        "definitional_conflict"
    ] = Field(description="The underlying category of conflict")
    severity: Literal["high", "medium", "low"] = Field(
        description="High: direct mutual contradiction; Medium: divergent forecasts or numbers; Low: differing emphasis or scope"
    )
    resolution_assessment: str = Field(
        description="Fact-checking synthesis: why do these sources differ? (e.g. different baseline years, differing definitions, bias, or uncertainty)"
    )

class ConflictAnalysisResult(BaseModel):
    conflicts: List[Conflict] = Field(description="List of detected factual or numerical conflicts between sources")
    overall_consensus_summary: str = Field(description="Summary of points where all or most sources agree")

class CitationItem(BaseModel):
    citation_num: int = Field(description="Reference index e.g. 1")
    source_id: str = Field(description="Source ID matching SourceDocument.source_id")
    url: str = Field(description="URL to the source")
    title: str = Field(description="Title of the source")
    domain: str = Field(description="Domain name")
    key_quote: str = Field(description="Supporting quote attributed to this citation")

class CitedReport(BaseModel):
    title: str = Field(description="Comprehensive and engaging title of the research report")
    executive_summary: str = Field(description="Concise 2-3 paragraph summary of core findings, consensus, and debates")
    background: str = Field(description="Context and why this topic is significant")
    key_findings: List[str] = Field(description="Bulleted core takeaways with inline citations like [1], [2]")
    conflict_analysis_section: str = Field(description="Detailed narrative discussing identified disputes and conflicting evidence")
    conclusions: str = Field(description="Balanced verdict, nuances, and open questions")
    citations: List[CitationItem] = Field(description="Numbered bibliography matching all inline citations")
    markdown_content: str = Field(description="Full markdown formatted report with embedded citations [1], headers, and tables")

class ToolExecutionLog(BaseModel):
    timestamp: str = Field(description="ISO timestamp")
    tool_name: str = Field(description="Name of the tool called")
    input_args: Dict[str, Any] = Field(description="Arguments passed to the tool")
    output_summary: str = Field(description="Summary of the tool's return value")
    duration_ms: int = Field(description="Execution latency in milliseconds")
    status: Literal["success", "warning", "error"] = Field(default="success")

class ResearchRun(BaseModel):
    run_id: str
    query: str
    depth: Literal["quick", "balanced", "deep"] = "balanced"
    status: Literal["pending", "planning", "searching", "extracting", "analyzing_claims", "detecting_conflicts", "synthesizing", "completed", "failed"] = "pending"
    current_step: str = "Initialized"
    progress_percent: int = 0
    plan: Optional[ResearchPlan] = None
    sources: List[SourceDocument] = Field(default_factory=list)
    claims: List[Claim] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)
    report: Optional[CitedReport] = None
    logs: List[ToolExecutionLog] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    error: Optional[str] = None
