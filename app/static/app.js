// Autonomous Research & Fact-Checking Assistant - Frontend Logic

let currentRunId = null;
let eventSource = null;
let currentRunData = {
  plan: null,
  sources: [],
  claims: [],
  conflicts: [],
  report: null,
  logs: []
};

document.addEventListener("DOMContentLoaded", () => {
  initUI();
  fetchConfig();
  setupEventListeners();
});

function initUI() {
  // Check if URL has run_id param
  const urlParams = new URLSearchParams(window.location.search);
  const runId = urlParams.get("run_id");
  if (runId) {
    loadExistingRun(runId);
  }
}

function setupEventListeners() {
  // Preset topic chips
  document.querySelectorAll(".chip, .inquiry-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.getAttribute("data-query");
      document.getElementById("queryInput").value = q;
      document.getElementById("queryInput").focus();
    });
  });

  // Form submission
  document.getElementById("researchForm").addEventListener("submit", handleStartResearch);

  // Tabs
  document.querySelectorAll(".tab-btn, .docket-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn, .docket-tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPane = document.getElementById(btn.getAttribute("data-tab"));
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // Toggle Activity Terminal Drawer
  document.getElementById("btnToggleTerminal").addEventListener("click", () => {
    const drawer = document.getElementById("terminalDrawer");
    drawer.style.display = (drawer.style.display === "block") ? "none" : "block";
  });

  // Claims Filter
  document.querySelectorAll(".filter-chip, .stance-btn").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".filter-chip, .stance-btn").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      renderClaims();
    });
  });
  document.getElementById("claimsFilterInput").addEventListener("input", renderClaims);

  // Copy Markdown
  document.getElementById("btnCopyReport").addEventListener("click", () => {
    if (currentRunData.report && currentRunData.report.markdown_content) {
      navigator.clipboard.writeText(currentRunData.report.markdown_content).then(() => {
        alert("Markdown report copied to clipboard!");
      });
    }
  });

  // Download Markdown
  document.getElementById("btnDownloadReport").addEventListener("click", () => {
    if (currentRunId) {
      window.location.href = `/api/export/${currentRunId}/markdown`;
    }
  });

  // Settings Modal
  const settingsModal = document.getElementById("settingsModal");
  document.getElementById("btnOpenSettings").addEventListener("click", () => {
    settingsModal.classList.add("active");
  });
  document.getElementById("btnCloseSettings").addEventListener("click", () => {
    settingsModal.classList.remove("active");
  });
  document.getElementById("btnCancelSettings").addEventListener("click", () => {
    settingsModal.classList.remove("active");
  });
  document.getElementById("btnSaveSettings").addEventListener("click", saveConfig);

  // Fact-Check Modal
  const factCheckModal = document.getElementById("factCheckModal");
  document.getElementById("btnOpenClaimVerifier").addEventListener("click", () => {
    factCheckModal.classList.add("active");
  });
  document.getElementById("btnCloseFactCheck").addEventListener("click", () => {
    factCheckModal.classList.remove("active");
  });
  document.getElementById("btnRunQuickCheck").addEventListener("click", runQuickFactCheck);

  // Close modals on backdrop click
  [settingsModal, factCheckModal].forEach(modal => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.remove("active");
    });
  });
}

// --- Start Autonomous Research ---
async function handleStartResearch(e) {
  e.preventDefault();
  const query = document.getElementById("queryInput").value.trim();
  if (!query) return;

  const depthRadio = document.querySelector('input[name="depth"]:checked');
  const depth = depthRadio ? depthRadio.value : "balanced";

  const btn = document.getElementById("btnStartResearch");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-small"></span><span>Agent Running...</span>`;

  // Reset UI
  resetRunState();
  document.getElementById("progressSection").style.display = "block";
  document.getElementById("resultsSection").style.display = "block";

  try {
    const res = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, depth })
    });
    const data = await res.json();
    currentRunId = data.run_id;
    window.history.pushState({}, "", `?run_id=${currentRunId}`);
    
    // Connect to SSE event stream
    connectEventSource(currentRunId);
  } catch (err) {
    console.error("Failed to start research:", err);
    alert("Error starting research agent. Check console.");
    btn.disabled = false;
    btn.innerHTML = `<span>Start Autonomous Research</span>`;
  }
}

function resetRunState() {
  currentRunData = { plan: null, sources: [], claims: [], conflicts: [], report: null, logs: [] };
  document.getElementById("terminalLogBody").innerHTML = "";
  document.getElementById("terminalMeta").textContent = "0 tool calls";
  document.getElementById("progressBarFill").style.width = "5%";
  document.getElementById("currentStepText").textContent = "Initializing agent...";
  
  // Reset steppers
  ["planning", "searching", "extracting", "claims", "conflicts", "synthesis"].forEach(s => {
    const node = document.getElementById(`step-node-${s}`);
    if (node) {
      node.classList.remove("active", "completed");
    }
  });

  document.getElementById("claimsGridContainer").innerHTML = "";
  document.getElementById("conflictsListContainer").innerHTML = "";
  document.getElementById("sourcesListContainer").innerHTML = "";
  document.getElementById("reportContentContainer").innerHTML = '<div class="loading-state">Agent synthesizing multi-source findings...</div>';
  document.getElementById("claimsCountBadge").textContent = "0";
  document.getElementById("conflictsCountBadge").textContent = "0";
  document.getElementById("sourcesCountBadge").textContent = "0";
}

// --- SSE Event Stream ---
function connectEventSource(runId) {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource(`/api/research/${runId}/events`);

  eventSource.addEventListener("state_sync", (e) => {
    const data = JSON.parse(e.data);
    applyStateSync(data);
  });

  eventSource.addEventListener("stage_change", (e) => {
    const data = JSON.parse(e.data);
    updateStageUI(data.status, data.step, data.progress);
  });

  eventSource.addEventListener("log", (e) => {
    const msg = typeof e.data === "string" ? JSON.parse(e.data).message || e.data : e.data;
    appendTerminalLog(msg, "log-system");
  });

  eventSource.addEventListener("tool_log", (e) => {
    const log = JSON.parse(e.data);
    currentRunData.logs.push(log);
    renderToolAuditRow(log);
    appendTerminalLog(`[TOOL CALL] ${log.tool_name} (${log.duration_ms}ms) -> ${log.output_summary}`, "log-tool");
    document.getElementById("terminalMeta").textContent = `${currentRunData.logs.length} tool calls`;
  });

  eventSource.addEventListener("plan_ready", (e) => {
    const plan = JSON.parse(e.data);
    currentRunData.plan = plan;
    renderPlan(plan);
  });

  eventSource.addEventListener("source_extracted", (e) => {
    const src = JSON.parse(e.data);
    currentRunData.sources.push(src);
    renderSources();
    document.getElementById("sourcesCountBadge").textContent = currentRunData.sources.length;
  });

  eventSource.addEventListener("claims_ready", (e) => {
    const claims = JSON.parse(e.data);
    currentRunData.claims = claims;
    renderClaims();
    document.getElementById("claimsCountBadge").textContent = currentRunData.claims.length;
  });

  eventSource.addEventListener("conflicts_ready", (e) => {
    const conflicts = JSON.parse(e.data);
    currentRunData.conflicts = conflicts;
    renderConflicts();
    document.getElementById("conflictsCountBadge").textContent = currentRunData.conflicts.length;
  });

  eventSource.addEventListener("report_complete", (e) => {
    const report = JSON.parse(e.data);
    currentRunData.report = report;
    renderReport(report);
    onRunFinished();
  });

  eventSource.onerror = (err) => {
    console.warn("EventSource stream closed or reconnecting:", err);
  };
}

function updateStageUI(status, stepText, progress) {
  if (progress !== undefined) {
    document.getElementById("progressBarFill").style.width = `${progress}%`;
  }
  if (stepText) {
    document.getElementById("currentStepText").textContent = stepText;
  }

  const stageMap = {
    "planning": "planning",
    "searching": "searching",
    "extracting": "extracting",
    "analyzing_claims": "claims",
    "detecting_conflicts": "conflicts",
    "synthesizing": "synthesis",
    "completed": "synthesis"
  };

  const currentStageKey = stageMap[status];
  const stageOrder = ["planning", "searching", "extracting", "claims", "conflicts", "synthesis"];
  const curIdx = stageOrder.indexOf(currentStageKey);

  stageOrder.forEach((stage, idx) => {
    const node = document.getElementById(`step-node-${stage}`);
    if (!node) return;
    if (idx < curIdx) {
      node.classList.remove("active");
      node.classList.add("completed");
    } else if (idx === curIdx) {
      node.classList.add("active");
      node.classList.remove("completed");
    } else {
      node.classList.remove("active", "completed");
    }
  });

  if (status === "completed") {
    stageOrder.forEach(stage => {
      const node = document.getElementById(`step-node-${stage}`);
      if (node) {
        node.classList.remove("active");
        node.classList.add("completed");
      }
    });
    document.getElementById("agentSpinner").style.display = "none";
    document.getElementById("btnStartResearch").disabled = false;
    document.getElementById("btnStartResearch").innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
      <span>Start Autonomous Research</span>
    `;
  }
}

function onRunFinished() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function appendTerminalLog(msg, typeClass = "") {
  const body = document.getElementById("terminalLogBody");
  const time = new Date().toLocaleTimeString([], { hour12: false });
  const entry = document.createElement("div");
  entry.className = `log-entry ${typeClass}`;
  entry.textContent = `[${time}] ${msg}`;
  body.appendChild(entry);
  body.scrollTop = body.scrollHeight;
}

// --- Renderers ---

function renderPlan(plan) {
  const container = document.getElementById("planDetailsContainer");
  if (!plan) return;

  let stepsHtml = plan.search_plan.map(step => `
    <div class="plan-step-item">
      <div class="plan-step-header">
        <span class="plan-step-id">${step.step_id}</span>
        <span class="plan-step-title">${step.title}</span>
      </div>
      <p style="font-size:0.8rem; color:var(--text-muted);">${step.rationale}</p>
      <div class="plan-step-queries">Queries: ${step.search_queries.join(" • ")}</div>
    </div>
  `).join("");

  container.innerHTML = `
    <div class="plan-objective"><strong>Objective:</strong> ${plan.objective}</div>
    <div style="margin-bottom: 12px; font-size: 0.85rem; color: var(--accent-cyan);">
      <strong>Focus Dimensions:</strong> ${plan.focus_areas.join(" | ")}
    </div>
    <div class="plan-steps-list">${stepsHtml}</div>
  `;
}

function renderSources() {
  const container = document.getElementById("sourcesListContainer");
  container.innerHTML = currentRunData.sources.map(s => {
    let credClass = s.credibility_score >= 88 ? "high" : (s.credibility_score >= 78 ? "med" : "mod");
    return `
      <div class="source-card">
        <div class="source-cred-badge">
          <span class="cred-score ${credClass}">${s.credibility_score}</span>
          <span class="cred-label">Cred</span>
        </div>
        <div class="source-info">
          <a class="source-title-link" href="${s.url}" target="_blank" rel="noopener">${s.title}</a>
          <div class="source-meta-line">
            <span>[${s.source_id}]</span>
            <span>🌐 ${s.domain}</span>
            <span>📅 ${s.published_date || "Recent"}</span>
            <span>⚖️ ${s.credibility_rationale}</span>
          </div>
          <p class="source-snippet">${s.snippet || (s.full_text ? s.full_text.slice(0, 200) + '...' : '')}</p>
        </div>
      </div>
    `;
  }).join("");
}

function renderClaims() {
  const container = document.getElementById("claimsGridContainer");
  const activeChip = document.querySelector(".filter-chip.active, .stance-btn.active");
  const activeStance = activeChip ? activeChip.getAttribute("data-stance") : "all";
  const keyword = document.getElementById("claimsFilterInput").value.toLowerCase().trim();

  const filtered = currentRunData.claims.filter(c => {
    const matchesStance = (activeStance === "all") || (c.stance.toLowerCase() === activeStance);
    const matchesKeyword = !keyword || (
      c.statement.toLowerCase().includes(keyword) || 
      c.quote.toLowerCase().includes(keyword) ||
      (c.topic && c.topic.toLowerCase().includes(keyword))
    );
    return matchesStance && matchesKeyword;
  });

  if (!filtered.length) {
    container.innerHTML = `<div style="grid-column: 1/-1; padding: 30px; text-align: center; color: var(--text-dim);">No claims match current filter criteria.</div>`;
    return;
  }

  container.innerHTML = filtered.map(c => {
    const stanceClass = `stance-${c.stance.toLowerCase()}`;
    const metricsHtml = (c.metrics_mentioned || []).map(m => `<span class="metric-tag">${m}</span>`).join("");
    return `
      <div class="claim-card">
        <div>
          <div class="claim-header">
            <span class="claim-id">${c.claim_id} • ${c.source_id}</span>
            <span class="claim-stance ${stanceClass}">${c.stance}</span>
          </div>
          <div class="claim-statement">${c.statement}</div>
        </div>
        <div class="claim-quote">"${c.quote}"</div>
        ${metricsHtml ? `<div class="claim-metrics">${metricsHtml}</div>` : ''}
        <div class="claim-footer">
          <span>Confidence: <strong>${c.confidence.toUpperCase()}</strong></span>
          <a class="claim-source-link" href="${c.source_url || '#'}" target="_blank" rel="noopener">View Source →</a>
        </div>
      </div>
    `;
  }).join("");
}

function renderConflicts() {
  const container = document.getElementById("conflictsListContainer");
  const conflicts = currentRunData.conflicts;
  
  if (!conflicts.length) {
    container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted); background: var(--bg-secondary); border-radius: var(--radius-md);">No direct empirical contradictions identified. Evidence across sources aligns on core trajectories.</div>`;
    return;
  }

  container.innerHTML = conflicts.map(conf => {
    const sevClass = conf.severity.toLowerCase() === "high" ? "conflict-severity-high" : "conflict-severity-medium";
    return `
      <div class="conflict-card">
        <div class="conflict-header">
          <span class="conflict-title">${conf.topic}</span>
          <div class="conflict-tags">
            <span class="${sevClass}">${conf.severity.toUpperCase()} SEVERITY</span>
            <span class="conflict-type-pill">${conf.conflict_type.replace(/_/g, " ")}</span>
          </div>
        </div>
        <div class="conflict-body">
          <div class="conflict-point"><strong>Discrepancy:</strong> ${conf.conflicting_point}</div>
          <div class="conflict-comparison-grid">
            <div class="perspective-box">
              <div class="perspective-header">Perspective A (${conf.source_a_title || conf.source_a_id})</div>
              <div class="perspective-claim">"${conf.claim_a}"</div>
            </div>
            <div class="perspective-box">
              <div class="perspective-header">Perspective B (${conf.source_b_title || conf.source_b_id})</div>
              <div class="perspective-claim">"${conf.claim_b}"</div>
            </div>
          </div>
          <div class="conflict-resolution-box">
            <div class="resolution-title">Fact-Checking Arbiter Resolution</div>
            <div class="resolution-text">${conf.resolution_assessment}</div>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function renderReport(report) {
  const container = document.getElementById("reportContentContainer");
  if (!report || !report.markdown_content) return;

  // Render markdown with marked.js or basic fallback
  let rawHtml = "";
  if (typeof marked !== "undefined" && marked.parse) {
    rawHtml = marked.parse(report.markdown_content);
  } else {
    rawHtml = report.markdown_content.replace(/\n\n/g, "<p>").replace(/# (.*)/g, "<h1>$1</h1>");
  }

  // Convert bracketed citations [1], [2], [1, 2] into interactive hoverable pills
  const enhancedHtml = rawHtml.replace(/\[(\d+(?:,\s*\d+)*)\]/g, (match, nums) => {
    const numList = nums.split(",").map(n => n.trim());
    return numList.map(n => `<span class="citation-pill" data-citation="${n}">[${n}]</span>`).join("");
  });

  container.innerHTML = enhancedHtml;

  // Bind tooltip hover listeners to citation pills
  setupCitationTooltips(report.citations || []);

  document.getElementById("reportGeneratedTime").textContent = `Generated: ${new Date().toLocaleTimeString()}`;
  document.getElementById("reportSourcesAttributed").textContent = `${(report.citations || []).length} Sources Cited`;
}

function setupCitationTooltips(citations) {
  const tooltip = document.getElementById("citationTooltip");
  const citMap = {};
  citations.forEach(c => {
    citMap[c.citation_num] = c;
  });

  document.querySelectorAll(".citation-pill").forEach(pill => {
    pill.addEventListener("mouseenter", (e) => {
      const num = pill.getAttribute("data-citation");
      const cit = citMap[num];
      if (!cit) return;

      document.getElementById("ttBadge").textContent = `[${num}]`;
      document.getElementById("ttTitle").textContent = cit.title || "Consulted Source";
      document.getElementById("ttDomain").textContent = `🌐 ${cit.domain || 'Source Reference'}`;
      document.getElementById("ttQuote").textContent = cit.key_quote ? `"${cit.key_quote}"` : "Evidence cited in report.";
      document.getElementById("ttLink").href = cit.url || "#";

      const rect = pill.getBoundingClientRect();
      tooltip.style.left = `${Math.min(window.innerWidth - 340, Math.max(10, rect.left - 100))}px`;
      tooltip.style.top = `${rect.bottom + 8}px`;
      tooltip.style.display = "block";
    });

    pill.addEventListener("mouseleave", () => {
      setTimeout(() => {
        if (!tooltip.matches(":hover")) {
          tooltip.style.display = "none";
        }
      }, 200);
    });
  });

  tooltip.addEventListener("mouseleave", () => {
    tooltip.style.display = "none";
  });
}

function renderToolAuditRow(log) {
  const tbody = document.getElementById("toolAuditTableBody");
  const tr = document.createElement("tr");
  const time = log.timestamp ? log.timestamp.split("T")[1].slice(0, 8) : "";
  const paramsStr = JSON.stringify(log.input_args).slice(0, 60);

  tr.innerHTML = `
    <td>${time}</td>
    <td><span class="tool-name-badge">${log.tool_name}</span></td>
    <td title='${JSON.stringify(log.input_args)}'>${paramsStr}</td>
    <td>${log.output_summary}</td>
    <td style="color:var(--accent-cyan); font-weight:600;">${log.duration_ms}ms</td>
  `;
  tbody.appendChild(tr);
}

// --- Quick Claim Verifier ---
async function runQuickFactCheck() {
  const claim = document.getElementById("singleClaimInput").value.trim();
  if (!claim) return;

  const btn = document.getElementById("btnRunQuickCheck");
  btn.disabled = true;
  btn.textContent = "Verifying across sources...";

  const resDiv = document.getElementById("quickCheckResult");
  resDiv.style.display = "none";

  try {
    const res = await fetch("/api/verify-claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim })
    });
    const data = await res.json();
    
    document.getElementById("qcVerdictTag").textContent = data.verdict;
    document.getElementById("qcConfidenceTag").textContent = `Confidence: ${data.confidence}%`;
    document.getElementById("qcSummaryText").textContent = data.summary;

    const sourcesHtml = (data.sources_consulted || []).map(s => `
      <div class="qc-source-item">
        <strong>${s.title}</strong> - <a href="${s.url}" target="_blank" style="color:var(--accent-cyan);">${s.url}</a>
        <p style="margin-top:4px; color:var(--text-muted); font-size:0.75rem;">${s.snippet}</p>
      </div>
    `).join("");
    document.getElementById("qcSourcesList").innerHTML = sourcesHtml;

    resDiv.style.display = "block";
  } catch (err) {
    console.error("Fact-check error:", err);
    alert("Error verifying claim.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Verify Claim";
  }
}

// --- Config & Settings ---
async function fetchConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    
    // Update status badge
    const badgeText = document.getElementById("providerStatusText");
    if (data.provider === "groq") {
      badgeText.textContent = `Provider: Groq (${data.groq_model})`;
    } else if (data.provider === "nvidia") {
      badgeText.textContent = `Provider: NVIDIA (${data.nvidia_model})`;
    } else {
      badgeText.textContent = "Provider: Demo / Simulated Pipeline";
    }

    // Populate modal fields
    document.getElementById("cfgProvider").value = data.provider;
    if (data.groq_configured) {
      document.getElementById("cfgGroqKey").placeholder = data.groq_key_preview;
    }
    if (data.nvidia_configured) {
      document.getElementById("cfgNvidiaKey").placeholder = data.nvidia_key_preview;
    }
  } catch (err) {
    console.warn("Could not fetch server config:", err);
  }
}

async function saveConfig() {
  const provider = document.getElementById("cfgProvider").value;
  const groq_key = document.getElementById("cfgGroqKey").value.trim() || undefined;
  const nvidia_key = document.getElementById("cfgNvidiaKey").value.trim() || undefined;
  const tavily_key = document.getElementById("cfgTavilyKey").value.trim() || undefined;

  try {
    await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, groq_key, nvidia_key, tavily_key })
    });
    document.getElementById("settingsModal").classList.remove("active");
    fetchConfig();
    alert("Settings updated!");
  } catch (err) {
    console.error("Failed to save config:", err);
    alert("Error saving settings.");
  }
}

async function loadExistingRun(runId) {
  try {
    const res = await fetch(`/api/research/${runId}`);
    if (res.ok) {
      const data = await res.json();
      currentRunId = runId;
      applyStateSync(data);
      document.getElementById("progressSection").style.display = "block";
      document.getElementById("resultsSection").style.display = "block";
      if (data.status !== "completed" && data.status !== "failed") {
        connectEventSource(runId);
      }
    }
  } catch (err) {
    console.warn("Could not load run:", err);
  }
}

function applyStateSync(data) {
  if (data.plan) {
    currentRunData.plan = data.plan;
    renderPlan(data.plan);
  }
  if (data.sources) {
    currentRunData.sources = data.sources;
    renderSources();
    document.getElementById("sourcesCountBadge").textContent = data.sources.length;
  }
  if (data.claims) {
    currentRunData.claims = data.claims;
    renderClaims();
    document.getElementById("claimsCountBadge").textContent = data.claims.length;
  }
  if (data.conflicts) {
    currentRunData.conflicts = data.conflicts;
    renderConflicts();
    document.getElementById("conflictsCountBadge").textContent = data.conflicts.length;
  }
  if (data.report) {
    currentRunData.report = data.report;
    renderReport(data.report);
  }
  if (data.logs) {
    currentRunData.logs = data.logs;
    document.getElementById("toolAuditTableBody").innerHTML = "";
    data.logs.forEach(renderToolAuditRow);
    document.getElementById("terminalMeta").textContent = `${data.logs.length} tool calls`;
  }
  updateStageUI(data.status, data.current_step, data.progress_percent);
}
