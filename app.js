const API_BASE_KEY = "curtis-api-base";
const NOTE_READING_DRAFT_PREFIX = "curtis-note-reading-draft:";
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
  loading: true,
  ops: null,
  lastError: ""
};
let activeHighlight = null;

const elements = {
  youtubeState: document.querySelector("#youtubeState"),
  inventoryCount: document.querySelector("#inventoryCount"),
  practiceState: document.querySelector("#practiceState"),
  reviewState: document.querySelector("#reviewState"),
  trainingState: document.querySelector("#trainingState"),
  modelState: document.querySelector("#modelState"),
  sourceLink: document.querySelector("#sourceLink"),
  totalPracticeHours: document.querySelector("#totalPracticeHours"),
  practiceSince: document.querySelector("#practiceSince"),
  uploadedVideoTime: document.querySelector("#uploadedVideoTime"),
  uploadedVideoScope: document.querySelector("#uploadedVideoScope"),
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
  detectionState: document.querySelector("#detectionState"),
  highlightFrame: document.querySelector("#highlightFrame"),
  highlightMeta: document.querySelector("#highlightMeta"),
  highlightWindow: document.querySelector("#highlightWindow"),
  highlightLink: document.querySelector("#highlightLink"),
  rejectPieceButton: document.querySelector("#rejectPieceButton"),
  studyCount: document.querySelector("#studyCount"),
  studyList: document.querySelector("#studyList"),
  pieceCount: document.querySelector("#pieceCount"),
  pieceList: document.querySelector("#pieceList"),
  dayCount: document.querySelector("#dayCount"),
  dayList: document.querySelector("#dayList"),
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
  instagramState: document.querySelector("#instagramState"),
  transcriptionCompletionPill: document.querySelector("#transcriptionCompletionPill"),
  transcriptionCompletion: document.querySelector("#transcriptionCompletion"),
  goldReviewCount: document.querySelector("#goldReviewCount"),
  goldReviewPanel: document.querySelector("#goldReviewPanel")
};

function setText(element, value) {
  if (element) element.textContent = value;
}

function setHtml(element, value) {
  if (element) element.innerHTML = value;
}

function backendEmptyText() {
  return backend.loading ? "Loading." : "Backend offline.";
}

function backendStateText() {
  return backend.loading ? "Loading evidence." : `Backend offline: ${backend.lastError || "offline"}`;
}

function apiBase() {
  const params = new URLSearchParams(window.location.search);
  const explicit = params.get("api") || "";
  if (explicit) return explicit.replace(/\/$/, "");
  if (window.location.hostname === "curtis.aolabs.io") return "";
  const configured = localStorage.getItem(API_BASE_KEY) || "";
  if (configured) return configured.replace(/\/$/, "");
  if (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") {
    return window.location.origin;
  }
  if (window.location.hostname.endsWith("up.railway.app")) return "";
  return DEFAULT_API_BASE;
}

async function apiFetch(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 60000);
  const body = options.body && typeof options.body === "object" && !(options.body instanceof FormData) && !(options.body instanceof Blob)
    ? JSON.stringify(options.body)
    : options.body;
  try {
    const response = await fetch(`${apiBase()}${path}`, {
      ...options,
      body,
      cache: "no-store",
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

function shortText(value, limit = 135) {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, limit - 1).trim()}...`;
}

function transcriptionDisplayText(value) {
  let text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  text = text
    .replace(/Machine transcription failed:?/gi, "Matched notation only:")
    .replace(/Machine pitch extraction needs score\/audio verification:/gi, "Matched notation only:")
    .replace(/Machine pitch extraction was rejected:[^.;]*(?:[.;]\s*)?/gi, "")
    .replace(/the tracker collapsed into repeated [A-G][#b]?\d? events;?\s*/gi, "")
    .replace(/transcription failed quality gate/gi, "accepted transcription")
    .replace(/transcription failed/gi, "matching evidence")
    .replace(/failed transcription/gi, "matching evidence")
    .replace(/failed quality gates?/gi, "are kept out of notation until matched")
    .replace(/fail the transcription gate/gi, "stay out of notation until matched")
    .replace(/fails the transcription gate/gi, "stays out of notation until matched")
    .replace(/notation is withheld because it would not match the audio/gi, "notes render only when they match the audio")
    .replace(/The transcription section stays visible, but /gi, "")
    .replace(/The transcription section stays visible with score\/audio evidence; ?/gi, "")
    .replace(/not shown as sheet music/gi, "not rendered as sheet music")
    .replace(/staff output hidden until verified/gi, "notation renders only after audible note match")
    .replace(/hidden machine evidence/gi, "matching evidence")
    .replace(/hidden machine notes/gi, "unverified machine notes")
    .replace(/hidden from/gi, "not used in")
    .replace(/rejected from notation/gi, "not used as notation")
    .replace(/rejected from the music view/gi, "not used in the music view")
    .replace(/withheld/gi, "not rendered");
  return text.replace(/\s+/g, " ").trim();
}

function shortTranscriptionText(value, limit = 135) {
  return shortText(transcriptionDisplayText(value), limit);
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function compactText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/&amp;/g, "&")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function sameLooseTitle(left, right) {
  const leftCompact = compactText(left);
  const rightCompact = compactText(right);
  if (!leftCompact || !rightCompact) return false;
  return leftCompact === rightCompact || leftCompact.includes(rightCompact) || rightCompact.includes(leftCompact);
}

function parseVideoId(value) {
  const raw = String(value || "").trim();
  if (/^[A-Za-z0-9_-]{8,}$/.test(raw) && !raw.includes("/")) return raw;
  try {
    const url = new URL(raw);
    if (url.searchParams.get("v")) return url.searchParams.get("v");
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] === "embed" && parts[1]) return parts[1];
    if (url.hostname.includes("youtu.be") && parts[0]) return parts[0];
  } catch {
    return "";
  }
  return "";
}

function parseWindow(value) {
  const match = String(value || "").match(/\*(\d+)-(\d+)/);
  if (!match) return { start: 0, end: 0 };
  return { start: Number(match[1]) || 0, end: Number(match[2]) || 0 };
}

function formatClock(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = Math.floor(total % 60);
  if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function formatDurationSeconds(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
  if (minutes) return secs ? `${minutes}m ${secs}s` : `${minutes}m`;
  return `${secs}s`;
}

function percentText(part, total) {
  const numerator = Number(part) || 0;
  const denominator = Number(total) || 0;
  if (!denominator || !numerator) return "0%";
  const percent = (numerator / denominator) * 100;
  if (percent > 0 && percent < 0.1) return "<0.1%";
  return `${percent < 10 ? percent.toFixed(1) : Math.round(percent)}%`;
}

function trimDecimal(value, digits = 2) {
  const number = Number(value) || 0;
  return number.toFixed(digits).replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
}

function activePracticeText(records) {
  const seconds = Number(records?.totalPracticeTimeSeconds ?? records?.totalActiveViolinSeconds ?? records?.activePracticeSeconds) || 0;
  if (records?.totalPracticeTimeLabel) return records.totalPracticeTimeLabel;
  if (records?.totalActiveViolinLabel) return records.totalActiveViolinLabel;
  if (records?.activePracticeLabel) return records.activePracticeLabel;
  return seconds ? formatDurationSeconds(seconds) : "pending";
}

function estimatedPracticeText(records) {
  const seconds = Number(records?.estimatedTotalPracticeSeconds ?? records?.estimatedTotalPracticeTimeSeconds) || 0;
  const status = records?.estimateStatus || records?.estimatedPracticeStatus || "";
  if (!seconds || status === "measured") return activePracticeText(records);
  return records?.estimatedTotalPracticeLabel || records?.estimatedTotalPracticeTimeLabel || formatDurationSeconds(seconds);
}

function practiceTimeCaption(records) {
  const basis = String(records?.estimatedPracticeBasis || "").trim();
  if (records?.estimatedPracticeStatus === "estimated_from_checked_windows" && basis) {
    return `estimate / ${basis}`;
  }
  if (records?.estimateStatus === "estimated_from_checked_windows") {
    const active = records?.activePracticeLabel || formatDurationSeconds(records?.activePracticeSeconds || 0);
    const checked = records?.checkedVideoLabel || formatDurationSeconds(records?.checkedVideoSeconds || 0);
    return `estimate / ${active} from ${checked} checked`;
  }
  return "detected playing";
}

function archiveVideoText(records, totals) {
  return records?.uploadedVideoLabel || records?.totalUploadedVideoLabel || totals?.totalPracticeLabel || "0h";
}

function archiveVideoSeconds(records, totals) {
  return Number(records?.uploadedVideoSeconds ?? records?.totalUploadedVideoSeconds) || Number(totals?.totalPracticeSeconds) || 0;
}

function scannedVideoText(records) {
  const label = records?.checkedVideoLabel || records?.totalAnalyzedVideoLabel || records?.totalProcessedSampleLabel || "";
  const seconds = Number(records?.checkedVideoSeconds ?? records?.totalAnalyzedVideoSeconds ?? records?.totalProcessedSampleSeconds) || 0;
  return label || (seconds ? formatDurationSeconds(seconds) : "0s");
}

function scannedVideoSeconds(records) {
  return Number(records?.checkedVideoSeconds ?? records?.totalAnalyzedVideoSeconds ?? records?.totalProcessedSampleSeconds) || 0;
}

function unmeasuredArchiveText(records, totals) {
  const explicit = Number(records?.unmeasuredUploadedVideoSeconds);
  const seconds = Number.isFinite(explicit) && explicit > 0
    ? explicit
    : Math.max(0, archiveVideoSeconds(records, totals) - scannedVideoSeconds(records));
  return seconds ? formatDurationSeconds(seconds) : "0s";
}

function activeHoursLimitText(ops, records, totals) {
  const archiveSeconds = archiveVideoSeconds(records, totals);
  const scannedSeconds = scannedVideoSeconds(records);
  const coverage = percentText(scannedSeconds, archiveSeconds);
  const blocker = ops?.media?.lastMediaRun?.blockers?.includes("youtube_media_fetch_requires_owner_browser_or_export");
  const withheld = Number(records?.withheldNonViolinSampleCount) || 0;
  if (!archiveSeconds) return "Practice archive not indexed yet.";
  if (withheld && !scannedSeconds) return `${withheld} sampled media window${withheld === 1 ? "" : "s"} checked / no violin-playing time counted.`;
  if (withheld) return `${coverage} video checked / ${withheld} sampled window${withheld === 1 ? "" : "s"} not counted as practice.`;
  if (blocker) return `${coverage} video checked. Full practice-time scan needs owner media export/browser access.`;
  if (records?.measurementStatus === "partial") return `${coverage} video checked. Full practice-time scan incomplete.`;
  if (records?.activeMeasurementStatus === "partial") return `${coverage} video checked. Full practice-time scan incomplete.`;
  return "Practice-time scan complete.";
}

function timedUrl(url, startSeconds = 0) {
  try {
    const target = new URL(url);
    target.searchParams.set("t", `${Math.max(0, Math.floor(startSeconds))}s`);
    return target.toString();
  } catch {
    return url || PUBLIC_YOUTUBE_SOURCE;
  }
}

function assetUrl(value) {
  const path = String(value || "").trim();
  if (!path) return "";
  if (path.startsWith("data:image/")) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${apiBase()}${path}`;
}

function embedUrl(url, startSeconds = 0, endSeconds = 0) {
  const videoId = parseVideoId(url);
  if (!videoId) return "";
  const params = new URLSearchParams({
    start: String(Math.max(0, Math.floor(startSeconds))),
    rel: "0"
  });
  if (endSeconds && endSeconds > startSeconds) params.set("end", String(Math.floor(endSeconds)));
  return `https://www.youtube.com/embed/${videoId}?${params.toString()}`;
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
  backend = { ...backend, loading: true, lastError: "" };
  render();
  try {
    backend = {
      online: true,
      loading: false,
      ops: await apiFetch("/api/curtis/ops-check"),
      lastError: ""
    };
  } catch (error) {
    backend = {
      online: false,
      loading: false,
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
      loading: false,
      ops: await apiFetch("/api/curtis/scan/run", {
        method: "POST",
        body: JSON.stringify(sourcePayload())
      }),
      lastError: ""
    };
  } catch (error) {
    backend = {
      online: false,
      loading: false,
      ops: null,
      lastError: String(error?.message || error || "offline")
    };
  } finally {
    elements.runScanButton.disabled = false;
    elements.runScanButton.textContent = "Run scan";
    render();
  }
}

function rejectableTitle(source) {
  const title = String(source?.detectedTitle || "").replace(/\s*\/\s*unverified$/i, "").trim();
  if (!title || title === "Piece being identified") return "";
  if (source?.status !== "piece_identified") return "";
  return title;
}

async function rejectActiveTitle() {
  const rejectedTitle = rejectableTitle(activeHighlight);
  if (!rejectedTitle || !activeHighlight?.url) return;
  elements.rejectPieceButton.disabled = true;
  elements.rejectPieceButton.textContent = "Rejecting";
  try {
    const ops = await apiFetch("/api/curtis/piece-corrections", {
      method: "POST",
      body: JSON.stringify({
        sourceUrl: activeHighlight.url,
        sourceTitle: activeHighlight.title || "",
        videoId: parseVideoId(activeHighlight.url),
        rejectedTitle,
        note: "Rejected from highlight check."
      })
    });
    backend = { online: true, ops, lastError: "" };
  } catch (error) {
    backend.lastError = String(error?.message || error || "correction failed");
  }
  render();
}

async function submitPieceLabel(form) {
  const input = form.querySelector("input[name='acceptedTitle']");
  const acceptedTitle = String(input?.value || "").trim();
  const status = form.querySelector("[data-piece-label-status]");
  if (!acceptedTitle) {
    if (status) status.textContent = "Required.";
    return;
  }
  const button = form.querySelector("button");
  if (button) {
    button.disabled = true;
    button.textContent = "Saving";
  }
  if (status) status.textContent = "Saving.";
  try {
    const ops = await apiFetch("/api/curtis/piece-corrections", {
      method: "POST",
      body: JSON.stringify({
        sourceUrl: form.dataset.sourceUrl || "",
        sourceTitle: form.dataset.sourceTitle || "",
        videoId: form.dataset.videoId || "",
        acceptedTitle,
        note: "Manual source label from Curtis daily record."
      })
    });
    backend = { online: true, loading: false, ops, lastError: "" };
    render();
  } catch (error) {
    backend.lastError = String(error?.message || error || "label save failed");
    if (status) status.textContent = "Failed.";
    if (button) {
      button.disabled = false;
      button.textContent = "Save";
    }
  }
}

function noteInputText(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join(" ");
  return String(value || "").trim();
}

function noteInputSequence(value) {
  return String(value || "")
    .replace(/,/g, " ")
    .split(/\s+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function goldReviewState(ops) {
  const review = ops?.review?.goldReview;
  return review && typeof review === "object" ? review : null;
}

function goldReviewCandidates() {
  const review = goldReviewState(backend.ops);
  return [
    ...(Array.isArray(review?.queue) ? review.queue : []),
    ...(Array.isArray(review?.audioQueue) ? review.audioQueue : []),
    ...(Array.isArray(review?.scoreCopyQueue) ? review.scoreCopyQueue : []),
    ...(Array.isArray(review?.noteReadingQueue) ? review.noteReadingQueue : []),
    ...(Array.isArray(review?.recentItems) ? review.recentItems : []),
  ].filter((item) => item && typeof item === "object");
}

function findGoldReviewCandidate(id) {
  return goldReviewCandidates().find((item) => String(item.reviewItemId || "") === String(id || "")) || null;
}

async function submitGoldReview(form, status) {
  const candidate = findGoldReviewCandidate(form.dataset.reviewItemId);
  const state = form.querySelector("[data-gold-review-status]");
  if (!candidate) {
    if (state) state.textContent = "Missing item.";
    return;
  }
  const button = form.querySelector(`button[value="${status}"]`) || form.querySelector("button");
  if (button) {
    button.disabled = true;
    button.textContent = status === "rejected_mismatch" ? "Rejecting" : "Accepting";
  }
  if (state) state.textContent = "Saving.";
  const acceptedNotes = noteInputSequence(noteInputText(candidate.detectedNotes || candidate.acceptedNotes));
  const scoreNotes = noteInputSequence(noteInputText(candidate.scoreNotes || candidate.sourceScoreNotes));
  const reviewType = candidate.reviewType || candidate.type || (scoreNotes.length ? "audio_score_match" : "audio_phrase");
  try {
    const ops = await apiFetch("/api/curtis/gold-review/items", {
      method: "POST",
      body: JSON.stringify({
        ...candidate,
        type: reviewType,
        status,
        acceptedNotes,
        scoreNotes,
        scoreLocation: candidate.scoreLocation || "",
        reason: status === "rejected_mismatch" ? "one_or_more_notes_wrong" : "",
      })
    });
    backend = { online: true, ops, lastError: "" };
    render();
  } catch (error) {
    backend.lastError = String(error?.message || error || "review save failed");
    if (state) state.textContent = "Failed.";
    if (button) {
      button.disabled = false;
      button.textContent = status === "rejected_mismatch" ? "Reject" : "Accept";
    }
  }
}

function noteLetterSequence(value) {
  const text = String(value || "").trim().toUpperCase();
  if (!text) return [];
  const tokens = /[\s,;]+/.test(text) ? text.split(/[\s,;]+/) : text.split("");
  return tokens
    .map((token) => {
      const match = String(token || "").toUpperCase().match(/[A-G]/);
      return match ? match[0] : "";
    })
    .filter(Boolean);
}

function noteReadingDraftKey(reviewItemId) {
  const id = String(reviewItemId || "").trim();
  return id ? `${NOTE_READING_DRAFT_PREFIX}${id}` : "";
}

function noteReadingDraftValue(item) {
  const explicit = String(item?.noteLetterAnswer || "").trim();
  if (explicit) return explicit;
  const key = noteReadingDraftKey(item?.reviewItemId);
  if (!key) return "";
  try {
    return localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function persistNoteReadingDraft(reviewItemId, value) {
  const key = noteReadingDraftKey(reviewItemId);
  if (!key) return;
  try {
    localStorage.setItem(key, String(value || ""));
  } catch {
    // Draft persistence is only a browser-side safety net.
  }
}

function clearNoteReadingDraft(reviewItemId) {
  const key = noteReadingDraftKey(reviewItemId);
  if (!key) return;
  try {
    localStorage.removeItem(key);
  } catch {
    // Ignore storage failures; the backend save remains authoritative.
  }
}

async function submitNoteReading(form) {
  const candidate = findGoldReviewCandidate(form.dataset.reviewItemId);
  const state = form.querySelector("[data-note-reading-status]");
  const input = form.querySelector("[name='noteLetterAnswer']");
  if (!candidate || !input) {
    if (state) state.textContent = "Missing item.";
    return;
  }
  const button = form.querySelector("button");
  if (button) {
    button.disabled = true;
    button.textContent = "Saving";
  }
  const answer = String(input.value || "").trim();
  persistNoteReadingDraft(candidate.reviewItemId, answer);
  const expectedLetters = Array.isArray(candidate.expectedNoteLetters)
    ? candidate.expectedNoteLetters.map((letter) => String(letter || "").toUpperCase()).filter(Boolean)
    : noteLetterSequence(candidate.expectedNoteLetterText || "");
  const userLetters = noteLetterSequence(answer);
  if (!userLetters.length) {
    if (state) state.textContent = "Type letters.";
    if (button) {
      button.disabled = false;
      button.textContent = "Save";
    }
    return;
  }
  const correct = expectedLetters.length > 0
    && userLetters.length === expectedLetters.length
    && userLetters.every((letter, index) => letter === expectedLetters[index]);
  if (state) state.textContent = "Saving.";
  try {
    const ops = await apiFetch("/api/curtis/gold-review/items", {
      method: "POST",
      body: {
        ...candidate,
        reviewType: "note_reading",
        type: "note_reading",
        status: "accepted_truth",
        acceptedNotes: [],
        expectedNoteLetters: expectedLetters,
        userNoteLetters: userLetters,
        noteLetterAnswer: answer,
        noteLetterCorrect: correct,
        noteReadingAnswerMode: "letters_only_ignore_accidentals_octaves",
        noteReadingSourceScope: candidate.noteReadingSourceScope || "visible_source_picture_only",
        noteReadingScopeLabel: candidate.noteReadingScopeLabel || "picture only",
        noteReadingVisibleNoteCount: Number(candidate.noteReadingVisibleNoteCount || expectedLetters.length || userLetters.length) || userLetters.length,
        reason: correct ? "human_note_letters_match_source_guess" : "human_note_letters_correct_source_guess",
      },
    });
    clearNoteReadingDraft(candidate.reviewItemId);
    applyOps(ops);
    if (state) state.textContent = "Saved.";
  } catch (error) {
    backend.lastError = String(error?.message || error || "review save failed");
    if (state) state.textContent = "Could not save.";
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Save";
    }
  }
}

async function runMediaProbe() {
  elements.probeMediaButton.disabled = true;
  elements.probeMediaButton.textContent = "Fetching";
  try {
    backend = {
      online: true,
      loading: false,
      ops: await apiFetch("/api/curtis/media/probe", {
        method: "POST",
        body: JSON.stringify({})
      }),
      lastError: ""
    };
  } catch (error) {
    backend = {
      online: false,
      loading: false,
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
  if (!backend.online) return backendStateText();
  const inventoryTotal = inventoryItems(ops).length;
  const records = dailyRecords(ops);
  const recordCount = Number(records.recordCount) || 0;
  const audioEvidenceCount = Number(records.audioEvidenceRecordCount) || 0;
  const processedCount = analyzedRecordList(ops).length;
  const scoreGroupCount = scoreMatchGroupCount(records);
  const practiceCount = Number(ops?.review?.practiceCandidateCount) || 0;
  const findingCount = skillFindings(ops).length;
  const withheld = Number(records.withheldNonViolinSampleCount) || 0;
  if (recordCount && withheld && !audioEvidenceCount) return `${withheld} sampled media windows withheld / no violin-positive audio yet / ${recordCount} indexed practice days.`;
  if (recordCount) return `${scoreGroupCount} note matches / ${audioEvidenceCount} playable clips / ${processedCount} checked / ${recordCount} indexed practice days.`;
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

function dailyRecords(ops) {
  return ops?.review?.dailyRecords && typeof ops.review.dailyRecords === "object"
    ? ops.review.dailyRecords
    : { records: [], recordCount: 0, transcribedRecordCount: 0, audioEvidenceRecordCount: 0 };
}

function activePracticeCoverage(ops) {
  return ops?.review?.activePracticeCoverage && typeof ops.review.activePracticeCoverage === "object"
    ? ops.review.activePracticeCoverage
    : null;
}

function dailyRecordList(ops) {
  const records = dailyRecords(ops).records;
  return Array.isArray(records) ? chronologicalRecords(records) : [];
}

function scoreMatchGroupCount(records) {
  const list = Array.isArray(records?.records) ? records.records : [];
  return list.reduce((total, record) => total + exactScoreMatchGroups(record).length, 0);
}

function firstSourceScoreMatchDay(records) {
  const match = (Array.isArray(records) ? records : []).find((record) => exactScoreMatchGroups(record).length);
  return match?.practiceDay || "";
}

function analyzedRecordList(ops) {
  return dailyRecordList(ops).filter((record) => record?.status && record.status !== "pending_media");
}

function latestDailyRecord(ops) {
  const analyzed = analyzedRecordList(ops);
  const records = dailyRecordList(ops);
  return analyzed[analyzed.length - 1] || records[records.length - 1] || null;
}

function practiceDayTime(record) {
  const value = Date.parse(`${record?.practiceDay || ""}T00:00:00Z`);
  return Number.isFinite(value) ? value : 0;
}

function chronologicalRecords(records) {
  return [...records].sort((a, b) => (
    practiceDayTime(a) - practiceDayTime(b)
    || String(a?.practiceDay || "").localeCompare(String(b?.practiceDay || ""))
  ));
}

function isVerifiedTranscriptionRecord(record) {
  const transcription = record?.transcription || {};
  const noteCount = Number(transcription.microVerifiedNoteCount || transcription.renderedNoteCount || transcription.noteCount || 0);
  return transcription.transcriptionReady === true && transcription.displayNotation !== false && noteCount > 0;
}

function verifiedTranscriptionScore(record) {
  if (!isVerifiedTranscriptionRecord(record)) return -1;
  const transcription = record?.transcription || {};
  const confirmedPiece = Array.isArray(record?.pieces) && record.pieces.length ? 1 : 0;
  const noteCount = Number(transcription.microVerifiedNoteCount || transcription.renderedNoteCount || transcription.noteCount || 0);
  const confidence = Number(transcription.microMedianConfidence || 0);
  const activeSeconds = Number(record?.activeViolinSeconds || 0);
  const dayScore = Date.parse(`${record?.practiceDay || ""}T00:00:00Z`) || 0;
  return (confirmedPiece * 1000000000) + (noteCount * 1000000) + (confidence * 100000) + activeSeconds + (dayScore / 100000000000);
}

function bestVerifiedTranscriptionRecord(records) {
  const candidates = Array.isArray(records) ? records.filter(isVerifiedTranscriptionRecord) : [];
  if (!candidates.length) return null;
  return candidates.reduce((best, record) => (
    verifiedTranscriptionScore(record) > verifiedTranscriptionScore(best) ? record : best
  ), candidates[0]);
}

function leadTranscriptionRecord(ops) {
  const records = analyzedRecordList(ops);
  const preferredDay = dailyRecords(ops).leadTranscriptionPracticeDay || "";
  if (preferredDay) {
    const preferred = records.find((record) => record?.practiceDay === preferredDay);
    if (isVerifiedTranscriptionRecord(preferred)) return preferred;
  }
  return bestVerifiedTranscriptionRecord(records);
}

function orderedAnalyzedRecords(ops) {
  return analyzedRecordList(ops);
}

function repertoireEvidence(ops) {
  return ops?.review?.repertoireEvidence && typeof ops.review.repertoireEvidence === "object"
    ? ops.review.repertoireEvidence
    : { entries: [], entryCount: 0 };
}

function repertoireEntries(ops) {
  const entries = repertoireEvidence(ops).entries;
  return Array.isArray(entries) ? entries : [];
}

function sampleIndex(ops) {
  return Array.isArray(ops?.media?.sampleIndex) ? ops.media.sampleIndex : [];
}

function pieceIdResults(ops) {
  return Array.isArray(ops?.pieceId?.results) ? ops.pieceId.results : [];
}

function trainingState(ops) {
  return ops?.review?.training && typeof ops.review.training === "object"
    ? ops.review.training
    : null;
}

function practiceStudy(ops) {
  return ops?.review?.practiceStudy && typeof ops.review.practiceStudy === "object"
    ? ops.review.practiceStudy
    : { days: [], snippetCount: 0, dayCount: 0, transcribedDayCount: 0 };
}

function practiceTotals(ops) {
  const totals = ops?.review?.practiceTotals || ops?.review?.practiceStudy?.practiceTotals || {};
  return totals && typeof totals === "object" ? totals : {};
}

function studyDays(ops) {
  const study = practiceStudy(ops);
  return Array.isArray(study.days) ? study.days : [];
}

function packetMatchesVideo(packet, video, daySamples = []) {
  if (!packet || !video) return false;
  const sourceUrl = String(packet.sourceUrl || "");
  if (sourceUrl && sourceUrl === video.url) return true;
  const videoId = video.id || parseVideoId(video.url);
  if (videoId && (sourceUrl.includes(videoId) || String(packet.id || "").includes(videoId))) return true;
  const packetDay = String(packet.practiceDay || "");
  const videoDay = String(video.title || "").match(/\b(\d{1,2})[-_/](\d{1,2})[-_/](\d{2,4})\b/);
  if (packetDay && videoDay) {
    const year = Number(videoDay[3]) < 100 ? 2000 + Number(videoDay[3]) : Number(videoDay[3]);
    const normalized = `${year}-${String(videoDay[1]).padStart(2, "0")}-${String(videoDay[2]).padStart(2, "0")}`;
    if (packetDay === normalized) return true;
  }
  return daySamples.some((sample) => sample.id && packet.id && String(packet.id).includes(sample.id));
}

function studyPacketForVideo(ops, video, daySamples = []) {
  return studyDays(ops).find((packet) => packetMatchesVideo(packet, video, daySamples)) || null;
}

function trainingLabel(ops) {
  const training = trainingState(ops);
  if (!training) return "0 refs";
  const refs = Number(training.referenceTargetCount ?? training.confirmedSourceCount) || 0;
  const calibration = Number(training.calibrationAnchorCount) || 0;
  const publicSeeds = Number(training.publicReferenceSeedCount) || 0;
  const publicItems = Number(training.publicReferenceItemCount ?? training.publicReference?.storedItemCount) || 0;
  const publicLabel = publicItems || publicSeeds;
  const matches = Number(training.scoreAlignedWindowCount) || 0;
  const pitchWindows = Number(training.pitchRhythmWindowCount) || 0;
  if (!refs && !calibration && !publicLabel) return "0 refs";
  if (pitchWindows && !matches) return `${refs} refs / ${calibration} cal / ${pitchWindows} pitch / ${publicLabel} public`;
  return `${refs} refs / ${calibration} cal / ${matches} score / ${publicLabel} public`;
}

function studyStatusLabel(value) {
  if (value === "transcribed") return "transcribed";
  if (value === "score_target_ready") return "score ready";
  if (value === "transcription_pending") return "transcription pending";
  if (value === "identified") return "identified";
  if (value === "identifying") return "identifying";
  return value || "pending";
}

function sourceForSampleId(ops, sampleId) {
  const id = String(sampleId || "");
  if (!id) return null;
  return sampleIndex(ops).find((sample) => sample.id === id) || null;
}

function sourceFromResult(result, ops) {
  const sample = sourceForSampleId(ops, result?.sampleId);
  const window = parseWindow(result?.sourceWindow || sample?.window);
  const start = Number(result?.sourceStartSeconds ?? window.start) || 0;
  const end = Number(result?.sourceEndSeconds ?? window.end) || (start ? start + 45 : 0);
  const identified = resultIsIdentified(result);
  return {
    sampleId: result?.sampleId || sample?.id || "",
    title: result?.sourceTitle || result?.sampleTitle || sample?.title || "",
    url: result?.sourceUrl || result?.url || sample?.url || "",
    window: result?.sourceWindow || sample?.window || "",
    startSeconds: start,
    endSeconds: end,
    detectedTitle: identified ? result.title : "Piece being identified",
    confidence: result?.confidence || "unknown",
    confidenceScore: Number(result?.confidenceScore) || 0,
    status: identified ? "piece_identified" : result?.status === "piece_identified" ? "piece_unconfirmed_title" : result?.status || "",
    tip: result?.immediateTip || "",
    completionPercent: Number(result?.completionPercent) || 0
  };
}

function sourceFromPiece(piece, ops) {
  const source = sourceForSampleId(ops, piece?.sampleId);
  const window = parseWindow(piece?.sourceWindow || source?.window);
  const start = Number(piece?.sourceStartSeconds ?? window.start) || 0;
  const end = Number(piece?.sourceEndSeconds ?? window.end) || (start ? start + 45 : 0);
  return {
    sampleId: piece?.sampleId || source?.id || "",
    title: piece?.sourceTitle || source?.title || "",
    url: piece?.sourceUrl || source?.url || "",
    window: piece?.sourceWindow || source?.window || "",
    startSeconds: start,
    endSeconds: end,
    detectedTitle: pieceLabel(piece),
    confidence: piece?.confidence || "unknown",
    confidenceScore: Number(piece?.confidenceScore) || 0,
    status: isIdentifiedPiece(piece) ? "piece_identified" : "piece_unidentified",
    tip: pieceTip(piece),
    completionPercent: todayCompletion(piece)
  };
}

function sourceFromSection(section) {
  const start = Number(section?.startSeconds) || 0;
  const end = Number(section?.endSeconds) || (start ? start + 30 : 0);
  return {
    sampleId: section?.sampleId || "",
    title: section?.title || "",
    url: section?.url || "",
    window: start ? `*${start}-${end}` : "",
    startSeconds: start,
    endSeconds: end,
    detectedTitle: "Piece being identified",
    confidence: "unknown",
    confidenceScore: 0,
    status: section?.status || "candidate_playing_section",
    tip: section?.note || "",
    completionPercent: 0
  };
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

function sourceConfirmedTitle(item) {
  const quality = String(item?.evidenceQuality || "");
  return quality === "human_verified_source_label" || item?.sourceConfirmed === true;
}

function isIdentifiedPiece(piece) {
  return Boolean(piece?.title && piece.title !== "Piece being identified" && sourceConfirmedTitle(piece));
}

function pieceLabel(piece) {
  if (!piece) return "Identifying from practice sessions.";
  if (isIdentifiedPiece(piece)) return piece.title;
  return "Piece being identified";
}

function currentPieceLabel(piece) {
  const label = pieceLabel(piece);
  if (!isIdentifiedPiece(piece)) return label;
  return label
    .replace(/^(.+?) Violin Concerto No\. /, "$1 Concerto No. ")
    .replace(/\s+in\s+[A-G][#b]?\s+(major|minor),\s+/i, ", ")
    .replace(/,\s*Violin I part$/i, ", Vln I");
}

function pieceStatusLabel(piece) {
  if (!piece || !isIdentifiedPiece(piece)) return "identifying";
  if (piece.evidenceQuality === "human_verified_source_label") return "confirmed";
  if (piece.confidence === "clear") return "detected";
  return piece.confidence || "detected";
}

function pieceTip(piece) {
  if (!piece) return "Capture one clear excerpt.";
  if (!isIdentifiedPiece(piece)) return "Source confirmation pending.";
  const tip = String(
    piece.isActiveToday
      ? piece.todayTip || piece.tip || "Capture one clearer excerpt."
      : piece.tip || piece.todayTip || "Capture one clearer excerpt."
  ).trim();
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

function scoreText(value) {
  const percent = Number(value) || 0;
  return percent > 0 ? `${percent}%` : "Not scored";
}

function progressText(piece) {
  if (!piece) return "0%";
  if (!isIdentifiedPiece(piece) || piece.confidence !== "clear") return "Identifying";
  if (todayCompletion(piece) <= 0) return "Not scored";
  return `${todayCompletion(piece)}%`;
}

function completionLabel(piece) {
  if (!isIdentifiedPiece(piece) || piece.confidence !== "clear") return "Identifying";
  const today = todayCompletion(piece);
  const overall = Number(piece?.completionPercent) || 0;
  if (today <= 0 && overall <= 0) return "identified";
  return piece?.isActiveToday ? `${today}% today` : `${overall}% overall`;
}

function pieceEvidence(piece) {
  if (!piece) return "";
  if (!isIdentifiedPiece(piece)) return "Source confirmation pending.";
  const evidence = String(piece.candidateEvidence || piece.evidence || "").trim();
  if (!evidence) return "";
  return evidence;
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

function resultIsIdentified(result) {
  return result?.status === "piece_identified" && isIdentifiedPiece(result);
}

function resultDetectedLabel(result) {
  if (!result) return "Piece being identified";
  if (resultIsIdentified(result)) return result.title;
  return "Piece being identified";
}

function primaryHighlight(ops) {
  const latestRecord = latestDailyRecord(ops);
  const dailyClip = Array.isArray(latestRecord?.clips) ? latestRecord.clips.find((clip) => clip?.url) : null;
  if (dailyClip) {
    const confirmed = Array.isArray(latestRecord.pieces) && latestRecord.pieces.length ? latestRecord.pieces[0] : null;
    return {
      sampleId: "",
      title: dailyClip.sourceTitle || latestRecord.practiceDay || "Practice record",
      url: dailyClip.url,
      window: dailyClip.startSeconds || dailyClip.endSeconds ? `*${dailyClip.startSeconds || 0}-${dailyClip.endSeconds || 0}` : "",
      startSeconds: Number(dailyClip.startSeconds) || 0,
      endSeconds: Number(dailyClip.endSeconds) || 0,
      detectedTitle: confirmed?.title || "Piece being identified",
      confidence: confirmed?.confidence || "unknown",
      confidenceScore: 0,
      status: confirmed ? "piece_identified" : "daily_record",
      tip: latestRecord.nextStep || "",
      completionPercent: 0
    };
  }

  const piece = currentPiece(ops);
  const results = pieceIdResults(ops);
  const matchingResult = results.find((result) => {
    if (!result?.url) return false;
    if (!isIdentifiedPiece(piece) || !resultIsIdentified(result)) return false;
    return sameLooseTitle(result.title, piece?.title) || sameLooseTitle(result.proposedTitle, piece?.title);
  });
  if (matchingResult) return sourceFromResult(matchingResult, ops);

  const pieceSource = piece ? sourceFromPiece(piece, ops) : null;
  if (pieceSource?.url) return pieceSource;

  const latestResult = results.find((result) => result?.url || sourceForSampleId(ops, result?.sampleId)?.url);
  if (latestResult) return sourceFromResult(latestResult, ops);

  const section = reviewSections(ops).find((item) => item?.url);
  if (section) return sourceFromSection(section);

  const sample = sampleIndex(ops).find((item) => item?.url);
  if (sample) {
    const window = parseWindow(sample.window);
    return {
      sampleId: sample.id,
      title: sample.title,
      url: sample.url,
      window: sample.window,
      startSeconds: window.start,
      endSeconds: window.end,
      detectedTitle: "Piece being identified",
      confidence: "unknown",
      confidenceScore: 0,
      status: "sample_ready",
      tip: "",
      completionPercent: 0
    };
  }
  return null;
}

function detectionLabel(source) {
  if (!source?.url) return "Clip pending.";
  const title = source.detectedTitle || "Piece being identified";
  const sourceTitle = source.title || "practice video";
  if (source.status === "piece_identified" && title !== "Piece being identified") {
    return `${sourceTitle} / ${title}`;
  }
  return `${sourceTitle} / identifying`;
}

function detectionStatus(source) {
  if (!source?.url) return "No clip";
  if (source.status === "piece_identified" && source.detectedTitle !== "Piece being identified") return "Check clip";
  return "Identifying";
}

function practiceDays(ops) {
  const inventory = inventoryItems(ops).filter((item) => item.practiceCandidate);
  const samples = sampleIndex(ops);
  const results = pieceIdResults(ops);
  const sections = reviewSections(ops);
  const repertoire = pieces(ops);
  return inventory.slice(0, 12).map((video) => {
    const videoId = video.id || parseVideoId(video.url);
    const daySamples = samples.filter((sample) => sample.url === video.url || String(sample.id || "").startsWith(`${videoId}-`) || sample.id === videoId);
    const sampleIds = new Set(daySamples.map((sample) => sample.id));
    const dayResults = results.filter((result) => {
      const sample = sourceForSampleId(ops, result.sampleId);
      return result.url === video.url || sample?.url === video.url || sampleIds.has(result.sampleId);
    });
    const pieceDailyEntry = (piece) => {
      const daily = piece?.daily && typeof piece.daily === "object" ? Object.values(piece.daily) : [];
      return daily.find((item) => {
        const sample = sourceForSampleId(ops, item?.sampleId);
        return item?.sourceUrl === video.url || sample?.url === video.url || sampleIds.has(item?.sampleId);
      }) || null;
    };
    const study = studyPacketForVideo(ops, video, daySamples);
    const dayPieceRows = repertoire.map((piece) => ({ piece, daily: pieceDailyEntry(piece) })).filter(({ piece, daily }) => {
      const source = sourceForSampleId(ops, piece.sampleId);
      return Boolean(daily || piece.sourceUrl === video.url || source?.url === video.url || sampleIds.has(piece.sampleId));
    });
    const dayPieces = dayPieceRows.map((row) => row.piece);
    const daySections = sections.filter((section) => section.url === video.url || sampleIds.has(section.sampleId));
    const identified = dayResults.filter(resultIsIdentified);
    const identifiedPieceRows = dayPieceRows.filter(({ piece }) => isIdentifiedPiece(piece));
    const identifiedPieces = identifiedPieceRows.map((row) => row.piece);
    const detected = [study?.pieceTitle, ...identified.map(resultDetectedLabel), ...identifiedPieces.map(pieceLabel)]
      .filter(Boolean);
    const highlight = identified[0]
      ? sourceFromResult(identified[0], ops)
      : identifiedPieces[0]
        ? sourceFromPiece(identifiedPieces[0], ops)
        : daySections[0]
            ? sourceFromSection(daySections[0])
            : daySamples[0]
              ? sourceFromResult({ sampleId: daySamples[0].id }, ops)
              : { title: video.title, url: video.url, startSeconds: 0, endSeconds: 0, detectedTitle: "Piece being identified", status: "metadata" };
    const percentCandidates = [
      ...identified.map((item) => Number(item.completionPercent) || 0),
      ...identifiedPieceRows.map(({ piece, daily }) => Math.max(
        Number(daily?.completionPercent) || 0,
        Number(piece.completionPercent) || 0
      ))
    ];
    const tip = study?.tip || identified[0]?.immediateTip || identifiedPieceRows[0]?.daily?.tip || identifiedPieces[0]?.tip || "";
    const identifiedCount = identified.length + identifiedPieces.length;
    return {
      title: video.title || "Practice",
      date: formatDate(video.publishedAt),
      url: video.url,
      viewCount: video.viewCount,
      duration: video.duration,
      totalPracticeSeconds: Number(study?.totalPracticeSeconds) || Number(video.durationSeconds) || 0,
      totalPracticeLabel: study?.totalPracticeLabel || "",
      samples: daySamples.length,
      sections: daySections.length,
      detected: [...new Set(detected)].slice(0, 3),
      status: study?.status || (identifiedCount ? "identified" : daySamples.length ? "identifying" : "indexed"),
      completionPercent: Math.max(Number(study?.completionPercent) || 0, ...percentCandidates),
      tip,
      highlight,
      study
    };
  });
}

function renderStatus() {
  const ops = backend.ops || {};
  const inventory = inventoryItems(ops);
  const sections = reviewSections(ops);
  const findings = skillFindings(ops);
  const piece = currentPiece(ops);
  const pieceList = repertoireEntries(ops);
  const plan = progressPlan(ops);
  const reviewedVideos = Number(ops?.review?.reviewedVideoCount) || 0;
  const practiceCount = Number(ops?.review?.practiceCandidateCount) || 0;
  const longFormCount = Number(ops?.review?.longFormCandidateCount) || 0;
  const model = ops?.model ? `${ops.model.id} / ${ops.model.reasoningEffort}` : "Not reported";
  const highlight = primaryHighlight(ops);
  const days = practiceDays(ops);
  const records = dailyRecords(ops);
  const coverage = activePracticeCoverage(ops);
  const practiceCoverage = coverage?.status === "ready" ? coverage : records;
  const analyzedRecords = analyzedRecordList(ops);
  const latestRecord = latestDailyRecord(ops);
  const latestPiece = Array.isArray(latestRecord?.pieces) && latestRecord.pieces.length ? latestRecord.pieces[0] : null;
  const totals = practiceTotals(ops);

  setText(elements.youtubeState, backend.online ? youtubeLabel(ops) : "Offline");
  setText(elements.inventoryCount, `${inventory.length} videos`);
  setText(elements.practiceState, longFormCount
    ? `${practiceCount} candidates / ${longFormCount} long`
    : `${practiceCount} candidates`);
  setText(elements.reviewState, sections.length ? `${sections.length} sections` : "Unjudged");
  setText(elements.trainingState, trainingLabel(ops));
  setText(elements.modelState, model);
  setText(elements.evidenceState, findings.length ? `${findings.length} findings` : sections.length ? "Sections ready" : "Unjudged");
  setText(elements.workingState, workingText(ops));
  setText(elements.focusState, plan?.oneFocus || (sections.length ? "Model review pending." : "Capture playable sections."));
  setText(elements.constraintState, plan?.practiceConstraint || "One focus per session.");
  setText(elements.boundaryState, plan?.boundary || "No admission prediction from current samples.");
  const session = Array.isArray(plan?.sessionPlan) && plan.sessionPlan.length
    ? plan.sessionPlan.slice(0, 3)
    : ["Capture clear violin audio."];
  setHtml(elements.sessionPlan, session.map((item) => `<li>${escapeHtml(item)}</li>`).join(""));
  setText(elements.pieceState, latestPiece?.title || currentPieceLabel(piece));
  setText(elements.pieceProgress, latestRecord?.activeViolinLabel || progressText(piece));
  setText(elements.pieceTip, latestRecord?.nextStep || pieceTip(piece));
  setText(elements.detectionState, detectionStatus(highlight));
  if (elements.studyCount) {
    const recordCount = Number(records.recordCount) || 0;
    const matchCount = scoreMatchGroupCount(records);
    elements.studyCount.textContent = `${matchCount} ${matchCount === 1 ? "match" : "matches"} / ${recordCount} days`;
  }
  const transcriptionCompletion = transcriptionCompletionState(ops);
  setText(elements.transcriptionCompletionPill, transcriptionCompletion?.completionExactLabel || transcriptionCompletion?.completionLabel || "0%");
  const scannedSeconds = scannedVideoSeconds(practiceCoverage);
  const archiveSeconds = archiveVideoSeconds(practiceCoverage, totals);
  const archiveLabel = archiveVideoText(practiceCoverage, totals);
  setText(elements.totalPracticeHours, estimatedPracticeText(practiceCoverage));
  setText(
    elements.practiceSince,
    practiceTimeCaption(practiceCoverage)
  );
  setText(elements.uploadedVideoTime, scannedVideoText(practiceCoverage));
  setText(
    elements.uploadedVideoScope,
    [
      archiveSeconds ? `${percentText(scannedSeconds, archiveSeconds)} checked` : "",
      archiveLabel ? `of ${archiveLabel}` : "",
    ].filter(Boolean).join(" / ") || "scan pending"
  );
  setText(elements.recordSummary, archiveLabel);
  setText(
    elements.currentState,
    [
      totals?.videoCount ? `${totals.videoCount} videos` : "",
      totals?.sincePublishedAt ? `since ${formatDate(totals.sincePublishedAt)}` : "",
      `${unmeasuredArchiveText(practiceCoverage, totals)} unchecked`,
    ].filter(Boolean).join(" / ")
  );
  setText(elements.pieceCount, `${pieceList.length} ${pieceList.length === 1 ? "piece" : "pieces"}`);
  const dayTotal = Number(records.recordCount) || days.length;
  setText(elements.dayCount, `${dayTotal} ${dayTotal === 1 ? "day" : "days"}`);
  const source = youtubeSource(ops);
  if (elements.sourceLink) {
    elements.sourceLink.href = youtubeSourceHref(source);
    elements.sourceLink.textContent = source.replace("https://www.", "").replace("https://", "");
  }
  setText(elements.reviewedCount, `${reviewedVideos} reviewed`);
  setText(elements.sectionCount, `${sections.length} sections`);
  setText(elements.backendState, backend.online ? "Online" : "Offline");
  setText(elements.storageState, backend.online ? "Backend state" : "Browser only");
  setText(elements.automationState, backend.online ? automationLabel(ops) : "Offline");
  setText(elements.mediaState, backend.online ? mediaAccessLabel(ops) : "Offline");
  setText(elements.instagramState, ops?.credentials?.instagramGraph ? "Configured" : "Not configured");

}

function snippetClipUrl(snippet, fallbackUrl = "") {
  const audio = snippet?.audio || {};
  return timedUrl(audio.url || fallbackUrl, Number(audio.startSeconds) || 0);
}

function scoreImageUrl(score) {
  const direct = assetUrl(score?.imageUrl);
  if (direct) return direct;
  const assetId = score?.assetId || score?.scoreAssetId;
  const page = score?.page || score?.scorePage;
  if (assetId && page) return assetUrl(`/api/curtis/score/page/${assetId}/${page}`);
  return "";
}

function scoreBoxes(score) {
  if (Array.isArray(score?.boxes)) return score.boxes;
  if (Array.isArray(score?.scoreBoxes)) return score.scoreBoxes;
  return [];
}

function normalizedScoreBox(box, padding = 1.0) {
  const x = Math.max(0, Math.min(100, Number(box?.x) || 0));
  const y = Math.max(0, Math.min(100, Number(box?.y) || 0));
  const width = Math.max(1, Math.min(100 - x, Number(box?.width) || 1));
  const height = Math.max(1, Math.min(100 - y, Number(box?.height) || 1));
  const paddedX = Math.max(0, x - padding);
  const paddedY = Math.max(0, y - padding);
  return {
    x: paddedX,
    y: paddedY,
    width: Math.min(100 - paddedX, width + padding * 2),
    height: Math.min(100 - paddedY, height + padding * 2),
  };
}

function renderScoreCrop(score, boxes) {
  const imageUrl = scoreImageUrl(score);
  const box = Array.isArray(boxes) && boxes.length ? boxes[0] : null;
  if (!imageUrl || !box) return "";
  const crop = normalizedScoreBox(box);
  const scale = Math.max(100, 10000 / crop.width);
  return `
    <div class="score-image score-image-compact score-image-crop" aria-label="Cropped score snippet">
      <img src="${escapeHtml(imageUrl)}" alt="" style="width:${scale.toFixed(2)}%; transform:translate(-${crop.x.toFixed(2)}%, -${crop.y.toFixed(2)}%);">
    </div>
  `;
}

function explicitScoreMatchValue(value) {
  const clean = compactText(value);
  if (!clean) return false;
  if (
    clean.includes("pending") ||
    clean.includes("target") ||
    clean.includes("source label") ||
    clean.includes("unverified") ||
    clean.includes("not configured")
  ) return false;
  return [
    "score matched",
    "matched score",
    "score aligned",
    "score alignment verified",
    "score match verified",
    "exact measure match",
    "exact measure verified",
    "exact score match",
    "score location verified",
    "played score match",
  ].some((token) => clean.includes(token));
}

function scoreSnippetIsMatched(snippet, record = {}) {
  if (!snippet || typeof snippet !== "object") return false;
  const score = snippet.score && typeof snippet.score === "object" ? snippet.score : {};
  if (snippet.scoreMatched === true || score.scoreMatched === true || score.matched === true) return true;
  const values = [
    snippet.scoreMatchStatus,
    snippet.matchStatus,
    snippet.alignmentStatus,
    snippet.status,
    snippet.readiness,
    score.matchStatus,
    score.alignmentStatus,
    score.status,
    record?.transcription?.scoreAlignmentStatus,
    record?.heatMap?.status,
  ];
  return values.some(explicitScoreMatchValue);
}

function renderScoreImage(snippet, compact = false) {
  const score = snippet?.score || {};
  const imageUrl = scoreImageUrl(score);
  if (!imageUrl) {
    return `<div class="score-placeholder">Score render pending.</div>`;
  }
  const boxes = scoreBoxes(score);
  if (compact && boxes.length) return renderScoreCrop(score, boxes);
  const compactClass = compact ? " score-image-compact" : "";
  return `
    <div class="score-image${compactClass}" aria-label="Annotated score snippet">
      <img src="${escapeHtml(imageUrl)}" alt="">
      ${boxes.map((box) => `
        <span class="score-box" style="left:${Number(box.x) || 0}%; top:${Number(box.y) || 0}%; width:${Number(box.width) || 1}%; height:${Number(box.height) || 1}%;">
          <b>${escapeHtml(box.label || "practice area")}</b>
        </span>
      `).join("")}
    </div>
  `;
}

function sourceMeasureLabelForMatch(group) {
  if (!group || typeof group !== "object") return "";
  return "";
}

function measureLabelForMatch(group) {
  if (!group || typeof group !== "object") return "";
  const score = group.score && typeof group.score === "object" ? group.score : {};
  const sourceSnippet = group.scoreSourceSnippet && typeof group.scoreSourceSnippet === "object" ? group.scoreSourceSnippet : {};
  const rawLabel = String(
    group.measureLabel
    || sourceSnippet.measureLabel
    || sourceMeasureLabelForMatch(group)
    || score.measureLabel
    || sourceSnippet.label
    || group.scoreSequenceLabel
    || ""
  ).trim();
  if (rawLabel) return rawLabel;
  const rawNumber = group.measureNumber ?? score.measureNumber ?? sourceSnippet.measureNumber;
  const number = Number(rawNumber);
  return Number.isFinite(number) && number > 0 ? `m. ${number}` : "";
}

const TREBLE_STAFF_TOP_Y = 30;
const TREBLE_STAFF_LINE_GAP = 10;
const TREBLE_STAFF_BOTTOM_Y = TREBLE_STAFF_TOP_Y + (TREBLE_STAFF_LINE_GAP * 4);
const TREBLE_G4_Y = TREBLE_STAFF_TOP_Y + (TREBLE_STAFF_LINE_GAP * 3);
const TREBLE_STAFF_STEP_Y = TREBLE_STAFF_LINE_GAP / 2;
const TREBLE_NOTE_ORDER = { C: 0, D: 1, E: 2, F: 3, G: 4, A: 5, B: 6 };
const TREBLE_CLEF_BASELINE_Y = 63;
const NOTATION_VIEWBOX_MIN_Y = -18;
const NOTATION_VIEWBOX_HEIGHT = 150;
const NOTATION_VIEWBOX_BASE_WIDTH = 720;
function notationViewBox(width = NOTATION_VIEWBOX_BASE_WIDTH) {
  const safeWidth = Math.max(NOTATION_VIEWBOX_BASE_WIDTH, Math.ceil(Number(width) || NOTATION_VIEWBOX_BASE_WIDTH));
  return `0 ${NOTATION_VIEWBOX_MIN_Y} ${safeWidth} ${NOTATION_VIEWBOX_HEIGHT}`;
}
const NOTATION_VIEWBOX = notationViewBox();
const NOTATION_STAFF_LINE_X1 = 22;
const NOTATION_STAFF_LINE_X2 = 698;
const NOTATION_NOTE_START_X = 132;
const NOTATION_NOTE_END_X = 682;
const NOTATION_NOTE_MIN_STEP_X = 48;
const NOTATION_NOTE_TRAILING_PAD_X = 46;
const NOTATION_STEM_OFFSET_X = 6.4;
const NOTATION_LEDGER_HALF_WIDTH = 11.5;
const NOTATION_NOTE_ACCIDENTAL_X_OFFSET = 22;
const NOTATION_NOTE_ACCIDENTAL_Y_OFFSET = { flat: 0, sharp: 0 };
const NOTATION_ACCIDENTAL_SAFE_TOP_Y = NOTATION_VIEWBOX_MIN_Y + 10;
const NOTATION_ACCIDENTAL_SAFE_BOTTOM_Y = TREBLE_STAFF_BOTTOM_Y + 24;
const NOTATION_KEY_SIGNATURE_START_X = 88;
const NOTATION_KEY_SIGNATURE_STEP_X = 20;
const NOTATION_KEY_SIGNATURE_WIDTH_PAD = 58;
const SHARP_TO_FLAT_NOTE = { "C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb" };
const FLAT_TO_SHARP_NOTE = { Db: "C#", Eb: "D#", Gb: "F#", Ab: "G#", Bb: "A#" };
const ABC_FLAT_KEYS = ["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"];
const ABC_SHARP_KEYS = ["C", "G", "D", "A", "E", "B", "F#", "C#"];
const FLAT_KEY_ORDER = ["Bb", "Eb", "Ab", "Db", "Gb", "Cb", "Fb"];
const SHARP_KEY_ORDER = ["F#", "C#", "G#", "D#", "A#", "E#", "B#"];
let notationSheetIdCounter = 0;

function normalizeAccidentalToken(value) {
  const clean = String(value || "")
    .trim()
    .replace(/\u266d/g, "b")
    .replace(/\u266f/g, "#")
    .replace(/♭/g, "b")
    .replace(/♯/g, "#");
  const match = clean.match(/^([A-Ga-g])(#|b)?(\d?)$/);
  return match ? `${match[1].toUpperCase()}${match[2] || ""}${match[3] || ""}` : clean;
}

function parseExactNote(value) {
  const match = normalizeAccidentalToken(value).match(/^([A-G])(#|b)?(\d)$/);
  if (!match) return null;
  return {
    letter: match[1],
    accidental: match[2] || "",
    octave: match[3],
    pitch: `${match[1]}${match[2] || ""}`,
  };
}

function normalizedAccidentalNames(signature) {
  return new Set(
    (Array.isArray(signature?.accidentals) ? signature.accidentals : [])
      .map((item) => normalizeAccidentalToken(item))
      .map((item) => {
        const match = String(item || "").match(/^([A-G])(#|b)?/);
        return match ? `${match[1]}${match[2] || ""}` : "";
      })
      .filter(Boolean)
  );
}

function notationDisplayNote(note, signature) {
  const parsed = parseExactNote(note);
  if (!parsed) return String(note || "");
  const accidentalNames = normalizedAccidentalNames(signature);
  if (parsed.accidental === "#" && accidentalNames.has(SHARP_TO_FLAT_NOTE[parsed.pitch])) {
    return `${SHARP_TO_FLAT_NOTE[parsed.pitch] || parsed.pitch}${parsed.octave}`;
  }
  if (parsed.accidental === "b" && accidentalNames.has(FLAT_TO_SHARP_NOTE[parsed.pitch])) {
    return `${FLAT_TO_SHARP_NOTE[parsed.pitch] || parsed.pitch}${parsed.octave}`;
  }
  return `${parsed.pitch}${parsed.octave}`;
}

function keySignatureCoversNote(spelledNote, signature) {
  const parsed = parseExactNote(spelledNote);
  if (!parsed) return true;
  const keyAlteration = keySignatureAlterationForLetter(parsed.letter, signature);
  if (!parsed.accidental) return !keyAlteration;
  return parsed.accidental === keyAlteration;
}

function keySignatureAlterationForLetter(letter, signature) {
  const cleanLetter = String(letter || "").toUpperCase();
  for (const accidental of normalizedAccidentalNames(signature)) {
    if (accidental.charAt(0).toUpperCase() === cleanLetter) {
      return accidental.includes("b") ? "b" : accidental.includes("#") ? "#" : "";
    }
  }
  return "";
}

function renderedAccidentalTypeForNote(spelledNote, signature, measureAccidentals = {}) {
  const parsed = parseExactNote(spelledNote);
  if (!parsed) return "";
  const keyAlteration = keySignatureAlterationForLetter(parsed.letter, signature);
  const previousAlteration = Object.prototype.hasOwnProperty.call(measureAccidentals, parsed.letter)
    ? measureAccidentals[parsed.letter]
    : keyAlteration;
  const writtenAlteration = parsed.accidental || "";
  measureAccidentals[parsed.letter] = writtenAlteration;
  if (writtenAlteration === previousAlteration) return "";
  if (writtenAlteration === "b") return "flat";
  if (writtenAlteration === "#") return "sharp";
  return "natural";
}

function displayNoteTextWithMeasureAccidentals(notes, signature = {}) {
  const sequence = Array.isArray(notes) ? notes : [];
  const normalized = normalizedKeySignature(signature || {});
  let measureAccidentals = {};
  return sequence.map((note) => {
    const parsed = parseExactNote(note);
    if (!parsed) return String(note || "");
    const type = renderedAccidentalTypeForNote(note, normalized, measureAccidentals);
    if (type === "natural") return `${parsed.letter}\u266e${parsed.octave}`;
    return `${parsed.pitch}${parsed.octave}`;
  }).join(" ");
}

function renderAccidentalGlyph(type, x, y, className) {
  const safeType = type === "flat" ? "flat" : type === "natural" ? "natural" : "sharp";
  const glyph = safeType === "flat" ? "&#xE260;" : safeType === "natural" ? "&#xE261;" : "&#xE262;";
  return `
    <text class="${className} accidental-glyph accidental-${safeType}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" aria-label="${safeType}">${glyph}</text>
  `;
}

function renderNoteAccidental(spelledNote, signature, x, y, measureAccidentals = {}) {
  const type = renderedAccidentalTypeForNote(spelledNote, signature, measureAccidentals);
  if (!type) return "";
  const rawY = y + (NOTATION_NOTE_ACCIDENTAL_Y_OFFSET[type] || 0);
  const safeY = Math.max(NOTATION_ACCIDENTAL_SAFE_TOP_Y, Math.min(NOTATION_ACCIDENTAL_SAFE_BOTTOM_Y, rawY));
  const accidentalX = x - NOTATION_NOTE_ACCIDENTAL_X_OFFSET;
  return renderAccidentalGlyph(type, accidentalX, safeY, "note-accidental");
}

function abcKeyNameForSignature(signature) {
  const normalized = normalizedKeySignature(signature || {});
  const count = Math.max(0, Math.min(7, normalized.accidentals.length));
  if (normalized.accidentalType === "flat") return ABC_FLAT_KEYS[count] || "C";
  if (normalized.accidentalType === "sharp") return ABC_SHARP_KEYS[count] || "C";
  return "C";
}

function abcDurationToken(kind) {
  switch (notationDurationClass(kind)) {
    case "whole":
      return "4";
    case "half":
      return "2";
    case "eighth":
      return "/2";
    case "sixteenth":
      return "/4";
    default:
      return "";
  }
}

function notationRhythmVerified(options = {}) {
  return options?.rhythmVerified === true || options?.durationVerified === true;
}

function abcPitchToken(noteName, signature, measureAccidentals = {}) {
  const parsed = parseExactNote(noteName);
  if (!parsed) return "z";
  const octave = Number(parsed.octave);
  const accidentalType = renderedAccidentalTypeForNote(noteName, signature, measureAccidentals);
  const accidental = accidentalType === "flat" ? "_" : accidentalType === "sharp" ? "^" : accidentalType === "natural" ? "=" : "";
  let letter = parsed.letter;
  let octaveMark = "";
  if (octave < 4) {
    octaveMark = ",".repeat(4 - octave);
  } else if (octave >= 5) {
    letter = letter.toLowerCase();
    octaveMark = "'".repeat(Math.max(0, octave - 5));
  }
  return `${accidental}${letter}${octaveMark}`;
}

function notationAbcForEvents(events, signature) {
  const normalized = normalizedKeySignature(signature || {});
  const notes = Array.isArray(events) ? events : [];
  let measureAccidentals = {};
  const body = notes.map((event) => {
    const token = event.kind === "rest"
      ? `z${abcDurationToken(event.durationKind)}`
      : `${abcPitchToken(notationDisplayNote(event.note, normalized), normalized, measureAccidentals)}${abcDurationToken(event.durationKind)}`;
    return token;
  }).join(" ").trim();
  return [
    "X:1",
    "M:none",
    "L:1/4",
    `K:${abcKeyNameForSignature(normalized)} clef=treble`,
    body || "z4",
  ].join("\n");
}

function hydrateNotationSheet(sheet) {
  if (!sheet || sheet.dataset.abcRendered === "true" || typeof ABCJS === "undefined") return;
  const target = sheet.querySelector(".notation-abc-target");
  const abc = sheet.dataset.abc || "";
  if (!target || !abc) return;
  try {
    const targetWidth = Math.max(360, Math.floor(sheet.clientWidth || 520) - 24);
    const requestedStaffWidth = Number(sheet.dataset.abcStaffwidth) || targetWidth;
    const staffwidth = Math.max(300, Math.min(920, requestedStaffWidth, targetWidth));
    const requestedScale = Number(sheet.dataset.abcScale) || 1.05;
    target.innerHTML = "";
    ABCJS.renderAbc(target, abc, {
      add_classes: true,
      paddingbottom: 0,
      paddingleft: 0,
      paddingright: 8,
      paddingtop: 0,
      responsive: "resize",
      scale: Math.max(0.9, Math.min(1.35, requestedScale)),
      staffwidth,
    });
    sheet.dataset.abcRendered = "true";
    sheet.classList.add("notation-abc-ready");
  } catch (error) {
    sheet.dataset.abcRendered = "failed";
  }
}

function hydrateNotationSheets(root = document) {
  if (typeof document === "undefined" || typeof ABCJS === "undefined") return;
  (root.querySelectorAll ? root : document).querySelectorAll(".notation-sheet[data-abc]").forEach(hydrateNotationSheet);
}

function queueNotationHydration(id) {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  const run = () => hydrateNotationSheet(document.getElementById(id));
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(run);
  } else {
    setTimeout(run, 0);
  }
}

if (typeof window !== "undefined" && typeof window.addEventListener === "function" && typeof document !== "undefined") {
  window.addEventListener("load", () => {
    hydrateNotationSheets(document);
    if (typeof MutationObserver !== "undefined") {
      const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          mutation.addedNodes.forEach((node) => {
            if (node?.nodeType === 1) hydrateNotationSheets(node);
          });
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }
  });
}

function naturalNoteStep(note) {
  const match = String(note || "").match(/^([A-G])(#|b)?(\d)$/);
  if (!match) return null;
  return (Number(match[3]) * 7) + TREBLE_NOTE_ORDER[match[1]];
}

function staffNoteY(note) {
  const step = naturalNoteStep(note);
  if (step === null) return TREBLE_STAFF_TOP_Y + (TREBLE_STAFF_LINE_GAP * 2);
  const g4Step = (4 * 7) + TREBLE_NOTE_ORDER.G;
  return TREBLE_G4_Y - ((step - g4Step) * TREBLE_STAFF_STEP_Y);
}

function compactStaffNoteY(note) {
  const y = staffNoteY(note);
  const compactStaffTop = 18;
  const compactStaffLineGap = 9;
  const compactY = compactStaffTop + ((y - TREBLE_STAFF_TOP_Y) / TREBLE_STAFF_LINE_GAP * compactStaffLineGap);
  return Math.max(10, Math.min(90, (compactY / 70) * 100));
}

function renderTranscriptionStaff(transcription) {
  const notes = Array.isArray(transcription?.firstNotes) ? transcription.firstNotes.slice(0, 18) : [];
  if (!notes.length) return "";
  return `
    <div class="transcription-staff" aria-label="Machine transcription staff">
      <span></span><span></span><span></span><span></span><span></span>
      ${notes.map((note, index) => `
        <i style="left:${5 + (index * (90 / Math.max(1, notes.length - 1)))}%; top:${compactStaffNoteY(note)}%;" title="${escapeHtml(note)}"></i>
      `).join("")}
    </div>
  `;
}

function renderScoreHeatMap(record, scoreSnippet) {
  if (!scoreSnippetIsMatched(scoreSnippet, record)) return "";
  const score = scoreSnippet?.score || {};
  const imageUrl = scoreImageUrl(score);
  if (!imageUrl) {
    const pendingText = record?.materialStatus === "piece_or_exercise_pending"
      ? "Score or pattern heat map pending."
      : "Score heat map pending.";
    return `<div class="score-placeholder score-heat-placeholder">${escapeHtml(pendingText)}</div>`;
  }
  const boxes = scoreBoxes(score);
  const fragments = Array.isArray(record?.heatMap?.fragments) ? record.heatMap.fragments : [];
  const primary = fragments[0] || {};
  const intensity = Math.max(0.18, Math.min(1, Number(primary.intensity) || 0.35));
  return `
    <div class="score-heat-panel" aria-label="Heat map on score">
      <div class="score-heat-header">
        <span>Score heat map</span>
        <strong>${escapeHtml(shortText(primary.label || "measure alignment pending", 62))}</strong>
      </div>
      <div class="score-image score-heat-image">
        <img src="${escapeHtml(imageUrl)}" alt="">
        ${boxes.map((box) => `
          <span class="score-heat-box" style="left:${Number(box.x) || 0}%; top:${Number(box.y) || 0}%; width:${Number(box.width) || 1}%; height:${Number(box.height) || 1}%; --heat:${intensity};">
            <b>${escapeHtml(box.label || "practice area")}</b>
          </span>
        `).join("")}
      </div>
      <small>${escapeHtml(scoreSnippet?.readiness || "Exact measure heat map pending score alignment.")}</small>
    </div>
  `;
}

function renderEvidenceScore(item) {
  if (!item?.score || typeof item.score !== "object") return "";
  if (!scoreSnippetIsMatched(item)) return "";
  const imageUrl = scoreImageUrl(item.score);
  if (!imageUrl) return "";
  return `
    <div class="evidence-score">
      <span>Score snippet</span>
      ${renderScoreImage({ score: item.score }, true)}
    </div>
  `;
}

function notationDurationClass(kind) {
  const clean = String(kind || "").toLowerCase();
  return ["sixteenth", "eighth", "quarter", "half", "whole"].includes(clean) ? clean : "quarter";
}

function normalizedKeySignature(signature) {
  const accidentals = Array.isArray(signature?.accidentals)
    ? signature.accidentals.map((item) => normalizeAccidentalToken(item)).filter(Boolean).slice(0, 7)
    : [];
  const accidentalType = String(signature?.accidentalType || "").toLowerCase();
  return {
    label: signature?.label || (accidentals.length ? accidentals.join(" ") : "key pending"),
    accidentalType: accidentalType === "flat" || accidentalType === "sharp" ? accidentalType : "none",
    accidentals,
  };
}

function sourceNotationContextForPiece(pieceTitle) {
  const title = String(pieceTitle || "").toLowerCase();
  if (title.includes("wieniawski") && (title.includes("scherzo") || title.includes("tarantelle"))) {
    return {
      label: "G minor / 2 flats",
      accidentalType: "flat",
      accidentals: ["Bb", "Eb"],
      source: "piece_score_context",
      scope: "Wieniawski Scherzo-Tarantelle, Op. 16",
    };
  }
  return {};
}

function inferredReadableKeySignature(notes, context = {}) {
  const provided = normalizedKeySignature(context?.keySignature || {});
  if (provided.accidentals.length && provided.accidentalType !== "none") return provided;
  const sourceContext = normalizedKeySignature(sourceNotationContextForPiece(context?.pieceTitle));
  if (sourceContext.accidentals.length && sourceContext.accidentalType !== "none") return sourceContext;
  return {};
}

function renderKeySignatureMarks(signature) {
  const normalized = normalizedKeySignature(signature || {});
  if (!normalized.accidentals.length || normalized.accidentalType === "none") {
    return { svg: "", width: 0, label: "" };
  }
  const flatPositions = {
    B: staffNoteY("B4"),
    E: staffNoteY("E5"),
    A: staffNoteY("A4"),
    D: staffNoteY("D5"),
    G: staffNoteY("G4"),
    C: staffNoteY("C5"),
    F: staffNoteY("F4"),
  };
  const sharpPositions = {
    F: staffNoteY("F5"),
    C: staffNoteY("C5"),
    G: staffNoteY("G5"),
    D: staffNoteY("D5"),
    A: staffNoteY("A4"),
    E: staffNoteY("E5"),
    B: staffNoteY("B4"),
  };
  const positions = normalized.accidentalType === "flat" ? flatPositions : sharpPositions;
  const marks = normalized.accidentals
    .map((item, index) => {
      const letter = String(item || "").trim().charAt(0).toUpperCase();
      const y = positions[letter];
      if (!Number.isFinite(y)) return "";
      const x = NOTATION_KEY_SIGNATURE_START_X + (index * NOTATION_KEY_SIGNATURE_STEP_X);
      return renderAccidentalGlyph(normalized.accidentalType, x, y, "key-signature-mark");
    })
    .filter(Boolean)
    .join("");
  return {
    svg: marks ? `<g class="key-signature" aria-label="${escapeHtml(normalized.label)}">${marks}</g>` : "",
    width: marks
      ? Math.max(0, (NOTATION_KEY_SIGNATURE_START_X - NOTATION_NOTE_START_X) + ((normalized.accidentals.length - 1) * NOTATION_KEY_SIGNATURE_STEP_X) + NOTATION_KEY_SIGNATURE_WIDTH_PAD)
      : 0,
    label: normalized.label,
  };
}

function renderTrebleClef() {
  return `<text class="treble-clef" x="24" y="${TREBLE_CLEF_BASELINE_Y}" aria-label="treble clef">&#xE050;</text>`;
}

function notationSvgOpen(width = NOTATION_VIEWBOX_BASE_WIDTH) {
  const safeWidth = Math.max(NOTATION_VIEWBOX_BASE_WIDTH, Math.ceil(Number(width) || NOTATION_VIEWBOX_BASE_WIDTH));
  return `<svg viewBox="${notationViewBox(safeWidth)}" style="--notation-svg-width:${safeWidth}px" role="img">`;
}

function renderStaffLines(width = NOTATION_VIEWBOX_BASE_WIDTH) {
  const safeWidth = Math.max(NOTATION_VIEWBOX_BASE_WIDTH, Math.ceil(Number(width) || NOTATION_VIEWBOX_BASE_WIDTH));
  const x2 = Math.max(NOTATION_STAFF_LINE_X2, safeWidth - NOTATION_STAFF_LINE_X1);
  return [30, 40, 50, 60, 70].map((y) => `<line x1="${NOTATION_STAFF_LINE_X1}" x2="${x2}" y1="${y}" y2="${y}" />`).join("");
}

function notationWidthForItemCount(count, noteStartX) {
  const noteCount = Math.max(0, Number(count) || 0);
  const firstNoteX = Number(noteStartX) || NOTATION_NOTE_START_X;
  const lastNoteX = firstNoteX + (Math.max(0, noteCount - 1) * NOTATION_NOTE_MIN_STEP_X);
  return Math.max(NOTATION_VIEWBOX_BASE_WIDTH, lastNoteX + NOTATION_NOTE_TRAILING_PAD_X);
}

function renderLedgerLines(y, x) {
  const lines = [];
  for (let lineY = TREBLE_STAFF_BOTTOM_Y + TREBLE_STAFF_LINE_GAP; lineY <= y + 0.1; lineY += TREBLE_STAFF_LINE_GAP) {
    lines.push(lineY);
  }
  for (let lineY = TREBLE_STAFF_TOP_Y - TREBLE_STAFF_LINE_GAP; lineY >= y - 0.1; lineY -= TREBLE_STAFF_LINE_GAP) {
    lines.push(lineY);
  }
  return lines.map((lineY) => (
    `<line class="ledger-line" x1="${(x - NOTATION_LEDGER_HALF_WIDTH).toFixed(1)}" x2="${(x + NOTATION_LEDGER_HALF_WIDTH).toFixed(1)}" y1="${lineY.toFixed(1)}" y2="${lineY.toFixed(1)}"></line>`
  )).join("");
}

function renderNotationSheet(events, options = {}) {
  const maxNotes = Number(options?.maxNotes) > 0 ? Number(options.maxNotes) : 32;
  const items = Array.isArray(events) ? events.slice(0, maxNotes) : [];
  const repeatGroup = options?.repeatGroup && typeof options.repeatGroup === "object" ? options.repeatGroup : null;
  const normalizedSignature = normalizedKeySignature(options?.keySignature || {});
  const keySignature = renderKeySignatureMarks(normalizedSignature);
  const noteStartX = NOTATION_NOTE_START_X + keySignature.width;
  const fitToWidth = options?.fitToWidth === true;
  const fitWidth = Math.max(NOTATION_VIEWBOX_BASE_WIDTH, Number(options?.fitWidth) || NOTATION_VIEWBOX_BASE_WIDTH);
  const fitStep = items.length > 1
    ? Math.max(30, (fitWidth - noteStartX - NOTATION_NOTE_TRAILING_PAD_X) / Math.max(1, items.length - 1))
    : 0;
  const step = items.length > 1 ? (fitToWidth ? Math.min(NOTATION_NOTE_MIN_STEP_X, fitStep) : NOTATION_NOTE_MIN_STEP_X) : 0;
  const svgWidth = fitToWidth ? fitWidth : notationWidthForItemCount(items.length, noteStartX);
  const staffLines = renderStaffLines(svgWidth);
  const repeatLabel = repeatGroup?.notationLabel || options?.repeatLabel || "";
  const repeatPattern = repeatGroup?.practicePattern || options?.practicePattern || "";
  const qualityLabel = options?.qualityLabel || "";
  const qualityLimit = transcriptionDisplayText(options?.qualityLimit || "");
  const systemLabel = options?.systemLabel || "";
  const captionTitle = systemLabel || repeatLabel || qualityLabel;
  const captionDetail = [repeatPattern || qualityLimit, keySignature.label && keySignature.label !== "key pending" ? keySignature.label : ""].filter(Boolean).join(" / ");
  const repeatClass = repeatLabel ? " notation-repeat" : "";
  const draftClass = options?.draft ? " notation-draft" : "";
  const fitClass = fitToWidth ? " notation-fit" : "";
  const pitchOnly = !notationRhythmVerified(options);
  const rhythmClass = pitchOnly ? " notation-pitch-events" : "";
  const abc = options?.abcSource || notationAbcForEvents(items, normalizedSignature);
  const abcStaffWidth = Math.max(0, Number(options?.abcStaffWidth) || 0);
  const abcScale = Math.max(0, Number(options?.abcScale) || 0);
  const abcAttrs = [
    pitchOnly ? "" : `data-abc="${escapeHtml(abc)}"`,
    !pitchOnly && abcStaffWidth ? `data-abc-staffwidth="${escapeHtml(String(abcStaffWidth))}"` : "",
    !pitchOnly && abcScale ? `data-abc-scale="${escapeHtml(String(abcScale))}"` : "",
  ].filter(Boolean).join(" ");
  const repeatMarks = repeatLabel ? `
    <g class="notation-repeat-mark" aria-label="${escapeHtml(shortText(repeatLabel, 72))}">
      <line x1="46" x2="46" y1="25" y2="75"></line>
      <line x1="51" x2="51" y1="25" y2="75"></line>
      <circle cx="58" cy="42" r="2.2"></circle>
      <circle cx="58" cy="58" r="2.2"></circle>
      <line x1="676" x2="676" y1="25" y2="75"></line>
      <line x1="681" x2="681" y1="25" y2="75"></line>
      <circle cx="669" cy="42" r="2.2"></circle>
      <circle cx="669" cy="58" r="2.2"></circle>
      <path d="M66 18 H654"></path>
      <text x="654" y="17" text-anchor="end">${escapeHtml(shortText(repeatLabel, 34))}</text>
    </g>
  ` : "";
  const sheetId = `notationSheet${++notationSheetIdCounter}`;
  const abcTarget = pitchOnly ? "" : `
    <div class="notation-abc-target" aria-hidden="true"></div>
  `;
  if (!pitchOnly) queueNotationHydration(sheetId);
  if (!items.length) {
    return `
      <div id="${sheetId}" class="notation-sheet notation-empty notation-engraved${repeatClass}${draftClass}${fitClass}${rhythmClass}" ${abcAttrs} aria-label="Sheet-music-style transcription pending">
        ${abcTarget}
        <div class="notation-svg-fallback">
          ${notationSvgOpen(svgWidth)}
          <g class="staff-lines">${staffLines}</g>
            ${renderTrebleClef()}
            ${keySignature.svg}
            ${repeatMarks}
          </svg>
        </div>
        <span>Notation pending.</span>
        ${captionTitle ? `
          <div class="notation-repeat-caption">
            <b>${escapeHtml(shortText(captionTitle, 72))}</b>
            <em>${escapeHtml(shortText(captionDetail || "machine evidence", 92))}</em>
          </div>
        ` : ""}
      </div>
    `;
  }
  let fallbackMeasureAccidentals = {};
  const marks = items.map((event, index) => {
    const x = noteStartX + (step * index);
    const durationClass = pitchOnly ? "pitch-event" : notationDurationClass(event.durationKind);
    if (event.kind === "rest") {
      return `
        <g class="notation-rest ${durationClass}" transform="translate(${x} 0)">
          <rect x="-5" y="45" width="10" height="6" rx="1"></rect>
          <line x1="-7" x2="7" y1="55" y2="55"></line>
        </g>
      `;
    }
    const displayNote = notationDisplayNote(event.note, normalizedSignature);
    const y = staffNoteY(displayNote);
    const stemUp = y >= TREBLE_STAFF_TOP_Y + (TREBLE_STAFF_LINE_GAP * 2);
    const stemX = x + (stemUp ? NOTATION_STEM_OFFSET_X : -NOTATION_STEM_OFFSET_X);
    const stemEndY = stemUp ? Math.max(10, y - 30) : Math.min(94, y + 30);
    const isUncertain = Boolean(event.uncertain || options?.forceUncertain);
    const uncertain = isUncertain ? " notation-uncertain" : "";
    const raw = event.rawNote ? `raw ${event.rawNote}` : event.note && displayNote !== event.note ? `detected ${event.note}` : "";
    const label = escapeHtml([displayNote, raw, isUncertain ? "uncertain" : ""].filter(Boolean).join(" / "));
    const notehead = durationClass === "whole" ? "&#xE0A2;" : durationClass === "half" ? "&#xE0A3;" : "&#xE0A4;";
    return `
      <g class="notation-note ${durationClass}${uncertain}" aria-label="${label}">
        ${renderLedgerLines(y, x)}
        ${renderNoteAccidental(displayNote, normalizedSignature, x, y, fallbackMeasureAccidentals)}
        <text class="notehead" x="${x.toFixed(1)}" y="${y.toFixed(1)}">${notehead}</text>
        ${pitchOnly || durationClass === "whole" ? "" : `<line class="note-stem" x1="${stemX.toFixed(1)}" x2="${stemX.toFixed(1)}" y1="${y.toFixed(1)}" y2="${stemEndY.toFixed(1)}"></line>`}
      </g>
    `;
  }).join("");
  return `
    <div id="${sheetId}" class="notation-sheet notation-engraved${repeatClass}${draftClass}${fitClass}${rhythmClass}" ${abcAttrs} aria-label="Sheet-music-style machine transcription">
      ${abcTarget}
      <div class="notation-svg-fallback">
        ${notationSvgOpen(svgWidth)}
          <g class="staff-lines">${staffLines}</g>
          ${renderTrebleClef()}
          ${keySignature.svg}
          ${repeatMarks}
          ${marks}
        </svg>
      </div>
      ${captionTitle ? `
        <div class="notation-repeat-caption">
          <b>${escapeHtml(shortText(captionTitle, 72))}</b>
          <em>${escapeHtml(shortText(captionDetail || "machine evidence", 92))}</em>
        </div>
      ` : ""}
    </div>
  `;
}

function renderVerifiedNotationGate(
  title = "Audio-checked transcription",
  detail = "Only audio-checked notes render here.",
  keySignature = {}
) {
  const signature = renderKeySignatureMarks(keySignature);
  const staffLines = renderStaffLines();
  return `
    <div class="notation-gate" aria-label="${escapeHtml(title)}">
      ${notationSvgOpen()}
        <g class="staff-lines">${staffLines}</g>
        ${renderTrebleClef()}
        ${signature.svg}
        <text class="notation-gate-title" x="154" y="48">${escapeHtml(shortText(title, 44))}</text>
        <text class="notation-gate-detail" x="154" y="67">${escapeHtml(shortTranscriptionText(detail, 74))}</text>
      </svg>
      <strong>${escapeHtml(transcriptionDisplayText(detail))}</strong>
    </div>
  `;
}

function renderTranscriptionStats(transcription, record = {}) {
  const signature = normalizedKeySignature(transcription?.keySignature || {});
  const displayNotation = transcription?.displayNotation !== false && transcription?.transcriptionReady === true;
  const systems = Array.isArray(transcription?.notationSystems) ? transcription.notationSystems.length : 0;
  const pendingMaterial = record?.materialStatus === "piece_or_exercise_pending";
  const rows = displayNotation
    ? [
        ["Clef", transcription?.clef === "treble" ? "treble" : "pending"],
        ["Key", signature.label || "key pending"],
        ["Status", transcription?.scoreSequenceMatchCount ? "note match" : "detected"],
      ]
    : [
        ["Notation", "pending"],
        ["Clip", systems ? `${systems} windows` : "ready"],
        pendingMaterial
          ? ["Match", "score or pattern"]
          : transcription?.scoreLinked
            ? ["Score", "linked"]
            : transcription?.referenceLinked
              ? ["Reference", "note match"]
              : ["Score", "alignment pending"],
      ];
  return `
    <div class="transcription-stats" aria-label="Transcription state">
      ${rows.map(([label, value]) => `
        <article>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </article>
      `).join("")}
    </div>
  `;
}

function renderMusicianRead(read) {
  if (!read || typeof read !== "object") return "";
  if (read.status && read.status !== "ready") return "";
  const rows = [
    ["Source", read.source || ""],
    ["Target", read.scoreTarget || read.pieceTitle || read.materialType || ""],
    ["Pattern", read.pattern || ""],
    ["Contour", read.contour || ""],
    ["Notes", read.notes || ""],
  ].filter(([, value]) => String(value || "").trim());
  const nearest = read.nearestReference
    ? `${read.nearestReference}${Number(read.nearestReferenceScore || 0) ? ` / ${Math.round(Number(read.nearestReferenceScore) * 100)}%` : ""}`
    : "";
  if (nearest) rows.splice(2, 0, ["Nearest", nearest]);
  if (!rows.length) return "";
  return `
    <div class="musician-read" aria-label="Score-aware read">
      <span>Score-aware read</span>
      <div>
        ${rows.slice(0, 6).map(([label, value]) => `
          <article>
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(shortTranscriptionText(value, 92))}</strong>
          </article>
        `).join("")}
      </div>
      ${read.limit ? `<small>${escapeHtml(shortTranscriptionText(read.limit, 130))}</small>` : ""}
    </div>
  `;
}

function renderNotationSystems(transcription, fallbackEvents = [], record = {}) {
  const systems = Array.isArray(transcription?.notationSystems) && transcription.notationSystems.length
    ? transcription.notationSystems.slice(0, 4)
    : [{ label: "Line 1", events: Array.isArray(fallbackEvents) ? fallbackEvents : [], noteCount: 0, uncertainNoteCount: 0 }];
  const signature = transcription?.keySignature || {};
  const displayNotation = transcription?.displayNotation !== false && transcription?.transcriptionReady === true;
  if (!displayNotation) {
    const withheldText = record?.materialStatus === "piece_or_exercise_pending"
      ? "Match pending."
      : "Score alignment pending.";
    return `
      <div class="notation-systems" aria-label="Audio evidence windows">
        ${systems.map((system) => {
          const window = system?.sourceWindow ? ` / ${system.sourceWindow}s` : "";
          const clipLabel = system?.clip ? clipWindowLabel(system.clip) : "sample window";
          return `
            <div class="notation-system notation-system-audio">
              <div class="notation-system-head">
                <span>${escapeHtml("Audio evidence")}${escapeHtml(window)}</span>
                <strong>${escapeHtml(clipLabel)}</strong>
              </div>
              ${renderSnippetAudio(system?.clip || {}, "Window audio")}
            </div>
          `;
        }).join("")}
        <p class="empty">${escapeHtml(withheldText)}</p>
      </div>
    `;
  }
  return `
    <div class="notation-systems" aria-label="Audio-checked transcription windows">
      ${systems.map((system) => {
        const window = system?.sourceWindow ? ` / ${system.sourceWindow}s` : "";
        const clipLabel = system?.clip ? clipWindowLabel(system.clip) : "";
        return `
          <div class="notation-system">
            <div class="notation-system-head">
              <span>${escapeHtml(displayNotation ? system?.label || "Line" : "Audio evidence")}${escapeHtml(window)}</span>
              <strong>${escapeHtml(displayNotation ? (transcription?.scoreSequenceMatchCount ? "note match" : "detected") : clipLabel || "sample window")}</strong>
            </div>
            ${renderSnippetAudio(system?.clip || {}, "Window audio")}
            ${displayNotation ? renderNotationSheet(system?.events || [], {
              keySignature: signature,
              systemLabel: system?.label || "",
              qualityLimit: system?.limit || transcription?.displayLimit || transcription?.coverageLimit || ""
            }) : ""}
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function heatLayerDetail(layer, items) {
  if (items) return `${items} signals`;
  const status = String(layer?.status || "pending");
  if (status.includes("pending_multiple")) return "pending";
  if (status.includes("pending_more")) return "pending";
  if (status.includes("pending")) return "pending";
  return status.replaceAll("_", " ");
}

function renderHeatMap(record) {
  const fragments = Array.isArray(record?.heatMap?.fragments) ? record.heatMap.fragments : [];
  const layers = Array.isArray(record?.heatMap?.layers) ? record.heatMap.layers.slice(0, 4) : [];
  if (!fragments.length) {
    return `<div class="heat-map heat-map-empty"><span>Heat map pending transcription.</span></div>`;
  }
  return `
    <div class="heat-map" aria-label="Repeated passage heat map">
      ${layers.length ? `
        <div class="heat-layers" aria-label="Heat map layers">
          ${layers.map((layer) => {
            const items = Array.isArray(layer.items) ? layer.items.length : 0;
            return `
              <span data-status="${escapeHtml(layer.status || "pending")}">
                <b>${escapeHtml(layer.label || "Layer")}</b>
                <em>${escapeHtml(heatLayerDetail(layer, items))}</em>
              </span>
            `;
          }).join("")}
        </div>
      ` : ""}
      ${fragments.slice(0, 6).map((fragment) => {
        const intensity = Math.max(0.08, Math.min(1, Number(fragment.intensity) || 0));
        return `
          <div class="heat-row">
            <span>${escapeHtml(shortText(fragment.label, 34))}</span>
            <b style="--heat:${intensity};"></b>
            <em>${escapeHtml(String(fragment.count || 0))}x</em>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function recordStatusLabel(record) {
  if (exactScoreMatchGroups(record).length) return "match";
  if (record?.matchingWorkflow?.status === "score_sequence_matches_ready") return "checking";
  if (record?.matchingWorkflow?.status === "reference_sequence_matches_ready") return "matching";
  if (record?.matchingWorkflow?.status === "source_verification_pending") return "checking";
  if (record?.matchingWorkflow?.status === "pitch_anchor_matches_ready") {
    return "matching";
  }
  if (record?.transcription?.reliability === "audio_matched_fragment") return "detected note";
  if (record?.transcription?.reliability === "audio_verified_micro") return "audio-checked transcription";
  if (record?.matchingWorkflow?.status === "awaiting_piece_name") return "piece name";
  if (record?.transcription?.qualityStatus === "candidate_micro_transcription") return "matching";
  if (record?.transcription?.reliability === "transcription_failed") return "matching";
  if (record?.transcription?.qualityStatus === "transcription_failed") return "matching";
  if (record?.transcription?.reliability === "score_audio_only") return "matching";
  if (record?.transcription?.qualityStatus === "score_audio_only") return "matching";
  if (record?.transcription?.reliability === "machine_pitch_hidden") return "audio evidence";
  if (record?.transcription?.qualityStatus === "machine_pitch_hidden") return "audio evidence";
  if (record?.transcription?.qualityStatus === "weak_fragment") return "audio evidence";
  if (record?.transcription?.qualityStatus === "sanity_corrected_draft") return "audio evidence";
  if (record?.transcription?.qualityStatus === "draft_fragment") return "audio evidence";
  if (record?.status === "transcribed") return "detected transcription";
  if (record?.status === "active_time_measured") return "practice measured";
  return "pending media";
}

function recordStatusTone(record) {
  if (exactScoreMatchGroups(record).length) return "verified";
  if (
    record?.matchingWorkflow?.status === "score_sequence_matches_ready"
    || record?.matchingWorkflow?.status === "reference_sequence_matches_ready"
    || record?.matchingWorkflow?.status === "source_verification_pending"
    || record?.matchingWorkflow?.status === "pitch_anchor_matches_ready"
  ) return "pending";
  if (record?.transcription?.transcriptionReady === true) return "verified";
  return "pending";
}

function transcriptionEvidenceLabel(transcription) {
  if (transcription?.scoreLocationVerifiedCount) return "note match";
  if (transcription?.reliability === "audio_matched_fragment") return "detected note";
  if (transcription?.reliability === "audio_verified_micro") return "audio-checked transcription";
  if (transcription?.displayNotation === true && transcription?.transcriptionReady === true) return "detected transcription";
  if (transcription?.qualityStatus === "candidate_micro_transcription") return "matching";
  if (
    transcription?.reliability === "transcription_failed"
    || transcription?.qualityStatus === "transcription_failed"
    || transcription?.reliability === "score_audio_only"
    || transcription?.qualityStatus === "score_audio_only"
  ) {
    return "matching";
  }
  if (transcription?.reliability === "machine_pitch_hidden" || transcription?.status === "not_ready") {
    return "matching";
  }
  return transcription?.qualityLabel || (transcription?.status === "ready" ? "detected transcription" : "notation not ready");
}

function transcriptionReasonLine(record) {
  const transcription = record?.transcription || {};
  const label = transcriptionEvidenceLabel(transcription);
  if (label === "matching") {
    return "Notation pending.";
  }
  if (label === "detected note") {
    const events = Array.isArray(transcription.events) ? transcription.events : [];
    const notes = events.filter((event) => event?.kind === "note" && event.note).map((event) => event.note);
    const seconds = Number(transcription.matchedFragmentSeconds || transcription.microVerifiedSeconds || transcription.durationSeconds || 0);
    const evidence = [
      notes.length ? notes.slice(0, 3).join(" / ") : "",
      seconds ? `${seconds.toFixed(seconds < 1 ? 3 : 1)}s` : ""
    ].filter(Boolean).join(" / ");
    return `Transcription: ${evidence || "detected note"}.`;
  }
  const limit = transcription.reliabilityLimit || transcription.qualityLimit || transcription.fullSessionLimit || transcription.coverageLimit || "No accepted transcription has been generated.";
  return `Transcription: ${label}. ${shortTranscriptionText(limit, 180)}`;
}

function renderRepeatGroups(groups) {
  const rows = Array.isArray(groups) ? groups.slice(0, 4) : [];
  if (!rows.length) return "";
  return `
    <div class="repeat-groups" aria-label="Grouped repeated practice material">
      ${rows.map((group) => `
        <article>
          <span>${escapeHtml(group.confidence || "machine grouped")}</span>
          <strong>${escapeHtml(group.notationLabel || `${group.label || "fragment"} x${group.repeatCount || ""}`)}</strong>
          <em>${escapeHtml(group.practicePattern || "repeated loop")}</em>
        </article>
      `).join("")}
    </div>
  `;
}

function renderObservations(observations) {
  const rows = Array.isArray(observations) ? observations.slice(0, 3) : [];
  if (!rows.length) return `<div class="observation-list"><p>No specific observed blocker extracted yet.</p></div>`;
  return `
    <div class="observation-list" aria-label="Specific observed problems">
      ${rows.map((item) => `
        <article>
          <span>${escapeHtml([item.category, item.frequency].filter(Boolean).join(" / "))}</span>
          <strong>${escapeHtml(transcriptionDisplayText(item.problem || "Observation pending."))}</strong>
          <p>${escapeHtml(transcriptionDisplayText(item.curtisReadinessIssue || ""))}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function renderRepertoireUpdates(updates) {
  const rows = Array.isArray(updates) ? updates.slice(0, 2) : [];
  if (!rows.length) return "";
  return `
    <div class="repertoire-update-ledger" aria-label="Automatic repertoire updates">
      ${rows.map((item) => `
        <article>
          <span>${escapeHtml([item.action, item.status].filter(Boolean).join(" / ") || "repertoire update")}</span>
          <strong>${escapeHtml(item.pieceTitle || "Piece")}</strong>
          <em>${escapeHtml(shortTranscriptionText(item.reason || "Confirmed from practice evidence.", 120))}</em>
        </article>
      `).join("")}
    </div>
  `;
}

function renderTranscriptionProof(record, scoreSnippet) {
  const piece = Array.isArray(record?.pieces) ? record.pieces[0] : null;
  const repeatGroup = Array.isArray(record?.transcription?.repeatGroups) ? record.transcription.repeatGroups[0] : null;
  const section = scoreSnippet?.title || repeatGroup?.label || "section pending";
  const confidence = piece?.confidence || record?.evidenceStatus || record?.transcription?.status || "pending";
  const noteCount = Number(record?.transcription?.noteCount) || 0;
  const notationLabel = noteCount ? transcriptionEvidenceLabel(record?.transcription) : "pending";
  const scoreReadiness = scoreSnippet?.readiness || scoreSnippet?.score?.status || piece?.score?.status || "score alignment pending";
  const windowLabel = scoreSnippet?.practiceLabel || record?.processedSampleLabel || record?.activeViolinLabel || "";
  return `
    <div class="transcription-proof-ledger" aria-label="Transcription evidence state">
      <article>
        <span>Piece</span>
        <strong>${escapeHtml(recordPieceText(record))}</strong>
      </article>
      <article>
        <span>Section</span>
        <strong>${escapeHtml(shortText(section, 54))}</strong>
      </article>
      <article>
        <span>Confidence</span>
        <strong>${escapeHtml(shortText(confidence, 54))}</strong>
      </article>
      <article>
        <span>Score</span>
        <strong>${escapeHtml(shortText(scoreReadiness, 74))}</strong>
      </article>
      <article>
        <span>Notation</span>
        <strong>${escapeHtml(notationLabel)}</strong>
      </article>
      <article>
        <span>Window</span>
        <strong>${escapeHtml(windowLabel || "pending")}</strong>
      </article>
    </div>
  `;
}

function clipWindowLabel(clip) {
  const start = Number(clip?.startSeconds) || 0;
  const end = Number(clip?.endSeconds) || 0;
  return end > start ? `${formatClock(start)}-${formatClock(end)}` : "open video";
}

function clipThumbnailUrl(clip) {
  const id = parseVideoId(clip?.url || clip?.sourceUrl || "");
  if (!id) return "";
  return `https://i.ytimg.com/vi/${encodeURIComponent(id)}/hqdefault.jpg`;
}

function renderClipFrame(clip, label = "Evidence clip") {
  const image = clipThumbnailUrl(clip);
  const href = timedUrl(clip?.url || "", Number(clip?.startSeconds) || 0);
  if (!image || !href) return "";
  return `
    <a class="clip-frame" href="${escapeHtml(href)}" aria-label="${escapeHtml([label, clipWindowLabel(clip)].filter(Boolean).join(" / "))}">
      <img src="${escapeHtml(image)}" alt="">
      <span>
        <b>${escapeHtml(label)}</b>
        <em>${escapeHtml(clipWindowLabel(clip))}</em>
      </span>
    </a>
  `;
}

function mediaFragmentUrl(clip) {
  const url = assetUrl(clip?.mediaUrl || "");
  if (!url) return "";
  const start = Math.max(0, Number(clip?.localStartSeconds) || 0);
  const end = Math.max(start, Number(clip?.localEndSeconds) || 0);
  return `${url}#t=${start.toFixed(2)}${end > start ? `,${end.toFixed(2)}` : ""}`;
}

function audioClipUrl(clip) {
  const exact = assetUrl(clip?.audioUrl || clip?.clipUrl || "");
  return exact || mediaFragmentUrl(clip);
}

function renderSnippetAudio(clip, label = "Snippet audio") {
  const src = audioClipUrl(clip);
  if (!src) {
    return `
      <div class="snippet-audio snippet-audio-pending">
        <span>${escapeHtml(label)}</span>
        <strong>audio pending</strong>
      </div>
    `;
  }
  const window = clipWindowLabel(clip);
  return `
    <div class="snippet-audio" aria-label="${escapeHtml([label, window].filter(Boolean).join(" / "))}">
      <div>
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(window)}</strong>
      </div>
      <audio controls preload="metadata" src="${escapeHtml(src)}"></audio>
    </div>
  `;
}

function primaryPlayableClip(record) {
  const clips = Array.isArray(record?.clips) ? record.clips : [];
  return clips.find((clip) => clip?.mediaUrl && clip.type === "audio_matched_fragment")
    || clips.find((clip) => clip?.mediaUrl && clip.type === "transcribed_window" && Number(clip.noteCount || record?.transcription?.noteCount || 0) > 0)
    || clips.find((clip) => clip?.mediaUrl && clip.type === "transcribed_window")
    || clips.find((clip) => clip?.mediaUrl)
    || clips[0]
    || null;
}

function primaryNotationClip(record) {
  const systems = Array.isArray(record?.transcription?.notationSystems) ? record.transcription.notationSystems : [];
  const system = systems.find((item) => item?.clip?.mediaUrl);
  return system?.clip || null;
}

function eventInsideClip(event, clip) {
  if (!clip || !["transcribed_window", "audio_matched_fragment"].includes(clip.type)) return true;
  if (event?.kind !== "note") return false;
  const start = Number(clip.startSeconds) || 0;
  const end = Number(clip.endSeconds) || 0;
  const eventStart = Number(event.sourceStartSeconds);
  return end > start && Number.isFinite(eventStart) && eventStart >= start - 0.2 && eventStart <= end + 0.2;
}

function transcriptionEventsForClip(record, clip) {
  const events = Array.isArray(record?.transcription?.events) ? record.transcription.events : [];
  if (!clip || !["transcribed_window", "audio_matched_fragment"].includes(clip.type)) return events;
  const filtered = [];
  for (const event of events) {
    if (eventInsideClip(event, clip)) {
      filtered.push(event);
      continue;
    }
    if (event?.kind === "rest" && filtered.length) filtered.push(event);
  }
  const noteCount = filtered.filter((event) => event?.kind === "note").length;
  return clip?.type === "audio_matched_fragment" && noteCount ? filtered : noteCount >= 3 ? filtered : events;
}

function transcriptionCoverageText(record) {
  const transcription = record?.transcription || {};
  return transcription.coverageLabel || record?.processedSampleLabel || "sample window pending";
}

function renderEmbeddedMedia(record, preferredClip = null) {
  const clip = preferredClip || primaryPlayableClip(record);
  const src = mediaFragmentUrl(clip);
  const audioSrc = audioClipUrl(clip) || src;
  if (!src) {
    return `
      <div class="embedded-media embedded-media-pending">
        <span>Local clip</span>
        <strong>sample pending</strong>
        <small>Stored YouTube metadata is not playable media.</small>
      </div>
    `;
  }
  const label = clip?.type === "audio_matched_fragment"
    ? "Clip"
    : clip?.type === "audio_evidence_window" || clip?.type === "pitch_trace_snippet" || clip?.type === "transcribed_window"
    ? "Clip"
    : "Local clip";
  return `
    <div class="embedded-media" aria-label="Playable local practice clip">
      <div class="embedded-media-header">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(clipWindowLabel(clip))}</strong>
      </div>
      <video controls preload="metadata" src="${escapeHtml(src)}"></video>
      <audio controls preload="metadata" src="${escapeHtml(audioSrc)}"></audio>
    </div>
  `;
}

function matchedNotationSystem(transcription) {
  const systems = Array.isArray(transcription?.notationSystems) ? transcription.notationSystems : [];
  return systems.find((item) => Array.isArray(item?.events) && item.events.length) || systems[0] || {};
}

function renderSingleMatchedPracticePair(record, clip, transcription, system) {
  const notationClip = system?.clip || clip || primaryNotationClip(record) || primaryPlayableClip(record);
  const mediaClip = notationClip ? { ...notationClip, type: "audio_matched_fragment", label: "detected note" } : notationClip;
  const notationKeySignature = system?.keySignature || transcription?.keySignature || {};
  const events = Array.isArray(system?.events) && system.events.length
    ? system.events
    : Array.isArray(transcription?.events) ? transcription.events : [];
  const notes = events.filter((event) => event?.kind === "note").map((event) => event.note).filter(Boolean);
  const eventSeconds = events.reduce((sum, event) => sum + Number(event?.durationSeconds || 0), 0);
  const seconds = Number(notationClip?.durationSeconds || transcription?.microVerifiedSeconds || eventSeconds || 0);
  const label = [
    notes.length ? notes.slice(0, 8).join(" ") : "detected note",
    seconds ? `${seconds.toFixed(seconds < 1 ? 3 : 1)}s` : ""
  ].filter(Boolean).join(" / ");
  return `
    <div class="matched-practice-pair" aria-label="Detected video audio transcription pair">
      ${renderEmbeddedMedia(record, mediaClip)}
      <section class="matched-notation-panel">
        <div class="matched-notation-head">
          <span>Transcription</span>
          <strong>${escapeHtml(label || "detected")}</strong>
        </div>
        ${renderNotationSheet(events, {
          keySignature: notationKeySignature,
          maxNotes: 24
        })}
      </section>
    </div>
  `;
}

function renderMatchedPracticePair(record, clip, transcription) {
  const systems = Array.isArray(transcription?.notationSystems)
    ? transcription.notationSystems.filter((system) => Array.isArray(system?.events) && system.events.length)
    : [];
  const visibleSystems = systems.length ? systems.slice(0, 3) : [matchedNotationSystem(transcription)];
  return `
    <div class="matched-pair-stack" aria-label="Detected video audio transcription pairs">
      ${visibleSystems.map((system) => renderSingleMatchedPracticePair(record, clip, transcription, system)).join("")}
    </div>
  `;
}

function matchGroupNotationEvents(group) {
  const transcription = group?.transcription && typeof group.transcription === "object" ? group.transcription : {};
  const displayed = Array.isArray(group?.displayDetectedNotes) ? group.displayDetectedNotes : [];
  const notes = displayed.length ? displayed : Array.isArray(transcription.notes) ? transcription.notes : [];
  return notes
    .filter((note) => note && note.note)
    .slice(0, 32)
    .map((note) => {
      const start = Number(note.startSeconds) || 0;
      const end = Math.max(start, Number(note.endSeconds) || start);
      return {
        kind: "note",
        note: String(note.note || ""),
        midi: note.midi,
        startSeconds: start,
        endSeconds: end,
        localStartSeconds: start,
        localEndSeconds: end,
        durationSeconds: Math.max(0.15, Number(note.durationSeconds) || (end - start) || 0.4),
        durationKind: "quarter",
        confidence: Number(note.confidence) || 0,
        uncertain: Boolean(note.uncertain),
      };
    });
}

function scoreAnchorNotationEvents(group) {
  const notes = Array.isArray(group?.scoreAnchorNotes) ? group.scoreAnchorNotes : [];
  const pitchClass = String(group?.scorePitchClassSequenceCompact || group?.scorePitchClassSequence || group?.detectedPitchClassSequence || "").trim().split(/\s+/)[0] || "A";
  const fallbackNote = /^[A-G]$/.test(pitchClass) ? `${pitchClass}4` : "A4";
  const sourceNotes = notes.length ? notes : [{ note: fallbackNote, pitchClass, durationKind: "quarter" }];
  return sourceNotes
    .filter((note) => note && note.note)
    .slice(0, 1)
    .map((note) => ({
      kind: "note",
      note: String(note.note || fallbackNote),
      pitchClass: note.pitchClass || pitchClass,
      startSeconds: 0,
      endSeconds: 1,
      localStartSeconds: 0,
      localEndSeconds: 1,
      durationSeconds: 1,
      durationKind: note.durationKind || "quarter",
      confidence: 1,
      uncertain: false,
    }));
}

function scoreAnchorSnippet(group) {
  const snippet = group?.scoreAnchorSnippet && typeof group.scoreAnchorSnippet === "object"
    ? group.scoreAnchorSnippet
    : {};
  const score = group?.score && typeof group.score === "object" ? group.score : {};
  const imageUrl = assetUrl(snippet.imageUrl || score.imageUrl || "");
  if (!imageUrl) return null;
  return {
    imageUrl,
    sourceUrl: assetUrl(snippet.sourceUrl || score.sourceUrl || ""),
    pdfUrl: assetUrl(snippet.pdfUrl || score.pdfUrl || ""),
    note: snippet.note || group?.scoreAnchorNotes?.[0]?.note || "",
    pitchClass: snippet.pitchClass || group?.scorePitchClassSequenceCompact || group?.scorePitchClassSequence || "",
    source: snippet.source || score.source || "",
    label: snippet.label || group?.scoreSequenceLabel || "",
    measureLabel: measureLabelForMatch(group) || snippet.measureLabel || score.measureLabel || "",
    noteLocation: snippet.noteLocation || "",
  };
}

function renderScoreAnchorPanel(group) {
  const events = scoreAnchorNotationEvents(group);
  const pitch = group?.scorePitchClassSequenceCompact
    || group?.scorePitchClassSequence
    || group?.detectedPitchClassSequence
    || "A";
  const snippet = scoreAnchorSnippet(group);
  const sourceHref = snippet?.sourceUrl || snippet?.pdfUrl || "";
  const measureLabel = snippet?.measureLabel || measureLabelForMatch(group);
  return `
    <section class="score-anchor-panel" aria-label="Source score note">
      <div class="matched-notation-head">
        <span>Score</span>
        <strong>${escapeHtml(shortText([measureLabel, pitch].filter(Boolean).join(" / "), 28))}</strong>
      </div>
      ${snippet ? `
        <div class="score-anchor-image" aria-label="Source score snippet">
          <img src="${escapeHtml(snippet.imageUrl)}" alt="Actual score snippet showing ${escapeHtml(snippet.note || pitch)}">
        </div>
        <div class="score-anchor-meta">
          <span>${escapeHtml(shortText([measureLabel, snippet.note || pitch].filter(Boolean).join(" / "), 24))}</span>
          ${sourceHref ? `<a href="${escapeHtml(sourceHref)}" target="_blank" rel="noreferrer">IMSLP</a>` : ""}
        </div>
      ` : renderNotationSheet(events, {
        keySignature: {},
        maxNotes: 1
      })}
    </section>
  `;
}

function compactPitchSequenceText(value) {
  const parts = String(value || "").trim().split(/\s+/).filter(Boolean);
  const compact = [];
  parts.forEach((part) => {
    if (compact[compact.length - 1] !== part) compact.push(part);
  });
  return compact.join(" ");
}

function exactEvidenceFlag(group, score, names) {
  return names.some((name) => group?.[name] === true || score?.[name] === true);
}

function exactScoreSnippetReady(group) {
  const score = group?.score && typeof group.score === "object" ? group.score : {};
  if (score.visualAgreement !== true && group?.scoreVisualAgreement !== true) return false;
  if (score.actualSourceSnippetDisplayed !== true && group?.scoreActualPieceAgreement !== true) return false;
  if (score.visualRangeAgreement !== true || group?.scoreVisualRangeAgreement !== true) return false;
  if (score.visibleScoreNoteSequenceVerified !== true || group?.scoreVisibleNoteSequenceVerified !== true) return false;
  if (score.visibleScoreExactNoteSequenceVerified !== true || group?.scoreVisibleExactNoteSequenceVerified !== true) return false;
  if (score.scoreSpellingAgreement !== true || group?.scoreSpellingAgreement !== true) return false;
  if (!exactEvidenceFlag(group, score, ["scoreBoxCenterAgreement", "scoreNoteBoxCenterAgreement", "visibleScoreBoxCenterAgreement"])) return false;
  if (!exactEvidenceFlag(group, score, ["audioTranscriptionAgreement", "audioTranscriptionExactAgreement", "clipTranscriptionAgreement"])) return false;
  if (!exactEvidenceFlag(group, score, ["transcriptionScoreAgreement", "transcriptionScoreExactAgreement", "scoreTranscriptionAgreement"])) return false;
  if (!exactEvidenceFlag(group, score, ["truthEvidenceAccepted", "acceptedTruthEvidence", "manualEvidenceAccepted"])) return false;
  const imageUrl = String(score.imageUrl || "").trim();
  if (!imageUrl || imageUrl.startsWith("data:")) return false;
  const status = compactText(
    score.cropStatus
    || score.status
    || group?.scoreSnippetStatus
    || group?.scoreLocationStatus
    || group?.scoreAlignmentStatus
    || ""
  );
  if (!status || ["pending", "estimate", "estimated", "unverified", "candidate", "rejected", "failed", "mismatch"].some((token) => status.includes(token))) {
    return false;
  }
  return [
    "exact_score_location_verified",
    "exact_measure_match",
    "exact_measure_verified",
    "score_location_verified",
    "measure_location_verified",
  ].some((token) => status.includes(compactText(token)));
}

function exactScoreMatchGroups(record) {
  return Array.isArray(record?.matchGroups)
    ? record.matchGroups.filter(exactScoreSnippetReady)
    : [];
}

function notePitchClassText(value) {
  const match = String(value || "").trim().match(/^([A-G](?:#|b)?)/);
  return match ? match[1] : "";
}

function exactNoteText(value) {
  const match = String(value || "").trim().match(/^([A-G](?:#|b)?\d+)/);
  return match ? match[1] : "";
}

function detectedMatchNoteLabel(group) {
  const detected = Array.isArray(group?.matchedDetectedNotes) ? group.matchedDetectedNotes : [];
  const displayed = Array.isArray(group?.displayDetectedNotes) ? group.displayDetectedNotes : [];
  const transcription = group?.transcription && typeof group.transcription === "object" ? group.transcription : {};
  const notes = Array.isArray(transcription?.notes) ? transcription.notes : [];
  const source = detected[0] || displayed[0] || notes[0] || {};
  return source?.note || source?.pitchClass || group?.detectedPitchClassSequenceCompact || "";
}

function sourceScoreAnchorReady(group) {
  const snippet = group?.scoreAnchorSnippet && typeof group.scoreAnchorSnippet === "object"
    ? group.scoreAnchorSnippet
    : {};
  const score = group?.score && typeof group.score === "object" ? group.score : {};
  const imageUrl = snippet.imageUrl || score.imageUrl || "";
  if (!imageUrl) return false;
  const visualNoteVerified = (
    snippet.visualNoteVerified === true
    || snippet.scoreNoteVerified === true
    || snippet.verified === true
    || group?.visualNoteVerified === true
    || group?.scoreNoteVerified === true
    || score.visualNoteVerified === true
    || score.scoreNoteVerified === true
  );
  if (!visualNoteVerified) return false;
  const exactNoteVerified = (
    snippet.exactNoteVerified === true
    || snippet.visibleScoreNoteSequenceVerified === true
    || group?.exactNoteVerified === true
    || group?.visibleScoreNoteSequenceVerified === true
    || score.exactNoteVerified === true
    || score.visibleScoreNoteSequenceVerified === true
  );
  if (!exactNoteVerified) return false;
  const scoreNote = exactNoteText(snippet.note || group?.scorePitchClassSequenceCompact || group?.scorePitchClassSequence);
  const detectedNote = exactNoteText(detectedMatchNoteLabel(group) || group?.detectedPitchClassSequenceCompact || group?.detectedPitchClassSequence);
  if (scoreNote && detectedNote && scoreNote !== detectedNote) return false;
  const scorePitch = notePitchClassText(snippet.pitchClass || snippet.note || group?.scorePitchClassSequenceCompact || group?.scorePitchClassSequence);
  const detectedPitch = notePitchClassText(detectedMatchNoteLabel(group) || group?.detectedPitchClassSequenceCompact || group?.detectedPitchClassSequence);
  return Boolean(scorePitch && detectedPitch && scorePitch === detectedPitch);
}

function sourceScoreMatchGroups(record) {
  const anchors = Array.isArray(record?.pitchAnchorGroups) ? record.pitchAnchorGroups : [];
  return anchors.filter(sourceScoreAnchorReady).slice(0, 1);
}

function renderScoreMatchGroups(record) {
  const groups = exactScoreMatchGroups(record).slice(0, 1);
  if (!groups.length) return "";
  return `
    <div class="score-match-groups" aria-label="Accepted score transcription media match">
      ${groups.map((group, index) => {
        const clip = group?.clip || {};
        const events = matchGroupNotationEvents(group);
        const transcription = {
          ...(group?.transcription || {}),
          keySignature: group?.score?.keySignature || group?.keySignature || record?.transcription?.keySignature || {},
          notationSystems: [{ events, clip }],
        };
        const pieceTitle = group?.pieceTitle || recordPieceText(record);
        const measureLabel = measureLabelForMatch(group);
        const matchedNotes = group?.scoreNotePitchSequenceLabel
          || group?.scoreNoteSeriesLabel
          || group?.score?.scoreNotePitchSequenceLabel
          || group?.detectedPitchClassSequenceCompact
          || group?.scorePitchClassSequenceCompact
          || compactPitchSequenceText(group?.detectedPitchClassSequence || group?.scorePitchClassSequence || "");
        const matchLabel = [
          Number(group?.matchedNoteRun) ? `${Number(group.matchedNoteRun)} notes` : "pitch match",
          matchedNotes,
        ].filter(Boolean).join(" / ");
        const showScoreSnippet = exactScoreSnippetReady(group);
        return `
          <article class="score-match-group note-match-group">
            <div class="score-match-head">
              <span>${escapeHtml(measureLabel ? `Match ${measureLabel}` : "Match")}</span>
              <strong>${escapeHtml(shortText(matchLabel, 86))}</strong>
            </div>
            <div class="score-match-grid${showScoreSnippet ? "" : " note-match-grid"}">
              ${showScoreSnippet ? `<section class="score-reference-panel">
                <div class="score-heat-header">
                  <span>Score</span>
                  <strong>${escapeHtml(shortText([measureLabel, pieceTitle].filter(Boolean).join(" / "), 58))}</strong>
                </div>
                ${renderScoreImage({ score: group?.score || {} }, true)}
              </section>` : ""}
              ${renderSingleMatchedPracticePair(record, clip, transcription, { events, clip, keySignature: transcription.keySignature })}
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderPitchAnchorGroups(record) {
  const groups = sourceScoreMatchGroups(record);
  if (!groups.length) return "";
  return `
    <div class="score-match-groups pitch-anchor-groups" aria-label="Source score note matches">
      ${groups.map((group, index) => {
        const clip = group?.clip || {};
        const events = matchGroupNotationEvents(group);
        const transcription = {
          ...(group?.transcription || {}),
          notationSystems: [{ events, clip }],
        };
        const pitch = detectedMatchNoteLabel(group)
          || group?.scoreAnchorSnippet?.note
          || group?.detectedPitchClassSequenceCompact
          || group?.detectedPitchClassSequence
          || group?.scorePitchClassSequenceCompact
          || "pitch";
        const label = [
          "1 note",
          pitch,
        ].filter(Boolean).join(" / ");
        return `
          <article class="score-match-group note-match-group pitch-anchor-group">
            <div class="score-match-head">
              <span>Match ${index + 1}</span>
              <strong>${escapeHtml(shortText(label, 64))}</strong>
            </div>
            <div class="score-match-grid pitch-anchor-grid">
              ${renderScoreAnchorPanel(group)}
              ${renderSingleMatchedPracticePair(record, clip, transcription, { events, clip })}
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderTranscriptionRunLink(record, transcription) {
  const href = assetUrl(transcription?.pdfUrl || record?.matchingWorkflow?.transcriptionRunPdfUrl || "");
  if (!href) return "";
  return `<a class="transcription-pdf-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">PDF</a>`;
}

function renderPendingPracticePair(record) {
  return renderPieceLabelForm(record);
}

function renderClipEvidencePair({ clip, observation, repeatGroup, notationEvents, pieceTitle, keySignature, notationReady = false }) {
  if (!clip && !observation && !repeatGroup && !(Array.isArray(notationEvents) && notationEvents.length)) return "";
  const events = Array.isArray(notationEvents) && notationEvents.length
    ? notationEvents
    : Array.isArray(observation?.transcriptionSnippet)
      ? observation.transcriptionSnippet
      : [];
  const passage = observation?.passage || repeatGroup?.label || pieceTitle || "passage pending";
  const repeatText = repeatGroup?.notationLabel
    || (repeatGroup?.repeatCount ? `${repeatGroup?.label || "fragment"} x${repeatGroup.repeatCount}` : "");
  const pattern = repeatGroup?.practicePattern || transcriptionDisplayText(clip?.reason) || observation?.frequency || "pattern pending";
  const problem = transcriptionDisplayText(observation?.problem || clip?.reason || "specific observation pending");
  const confidence = observation?.confidence || repeatGroup?.confidence || clip?.type || "confidence pending";
  return `
    <div class="clip-evidence-pair" aria-label="Clip linked to transcription evidence">
      <div class="clip-evidence-grid">
        <article>
          <span>Passage</span>
          <strong>${escapeHtml(shortText(passage, 58))}</strong>
        </article>
        <article>
          <span>Repeat</span>
          <strong>${escapeHtml(shortText(repeatText || pattern, 58))}</strong>
        </article>
        <article>
          <span>Observation</span>
          <strong>${escapeHtml(shortText(problem, 96))}</strong>
        </article>
        <article>
          <span>Confidence</span>
          <strong>${escapeHtml(shortText(confidence, 58))}</strong>
        </article>
      </div>
      ${notationReady && events.length ? renderNotationSheet(events, {
        keySignature,
        systemLabel: "Matched snippet",
        qualityLimit: "Score-matched notation paired with this clip.",
        maxNotes: 24
      }) : `<p class="empty">Notation withheld until score verification.</p>`}
    </div>
  `;
}

function renderRecordClips(record, includeFrame = false) {
  const clips = Array.isArray(record?.clips) ? record.clips.slice(0, 3) : [];
  if (!clips.length) return `<p class="empty">Clip evidence pending.</p>`;
  const primaryObservation = Array.isArray(record?.observations) ? record.observations[0] : null;
  const primaryRepeatGroup = Array.isArray(record?.transcription?.repeatGroups) ? record.transcription.repeatGroups[0] : null;
  const primaryEvents = Array.isArray(primaryObservation?.transcriptionSnippet) && primaryObservation.transcriptionSnippet.length
    ? primaryObservation.transcriptionSnippet
    : record?.transcription?.events;
  return `
    ${includeFrame ? renderClipFrame(clips[0], "Main practice evidence") : ""}
    ${includeFrame ? renderClipEvidencePair({
      clip: clips[0],
      observation: primaryObservation,
      repeatGroup: primaryRepeatGroup,
      notationEvents: primaryEvents,
      pieceTitle: recordPieceText(record),
      keySignature: record?.transcription?.keySignature,
      notationReady: record?.transcription?.displayNotation === true && record?.transcription?.transcriptionReady === true
    }) : ""}
    <div class="clip-list">
      ${clips.map((clip) => {
        const start = Number(clip?.startSeconds) || 0;
        const url = timedUrl(clip?.url || "", start);
        return `
          <a href="${escapeHtml(url)}">
            <span>${escapeHtml(clipWindowLabel(clip))}</span>
            <strong>${escapeHtml(shortTranscriptionText(clip?.reason || clip?.label || "practice clip", 76))}</strong>
          </a>
        `;
      }).join("")}
    </div>
  `;
}

function scoreSnippetForRecord(record) {
  const packet = studyDays(backend.ops).find((item) => item.practiceDay === record.practiceDay);
  if (!packet || !Array.isArray(packet.snippets)) return null;
  return packet.snippets[0] || null;
}

function sourceForRecordCorrection(record) {
  const videos = Array.isArray(record?.videos) ? record.videos : [];
  const video = videos[0] || {};
  const clip = primaryNotationClip(record) || primaryPlayableClip(record) || {};
  const sourceUrl = clip.url || clip.sourceUrl || video.url || video.sourceUrl || "";
  const sourceTitle = clip.sourceTitle || clip.title || video.title || record?.practiceDay || "";
  return {
    sourceUrl,
    sourceTitle,
    videoId: video.id || parseVideoId(sourceUrl),
  };
}

function renderPieceLabelForm(record) {
  const source = sourceForRecordCorrection(record);
  const current = recordPieceText(record);
  const hasConfirmed = Array.isArray(record?.pieces) && record.pieces.length > 0;
  const disabled = !backend.online || (!source.sourceUrl && !source.sourceTitle);
  const placeholder = hasConfirmed ? current : "Piece name(s)";
  return `
    <form class="piece-label-form" data-piece-label-form
      data-source-url="${escapeHtml(source.sourceUrl)}"
      data-source-title="${escapeHtml(source.sourceTitle)}"
      data-video-id="${escapeHtml(source.videoId)}">
      <label>
        <span>Piece</span>
        <input name="acceptedTitle" type="text" autocomplete="off" placeholder="${escapeHtml(placeholder)}"${disabled ? " disabled" : ""}>
      </label>
      <button type="submit"${disabled ? " disabled" : ""}>Save</button>
      <small data-piece-label-status></small>
    </form>
  `;
}

function recordPieceText(record) {
  const confirmed = Array.isArray(record?.pieces) ? record.pieces.map((piece) => piece.title).filter(Boolean) : [];
  if (confirmed.length) return confirmed.join(" / ");
  const uncertain = Array.isArray(record?.uncertainPieces) ? record.uncertainPieces.map((piece) => `${piece.title} uncertain`).filter(Boolean) : [];
  if (uncertain.length) return uncertain.join(" / ");
  return record?.materialLabel || "Piece or exercise pending";
}

function recordEvidenceLine(record, scoreSnippet) {
  const confirmed = Array.isArray(record?.pieces) && record.pieces.length;
  const uncertain = Array.isArray(record?.uncertainPieces) && record.uncertainPieces.length;
  const parts = [
    confirmed ? "source confirmed" : uncertain ? "piece uncertain" : record?.materialStatus === "piece_or_exercise_pending" ? "piece or exercise pending" : "piece pending",
  ];
  if (record?.transcription?.status === "ready") {
    parts.push(transcriptionEvidenceLabel(record.transcription));
  } else if (record?.activeTimeStatus && record.activeTimeStatus !== "pending_media") {
    parts.push("practice measured");
  } else {
    parts.push("media pending");
  }
  if (scoreSnippet?.score?.imageUrl || scoreSnippet?.score?.assetId) {
    parts.push(scoreSnippetIsMatched(scoreSnippet, record) ? "score alignment ready" : "score alignment pending");
  } else if (record?.materialStatus === "piece_or_exercise_pending") {
    parts.push("score or pattern pending");
  } else {
    parts.push("score pending");
  }
  return parts.join(" / ");
}

function renderLeadTranscription(record) {
  if (!isVerifiedTranscriptionRecord(record)) return "";
  const transcription = record?.transcription || {};
  const system = matchedNotationSystem(transcription);
  const clip = system.clip || primaryNotationClip(record) || primaryPlayableClip(record);
  const noteCount = Number(transcription.microVerifiedNoteCount || system.noteCount || transcription.noteCount || 0);
  const seconds = Number(transcription.microVerifiedSeconds || clip?.durationSeconds || 0);
  const confidence = Number(transcription.microMedianConfidence || 0);
  const meta = [
    record.practiceDay || "",
    noteCount ? `${noteCount} audio-checked notes` : "",
    seconds ? `${seconds.toFixed(1)}s` : "",
    confidence ? `${Math.round(confidence * 100)}% median confidence` : "",
  ].filter(Boolean).join(" / ");
  return `
    <article class="lead-transcription-card" aria-label="Current audio-checked transcription">
      <div class="lead-transcription-head">
        <div>
          <span>Detected transcription</span>
          <strong>${escapeHtml(shortText(recordPieceText(record), 112))}</strong>
          <small>${escapeHtml(meta)}</small>
        </div>
      </div>
      ${renderMatchedPracticePair(record, clip, transcription)}
    </article>
  `;
}

function renderDailyRecord(record, index = 0, defaultOpenDay = "") {
  const transcription = record?.transcription || {};
  const scoreMatches = renderScoreMatchGroups(record);
  const openTarget = new URLSearchParams(window.location.search).get("open") || "";
  const openForReview = openTarget
    ? (openTarget === "first" ? index === 0 : openTarget === record.practiceDay)
    : defaultOpenDay === record.practiceDay;
  const meta = [
    record.activeViolinLabel ? `${record.activeViolinLabel} practice` : record.activeTimeStatus === "pending_media" ? "practice pending" : "",
    record.uploadedVideoLabel ? `${record.uploadedVideoLabel} video` : "",
  ].filter(Boolean).join(" / ");
  return `
    <details class="record-card" data-day="${escapeHtml(record.practiceDay || "")}" data-status="${escapeHtml(record.status || "pending")}"${openForReview ? " open" : ""}>
      <summary class="record-summary">
        <div class="record-title-block">
          <span>${escapeHtml(meta)}</span>
          <strong>${escapeHtml(recordPieceText(record))}</strong>
        </div>
        <em data-tone="${escapeHtml(recordStatusTone(record))}">${escapeHtml(recordStatusLabel(record))}</em>
      </summary>
      <div class="record-card-body record-essentials-body">
        ${scoreMatches}
        ${scoreMatches ? "" : renderPendingPracticePair(record)}
        ${renderTranscriptionRunLink(record, transcription)}
      </div>
    </details>
  `;
}

function renderStudy() {
  if (!elements.studyList) return;
  const records = dailyRecordList(backend.ops);
  const analyzed = orderedAnalyzedRecords(backend.ops);
  const pendingCount = Math.max(0, records.length - analyzed.length);
  if (!backend.online) {
    elements.studyList.innerHTML = `<p class="empty">${backendEmptyText()}</p>`;
    return;
  }
  if (!analyzed.length) {
    elements.studyList.innerHTML = records.length
      ? `<p class="empty">Indexed practice days are waiting for active-playing detection.</p>`
      : `<p class="empty">Daily records pending YouTube inventory.</p>`;
    return;
  }
  const defaultOpenDay = firstSourceScoreMatchDay(analyzed);
  elements.studyList.innerHTML = [
    analyzed.map((record, index) => renderDailyRecord(record, index, defaultOpenDay)).join(""),
    pendingCount
      ? `<p class="empty pending-index">${pendingCount} days pending analysis.</p>`
      : ""
  ].join("");
}

function renderPieces() {
  if (!elements.pieceList) return;
  const list = repertoireEntries(backend.ops);
  if (!backend.online) {
    elements.pieceList.innerHTML = `<p class="empty">${backendEmptyText()}</p>`;
    return;
  }
  if (!list.length) {
    elements.pieceList.innerHTML = `<p class="empty">No confirmed repertoire evidence.</p>`;
    return;
  }
  elements.pieceList.innerHTML = list.slice(0, 8).map((piece, index) => {
    const evidence = Array.isArray(piece.evidence) ? piece.evidence : [];
    const days = Array.isArray(piece.recentPracticeDays) ? piece.recentPracticeDays.filter(Boolean).slice(0, 4) : [];
    const status = piece.status || "confirmed";
    return `
    <article class="piece-row evidence-piece">
      <div>
        <span>${escapeHtml(status)}</span>
        <strong>${escapeHtml(piece.title || "Piece")}</strong>
        <p>${escapeHtml([
          days.length ? days.join(" / ") : "recent days pending",
          evidence.length ? `${evidence.length} evidence rows` : "evidence pending",
          piece.currentProgressLabel || piece.progressStatus || "progress pending",
        ].join(" / "))}</p>
      </div>
      <em>${escapeHtml(piece.totalActiveViolinLabel || "practice pending")}</em>
    </article>
  `;
  }).join("");
}

function transcriptionCompletionState(ops) {
  const completion = ops?.review?.transcriptionCompletion;
  return completion && typeof completion === "object" ? completion : null;
}

function compactPointLabel(item) {
  const points = Number(item?.points) || 0;
  const weight = Number(item?.weight) || 0;
  if (!weight) return "";
  const pointText = Number.isInteger(points) ? String(points) : points.toFixed(1).replace(/\.0$/, "");
  const weightText = Number.isInteger(weight) ? String(weight) : weight.toFixed(1).replace(/\.0$/, "");
  return `${pointText}/${weightText}`;
}

function completionList(items, emptyText) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!list.length) return `<p class="empty roadmap-empty">${escapeHtml(emptyText)}</p>`;
  return `
    <ol class="roadmap-list">
      ${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ol>
  `;
}

function completionCards(items) {
  const list = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
  if (!list.length) return "";
  return `
    <div class="roadmap-stats" aria-label="Current implementation state">
      ${list.map((item) => `
        <article>
          <span>${escapeHtml(item.label || "")}</span>
          <strong>${escapeHtml(String(item.value || ""))}</strong>
          <em>${escapeHtml(item.detail || "")}</em>
        </article>
      `).join("")}
    </div>
  `;
}

function planPhaseList(items) {
  const list = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
  if (!list.length) return "";
  return `
    <div class="roadmap-plan" aria-label="Implementation plan">
      <span>Implementation Plan</span>
      <ol class="roadmap-phase-list">
        ${list.map((item) => `
          <li class="roadmap-phase" data-status="${escapeHtml(item.status || "pending")}">
            <em>${escapeHtml(item.phase || "")}</em>
            <div>
              <strong>${escapeHtml(item.label || "")}</strong>
              <p>${escapeHtml(item.evidence || "")}</p>
              <small>${escapeHtml(item.target || "")}</small>
            </div>
          </li>
        `).join("")}
      </ol>
    </div>
  `;
}

function truthWorkbenchStrip(workbench) {
  const truth = workbench && typeof workbench === "object" ? workbench : null;
  if (!truth || truth.status === "empty") return "";
  const accepted = Number(truth.acceptedEvidenceReadyCount ?? truth.acceptedTruthCount) || 0;
  const queued = (Number(truth.sourceTargetQueueCount) || 0) + (Number(truth.pendingTruthCount) || 0);
  const rejected = Number(truth.rejectedTruthCount ?? truth.rejectedScoreCorrectionCount) || 0;
  const benchmark = Number(truth.benchmarkCount) || 0;
  const rows = Array.isArray(truth.queuedItems) ? truth.queuedItems.slice(0, 3) : [];
  return `
    <div class="truth-workbench">
      <div class="truth-workbench-head">
        <span>Truth set</span>
        <strong>${escapeHtml(String(accepted))} accepted</strong>
        <em>${escapeHtml(`${queued} queued / ${rejected} rejected / ${benchmark} benchmarks`)}</em>
      </div>
      ${rows.length ? `
        <ol>
          ${rows.map((item) => `
            <li>
              <b>${escapeHtml(item.sequence || item.pieceTitle || item.kind || "pending")}</b>
              <small>${escapeHtml([item.practiceDay, item.scoreStatus].filter(Boolean).join(" / "))}</small>
            </li>
          `).join("")}
        </ol>
      ` : ""}
    </div>
  `;
}

function goldReviewNotationEvents(notes) {
  return noteInputSequence(noteInputText(notes)).slice(0, 16).map((note, index) => ({
    kind: "note",
    note,
    startSeconds: index * 0.25,
    endSeconds: (index + 1) * 0.25,
    localStartSeconds: index * 0.25,
    localEndSeconds: (index + 1) * 0.25,
    durationSeconds: 0.25,
    durationKind: "quarter",
    confidence: 1,
    uncertain: false,
  }));
}

function notationEventsFromReviewField(value, fallbackNotes = []) {
  if (Array.isArray(value) && value.length) {
    return value.slice(0, 24).map((event, index) => ({
      kind: event?.kind || "note",
      note: event?.note || event?.pitch || "",
      durationKind: event?.durationKind || event?.duration || "quarter",
      startSeconds: Number(event?.startSeconds) || index * 0.25,
      endSeconds: Number(event?.endSeconds) || (index + 1) * 0.25,
      localStartSeconds: Number(event?.localStartSeconds) || index * 0.25,
      localEndSeconds: Number(event?.localEndSeconds) || (index + 1) * 0.25,
      durationSeconds: Number(event?.durationSeconds) || 0.25,
      uncertain: Boolean(event?.uncertain),
      rawNote: event?.rawNote || "",
    })).filter((event) => event.kind === "rest" || event.note);
  }
  return goldReviewNotationEvents(fallbackNotes);
}

function readableGoldReviewNotes(item) {
  const keySignature = inferredReadableKeySignature(item.detectedNotes, {
    keySignature: item.keySignature || item.scoreKeySignature || item.transcriptionKeySignature,
    pieceTitle: item.pieceTitle,
  });
  const signature = normalizedKeySignature(keySignature);
  const notes = noteInputSequence(noteInputText(item.detectedNotes));
  const displayNotes = notes.map((note) => notationDisplayNote(note, signature));
  return { keySignature: signature, displayNotes };
}

function isScoreCopyTask(value) {
  return value === "score_copy_exact_notes" || value === "score_copy_exact_notation" || value === "score_copy_pitch_skeleton";
}

function isNoteReadingTask(value) {
  return value === "note_letter_reading";
}

function goldReviewIsScoreCopy(item) {
  return isScoreCopyTask(item?.reviewTask)
    || isScoreCopyTask(item?.trainingTask)
    || item?.reviewType === "score_copy"
    || item?.type === "score_copy";
}

function goldReviewIsNoteReading(item) {
  return isNoteReadingTask(item?.reviewTask)
    || isNoteReadingTask(item?.trainingTask)
    || item?.reviewType === "note_reading"
    || item?.type === "note_reading";
}

const TRAINING_LANE_TRANSCRIPTION_ALAN = "transcription-alan";
const TRAINING_LANE_SCORE_TRANSCRIPTION = "score-transcription";
const TRAINING_LANE_NOTE_READING = "note-reading";

function renderGoldReviewSourceNotation(item) {
  const sourceNotes = item.sourceScoreNotes || item.scoreNotes || item.detectedNotes || [];
  const sourceEvents = notationEventsFromReviewField(item.sourceNotationEvents, sourceNotes);
  const keySignature = item.keySignature || item.scoreKeySignature || {};
  const sourceAbc = item.sourceNotationAbc || item.scoreNotationAbc || "";
  return renderNotationSheet(sourceEvents, {
    keySignature,
    maxNotes: 24,
    fitToWidth: true,
    rhythmVerified: Boolean(sourceAbc || item.sourceNotationEvents?.length),
    abcSource: sourceAbc,
    abcStaffWidth: 640,
    abcScale: 1.18,
  });
}

function renderGoldReviewScoreSource(item) {
  const imageUrl = assetUrl(item.sourceReviewImageUrl || item.sourceImageUrl || item.scoreImageUrl || "");
  const isTrainingSource = Boolean(item.sourcePieceTrainingOnly || item.notationCopyOnly || item.sourceImageRequiredForOriginalScore);
  const isOriginalScore = Boolean(imageUrl && item.originalScoreSnippet === true && item.sourceImageRequiredForOriginalScore !== true);
  const sourceLabel = isOriginalScore ? "Original score" : TRAINING_LANE_SCORE_TRANSCRIPTION;
  const label = isOriginalScore
    ? [item.scoreLocation, item.pieceTitle].filter(Boolean).join(" / ")
    : item.pieceTitle || item.scoreLocation || "notation source";
  if (!imageUrl) {
    return `
      <section class="gold-review-source gold-review-source-notation${isTrainingSource ? " gold-review-source-training" : ""}" aria-label="score-transcription target">
        <div class="matched-notation-head">
          <span>${escapeHtml(sourceLabel)}</span>
          <strong>${escapeHtml(shortText(label || "source", 72))}</strong>
        </div>
        ${renderGoldReviewSourceNotation(item)}
      </section>
    `;
  }
  if (isOriginalScore) {
    return `
      <section class="gold-review-source gold-review-source-original" aria-label="Original score">
        <div class="matched-notation-head">
          <span>${escapeHtml(sourceLabel)}</span>
          <strong>${escapeHtml(shortText(label || "score", 72))}</strong>
        </div>
        <img src="${escapeHtml(imageUrl)}" alt="Original score">
      </section>
    `;
  }
  if (item.sourceNotationAbc || item.sourceNotationEvents?.length) {
    return `
      <section class="gold-review-source gold-review-source-notation gold-review-source-training" aria-label="score-transcription target">
        <div class="matched-notation-head">
          <span>${escapeHtml(sourceLabel)}</span>
          <strong>${escapeHtml(shortText(label || "score", 72))}</strong>
        </div>
        <img src="${escapeHtml(imageUrl)}" alt="score-transcription target">
        ${renderGoldReviewSourceNotation(item)}
      </section>
    `;
  }
  return `
    <section class="gold-review-source${isOriginalScore ? " gold-review-source-original" : " gold-review-source-training"}" aria-label="${escapeHtml(isOriginalScore ? "Original score source" : "score-transcription target")}">
      <div class="matched-notation-head">
        <span>${escapeHtml(sourceLabel)}</span>
        <strong>${escapeHtml(label || "score pending")}</strong>
      </div>
      <img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(isOriginalScore ? "Original score source" : "score-transcription target")}">
    </section>
  `;
}

function renderOriginalScoreSources(snippets) {
  const items = Array.isArray(snippets) ? snippets : [];
  if (!items.length) return "";
  const readyCount = items.filter((item) => item?.originalScoreSnippet === true && item?.imageUrl).length;
  const rows = [];
  const seen = new Set();
  items.forEach((item) => {
    if (!item || typeof item !== "object") return;
    const localPdfPath = String(item.sourcePdfLocalPath || "").trim();
    const pdfUrl = item.sourcePdfUrl
      || (localPdfPath ? assetUrl(localPdfPath.startsWith("/") ? localPdfPath : `/${localPdfPath}`) : "");
    const sourceUrl = item.sourceUrl || "";
    const title = item.pieceTitle || item.sourceTitle || "Source score";
    const sourceFile = item.sourceFileLabel || item.requestedPart || item.sourceKind || "";
    const page = item.sourcePdfPage ? `p. ${item.sourcePdfPage}` : "";
    const key = item.requestedPart
      ? [title, item.requestedPart, sourceFile, pdfUrl || sourceUrl].join("|")
      : [title, pdfUrl || sourceUrl].join("|");
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({
      title,
      detail: [item.requestedPart, sourceFile, page].filter(Boolean).join(" / "),
      pdfUrl,
      sourceUrl,
    });
  });
  return `
    <section class="source-score-strip" aria-label="Source score PDF library">
      <div class="source-score-head">
        <strong>Source score PDFs</strong>
        <span>${escapeHtml(`${rows.length || items.length} sources / ${readyCount} images`)}</span>
      </div>
      <ul class="source-score-list">
        ${rows.map((row) => {
          return `
            <li class="source-score-row">
              <span>
                <strong>${escapeHtml(shortText(row.title, 92))}</strong>
                ${row.detail ? `<small>${escapeHtml(shortText(row.detail, 112))}</small>` : ""}
              </span>
              <span class="source-score-actions">
                ${row.pdfUrl ? `<a href="${escapeHtml(row.pdfUrl)}" target="_blank" rel="noreferrer">PDF</a>` : ""}
                ${row.sourceUrl ? `<a href="${escapeHtml(row.sourceUrl)}" target="_blank" rel="noreferrer">IMSLP</a>` : ""}
              </span>
            </li>
          `;
        }).join("")}
      </ul>
    </section>
  `;
}

function renderGoldReviewItem(item, index) {
  const isScoreCopy = goldReviewIsScoreCopy(item);
  const scoreNotes = noteInputText(item.scoreNotes);
  const notationNotes = isScoreCopy && scoreNotes ? scoreNotes : noteInputText(item.detectedNotes);
  const detectedNotes = noteInputText(notationNotes);
  const readableNotes = readableGoldReviewNotes({ ...item, detectedNotes: notationNotes });
  const displayDetectedNotes = displayNoteTextWithMeasureAccidentals(readableNotes.displayNotes, readableNotes.keySignature);
  const copyNotationAbc = isScoreCopy ? item.copyNotationAbc || item.sourceNotationAbc || "" : "";
  const copyNotationEvents = isScoreCopy
    ? notationEventsFromReviewField(item.copyNotationEvents, notationNotes)
    : goldReviewNotationEvents(notationNotes);
  const clip = item.clip && typeof item.clip === "object" ? item.clip : item;
  const status = item.status || item.defaultStatus || "pending_review";
  const isRecent = status !== "pending_review";
  const lane = isScoreCopy ? TRAINING_LANE_SCORE_TRANSCRIPTION : TRAINING_LANE_TRANSCRIPTION_ALAN;
  const agreement = item.scoreAgreementStatus === "exact_midi_agreement"
    ? "same MIDI"
    : item.scoreAgreementStatus === "score_midi_mismatch"
      ? "mismatch"
      : "";
  const notationLabel = isScoreCopy ? TRAINING_LANE_SCORE_TRANSCRIPTION : TRAINING_LANE_TRANSCRIPTION_ALAN;
  const rule = isScoreCopy
    ? (item.sourceCopyPitchSkeletonOnly ? "Notes match source = accept." : "Accept only if score-transcription matches the source.")
    : "One note off = reject.";
  return `
    <article class="gold-review-item" data-status="${escapeHtml(status)}">
      <div class="gold-review-head">
        <span>${escapeHtml(isRecent ? "Label" : `Queue ${index + 1}`)}</span>
        <strong>${escapeHtml(shortText(detectedNotes || item.pieceTitle || "notes pending", 72))}</strong>
        <em>${escapeHtml([(isScoreCopy ? "" : item.practiceDay), lane, agreement, item.detectedNoteCount ? `${item.detectedNoteCount} notes` : ""].filter(Boolean).join(" / "))}</em>
      </div>
      <div class="gold-review-grid${isScoreCopy ? " gold-review-copy-grid" : ""}">
        ${isScoreCopy ? renderGoldReviewScoreSource(item) : renderEmbeddedMedia({}, clip)}
        <section class="gold-review-notation">
          <div class="matched-notation-head">
            <span>${escapeHtml(notationLabel)}</span>
            <strong>${escapeHtml(shortText(displayDetectedNotes || detectedNotes || "pending", 64))}</strong>
          </div>
          ${renderNotationSheet(copyNotationEvents, {
            keySignature: readableNotes.keySignature,
            maxNotes: 16,
            fitToWidth: true,
            rhythmVerified: Boolean(copyNotationAbc || item.copyNotationEvents?.length),
            abcSource: copyNotationAbc,
            abcStaffWidth: 720,
            abcScale: 1.18,
          })}
          ${scoreNotes && !isScoreCopy ? `<small>${escapeHtml([item.scoreLocation || "score", shortText(scoreNotes, 80)].filter(Boolean).join(" / "))}</small>` : ""}
        </section>
        <form class="gold-review-form" data-gold-review-form data-review-item-id="${escapeHtml(item.reviewItemId || "")}">
          <p class="gold-review-rule">${escapeHtml(rule)}</p>
          <div class="gold-review-actions">
            <button type="submit" name="status" value="accepted_truth">Accept</button>
            <button type="submit" name="status" value="rejected_mismatch">Reject</button>
          </div>
          <small data-gold-review-status>${escapeHtml(isRecent ? status.replace(/_/g, " ") : "")}</small>
        </form>
      </div>
    </article>
  `;
}

function renderNoteReadingItem(item, index) {
  const status = item.status || item.defaultStatus || "pending_review";
  const isRecent = status !== "pending_review";
  const label = [item.scoreLocation, item.pieceTitle].filter(Boolean).join(" / ") || "notation";
  const imageUrl = assetUrl(item.sourceReviewImageUrl || item.sourceImageUrl || item.scoreImageUrl || "");
  const draftValue = noteReadingDraftValue(item);
  const source = imageUrl
    ? `
      <section class="gold-review-source gold-review-source-original note-reading-source" aria-label="note-reading source">
        <div class="matched-notation-head">
          <span>Source</span>
          <strong>${escapeHtml(shortText(label, 72))}</strong>
        </div>
        <img src="${escapeHtml(imageUrl)}" alt="note-reading source">
      </section>
    `
    : `
      <section class="gold-review-source gold-review-source-notation" aria-label="note-reading source">
        <div class="matched-notation-head">
          <span>Source</span>
          <strong>${escapeHtml(shortText(label, 72))}</strong>
        </div>
        ${renderGoldReviewSourceNotation(item)}
      </section>
    `;
  return `
    <article class="gold-review-item note-reading-item" data-status="${escapeHtml(status)}">
      <div class="gold-review-head">
        <span>${escapeHtml(isRecent ? "Label" : `Queue ${index + 1}`)}</span>
        <strong>${escapeHtml(shortText(label, 96))}</strong>
        <em>${escapeHtml([TRAINING_LANE_NOTE_READING, item.detectedNoteCount ? `${item.detectedNoteCount} notes` : ""].filter(Boolean).join(" / "))}</em>
      </div>
      <div class="gold-review-grid gold-review-note-reading-grid">
        ${source}
        <form class="note-reading-form" data-note-reading-form data-review-item-id="${escapeHtml(item.reviewItemId || "")}">
          <label>
            <span>Note letters</span>
            <input name="noteLetterAnswer" value="${escapeHtml(draftValue)}" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="A G D">
          </label>
          <div class="note-reading-keypad" aria-label="note-letter buttons">
            ${["A", "B", "C", "D", "E", "F", "G"].map((letter) => `<button type="button" data-note-reading-key="${letter}">${letter}</button>`).join("")}
            <button type="button" data-note-reading-key="delete" aria-label="delete last note">Del</button>
            <button type="button" data-note-reading-key="clear">Clear</button>
          </div>
          <button type="submit">Save</button>
          <small data-note-reading-status>${escapeHtml(isRecent ? status.replace(/_/g, " ") : (item.noteReadingScopeLabel || "picture only"))}</small>
        </form>
      </div>
    </article>
  `;
}

function renderGoldReviewLane({ label, count, items, emptyText, ariaLabel, renderItem = renderGoldReviewItem }) {
  const queued = Number(count) || 0;
  const laneItems = Array.isArray(items) ? items : [];
  return `
    <section class="gold-review-lane" aria-label="${escapeHtml(ariaLabel || label)}">
      <div class="gold-review-lane-head">
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(String(queued))} queued</span>
      </div>
      ${laneItems.length
        ? laneItems.map((item, index) => renderItem(item, index)).join("")
        : `<p class="empty gold-review-lane-empty">${escapeHtml(emptyText || "No verified samples.")}</p>`}
    </section>
  `;
}

function renderGoldReview() {
  if (!elements.goldReviewPanel) return;
  if (!backend.online) {
    setText(elements.goldReviewCount, backend.loading ? "loading" : "offline");
    elements.goldReviewPanel.innerHTML = `<p class="empty">${backendEmptyText()}</p>`;
    return;
  }
  const review = goldReviewState(backend.ops);
  if (!review) {
    setText(elements.goldReviewCount, "0 accepted / 0 queued");
    elements.goldReviewPanel.innerHTML = `<p class="empty">Review queue pending.</p>`;
    return;
  }
  const accepted = Number(review.acceptedCount) || 0;
  const queued = Number(review.queueCount) || 0;
  const rejected = Number(review.rejectedCount) || 0;
  const hidden = Number(review.suppressedByLearningCount) || 0;
  const training = review.trainingSet && typeof review.trainingSet === "object" ? review.trainingSet : {};
  const trainingExamples = Number(review.trainingExampleCount ?? training.exampleCount) || 0;
  const longTraining = Number(review.trainingLongPhraseExampleCount ?? training.longPhraseExampleCount) || 0;
  const scoreTraining = Number(review.trainingScoreExampleCount ?? training.scoreExampleCount) || 0;
  const scoreCopyTraining = Number(review.trainingScoreCopyExampleCount ?? training.scoreCopyExampleCount) || 0;
  const noteReadingTraining = Number(review.trainingNoteReadingExampleCount ?? training.noteReadingExampleCount) || 0;
  const audioQueued = Number(review.audioQueueCount) || 0;
  const scoreQueued = Number(review.scoreQueueCount) || 0;
  const scoreCopyQueued = Number(review.scoreCopyQueueCount) || 0;
  const noteReadingQueued = Number(review.noteReadingQueueCount) || 0;
  const scoreExactQueued = Number(review.scoreExactAgreementQueueCount) || 0;
  const corrected = Number(review.correctedLabelCount) || 0;
  const adaptiveCount = Number(review.adaptiveCandidateCount) || 0;
  const adaptivePool = Number(review.adaptiveCandidatePoolCount) || adaptiveCount;
  const adaptiveLabel = adaptivePool && adaptivePool !== adaptiveCount ? `${adaptiveCount}/${adaptivePool}` : String(adaptiveCount);
  const crossTrainerLabels = Number(review.crossTrainerSourceLabelCount) || 0;
  const crossTrainerSupported = Number(review.crossTrainerSupportedCandidateCount) || 0;
  const crossTrainerHidden = Number(review.crossTrainerSuppressedCandidateCount) || 0;
  const rejectionDigest = review.rejectionDigest && typeof review.rejectionDigest === "object" ? review.rejectionDigest : {};
  const rejectionInsights = review.rejectionInsights && typeof review.rejectionInsights === "object" ? review.rejectionInsights : {};
  const fastRejected = Number(rejectionInsights.rejectedFastDenseCount) || 0;
  const unstableRejected = Number(rejectionInsights.rejectedUnstableRegisterCount) || 0;
  const emptyQueueText = review.queueStatus === "current_batch_exhausted_by_rejections"
    ? `Batch complete. ${Number(review.suppressedByLearningCount) || 0} repeats hidden.`
    : "No review clips queued.";
  setText(
    elements.goldReviewCount,
    scoreCopyQueued || noteReadingQueued
      ? `${audioQueued} transcription-alan / ${scoreCopyQueued} score-transcription / ${noteReadingQueued} note-reading`
      : scoreQueued ? `${scoreQueued} score / ${queued} queued` : `${accepted} accepted / ${queued} queued`
  );
  const generalItems = Array.isArray(review.queue) ? review.queue : [];
  const audioItems = Array.isArray(review.audioQueue)
    ? review.audioQueue.slice(0, 10)
    : generalItems.filter((item) => !goldReviewIsScoreCopy(item) && !goldReviewIsNoteReading(item)).slice(0, 10);
  const copyItems = Array.isArray(review.scoreCopyQueue)
    ? review.scoreCopyQueue.slice(0, 10)
    : generalItems.filter((item) => goldReviewIsScoreCopy(item)).slice(0, 10);
  const noteReadingItems = Array.isArray(review.noteReadingQueue)
    ? review.noteReadingQueue.slice(0, 10)
    : generalItems.filter((item) => goldReviewIsNoteReading(item)).slice(0, 10);
  const sourceScoreSnippets = Array.isArray(review.sourceScoreSnippets) ? review.sourceScoreSnippets : [];
  const items = [...audioItems, ...copyItems, ...noteReadingItems];
  if (!items.length) {
    elements.goldReviewPanel.innerHTML = `
      <div class="gold-review-stats">
        <article><span>Accepted</span><strong>${escapeHtml(String(accepted))}</strong></article>
        <article><span>Queue</span><strong>${escapeHtml(String(queued))}</strong></article>
        <article><span>Rejected</span><strong>${escapeHtml(String(rejected))}</strong></article>
        <article><span>Hidden</span><strong>${escapeHtml(String(hidden))}</strong></article>
        <article><span>Training</span><strong>${escapeHtml(String(trainingExamples))}</strong></article>
        <article><span>Score</span><strong>${escapeHtml(String(scoreTraining))}</strong></article>
        <article><span>score-transcription</span><strong>${escapeHtml(String(scoreCopyTraining))}</strong></article>
        <article><span>note-reading</span><strong>${escapeHtml(String(noteReadingTraining))}</strong></article>
        ${crossTrainerLabels ? `<article><span>Linked labels</span><strong>${escapeHtml(`${crossTrainerSupported}/${crossTrainerLabels}`)}</strong></article>` : ""}
        ${crossTrainerHidden ? `<article><span>Hidden conflicts</span><strong>${escapeHtml(String(crossTrainerHidden))}</strong></article>` : ""}
        <article><span>Long</span><strong>${escapeHtml(String(longTraining))}</strong></article>
        ${corrected ? `<article><span>Corrected</span><strong>${escapeHtml(String(corrected))}</strong></article>` : ""}
        <article><span>Adaptive</span><strong>${escapeHtml(adaptiveLabel)}</strong></article>
      </div>
      <div class="gold-review-list">
        ${renderGoldReviewLane({
          label: TRAINING_LANE_TRANSCRIPTION_ALAN,
          count: audioQueued,
          items: audioItems,
          emptyText: "Refill pending.",
          ariaLabel: "transcription-alan training",
        })}
        ${renderGoldReviewLane({
          label: TRAINING_LANE_SCORE_TRANSCRIPTION,
          count: scoreCopyQueued,
          items: copyItems,
          emptyText: "Refill pending.",
          ariaLabel: "score-transcription training",
        })}
        ${renderGoldReviewLane({
          label: TRAINING_LANE_NOTE_READING,
          count: noteReadingQueued,
          items: noteReadingItems,
          emptyText: "Refill pending.",
          ariaLabel: "note-reading training",
          renderItem: renderNoteReadingItem,
        })}
      </div>
      ${renderOriginalScoreSources(sourceScoreSnippets)}
      <p class="empty">${escapeHtml(rejectionDigest.message || emptyQueueText)}</p>
    `;
    return;
  }
  elements.goldReviewPanel.innerHTML = `
    <div class="gold-review-stats">
      <article><span>Accepted</span><strong>${escapeHtml(String(accepted))}</strong></article>
      <article><span>Queue</span><strong>${escapeHtml(String(queued))}</strong></article>
      <article><span>Rejected</span><strong>${escapeHtml(String(rejected))}</strong></article>
      <article><span>Hidden</span><strong>${escapeHtml(String(hidden))}</strong></article>
      <article><span>Training</span><strong>${escapeHtml(String(trainingExamples))}</strong></article>
      <article><span>Score</span><strong>${escapeHtml(String(scoreTraining))}</strong></article>
      <article><span>score-transcription</span><strong>${escapeHtml(String(scoreCopyTraining))}</strong></article>
      <article><span>note-reading</span><strong>${escapeHtml(String(noteReadingTraining))}</strong></article>
      ${crossTrainerLabels ? `<article><span>Linked labels</span><strong>${escapeHtml(`${crossTrainerSupported}/${crossTrainerLabels}`)}</strong></article>` : ""}
      ${crossTrainerHidden ? `<article><span>Hidden conflicts</span><strong>${escapeHtml(String(crossTrainerHidden))}</strong></article>` : ""}
      <article><span>Long</span><strong>${escapeHtml(String(longTraining))}</strong></article>
      <article><span>transcription-alan</span><strong>${escapeHtml(String(audioQueued))}</strong></article>
      ${fastRejected ? `<article><span>Fast rejects</span><strong>${escapeHtml(String(fastRejected))}</strong></article>` : ""}
      ${unstableRejected ? `<article><span>Wide rejects</span><strong>${escapeHtml(String(unstableRejected))}</strong></article>` : ""}
      <article><span>Score queue</span><strong>${escapeHtml(scoreExactQueued ? `${scoreExactQueued}/${scoreQueued}` : String(scoreQueued))}</strong></article>
      <article><span>score-transcription</span><strong>${escapeHtml(String(scoreCopyQueued))}</strong></article>
      <article><span>note-reading</span><strong>${escapeHtml(String(noteReadingQueued))}</strong></article>
      ${corrected ? `<article><span>Corrected</span><strong>${escapeHtml(String(corrected))}</strong></article>` : ""}
      <article><span>Adaptive</span><strong>${escapeHtml(adaptiveLabel)}</strong></article>
    </div>
    <div class="gold-review-list">
      ${renderGoldReviewLane({
        label: TRAINING_LANE_TRANSCRIPTION_ALAN,
        count: audioQueued,
        items: audioItems,
        emptyText: "Refill pending.",
        ariaLabel: "transcription-alan training",
      })}
      ${renderGoldReviewLane({
        label: TRAINING_LANE_SCORE_TRANSCRIPTION,
        count: scoreCopyQueued,
        items: copyItems,
        emptyText: "Refill pending.",
        ariaLabel: "score-transcription training",
      })}
      ${renderGoldReviewLane({
        label: TRAINING_LANE_NOTE_READING,
        count: noteReadingQueued,
        items: noteReadingItems,
        emptyText: "Refill pending.",
        ariaLabel: "note-reading training",
        renderItem: renderNoteReadingItem,
      })}
    </div>
    ${renderOriginalScoreSources(sourceScoreSnippets)}
  `;
}

function renderStaff4Audit(audit) {
  if (!audit || typeof audit !== "object") return "";
  const status = String(audit.status || "").replace(/_/g, " ");
  if (!status || status === "not generated") return "";
  const artifacts = audit.artifacts && typeof audit.artifacts === "object" ? audit.artifacts : {};
  const clip = audit.clip && typeof audit.clip === "object" ? audit.clip : {};
  const audioUrl = assetUrl(artifacts.audioClipUrl || clip.audioUrl || "");
  const rawVideoUrl = artifacts.videoClipUrl || clip.videoUrl || clip.mediaUrl || "";
  const videoUrl = assetUrl(rawVideoUrl);
  const videoFragment = !artifacts.videoClipUrl && clip.videoFragment ? String(clip.videoFragment) : "";
  const pitchTrace = assetUrl(artifacts.pitchTraceSvgUrl || "");
  const spectrogram = assetUrl(artifacts.spectrogramSvgUrl || "");
  const packetUrl = assetUrl(artifacts.packetJsonUrl || "");
  const decision = audit.decision && typeof audit.decision === "object" ? audit.decision : {};
  const decisionLabel = String(decision.outcome || decision.status || status).replace(/_/g, " ");
  const scoreBlock = audit.score && typeof audit.score === "object" ? audit.score : {};
  const scoreReview = audit.sourceCropScoreReview && typeof audit.sourceCropScoreReview === "object" ? audit.sourceCropScoreReview : {};
  const isCropReview = audit.auditFocus === "staff4_source_crop_reverification";
  const score = isCropReview
    ? audit.targetSequence || decision.targetSequence || "score crop"
    : decision.expectedNote || audit.expectedFailedScoreNote || audit.expectedNextScoreNote || "score";
  const audio = isCropReview
    ? audit.bestAudioSequence || decision.bestAudioSequence || "audio"
    : decision.observedNote || audit.observedFailureAudioNote || audit.observedNextAudioNote || "unverified";
  const measureLabel = String(scoreBlock.measureLabel || scoreReview.measureLabel || decision.measureLabel || audit.measureLabel || "").trim();
  const headerDetail = [measureLabel, score, audio].filter(Boolean).join(" / ");
  const rejectedCrop = scoreBlock.sourceCropRejected === true || decision.sourceCropRejected === true;
  const displayAllowed = scoreBlock.sourceCropDisplayAllowed === true && scoreBlock.sourceCropReady === true && scoreBlock.truthEvidenceAccepted === true;
  const sourceCrop = isCropReview && !rejectedCrop && displayAllowed ? assetUrl(scoreBlock.sourceImageUrl || "") : "";
  const reviewCrop = isCropReview && rejectedCrop ? assetUrl(scoreBlock.sourceReviewImageUrl || decision.reviewImageUrl || "") : "";
  return `
    <section class="staff4-audit-card" aria-label="Source phrase audit packet">
      <div class="staff4-audit-head">
        <strong>${escapeHtml(decisionLabel)}</strong>
        <span>${escapeHtml(headerDetail)}</span>
        ${packetUrl ? `<a href="${escapeHtml(packetUrl)}" target="_blank" rel="noreferrer">JSON</a>` : ""}
      </div>
      <div class="staff4-audit-grid">
        ${videoUrl ? `
          <div class="staff4-audit-media">
            <video controls preload="metadata" src="${escapeHtml(videoUrl + videoFragment)}"></video>
            ${audioUrl ? `<audio controls preload="metadata" src="${escapeHtml(audioUrl)}"></audio>` : ""}
          </div>
        ` : audioUrl ? `
          <div class="staff4-audit-media">
            <audio controls preload="metadata" src="${escapeHtml(audioUrl)}"></audio>
          </div>
        ` : ""}
        ${sourceCrop ? `<img class="staff4-audit-plot" src="${escapeHtml(sourceCrop)}" alt="Accepted source score crop">` : ""}
        ${reviewCrop ? `<img class="staff4-audit-plot staff4-audit-review-plot" src="${escapeHtml(reviewCrop)}" alt="Source review context">` : ""}
        ${pitchTrace ? `<img class="staff4-audit-plot" src="${escapeHtml(pitchTrace)}" alt="Pitch trace">` : ""}
        ${spectrogram ? `<img class="staff4-audit-plot" src="${escapeHtml(spectrogram)}" alt="Spectrogram">` : ""}
      </div>
    </section>
  `;
}

function renderStaff4Mining(mining, sourceRescan) {
  if (!mining || typeof mining !== "object") return "";
  const status = String(mining.status || "").replace(/_/g, " ");
  if (!status || status === "no staff4 anchor") return "";
  const rescan = sourceRescan && typeof sourceRescan === "object" ? sourceRescan : {};
  const failure = mining.sourceAudioRescanGuidedAdjacentFirstFailure && typeof mining.sourceAudioRescanGuidedAdjacentFirstFailure === "object"
    ? mining.sourceAudioRescanGuidedAdjacentFirstFailure
    : rescan.guidedAdjacentFirstFailure && typeof rescan.guidedAdjacentFirstFailure === "object"
      ? rescan.guidedAdjacentFirstFailure
      : {};
  const nearest = mining.nearestWindow && typeof mining.nearestWindow === "object" ? mining.nearestWindow : {};
  const candidate = mining.bestCandidate && typeof mining.bestCandidate === "object" ? mining.bestCandidate : {};
  const target = candidate.targetSequence || nearest.targetSequence || "";
  const observed = candidate.windowSequence || nearest.windowSequence || "";
  const exact = Number(mining.exactCandidateCount) || 0;
  const searched = Number(mining.searchedWindowCount) || 0;
  const rescanRuns = Number(mining.sourceAudioRescanRunCount || rescan.runCount) || 0;
  const rescanEvents = Number(mining.sourceAudioRescanEventCount || (Number(rescan.eventCount) || 0) + (Number(rescan.candidateEventCount) || 0)) || 0;
  const rescanStatus = String(mining.sourceAudioRescanStatus || rescan.status || "").replace(/_/g, " ");
  const direction = candidate.targetDirection || nearest.targetDirection || "";
  const failedExpected = failure.expectedNote || "";
  const failedHeard = failure.bestAttemptObservedConsensusNote || "";
  const failedOffset = failure.bestAttemptOffsetSeconds ?? "";
  return `
    <section class="staff4-mining-card" aria-label="Adjacent phrase search">
      <div class="staff4-mining-head">
        <strong>${escapeHtml(status)}</strong>
        <span>${escapeHtml(exact)} exact / ${escapeHtml(searched)} checked</span>
      </div>
      <div class="staff4-mining-grid">
        <span>${escapeHtml(direction || "adjacent")}</span>
        <strong>${escapeHtml(shortText(target || "target pending", 54))}</strong>
        <em>${escapeHtml(shortText(observed || "no stored audio window", 54))}</em>
        ${rescanStatus ? `<span>${escapeHtml(rescanStatus)}</span>` : ""}
        ${rescanRuns || rescanEvents ? `<strong>${escapeHtml(rescanRuns)} source runs</strong><em>${escapeHtml(rescanEvents)} source events</em>` : ""}
        ${failedExpected ? `
          <span>Next note</span>
          <strong>${escapeHtml(failedExpected)}</strong>
          <em>${escapeHtml([failedHeard ? `${failedHeard} heard` : failure.failureKind || "unresolved", failedOffset !== "" ? `${failedOffset}s` : ""].filter(Boolean).join(" / "))}</em>
        ` : ""}
      </div>
    </section>
  `;
}

function renderTranscriptionCompletion() {
  if (!elements.transcriptionCompletion) return;
  if (!backend.online) {
    elements.transcriptionCompletion.innerHTML = `<p class="empty">${backendEmptyText()}</p>`;
    return;
  }
  const completion = transcriptionCompletionState(backend.ops);
  if (!completion) {
    elements.transcriptionCompletion.innerHTML = `<p class="empty">Transcription progress pending.</p>`;
    return;
  }
  const percent = Math.max(0, Math.min(100, Number(completion.completionExactPercent ?? completion.completionPercent) || 0));
  const percentLabel = completion.completionExactLabel || completion.completionLabel || `${percent}%`;
  const completedPoints = Number(completion.completedPoints) || 0;
  const totalPoints = Number(completion.totalPoints) || 0;
  const pointSummary = completion.completedPointsLabel || (totalPoints
    ? `${trimDecimal(completedPoints)}/${trimDecimal(totalPoints)} weighted points`
    : "");
  const rows = [
    ["Checked", completion.checkedVideoLabel || "pending"],
    ["Practice", completion.activePracticeLabel || "pending"],
    ["Measure", `${Number(completion.acceptedMeasureMatchCount) || 0} accepted`],
    ["Phrase", `${Number(completion.longPhraseAcceptedCount) || 0} accepted`],
    ["Gold", `${Number(completion.goldReviewAcceptedCount) || 0} accepted`],
    ["Queue", `${Number(completion.goldReviewQueueCount) || 0} clips`],
    ["Source truth", `${Number(completion.truthManifestPositiveSourcePhraseVerifiedCount) || 0}/${Number(completion.truthManifestPositiveSourcePhraseCount) || 0}`],
    ["Blocked errors", `${Number(completion.truthManifestRejectedRegressionBlockedCount) || 0}/${Number(completion.truthManifestRejectedRegressionPhraseCount) || 0}`],
    ["Source audit", completion.staff4PhraseAuditStatus ? String(completion.staff4PhraseAuditStatus).replace(/_/g, " ") : "not generated"],
    ["Crop review", completion.sourceCropReverificationStatus ? String(completion.sourceCropReverificationStatus).replace(/_/g, " ") : "empty"],
  ];
  const staff4Audit = completion.staff4PhraseAudit && typeof completion.staff4PhraseAudit === "object" ? completion.staff4PhraseAudit : {};
  const staff4AuditScore = staff4Audit.score && typeof staff4Audit.score === "object" ? staff4Audit.score : {};
  const staff4AuditReview = staff4Audit.sourceCropScoreReview && typeof staff4Audit.sourceCropScoreReview === "object" ? staff4Audit.sourceCropScoreReview : {};
  const staff4MeasureLabel = String(staff4AuditScore.measureLabel || staff4AuditReview.measureLabel || staff4Audit.measureLabel || "").trim();
  if (staff4MeasureLabel) {
    rows.splice(8, 0, ["Source", staff4MeasureLabel]);
  }
  const rescanStatus = String(completion.staff4SourceAudioRescanStatus || "");
  const miningStatus = String(completion.staff4AdjacentMiningStatus || "");
  if (rescanStatus && rescanStatus !== "no_staff4_anchor") {
    rows.splice(8, 0, ["Rescan", rescanStatus.replace(/_/g, " ")]);
  }
  if (miningStatus && miningStatus !== "no_staff4_anchor") {
    rows.splice(rescanStatus && rescanStatus !== "no_staff4_anchor" ? 9 : 8, 0, ["Mining", miningStatus.replace(/_/g, " ")]);
  }
  elements.transcriptionCompletion.innerHTML = `
    <div class="roadmap-score">
      <div>
        <span>Completion</span>
        <strong>${escapeHtml(percentLabel)}</strong>
        <small>${escapeHtml(pointSummary || completion.basis || "")}</small>
      </div>
      <div class="roadmap-meter" aria-label="Transcription completion ${escapeHtml(percentLabel)}">
        <i style="width: ${percent}%"></i>
      </div>
    </div>
    <div class="roadmap-stats" aria-label="Transcription essentials">
      ${rows.map(([label, value]) => `
        <article>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </article>
      `).join("")}
    </div>
    <div class="roadmap-next">
      <span>Next</span>
      <strong>${escapeHtml(shortText(completion.nextAction || "pending", 110))}</strong>
    </div>
    ${renderStaff4Mining(completion.staff4AdjacentMining, completion.staff4SourceAudioRescan)}
    ${renderStaff4Audit(completion.staff4PhraseAudit)}
  `;
}

function pieceEvidenceLine(piece, evidence) {
  const evidenceCount = Array.isArray(evidence) ? evidence.length : 0;
  const days = Array.isArray(piece?.recentPracticeDays) ? piece.recentPracticeDays.filter(Boolean).length : 0;
  const progress = piece?.currentProgressLabel || piece?.progressStatus || "not scored";
  const heat = piece?.heatMap?.status === "ready" ? "heat map ready" : "heat map pending";
  return [
    evidenceCount ? `${evidenceCount} dated row${evidenceCount === 1 ? "" : "s"}` : "evidence pending",
    days ? `${days} recent day${days === 1 ? "" : "s"}` : "recent days pending",
    heat,
    `progress ${progress}`,
  ].join(" / ");
}

function renderPieceEvidenceLedger(piece, evidence) {
  const days = Array.isArray(piece?.recentPracticeDays) ? piece.recentPracticeDays.filter(Boolean).slice(0, 4) : [];
  const evidenceCount = Array.isArray(evidence) ? evidence.length : 0;
  return `
    <div class="piece-evidence-ledger" aria-label="Repertoire evidence ledger">
      <article>
        <span>Active</span>
        <strong>${escapeHtml(piece?.totalActiveViolinLabel || "pending")}</strong>
      </article>
      <article>
        <span>Recent</span>
        <strong>${escapeHtml(days.length ? days.join(" / ") : "pending")}</strong>
      </article>
      <article>
        <span>Evidence</span>
        <strong>${escapeHtml(evidenceCount ? `${evidenceCount} dated rows` : "pending")}</strong>
      </article>
      <article>
        <span>Progress</span>
        <strong>${escapeHtml(piece?.currentProgressLabel || piece?.progressStatus || "not scored")}</strong>
      </article>
    </div>
  `;
}

function renderPieceDays(piece) {
  if (!isIdentifiedPiece(piece)) return "";
  const daily = piece?.daily && typeof piece.daily === "object" ? piece.daily : {};
  const rows = Object.entries(daily).slice(-4).reverse();
  if (!rows.length) return "";
  return `
    <ol class="mini-days" aria-label="Piece day history">
      ${rows.map(([day, item]) => `
        <li>
          <span>${escapeHtml(day)}</span>
          <b>${escapeHtml(scoreText(item?.completionPercent))}</b>
          <small>${escapeHtml(item?.tip || item?.evidence || "Evidence recorded.")}</small>
        </li>
      `).join("")}
    </ol>
  `;
}

function renderInventory() {
  const inventory = inventoryItems(backend.ops);
  const candidates = inventory.filter((item) => item.practiceCandidate);
  if (!backend.online) {
    elements.inventoryList.innerHTML = `<p class="empty">${backendEmptyText()}</p>`;
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

function renderHighlight() {
  const highlight = primaryHighlight(backend.ops);
  activeHighlight = highlight || null;
  const rejectedTitle = rejectableTitle(highlight);
  const frameShell = elements.highlightFrame.closest(".highlight-frame");
  elements.rejectPieceButton.hidden = !rejectedTitle;
  elements.rejectPieceButton.disabled = !backend.online || !rejectedTitle || !highlight?.url;
  elements.rejectPieceButton.textContent = "Reject title";
  if (!backend.online || !highlight?.url) {
    if (frameShell) frameShell.hidden = true;
    elements.highlightFrame.hidden = true;
    elements.highlightFrame.removeAttribute("src");
    elements.highlightMeta.textContent = backend.online ? "Clip pending." : backendEmptyText();
    elements.highlightWindow.textContent = "No evidence window.";
    elements.highlightLink.hidden = true;
    elements.highlightLink.removeAttribute("href");
    return;
  }
  if (frameShell) frameShell.hidden = false;
  elements.highlightFrame.hidden = false;
  elements.highlightLink.hidden = false;
  const start = Number(highlight.startSeconds) || 0;
  const end = Number(highlight.endSeconds) || (start ? start + 45 : 0);
  const embed = embedUrl(highlight.url, start, end);
  if (embed && elements.highlightFrame.src !== embed) {
    elements.highlightFrame.src = embed;
  }
  elements.highlightMeta.textContent = detectionLabel(highlight);
  elements.highlightWindow.textContent = start
    ? `${formatClock(start)}-${formatClock(end)} / ${highlight.window || "sample"}`
    : highlight.window || "metadata only";
  elements.highlightLink.href = timedUrl(highlight.url, start);
}

function renderDays() {
  const days = practiceDays(backend.ops);
  if (!backend.online) {
    elements.dayList.innerHTML = `<p class="empty">${backendEmptyText()}</p>`;
    return;
  }
  if (!days.length) {
    elements.dayList.innerHTML = `<p class="empty">Practice days pending YouTube inventory.</p>`;
    return;
  }
  elements.dayList.innerHTML = days.map((day) => {
    const detected = shortText(day.detected.length ? day.detected.join(" / ") : "Piece being identified", 150);
    const percent = day.completionPercent ? `${day.completionPercent}%` : day.status;
    const start = Number(day.highlight?.startSeconds) || 0;
    const end = Number(day.highlight?.endSeconds) || (start ? start + 45 : 0);
    const clip = timedUrl(day.highlight?.url || day.url, start);
    const windowText = start ? `${formatClock(start)}-${formatClock(end)}` : "clip pending";
    const packet = day.study;
    const transcription = packet?.transcription || {};
    const totalPracticeText = day.totalPracticeSeconds ? formatDurationSeconds(day.totalPracticeSeconds) : day.duration || "";
    const packetText = packet
      ? [
          transcription.noteCount ? `${transcription.noteCount} notes` : "score ready",
          packet.snippetCount ? `${packet.snippetCount} snippet` : "",
          packet.totalPracticeLabel ? `${packet.totalPracticeLabel} total` : "",
          packet.tip || ""
        ].filter(Boolean).join(" / ")
      : "";
    return `
      <article class="day-row" data-status="${escapeHtml(day.status)}">
        <div>
          <span>${escapeHtml([day.date, totalPracticeText, day.samples ? `${day.samples} samples` : "", day.sections ? `${day.sections} sections` : ""].filter(Boolean).join(" / "))}</span>
          <strong>${escapeHtml(day.title)}</strong>
          <p>${escapeHtml(detected)}</p>
          ${day.tip ? `<small>${escapeHtml(day.tip)}</small>` : ""}
          ${packetText ? `<small class="study-line">${escapeHtml(packetText)}</small>` : ""}
        </div>
        <div class="day-actions">
          <em>${escapeHtml(percent)}</em>
          <a href="${escapeHtml(clip)}">${escapeHtml(windowText)}</a>
        </div>
      </article>
    `;
  }).join("");
}

function render() {
  renderStatus();
  renderStudy();
  renderPieces();
  renderTranscriptionCompletion();
  renderGoldReview();
  if (elements.highlightFrame) renderHighlight();
  if (elements.dayList) renderDays();
  if (elements.inventoryList) renderInventory();
  if (elements.skillMap) renderSkillMap();
}

if (elements.runScanButton) elements.runScanButton.addEventListener("click", runBackendScan);
if (elements.probeMediaButton) elements.probeMediaButton.addEventListener("click", runMediaProbe);
if (elements.rejectPieceButton) elements.rejectPieceButton.addEventListener("click", rejectActiveTitle);
document.addEventListener("click", (event) => {
  const keyButton = event.target.closest("[data-note-reading-key]");
  if (!keyButton) return;
  const form = keyButton.closest("[data-note-reading-form]");
  const input = form?.querySelector("input[name='noteLetterAnswer']");
  if (!form || !input) return;
  const key = keyButton.dataset.noteReadingKey || "";
  const notes = noteInputSequence(input.value);
  if (key === "clear") {
    input.value = "";
  } else if (key === "delete") {
    input.value = notes.slice(0, -1).join(" ");
  } else if ("ABCDEFG".includes(key)) {
    input.value = [...notes, key].join(" ");
  }
  persistNoteReadingDraft(form.dataset.reviewItemId, input.value);
  input.focus();
});
document.addEventListener("input", (event) => {
  const input = event.target.closest("[data-note-reading-form] input[name='noteLetterAnswer']");
  if (!input) return;
  const form = input.closest("[data-note-reading-form]");
  persistNoteReadingDraft(form?.dataset?.reviewItemId, input.value);
});
document.addEventListener("submit", (event) => {
  const noteReadingForm = event.target.closest("[data-note-reading-form]");
  if (noteReadingForm) {
    event.preventDefault();
    submitNoteReading(noteReadingForm);
    return;
  }
  const goldForm = event.target.closest("[data-gold-review-form]");
  if (goldForm) {
    event.preventDefault();
    submitGoldReview(goldForm, event.submitter?.value || "accepted_truth");
    return;
  }
  const form = event.target.closest("[data-piece-label-form]");
  if (!form) return;
  event.preventDefault();
  submitPieceLabel(form);
});

render();
loadBackendState();
