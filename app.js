const STORAGE_KEY = "curtis-admission-record-v1";
const API_BASE_KEY = "curtis-api-base";
const DEFAULT_API_BASE = "https://curtis-app-production.up.railway.app";

const tasks = [
  { id: "profile", label: "Instrument and program", meta: "Required before department repertoire can be locked." },
  { id: "repertoire", label: "Department repertoire", meta: "Official audition page by instrument or department." },
  { id: "prescreening", label: "Prescreening files", meta: "Due with application when required by department." },
  { id: "writtenEssay", label: "Written essay", meta: "One prompt selected from official application set." },
  { id: "videoEssay", label: "Video essay", meta: "One prompt selected from official application set." },
  { id: "recommendations", label: "Three recommendations", meta: "Private teacher plus two qualified musicians or mentors." },
  { id: "transcript", label: "Transcript", meta: "Unofficial upload; official copy after acceptance." },
  { id: "fee", label: "Fee waiver or payment", meta: "Application, screening, audition, and late-fee boundary." },
  { id: "liveAudition", label: "Live audition logistics", meta: "February and March in-person rounds when invited." },
  { id: "sourceReview", label: "Source review", meta: "Official Curtis pages checked before claims change." }
];

const facts = [
  {
    label: "Process",
    text: "Admission is a two-step process: applying and auditioning.",
    url: "https://www.curtis.edu/apply/applying/"
  },
  {
    label: "Timeline",
    text: "General cycle: applications open in September; early December deadline; January-February audition invitations; February-March live auditions.",
    url: "https://www.curtis.edu/apply/applying/"
  },
  {
    label: "Prescreening",
    text: "Prescreening materials are due with the application when required by department.",
    url: "https://www.curtis.edu/apply/faq/"
  },
  {
    label: "Recommendations",
    text: "Three recommendations: current private teacher plus two qualified musicians or mentors.",
    url: "https://www.curtis.edu/apply/applying/"
  },
  {
    label: "Boundary",
    text: "Submitting an application does not obligate Curtis to provide an audition.",
    url: "https://www.curtis.edu/apply/applying/"
  },
  {
    label: "Audition",
    text: "Audition dates, repertoire, and prescreening requirements vary by department.",
    url: "https://www.curtis.edu/apply/audition/"
  },
  {
    label: "Age",
    text: "Curtis states no minimum or maximum age to audition.",
    url: "https://www.curtis.edu/learn/"
  }
];

const skillDimensions = [
  { id: "intonation", label: "Intonation", focus: "Pitch center, double-stops, exposed entrances." },
  { id: "time", label: "Time", focus: "Pulse, subdivision, tempo stability." },
  { id: "tone", label: "Tone", focus: "Core sound, projection, contact point." },
  { id: "articulation", label: "Articulation", focus: "Attack, release, bow clarity." },
  { id: "shifts", label: "Shifts", focus: "Position changes, preparation, arrival quality." },
  { id: "musicality", label: "Musicality", focus: "Phrase shape, contrast, long line." },
  { id: "auditionDelivery", label: "Audition delivery", focus: "Start state, recovery, room-ready control." }
];

const defaultState = {
  profile: {
    instrument: "",
    program: "",
    cycle: "Next open cycle",
    teacher: ""
  },
  taskState: Object.fromEntries(tasks.map((task) => [task.id, task.id === "sourceReview" ? "active" : "unset"])),
  repertoire: [],
  logs: [],
  sources: {
    youtube: "",
    instagram: "",
    scanScope: "Latest public posts",
    scanCadence: "Run now"
  },
  clips: []
};

let state = loadState();
let backend = {
  online: false,
  ops: null,
  lastError: ""
};

const elements = {
  profileForm: document.querySelector("#profileForm"),
  instrumentInput: document.querySelector("#instrumentInput"),
  programInput: document.querySelector("#programInput"),
  cycleInput: document.querySelector("#cycleInput"),
  teacherInput: document.querySelector("#teacherInput"),
  taskList: document.querySelector("#taskList"),
  nextOperation: document.querySelector("#nextOperation"),
  progressText: document.querySelector("#progressText"),
  progressFill: document.querySelector("#progressFill"),
  factList: document.querySelector("#factList"),
  completeCount: document.querySelector("#completeCount"),
  activeCount: document.querySelector("#activeCount"),
  pieceCount: document.querySelector("#pieceCount"),
  minuteCount: document.querySelector("#minuteCount"),
  repertoireForm: document.querySelector("#repertoireForm"),
  pieceInput: document.querySelector("#pieceInput"),
  pieceRole: document.querySelector("#pieceRole"),
  pieceState: document.querySelector("#pieceState"),
  repertoireList: document.querySelector("#repertoireList"),
  logForm: document.querySelector("#logForm"),
  logDate: document.querySelector("#logDate"),
  logType: document.querySelector("#logType"),
  logMinutes: document.querySelector("#logMinutes"),
  logNote: document.querySelector("#logNote"),
  logList: document.querySelector("#logList"),
  exportButton: document.querySelector("#exportButton"),
  sourceForm: document.querySelector("#sourceForm"),
  youtubeInput: document.querySelector("#youtubeInput"),
  instagramInput: document.querySelector("#instagramInput"),
  scanScope: document.querySelector("#scanScope"),
  scanCadence: document.querySelector("#scanCadence"),
  youtubeState: document.querySelector("#youtubeState"),
  instagramState: document.querySelector("#instagramState"),
  backendState: document.querySelector("#backendState"),
  automationState: document.querySelector("#automationState"),
  storageState: document.querySelector("#storageState"),
  connectYoutubeButton: document.querySelector("#connectYoutubeButton"),
  runScanButton: document.querySelector("#runScanButton"),
  scanSummary: document.querySelector("#scanSummary"),
  mediaReviewState: document.querySelector("#mediaReviewState"),
  skillSummary: document.querySelector("#skillSummary"),
  skillMap: document.querySelector("#skillMap"),
  clipList: document.querySelector("#clipList"),
  reviewedCount: document.querySelector("#reviewedCount"),
  sectionCount: document.querySelector("#sectionCount")
};

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return structuredClone(defaultState);
    const parsed = JSON.parse(raw);
    const sources = { ...defaultState.sources, ...parsed.sources };
    if (sources.scanScope === "Manual URLs") sources.scanScope = "Latest public posts";
    if (sources.scanCadence === "Manual") sources.scanCadence = "Run now";
    return {
      profile: { ...defaultState.profile, ...parsed.profile },
      taskState: { ...defaultState.taskState, ...parsed.taskState },
      repertoire: Array.isArray(parsed.repertoire) ? parsed.repertoire : [],
      logs: Array.isArray(parsed.logs) ? parsed.logs : [],
      sources,
      clips: Array.isArray(parsed.clips) ? parsed.clips : []
    };
  } catch {
    return structuredClone(defaultState);
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

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
  const timeout = window.setTimeout(() => controller.abort(), 12000);
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

function sourcePayload() {
  return {
    youtube: elements.youtubeInput.value.trim(),
    instagram: elements.instagramInput.value.trim(),
    scanScope: elements.scanScope.value,
    scanCadence: elements.scanCadence.value
  };
}

function setBackendOps(ops) {
  syncSourcesFromBackend(ops);
  backend = {
    online: true,
    ops,
    lastError: ""
  };
}

function syncSourcesFromBackend(ops) {
  const sources = ops?.sources || {};
  let changed = false;
  ["youtube", "instagram", "scanScope", "scanCadence"].forEach((key) => {
    const value = sources[key];
    if (typeof value !== "string" || !value.trim()) return;
    if (state.sources[key] === value) return;
    if (key === "youtube" || key === "instagram") {
      state.sources[key] = value;
      changed = true;
      return;
    }
    if (!state.sources[key] || state.sources[key] === defaultState.sources[key]) {
      state.sources[key] = value;
      changed = true;
    }
  });
  if (changed) saveState();
}

function setBackendOffline(error) {
  backend = {
    online: false,
    ops: null,
    lastError: error ? String(error.message || error) : "offline"
  };
}

async function loadBackendState() {
  try {
    setBackendOps(await apiFetch("/api/curtis/ops-check"));
  } catch (error) {
    setBackendOffline(error);
  }
  render();
}

async function saveSourcesToBackend() {
  try {
    setBackendOps(await apiFetch("/api/curtis/sources", {
      method: "POST",
      body: JSON.stringify(state.sources)
    }));
  } catch (error) {
    setBackendOffline(error);
  }
}

async function runBackendScan() {
  elements.runScanButton.disabled = true;
  elements.runScanButton.textContent = "Scanning";
  state.sources = sourcePayload();
  saveState();
  render();
  try {
    setBackendOps(await apiFetch("/api/curtis/scan/run", {
      method: "POST",
      body: JSON.stringify(state.sources)
    }));
  } catch (error) {
    setBackendOffline(error);
  } finally {
    elements.runScanButton.disabled = false;
    elements.runScanButton.textContent = "Run Scan";
    render();
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function renderProfile() {
  elements.instrumentInput.value = state.profile.instrument;
  elements.programInput.value = state.profile.program;
  elements.cycleInput.value = state.profile.cycle;
  elements.teacherInput.value = state.profile.teacher;
  elements.logDate.value ||= today();
}

function setTask(id, value) {
  state.taskState[id] = value;
  saveState();
  render();
}

function renderTasks() {
  elements.taskList.innerHTML = tasks.map((task) => {
    const current = state.taskState[task.id] || "unset";
    const controls = ["unset", "active", "complete"].map((value) => `
      <button type="button" data-task="${task.id}" data-state="${value}" aria-pressed="${current === value}">
        ${value}
      </button>
    `).join("");
    return `
      <article class="task-row">
        <div>
          <span class="task-meta">${escapeHtml(task.meta)}</span>
          <p class="task-title">${escapeHtml(task.label)}</p>
        </div>
        <div class="task-controls" aria-label="${escapeHtml(task.label)} status">${controls}</div>
      </article>
    `;
  }).join("");

  elements.taskList.querySelectorAll("button[data-task]").forEach((button) => {
    button.addEventListener("click", () => setTask(button.dataset.task, button.dataset.state));
  });
}

function renderFacts() {
  elements.factList.innerHTML = facts.map((fact) => `
    <div>
      <dt>${escapeHtml(fact.label)}</dt>
      <dd>${escapeHtml(fact.text)} <a href="${fact.url}">Source</a></dd>
    </div>
  `).join("");
}

function renderRepertoire() {
  if (!state.repertoire.length) {
    elements.repertoireList.innerHTML = '<p class="empty">No repertoire entries.</p>';
    return;
  }

  elements.repertoireList.innerHTML = state.repertoire.map((entry) => `
    <article class="entry-row">
      <div>
        <span class="entry-meta">${escapeHtml(entry.role)} / ${escapeHtml(entry.state)}</span>
        <p class="entry-title">${escapeHtml(entry.piece)}</p>
      </div>
      <button type="button" class="entry-delete" data-delete-piece="${entry.id}" aria-label="Remove repertoire entry">X</button>
    </article>
  `).join("");

  elements.repertoireList.querySelectorAll("[data-delete-piece]").forEach((button) => {
    button.addEventListener("click", () => {
      state.repertoire = state.repertoire.filter((entry) => entry.id !== button.dataset.deletePiece);
      saveState();
      render();
    });
  });
}

function renderLogs() {
  const logs = [...state.logs].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 12);
  if (!logs.length) {
    elements.logList.innerHTML = '<p class="empty">No work log entries.</p>';
    return;
  }

  elements.logList.innerHTML = logs.map((entry) => `
    <article class="entry-row">
      <div>
        <span class="entry-meta">${escapeHtml(entry.date)} / ${escapeHtml(entry.type)} / ${Number(entry.minutes) || 0} min</span>
        <p class="entry-title">${escapeHtml(entry.note || "Recorded work")}</p>
      </div>
      <button type="button" class="entry-delete" data-delete-log="${entry.id}" aria-label="Remove log entry">X</button>
    </article>
  `).join("");

  elements.logList.querySelectorAll("[data-delete-log]").forEach((button) => {
    button.addEventListener("click", () => {
      state.logs = state.logs.filter((entry) => entry.id !== button.dataset.deleteLog);
      saveState();
      render();
    });
  });
}

function renderSources() {
  const ops = backend.ops || {};
  const credentials = ops.credentials || {};
  const youtubeAuth = ops.auth?.youtube || {};
  const blockers = ops.blockers || [];
  const inventory = ops.inventory || { youtube: [], instagram: [] };
  const totalInventory = (inventory.youtube || []).length + (inventory.instagram || []).length;

  elements.youtubeInput.value = state.sources.youtube;
  elements.instagramInput.value = state.sources.instagram;
  elements.scanScope.value = state.sources.scanScope;
  elements.scanCadence.value = state.sources.scanCadence;
  elements.youtubeState.textContent = youtubeAuth.connected
    ? youtubeConnectedLabel(youtubeAuth)
    : credentials.youtubeOAuthConfigured
      ? sourceStateLabel(
      state.sources.youtube,
      credentials.youtubeApiKey || credentials.youtubeOAuthConfigured,
      blockers,
      "youtube"
      )
      : "OAuth setup needed";
  elements.instagramState.textContent = sourceStateLabel(
    state.sources.instagram,
    credentials.instagramGraph,
    blockers,
    "instagram"
  );
  elements.backendState.textContent = backend.online ? automationLabel(ops) : "Offline";
  elements.automationState.textContent = backend.online ? automationLabel(ops) : "Offline";
  elements.storageState.textContent = backend.online ? "Backend state active" : "Browser state only";
  elements.scanSummary.textContent = scanSummaryText(ops, totalInventory);
  elements.connectYoutubeButton.disabled = Boolean(youtubeAuth.connected || !backend.online || !credentials.youtubeOAuthConfigured);
  elements.connectYoutubeButton.textContent = youtubeAuth.connected
    ? "YouTube Connected"
    : credentials.youtubeOAuthConfigured
      ? "Connect YouTube"
      : "OAuth Setup Needed";
}

function automationLabel(ops) {
  const blockers = ops.blockers || [];
  const youtubeAuth = ops.auth?.youtube || {};
  if (youtubeAuth.connected && blockers.length === 1 && blockers.includes("youtube_data_api_returns_metadata_not_video_media")) {
    return "Channel inventory ready";
  }
  if (blockers.includes("missing_youtube_source") && blockers.includes("missing_instagram_source")) {
    return "Source needed";
  }
  if (blockers.includes("missing_youtube_oauth_connection")) return "Connect YouTube";
  if (blockers.includes("youtube_oauth_token_refresh_failed")) return "Reconnect YouTube";
  if (blockers.includes("missing_instagram_access_token_or_user_id")) return "Instagram token needed";
  if (blockers.includes("missing_youtube_api_key_or_oauth")) return "YouTube key needed";
  if (ops.status === "inventory_ready") return "Inventory ready";
  if (ops.status === "blocked") return "Blocked";
  return ops.status || "Ready";
}

function sourceStateLabel(source, credentialReady, blockers, platform) {
  const missingCredential = platform === "youtube"
    ? blockers.includes("missing_youtube_api_key_or_oauth")
    : blockers.includes("missing_instagram_access_token_or_user_id");
  if (!source && credentialReady) return "Credential set / source unset";
  if (!source) return "Unset";
  if (credentialReady && !missingCredential) return "Ready";
  return "Source set / credential blocked";
}

function youtubeConnectedLabel(auth) {
  return auth.channelTitle ? `Connected / ${auth.channelTitle}` : "Connected";
}

function scanSummaryText(ops, totalInventory) {
  if (!backend.online) return `Backend offline: ${backend.lastError || "not reachable"}`;
  const model = ops.model ? `${ops.model.id} / ${ops.model.reasoningEffort}` : "model unset";
  const youtubeAuth = ops.auth?.youtube || {};
  const lastScan = ops.lastScan;
  if (youtubeAuth.connected && totalInventory) {
    return `YouTube connected. Inventory ${totalInventory}. Model ${model}.`;
  }
  if (!lastScan) {
    const blockers = (ops.blockers || []).join(", ") || "none";
    return `Model ${model}. Inventory ${totalInventory}. Blockers: ${blockers}.`;
  }
  const blockers = (lastScan.blockers || []).join(", ") || "none";
  return `Last scan ${lastScan.status}. Inventory ${lastScan.inventoryCount || 0}. Model ${model}. Blockers: ${blockers}.`;
}

function renderClips() {
  const backendSections = backend.ops?.review?.notableSections || [];
  const sections = [...backendSections, ...state.clips];
  const inventory = backend.ops?.inventory || { youtube: [], instagram: [] };
  const queued = [...(inventory.youtube || []), ...(inventory.instagram || [])];

  if (!sections.length && queued.length) {
    elements.clipList.innerHTML = queued.map((entry) => `
      <article class="entry-row">
        <div>
          <span class="entry-meta">${escapeHtml(entry.platform || "media")} / ${escapeHtml(entry.analysisState || "queued")}</span>
          <p class="entry-title">${escapeHtml(entry.title || entry.url || entry.id || "Queued media")}</p>
          ${entry.url ? `<a class="entry-link" href="${escapeHtml(entry.url)}">${escapeHtml(entry.url)}</a>` : ""}
        </div>
      </article>
    `).join("");
    return;
  }

  if (!sections.length) {
    elements.clipList.innerHTML = '<p class="empty">No processed sections.</p>';
    return;
  }

  elements.clipList.innerHTML = sections.map((entry) => {
    const dimension = skillDimensions.find((item) => item.id === entry.dimension);
    const label = dimension ? dimension.label : entry.dimension || "Unjudged";
    const url = entry.url || "";
    return `
      <article class="entry-row">
        <div>
          <span class="entry-meta">${escapeHtml(label)} / ${escapeHtml(entry.judgment || "Unjudged")} / ${escapeHtml(entry.timecode || "no timecode")}</span>
          <p class="entry-title">${escapeHtml(entry.note || url || "Processed section")}</p>
          ${url ? `<a class="entry-link" href="${escapeHtml(url)}">${escapeHtml(url)}</a>` : ""}
        </div>
        ${entry.id && state.clips.some((clip) => clip.id === entry.id)
          ? `<button type="button" class="entry-delete" data-delete-clip="${entry.id}" aria-label="Remove reviewed section">X</button>`
          : ""}
      </article>
    `;
  }).join("");

  elements.clipList.querySelectorAll("[data-delete-clip]").forEach((button) => {
    button.addEventListener("click", () => {
      state.clips = state.clips.filter((entry) => entry.id !== button.dataset.deleteClip);
      saveState();
      render();
    });
  });
}

function clipCountsForDimension(id) {
  const backendSections = backend.ops?.review?.notableSections || [];
  const entries = [...backendSections, ...state.clips].filter((entry) => entry.dimension === id);
  return {
    total: entries.length,
    strong: entries.filter((entry) => entry.judgment === "Strong signal").length,
    needs: entries.filter((entry) => entry.judgment === "Needs work").length,
    regression: entries.filter((entry) => entry.judgment === "Regression").length
  };
}

function dimensionStatus(counts) {
  if (!counts.total) return "Unjudged";
  if (counts.regression) return "Regression";
  if (counts.needs > counts.strong) return "Needs work";
  if (counts.strong) return "Strong signal";
  return "Unjudged";
}

function renderSkillMap() {
  const review = backend.ops?.review || {};
  const backendSections = review.notableSections || [];
  const localReviewedVideos = new Set(state.clips.map((entry) => entry.url)).size;
  const reviewedVideos = Math.max(Number(review.reviewedVideoCount) || 0, localReviewedVideos);
  const inventoryCount = Number(review.inventoryCount) || 0;
  const sectionCount = backendSections.length + state.clips.length;
  elements.mediaReviewState.textContent = `${reviewedVideos} videos reviewed`;

  const needs = skillDimensions
    .map((dimension) => ({ ...dimension, counts: clipCountsForDimension(dimension.id) }))
    .filter((dimension) => {
      const status = dimensionStatus(dimension.counts);
      return status === "Needs work" || status === "Regression";
    });

  if (!sectionCount && inventoryCount) {
    elements.skillSummary.textContent = "Inventory ready. Video-section judgment blocked.";
  } else if (!sectionCount) {
    elements.skillSummary.textContent = "No video reviewed.";
  } else if (needs.length) {
    elements.skillSummary.textContent = `Current work: ${needs.map((dimension) => dimension.label).join(", ")}.`;
  } else {
    elements.skillSummary.textContent = "No weakness claim from current evidence.";
  }

  elements.skillMap.innerHTML = skillDimensions.map((dimension) => {
    const counts = clipCountsForDimension(dimension.id);
    const status = dimensionStatus(counts);
    return `
      <article class="skill-row" data-status="${escapeHtml(status)}">
        <div>
          <span>${escapeHtml(status)}</span>
          <strong>${escapeHtml(dimension.label)}</strong>
          <p>${escapeHtml(dimension.focus)}</p>
        </div>
        <em>${counts.total}</em>
      </article>
    `;
  }).join("");
}

function computeNextOperation() {
  if (!state.profile.instrument.trim() || !state.profile.program.trim()) {
    return "Set instrument and program.";
  }
  if (!state.sources.youtube.trim() && !state.sources.instagram.trim() && !state.clips.length) {
    return "Set practice video source.";
  }
  const blockers = backend.ops?.blockers || [];
  if (blockers.includes("missing_youtube_api_key_or_oauth") || blockers.includes("missing_instagram_access_token_or_user_id")) {
    return "Connect platform credentials.";
  }
  if (backend.ops?.status === "inventory_ready" && !(backend.ops?.review?.reviewedVideoCount)) {
    return "Enable media section processing.";
  }
  if (!state.repertoire.length) {
    return "Enter official department repertoire.";
  }
  const activeTask = tasks.find((task) => state.taskState[task.id] !== "complete");
  if (!activeTask) {
    return "Run source review before submission.";
  }
  if (state.taskState[activeTask.id] === "unset") {
    return `Start ${activeTask.label.toLowerCase()}.`;
  }
  return `Complete ${activeTask.label.toLowerCase()}.`;
}

function renderStats() {
  const values = Object.values(state.taskState);
  const complete = values.filter((value) => value === "complete").length;
  const active = values.filter((value) => value === "active").length;
  const minutes = state.logs.reduce((sum, entry) => sum + (Number(entry.minutes) || 0), 0);
  const review = backend.ops?.review || {};
  const reviewedVideos = Math.max(Number(review.reviewedVideoCount) || 0, new Set(state.clips.map((entry) => entry.url)).size);
  const sectionTotal = (review.notableSections || []).length + state.clips.length;
  const percent = Math.round((complete / tasks.length) * 100);

  elements.completeCount.textContent = complete;
  elements.activeCount.textContent = active;
  elements.pieceCount.textContent = state.repertoire.length;
  elements.minuteCount.textContent = minutes;
  elements.reviewedCount.textContent = reviewedVideos;
  elements.sectionCount.textContent = sectionTotal;
  elements.progressText.textContent = `${complete} / ${tasks.length} complete`;
  elements.progressFill.style.width = `${percent}%`;
  elements.nextOperation.textContent = computeNextOperation();
}

function render() {
  renderProfile();
  renderTasks();
  renderFacts();
  renderRepertoire();
  renderLogs();
  renderSources();
  renderClips();
  renderSkillMap();
  renderStats();
}

elements.profileForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.profile = {
    instrument: elements.instrumentInput.value.trim(),
    program: elements.programInput.value.trim(),
    cycle: elements.cycleInput.value.trim() || "Next open cycle",
    teacher: elements.teacherInput.value.trim()
  };
  state.taskState.profile = state.profile.instrument && state.profile.program ? "complete" : "active";
  saveState();
  render();
});

elements.repertoireForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const piece = elements.pieceInput.value.trim();
  if (!piece) return;
  state.repertoire.unshift({
    id: crypto.randomUUID(),
    piece,
    role: elements.pieceRole.value,
    state: elements.pieceState.value
  });
  state.taskState.repertoire = "active";
  elements.pieceInput.value = "";
  saveState();
  render();
});

elements.logForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const note = elements.logNote.value.trim();
  state.logs.unshift({
    id: crypto.randomUUID(),
    date: elements.logDate.value || today(),
    type: elements.logType.value,
    minutes: Number(elements.logMinutes.value) || 0,
    note
  });
  elements.logNote.value = "";
  elements.logMinutes.value = "";
  saveState();
  render();
});

elements.sourceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.sources = sourcePayload();
  saveState();
  await saveSourcesToBackend();
  render();
});

elements.runScanButton.addEventListener("click", runBackendScan);

elements.connectYoutubeButton.addEventListener("click", () => {
  window.location.href = `${apiBase()}/api/auth/youtube/start`;
});

elements.exportButton.addEventListener("click", async () => {
  const payload = JSON.stringify({ exportedAt: new Date().toISOString(), ...state }, null, 2);
  try {
    await navigator.clipboard.writeText(payload);
    elements.exportButton.textContent = "Copied";
  } catch {
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `curtis-record-${today()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    elements.exportButton.textContent = "Exported";
  }
  window.setTimeout(() => {
    elements.exportButton.textContent = "Export";
  }, 1200);
});

render();
loadBackendState();
