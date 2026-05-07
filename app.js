const API_BASE_KEY = "curtis-api-base";
const DEFAULT_API_BASE = "https://curtis-app-production.up.railway.app";
const PUBLIC_YOUTUBE_SOURCE = "https://www.youtube.com/@nalalan";

const skillDimensions = [
  { id: "intonation", label: "Intonation", focus: "Pitch center, double-stops, exposed entrances." },
  { id: "time", label: "Time", focus: "Pulse, subdivision, tempo stability." },
  { id: "tone", label: "Tone", focus: "Core sound, projection, contact point." },
  { id: "articulation", label: "Articulation", focus: "Attack, release, bow clarity." },
  { id: "shifts", label: "Shifts", focus: "Position changes, preparation, arrival quality." },
  { id: "musicality", label: "Musicality", focus: "Phrase shape, contrast, long line." },
  { id: "auditionDelivery", label: "Audition delivery", focus: "Start state, recovery, room-ready control." }
];

let backend = {
  online: false,
  ops: null,
  lastError: ""
};

const elements = {
  youtubeState: document.querySelector("#youtubeState"),
  inventoryCount: document.querySelector("#inventoryCount"),
  practiceState: document.querySelector("#practiceState"),
  reviewState: document.querySelector("#reviewState"),
  modelState: document.querySelector("#modelState"),
  sourceLink: document.querySelector("#sourceLink"),
  runScanButton: document.querySelector("#runScanButton"),
  probeMediaButton: document.querySelector("#probeMediaButton"),
  currentState: document.querySelector("#currentState"),
  evidenceState: document.querySelector("#evidenceState"),
  workingState: document.querySelector("#workingState"),
  focusState: document.querySelector("#focusState"),
  constraintState: document.querySelector("#constraintState"),
  boundaryState: document.querySelector("#boundaryState"),
  sessionPlan: document.querySelector("#sessionPlan"),
  pieceState: document.querySelector("#pieceState"),
  pieceProgress: document.querySelector("#pieceProgress"),
  pieceTip: document.querySelector("#pieceTip"),
  pieceCount: document.querySelector("#pieceCount"),
  pieceList: document.querySelector("#pieceList"),
  recordSummary: document.querySelector("#recordSummary"),
  inventoryList: document.querySelector("#inventoryList"),
  reviewedCount: document.querySelector("#reviewedCount"),
  sectionCount: document.querySelector("#sectionCount"),
  skillSummary: document.querySelector("#skillSummary"),
  skillMap: document.querySelector("#skillMap"),
  backendState: document.querySelector("#backendState"),
  storageState: document.querySelector("#storageState"),
  automationState: document.querySelector("#automationState"),
  mediaState: document.querySelector("#mediaState"),
  instagramState: document.querySelector("#instagramState")
};

function apiBase() {
  const params = new URLSearchParams(window.location.search);
  const explicit = params.get("api") || "";
  if (explicit) return explicit.replace(/\/$/, "");
  if (window.location.hostname === "curtis.aolabs.io") return "";
  const configured = localStorage.getItem(API_BASE_KEY) || "";
  if (configured) return configured.replace(/\/$/, "");
  if (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") {
    return window.location.port === "8000" ? "" : "http://127.0.0.1:8000";
  }
  if (window.location.hostname.endsWith("up.railway.app")) return "";
  return DEFAULT_API_BASE;
}

async function apiFetch(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${apiBase()}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      },
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return await response.json();
  } finally {
    window.clearTimeout(timeout);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function youtubeSource(ops) {
  return String(ops?.sources?.youtube || "").trim() || PUBLIC_YOUTUBE_SOURCE;
}

function youtubeSourceHref(source) {
  if (source.startsWith("http://") || source.startsWith("https://")) return source;
  if (source.startsWith("@")) return `https://www.youtube.com/${source}`;
  return PUBLIC_YOUTUBE_SOURCE;
}

function sourcePayload() {
  return {
    youtube: youtubeSource(backend.ops),
    instagram: "",
    scanScope: "Latest public posts",
    scanCadence: "Daily"
  };
}

async function loadBackendState() {
  try {
    backend = {
      online: true,
      ops: await apiFetch("/api/curtis/ops-check"),
      lastError: ""
    };
  } catch (error) {
    backend = {
      online: false,
      ops: null,
      lastError: String(error?.message || error || "offline")
    };
  }
  render();
}

async function runBackendScan() {
  elements.runScanButton.disabled = true;
  elements.runScanButton.textContent = "Scanning";
  try {
    backend = {
      online: true,
      ops: await apiFetch("/api/curtis/scan/run", {
        method: "POST",
        body: JSON.stringify(sourcePayload())
      }),
      lastError: ""
    };
  } catch (error) {
    backend = {
      online: false,
      ops: null,
      lastError: String(error?.message || error || "offline")
    };
  } finally {
    elements.runScanButton.disabled = false;
    elements.runScanButton.textContent = "Run scan";
    render();
  }
}

async function runMediaProbe() {
  elements.probeMediaButton.disabled = true;
  elements.probeMediaButton.textContent = "Fetching";
  try {
    backend = {
      online: true,
      ops: await apiFetch("/api/curtis/media/probe", {
        method: "POST",
        body: JSON.stringify({})
      }),
      lastError: ""
    };
  } catch (error) {
    backend = {
      online: false,
      ops: null,
      lastError: String(error?.message || error || "offline")
    };
  } finally {
    elements.probeMediaButton.disabled = false;
    elements.probeMediaButton.textContent = "Get media";
    render();
  }
}

function youtubeLabel(ops) {
  const auth = ops?.auth?.youtube || {};
  const credentials = ops?.credentials || {};
  const source = youtubeSource(ops);
  if (auth.connected) return auth.channelTitle ? `Connected / ${auth.channelTitle}` : "Connected";
  if (source) return source.replace("https://www.youtube.com/", "");
  if (credentials.youtubeApiKey) return "Public API ready";
  return "API key missing";
}

function automationLabel(ops) {
  const blockers = ops?.blockers || [];
  const inventoryTotal = inventoryItems(ops).length;
  if (inventoryTotal) return "Inventory ready";
  if (blockers.includes("youtube_channel_not_found")) return "Channel not found";
  if (blockers.includes("missing_youtube_api_key_or_oauth")) return "YouTube key missing";
  if (blockers.includes("youtube_api_error")) return "YouTube API error";
  if (blockers.includes("youtube_scan_failed")) return "Scan failed";
  if (blockers.includes("unresolved_youtube_source")) return "Source unresolved";
  if (!youtubeSource(ops)) return "Source missing";
  return ops?.status || "Ready";
}

function currentStateText(ops) {
  if (!backend.online) return `Backend offline: ${backend.lastError}`;
  const inventoryTotal = inventoryItems(ops).length;
  const practiceCount = Number(ops?.review?.practiceCandidateCount) || 0;
  const findingCount = skillFindings(ops).length;
  if (findingCount) return `${findingCount} Curtis-focused findings. ${progressPlan(ops)?.oneFocus || "Review active."}`;
  const sectionCount = reviewSections(ops).length;
  if (sectionCount) return `${sectionCount} audio/video sections scanned. Musicianship judgment pending.`;
  if (practiceCount) return `${practiceCount} likely practice/music videos indexed. Section listening pending.`;
  if (inventoryTotal) return `${inventoryTotal} public YouTube videos indexed. Practice filter pending.`;
  const blockers = [...new Set([...(ops?.lastScan?.blockers || []), ...(ops?.blockers || [])])];
  if (blockers.includes("youtube_channel_not_found")) return "Public channel not found.";
  if (blockers.includes("missing_youtube_api_key_or_oauth")) return "YouTube API key missing.";
  if (blockers.includes("youtube_api_error")) return "YouTube API returned an error.";
  if (blockers.includes("youtube_data_api_returns_metadata_not_video_media")) return "Metadata indexed. Media-section review pending.";
  return "Ready for public YouTube scan.";
}

function inventoryItems(ops) {
  return Array.isArray(ops?.inventory?.youtube) ? ops.inventory.youtube : [];
}

function reviewSections(ops) {
  return Array.isArray(ops?.review?.notableSections) ? ops.review.notableSections : [];
}

function skillFindings(ops) {
  return Array.isArray(ops?.review?.skillFindings) ? ops.review.skillFindings : [];
}

function progressPlan(ops) {
  return ops?.review?.progressPlan && typeof ops.review.progressPlan === "object"
    ? ops.review.progressPlan
    : null;
}

function pieces(ops) {
  return Array.isArray(ops?.review?.pieces) ? ops.review.pieces : [];
}

function primaryPiece(ops) {
  const list = pieces(ops);
  return list.length ? list[0] : null;
}

function currentPiece(ops) {
  return ops?.review?.todayPiece && typeof ops.review.todayPiece === "object"
    ? ops.review.todayPiece
    : primaryPiece(ops);
}

function isIdentifiedPiece(piece) {
  return Boolean(piece?.title && piece.title !== "Piece being identified");
}

function pieceLabel(piece) {
  if (!piece) return "Identifying from practice sessions.";
  if (isIdentifiedPiece(piece)) return piece.title;
  return "Piece being identified";
}

function pieceTip(piece) {
  if (!piece) return "Capture one clear excerpt.";
  const tip = String(piece.todayTip || piece.tip || "Capture one clearer excerpt.").trim();
  const signal = `${piece.title || ""} ${piece.evidence || ""} ${piece.candidateEvidence || ""}`.toLowerCase();
  if (/^capture one clear(er)? excerpt\.?$/i.test(tip)) {
    if (signal.includes("ricochet") || signal.includes("arpeggio")) {
      return "Slow the left-hand arpeggio targets first, then add one short controlled ricochet burst.";
    }
    if (signal.includes("etude") || signal.includes("caprice")) {
      return "Isolate one small technical cell and record a slower clean take.";
    }
  }
  return tip;
}

function todayCompletion(piece) {
  if (!piece) return 0;
  return Number(piece.todayCompletionPercent ?? piece.completionPercent) || 0;
}

function progressText(piece) {
  if (!piece) return "0%";
  if (!isIdentifiedPiece(piece) || piece.confidence !== "clear") return "Identifying";
  return `${todayCompletion(piece)}%`;
}

function completionLabel(piece) {
  if (!isIdentifiedPiece(piece) || piece.confidence !== "clear") return "Identifying";
  const today = todayCompletion(piece);
  const overall = Number(piece?.completionPercent) || 0;
  return piece?.isActiveToday ? `${today}% today` : `${overall}% overall`;
}

function pieceEvidence(piece) {
  if (!piece) return "";
  const evidence = String(piece.candidateEvidence || piece.evidence || "").trim();
  if (!evidence) return "";
  return isIdentifiedPiece(piece) ? evidence : `Signal: ${evidence}`;
}

function workingText(ops) {
  const samples = Number(ops?.media?.sampleCount) || (Array.isArray(ops?.media?.samples) ? ops.media.samples.length : 0);
  const sections = reviewSections(ops).length;
  const findings = skillFindings(ops).length;
  if (findings) return `${samples} samples / ${sections} sections / ${findings} findings`;
  if (sections) return `${samples} samples / ${sections} sections`;
  if (samples) return `${samples} samples captured`;
  if (inventoryItems(ops).length) return `${inventoryItems(ops).length} videos indexed`;
  return backend.online ? "Ready" : "Offline";
}

function mediaStateLabel(value) {
  if (value === "metadata_ready_media_blocked") return "metadata ready";
  if (value === "media_url_ready") return "media ready";
  return value || "queued";
}

function mediaAccessLabel(ops) {
  const run = ops?.media?.lastMediaRun;
  const samples = Array.isArray(ops?.media?.samples) ? ops.media.samples : [];
  if (samples.length) return "Sample ready";
  if (run?.blockers?.includes("youtube_media_fetch_requires_owner_browser_or_export")) return "Owner export needed";
  if (run?.blockers?.includes("youtube_media_fetch_needs_cookies")) return "Browser access needed";
  if (run?.status === "blocked") return "Blocked";
  if (ops?.review?.mediaAccess === "metadata_only") return "Metadata only";
  return "Not fetched";
}

function videoBadge(item) {
  if (item.mediaKind === "practice_log") return "practice log";
  if (item.mediaKind === "performance_or_rehearsal") return "rehearsal";
  if (item.mediaKind === "music_candidate") return "music";
  return mediaStateLabel(item.analysisState);
}

function renderStatus() {
  const ops = backend.ops || {};
  const inventory = inventoryItems(ops);
  const sections = reviewSections(ops);
  const findings = skillFindings(ops);
  const piece = currentPiece(ops);
  const pieceList = pieces(ops);
  const plan = progressPlan(ops);
  const reviewedVideos = Number(ops?.review?.reviewedVideoCount) || 0;
  const practiceCount = Number(ops?.review?.practiceCandidateCount) || 0;
  const longFormCount = Number(ops?.review?.longFormCandidateCount) || 0;
  const model = ops?.model ? `${ops.model.id} / ${ops.model.reasoningEffort}` : "Not reported";

  elements.youtubeState.textContent = backend.online ? youtubeLabel(ops) : "Offline";
  elements.inventoryCount.textContent = `${inventory.length} videos`;
  elements.practiceState.textContent = longFormCount
    ? `${practiceCount} candidates / ${longFormCount} long`
    : `${practiceCount} candidates`;
  elements.reviewState.textContent = sections.length ? `${sections.length} sections` : "Unjudged";
  elements.modelState.textContent = model;
  elements.evidenceState.textContent = findings.length ? `${findings.length} findings` : sections.length ? "Sections ready" : "Unjudged";
  elements.workingState.textContent = workingText(ops);
  elements.focusState.textContent = plan?.oneFocus || (sections.length ? "Model review pending." : "Capture playable sections.");
  elements.constraintState.textContent = plan?.practiceConstraint || "One focus per session.";
  elements.boundaryState.textContent = plan?.boundary || "No admission prediction from current samples.";
  const session = Array.isArray(plan?.sessionPlan) && plan.sessionPlan.length
    ? plan.sessionPlan.slice(0, 3)
    : ["Capture clear violin audio."];
  elements.sessionPlan.innerHTML = session.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  elements.pieceState.textContent = pieceLabel(piece);
  elements.pieceProgress.textContent = progressText(piece);
  elements.pieceTip.textContent = pieceTip(piece);
  elements.pieceCount.textContent = `${pieceList.length} ${pieceList.length === 1 ? "piece" : "pieces"}`;
  const source = youtubeSource(ops);
  elements.sourceLink.href = youtubeSourceHref(source);
  elements.sourceLink.textContent = source.replace("https://www.", "").replace("https://", "");
  elements.currentState.textContent = currentStateText(ops);
  elements.recordSummary.textContent = `${inventory.length} videos / ${sections.length} sections / ${findings.length} findings`;
  elements.reviewedCount.textContent = `${reviewedVideos} reviewed`;
  elements.sectionCount.textContent = `${sections.length} sections`;
  elements.backendState.textContent = backend.online ? "Online" : "Offline";
  elements.storageState.textContent = backend.online ? "Backend state" : "Browser only";
  elements.automationState.textContent = backend.online ? automationLabel(ops) : "Offline";
  elements.mediaState.textContent = backend.online ? mediaAccessLabel(ops) : "Offline";
  elements.instagramState.textContent = ops?.credentials?.instagramGraph ? "Configured" : "Not configured";

}

function renderPieces() {
  const list = pieces(backend.ops);
  if (!backend.online) {
    elements.pieceList.innerHTML = `<p class="empty">Backend offline.</p>`;
    return;
  }
  if (!list.length) {
    elements.pieceList.innerHTML = `<p class="empty">Piece list pending clearer evidence.</p>`;
    return;
  }
  elements.pieceList.innerHTML = list.slice(0, 8).map((piece) => `
    <article class="piece-row">
      <div>
        <span>${escapeHtml(piece.confidence || "unknown")}</span>
        <strong>${escapeHtml(pieceLabel(piece))}</strong>
        <p>${escapeHtml(pieceEvidence(piece) || pieceTip(piece))}</p>
      </div>
      <em>${escapeHtml(completionLabel(piece))}</em>
    </article>
  `).join("");
}

function renderInventory() {
  const inventory = inventoryItems(backend.ops);
  const candidates = inventory.filter((item) => item.practiceCandidate);
  if (!backend.online) {
    elements.inventoryList.innerHTML = `<p class="empty">Backend offline.</p>`;
    return;
  }
  if (!inventory.length) {
    elements.inventoryList.innerHTML = `<p class="empty">No public videos indexed.</p>`;
    return;
  }
  const displayItems = (candidates.length ? candidates : inventory).slice(0, 8);
  elements.inventoryList.innerHTML = displayItems.map((item) => {
    const meta = [formatDate(item.publishedAt), item.duration, item.viewCount ? `${item.viewCount} views` : ""]
      .filter(Boolean)
      .join(" / ");
    return `
      <article class="video-row">
        <div>
          <span>${escapeHtml(meta || item.channelTitle || "YouTube")}</span>
          <a href="${escapeHtml(item.url)}">${escapeHtml(item.title || item.url || "YouTube video")}</a>
        </div>
        <em>${escapeHtml(videoBadge(item))}</em>
      </article>
    `;
  }).join("");
}

function clipCountsForDimension(id) {
  const entries = [
    ...reviewSections(backend.ops).filter((entry) => entry.dimension === id),
    ...skillFindings(backend.ops).filter((entry) => entry.dimension === id)
  ];
  return {
    total: entries.length,
    strong: entries.filter((entry) => entry.judgment === "Strong signal").length,
    needs: entries.filter((entry) => entry.judgment === "Needs work").length,
    regression: entries.filter((entry) => entry.judgment === "Regression").length
  };
}

function evidenceForDimension(id, fallback) {
  const priority = { "Needs work": 3, "Strong signal": 2, "Unjudged": 1 };
  const entry = skillFindings(backend.ops)
    .filter((finding) => finding.dimension === id && finding.evidence)
    .sort((a, b) => (priority[b.judgment] || 0) - (priority[a.judgment] || 0))[0];
  return entry ? entry.evidence : fallback;
}

function dimensionStatus(counts) {
  if (!counts.total) return "Unjudged";
  if (counts.regression) return "Regression";
  if (counts.needs > counts.strong) return "Needs work";
  if (counts.strong) return "Strong signal";
  return "Unjudged";
}

function renderSkillMap() {
  const inventoryTotal = inventoryItems(backend.ops).length;
  const sections = reviewSections(backend.ops);
  const practiceCount = Number(backend.ops?.review?.practiceCandidateCount) || 0;
  const needs = skillDimensions
    .map((dimension) => ({ ...dimension, counts: clipCountsForDimension(dimension.id) }))
    .filter((dimension) => ["Needs work", "Regression"].includes(dimensionStatus(dimension.counts)));

  if (!sections.length && practiceCount) {
    elements.skillSummary.textContent = "Practice corpus ready. Section listening pending.";
  } else if (!sections.length && inventoryTotal) {
    elements.skillSummary.textContent = "Inventory ready. Practice filter pending.";
  } else if (!sections.length) {
    elements.skillSummary.textContent = "No video sections processed.";
  } else if (needs.length) {
    elements.skillSummary.textContent = `Current work: ${needs.map((dimension) => dimension.label).join(", ")}.`;
  } else if (sections.every((section) => section.judgment === "Unjudged")) {
    elements.skillSummary.textContent = "Candidate sections scanned. Musicianship judgment pending.";
  } else {
    elements.skillSummary.textContent = "No weakness claim from current evidence.";
  }

  if (!sections.length) {
    elements.skillMap.innerHTML = `<p class="empty">Skill map pending section review.</p>`;
    return;
  }

  elements.skillMap.innerHTML = skillDimensions.map((dimension) => {
    const counts = clipCountsForDimension(dimension.id);
    const status = dimensionStatus(counts);
    return `
      <article class="skill-row" data-status="${escapeHtml(status)}">
        <div>
          <span>${escapeHtml(status)}</span>
          <strong>${escapeHtml(dimension.label)}</strong>
          <p>${escapeHtml(evidenceForDimension(dimension.id, dimension.focus))}</p>
        </div>
        <em>${counts.total}</em>
      </article>
    `;
  }).join("");
}

function render() {
  renderStatus();
  renderPieces();
  renderInventory();
  renderSkillMap();
}

elements.runScanButton.addEventListener("click", runBackendScan);
elements.probeMediaButton.addEventListener("click", runMediaProbe);

render();
loadBackendState();
