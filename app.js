const STORAGE_KEY = "curtis-admission-record-v1";

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
    scanScope: "Manual URLs",
    scanCadence: "Manual"
  },
  clips: []
};

let state = loadState();

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
  mediaReviewState: document.querySelector("#mediaReviewState"),
  skillSummary: document.querySelector("#skillSummary"),
  skillMap: document.querySelector("#skillMap"),
  clipForm: document.querySelector("#clipForm"),
  clipUrl: document.querySelector("#clipUrl"),
  clipTimecode: document.querySelector("#clipTimecode"),
  clipDimension: document.querySelector("#clipDimension"),
  clipJudgment: document.querySelector("#clipJudgment"),
  clipNote: document.querySelector("#clipNote"),
  clipList: document.querySelector("#clipList"),
  reviewedCount: document.querySelector("#reviewedCount"),
  sectionCount: document.querySelector("#sectionCount")
};

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return structuredClone(defaultState);
    const parsed = JSON.parse(raw);
    return {
      profile: { ...defaultState.profile, ...parsed.profile },
      taskState: { ...defaultState.taskState, ...parsed.taskState },
      repertoire: Array.isArray(parsed.repertoire) ? parsed.repertoire : [],
      logs: Array.isArray(parsed.logs) ? parsed.logs : [],
      sources: { ...defaultState.sources, ...parsed.sources },
      clips: Array.isArray(parsed.clips) ? parsed.clips : []
    };
  } catch {
    return structuredClone(defaultState);
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
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
  elements.youtubeInput.value = state.sources.youtube;
  elements.instagramInput.value = state.sources.instagram;
  elements.scanScope.value = state.sources.scanScope;
  elements.scanCadence.value = state.sources.scanCadence;
  elements.youtubeState.textContent = state.sources.youtube ? "Source set / auth pending" : "Unset";
  elements.instagramState.textContent = state.sources.instagram ? "Source set / auth pending" : "Unset";
}

function renderClipDimensionOptions() {
  elements.clipDimension.innerHTML = skillDimensions.map((dimension) => (
    `<option value="${dimension.id}">${escapeHtml(dimension.label)}</option>`
  )).join("");
}

function renderClips() {
  if (!state.clips.length) {
    elements.clipList.innerHTML = '<p class="empty">No reviewed sections.</p>';
    return;
  }

  elements.clipList.innerHTML = state.clips.map((entry) => {
    const dimension = skillDimensions.find((item) => item.id === entry.dimension);
    const label = dimension ? dimension.label : entry.dimension;
    return `
      <article class="entry-row">
        <div>
          <span class="entry-meta">${escapeHtml(label)} / ${escapeHtml(entry.judgment)} / ${escapeHtml(entry.timecode || "no timecode")}</span>
          <p class="entry-title">${escapeHtml(entry.note || entry.url)}</p>
          <a class="entry-link" href="${escapeHtml(entry.url)}">${escapeHtml(entry.url)}</a>
        </div>
        <button type="button" class="entry-delete" data-delete-clip="${entry.id}" aria-label="Remove reviewed section">X</button>
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
  const entries = state.clips.filter((entry) => entry.dimension === id);
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
  const reviewedVideos = new Set(state.clips.map((entry) => entry.url)).size;
  elements.mediaReviewState.textContent = `${reviewedVideos} videos reviewed`;

  const needs = skillDimensions
    .map((dimension) => ({ ...dimension, counts: clipCountsForDimension(dimension.id) }))
    .filter((dimension) => {
      const status = dimensionStatus(dimension.counts);
      return status === "Needs work" || status === "Regression";
    });

  if (!state.clips.length) {
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
  const reviewedVideos = new Set(state.clips.map((entry) => entry.url)).size;
  const percent = Math.round((complete / tasks.length) * 100);

  elements.completeCount.textContent = complete;
  elements.activeCount.textContent = active;
  elements.pieceCount.textContent = state.repertoire.length;
  elements.minuteCount.textContent = minutes;
  elements.reviewedCount.textContent = reviewedVideos;
  elements.sectionCount.textContent = state.clips.length;
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

elements.sourceForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.sources = {
    youtube: elements.youtubeInput.value.trim(),
    instagram: elements.instagramInput.value.trim(),
    scanScope: elements.scanScope.value,
    scanCadence: elements.scanCadence.value
  };
  saveState();
  render();
});

elements.clipForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const url = elements.clipUrl.value.trim();
  if (!url) return;
  state.clips.unshift({
    id: crypto.randomUUID(),
    url,
    timecode: elements.clipTimecode.value.trim(),
    dimension: elements.clipDimension.value,
    judgment: elements.clipJudgment.value,
    note: elements.clipNote.value.trim()
  });
  elements.clipUrl.value = "";
  elements.clipTimecode.value = "";
  elements.clipJudgment.value = "Unjudged";
  elements.clipNote.value = "";
  saveState();
  render();
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

renderClipDimensionOptions();
render();
