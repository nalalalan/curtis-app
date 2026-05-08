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
  instagramState: document.querySelector("#instagramState")
};

function setText(element, value) {
  if (element) element.textContent = value;
}

function setHtml(element, value) {
  if (element) element.innerHTML = value;
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

function shortText(value, limit = 135) {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, limit - 1).trim()}...`;
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

function practiceHoursText(totals) {
  const seconds = Number(totals?.totalPracticeSeconds) || 0;
  if (!seconds) return "0h";
  const hours = seconds / 3600;
  return hours >= 100 ? `${Math.round(hours)}h` : `${hours.toFixed(1)}h`;
}

function activePracticeText(records) {
  const seconds = Number(records?.totalActiveViolinSeconds) || 0;
  if (records?.totalActiveViolinLabel) return records.totalActiveViolinLabel;
  return seconds ? formatDurationSeconds(seconds) : "pending";
}

function uploadedVideoText(records, totals) {
  return records?.totalUploadedVideoLabel || totals?.totalPracticeLabel || "0h";
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
  const records = dailyRecords(ops);
  const recordCount = Number(records.recordCount) || 0;
  const transcribedCount = Number(records.transcribedRecordCount) || 0;
  const processedCount = analyzedRecordList(ops).length;
  const practiceCount = Number(ops?.review?.practiceCandidateCount) || 0;
  const findingCount = skillFindings(ops).length;
  if (recordCount) return `${transcribedCount} transcribed / ${processedCount} processed / ${recordCount} indexed practice days.`;
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
    : { records: [], recordCount: 0, transcribedRecordCount: 0 };
}

function dailyRecordList(ops) {
  const records = dailyRecords(ops).records;
  return Array.isArray(records) ? records : [];
}

function analyzedRecordList(ops) {
  return dailyRecordList(ops).filter((record) => record?.status && record.status !== "pending_media");
}

function latestDailyRecord(ops) {
  return analyzedRecordList(ops)[0] || dailyRecordList(ops)[0] || null;
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
  if (!training) return "0 anchors";
  const anchors = Number(training.referenceTargetCount ?? training.confirmedSourceCount) || 0;
  const matches = Number(training.scoreAlignedWindowCount) || 0;
  const pitchWindows = Number(training.pitchRhythmWindowCount) || 0;
  if (!anchors) return "0 refs";
  if (pitchWindows && !matches) return `${anchors} refs / ${pitchWindows} pitch windows`;
  return `${anchors} refs / ${matches} score matches`;
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
    const transcribedCount = Number(records.transcribedRecordCount) || 0;
    const analyzedCount = analyzedRecords.length;
    elements.studyCount.textContent = `${transcribedCount} transcribed / ${analyzedCount} processed`;
  }
  const activeSeconds = Number(records.totalActiveViolinSeconds) || 0;
  const uploadedLabel = uploadedVideoText(records, totals);
  setText(elements.totalPracticeHours, activePracticeText(records));
  setText(
    elements.practiceSince,
    activeSeconds
      ? "Real active violin-playing time only."
      : "Pending active-playing detection across the full practice archive."
  );
  setText(elements.uploadedVideoTime, uploadedLabel);
  setText(
    elements.uploadedVideoScope,
    [
      totals?.sinceTitle ? `Since ${totals.sinceTitle}` : "Ledger pending",
      totals?.sincePublishedAt ? formatDate(totals.sincePublishedAt) : "",
      totals?.videoCount ? `${totals.videoCount} videos` : "",
      "not counted as active practice"
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
  setText(elements.currentState, currentStateText(ops));
  setText(
    elements.recordSummary,
    `${Number(records.transcribedRecordCount) || 0} transcribed / ${analyzedRecords.length} processed / ${Number(records.recordCount) || 0} indexed`
  );
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

function renderScoreImage(snippet, compact = false) {
  const score = snippet?.score || {};
  const imageUrl = scoreImageUrl(score);
  if (!imageUrl) {
    return `<div class="score-placeholder">Score render pending.</div>`;
  }
  const boxes = scoreBoxes(score);
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

function noteY(note) {
  const match = String(note || "").match(/^([A-G])(#|b)?(\d)$/);
  if (!match) return 50;
  const order = { C: 0, D: 1, E: 2, F: 3, G: 4, A: 5, B: 6 };
  const value = (Number(match[3]) * 7) + (order[match[1]] || 0);
  const violinLow = (3 * 7) + order.G;
  const violinHigh = (7 * 7) + order.C;
  const normalized = (value - violinLow) / Math.max(1, violinHigh - violinLow);
  return Math.max(12, Math.min(84, 84 - (normalized * 72)));
}

function renderTranscriptionStaff(transcription) {
  const notes = Array.isArray(transcription?.firstNotes) ? transcription.firstNotes.slice(0, 18) : [];
  if (!notes.length) return "";
  return `
    <div class="transcription-staff" aria-label="Machine transcription staff">
      <span></span><span></span><span></span><span></span><span></span>
      ${notes.map((note, index) => `
        <i style="left:${5 + (index * (90 / Math.max(1, notes.length - 1)))}%; top:${noteY(note)}%;" title="${escapeHtml(note)}"></i>
      `).join("")}
    </div>
  `;
}

function renderScoreHeatMap(record, scoreSnippet) {
  const score = scoreSnippet?.score || {};
  const imageUrl = scoreImageUrl(score);
  if (!imageUrl) {
    return `<div class="score-placeholder score-heat-placeholder">Score heat map pending.</div>`;
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

function renderNotationSheet(events, options = {}) {
  const items = Array.isArray(events) ? events.slice(0, 42) : [];
  const staffLines = [30, 40, 50, 60, 70].map((y) => `<line x1="22" x2="698" y1="${y}" y2="${y}" />`).join("");
  const repeatGroup = options?.repeatGroup && typeof options.repeatGroup === "object" ? options.repeatGroup : null;
  const repeatLabel = repeatGroup?.notationLabel || options?.repeatLabel || "";
  const repeatPattern = repeatGroup?.practicePattern || options?.practicePattern || "";
  const qualityLabel = options?.qualityLabel || "";
  const qualityLimit = options?.qualityLimit || "";
  const captionTitle = repeatLabel || qualityLabel;
  const captionDetail = repeatPattern || qualityLimit;
  const repeatClass = repeatLabel ? " notation-repeat" : "";
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
  if (!items.length) {
    return `
      <div class="notation-sheet notation-empty${repeatClass}" aria-label="Sheet-music-style transcription pending">
        <svg viewBox="0 0 720 104" role="img">
          <g class="staff-lines">${staffLines}</g>
          <text x="34" y="57">G</text>
          ${repeatMarks}
        </svg>
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
  const step = items.length > 1 ? 630 / (items.length - 1) : 0;
  const marks = items.map((event, index) => {
    const x = 48 + (step * index);
    const durationClass = notationDurationClass(event.durationKind);
    if (event.kind === "rest") {
      return `
        <g class="notation-rest ${durationClass}" transform="translate(${x} 0)">
          <rect x="-5" y="45" width="10" height="6" rx="1"></rect>
          <line x1="-7" x2="7" y1="55" y2="55"></line>
        </g>
      `;
    }
    const y = noteY(event.note) + 3;
    const uncertain = event.uncertain ? " notation-uncertain" : "";
    const raw = event.rawNote ? `raw ${event.rawNote}` : "";
    const label = escapeHtml([event.note, raw, event.uncertain ? "uncertain" : ""].filter(Boolean).join(" / "));
    return `
      <g class="notation-note ${durationClass}${uncertain}" aria-label="${label}">
        <ellipse cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" rx="6.6" ry="4.4" transform="rotate(-16 ${x.toFixed(1)} ${y.toFixed(1)})"></ellipse>
        ${durationClass === "whole" ? "" : `<line x1="${(x + 6).toFixed(1)}" x2="${(x + 6).toFixed(1)}" y1="${y.toFixed(1)}" y2="${Math.max(14, y - 28).toFixed(1)}"></line>`}
      </g>
    `;
  }).join("");
  return `
    <div class="notation-sheet${repeatClass}" aria-label="Sheet-music-style machine transcription">
      <svg viewBox="0 0 720 104" role="img">
        <g class="staff-lines">${staffLines}</g>
        <text x="34" y="57">G</text>
        ${repeatMarks}
        ${marks}
      </svg>
      ${captionTitle ? `
        <div class="notation-repeat-caption">
          <b>${escapeHtml(shortText(captionTitle, 72))}</b>
          <em>${escapeHtml(shortText(captionDetail || "machine evidence", 92))}</em>
        </div>
      ` : ""}
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
  if (record?.transcription?.qualityStatus === "weak_fragment") return "weak notation";
  if (record?.transcription?.qualityStatus === "sanity_corrected_draft") return "corrected draft";
  if (record?.transcription?.qualityStatus === "draft_fragment") return "draft notation";
  if (record?.status === "transcribed") return "transcribed";
  if (record?.status === "active_time_measured") return "active measured";
  return "pending media";
}

function transcriptionEvidenceLabel(transcription) {
  const count = Number(transcription?.noteCount) || 0;
  const label = transcription?.qualityLabel || (transcription?.status === "ready" ? "machine fragment" : "notation pending");
  if (!count) return label;
  return `${label} / ${count} notes`;
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
          <strong>${escapeHtml(item.problem || "Observation pending.")}</strong>
          <p>${escapeHtml(item.curtisReadinessIssue || "")}</p>
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
          <em>${escapeHtml(shortText(item.reason || "Confirmed from practice evidence.", 120))}</em>
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
  const scoreReadiness = scoreSnippet?.readiness || scoreSnippet?.score?.status || piece?.score?.status || "score match pending";
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

function primaryPlayableClip(record) {
  const clips = Array.isArray(record?.clips) ? record.clips : [];
  return clips.find((clip) => clip?.mediaUrl && clip.type === "transcribed_window" && Number(clip.noteCount || record?.transcription?.noteCount || 0) > 0)
    || clips.find((clip) => clip?.mediaUrl && clip.type === "transcribed_window")
    || clips.find((clip) => clip?.mediaUrl)
    || clips[0]
    || null;
}

function eventInsideClip(event, clip) {
  if (!clip || clip.type !== "transcribed_window") return true;
  if (event?.kind !== "note") return false;
  const start = Number(clip.startSeconds) || 0;
  const end = Number(clip.endSeconds) || 0;
  const eventStart = Number(event.sourceStartSeconds);
  return end > start && Number.isFinite(eventStart) && eventStart >= start - 0.2 && eventStart <= end + 0.2;
}

function transcriptionEventsForClip(record, clip) {
  const events = Array.isArray(record?.transcription?.events) ? record.transcription.events : [];
  if (!clip || clip.type !== "transcribed_window") return events;
  const filtered = [];
  for (const event of events) {
    if (eventInsideClip(event, clip)) {
      filtered.push(event);
      continue;
    }
    if (event?.kind === "rest" && filtered.length) filtered.push(event);
  }
  const noteCount = filtered.filter((event) => event?.kind === "note").length;
  return noteCount >= 3 ? filtered : events;
}

function transcriptionCoverageText(record) {
  const transcription = record?.transcription || {};
  return transcription.coverageLabel || record?.processedSampleLabel || "sample window pending";
}

function renderEmbeddedMedia(record, preferredClip = null) {
  const clip = preferredClip || primaryPlayableClip(record);
  const src = mediaFragmentUrl(clip);
  if (!src) {
    return `
      <div class="embedded-media embedded-media-pending">
        <span>Local clip</span>
        <strong>sample pending</strong>
        <small>Stored YouTube metadata is not playable media.</small>
      </div>
    `;
  }
  const label = clip?.type === "transcribed_window" ? "Transcribed sample" : "Local clip";
  return `
    <div class="embedded-media" aria-label="Playable local practice clip">
      <div class="embedded-media-header">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(clipWindowLabel(clip))}</strong>
      </div>
      <video controls preload="metadata" src="${escapeHtml(src)}"></video>
      <audio controls preload="metadata" src="${escapeHtml(src)}"></audio>
    </div>
  `;
}

function renderClipEvidencePair({ clip, observation, repeatGroup, notationEvents, pieceTitle }) {
  if (!clip && !observation && !repeatGroup && !(Array.isArray(notationEvents) && notationEvents.length)) return "";
  const events = Array.isArray(notationEvents) && notationEvents.length
    ? notationEvents
    : Array.isArray(observation?.transcriptionSnippet)
      ? observation.transcriptionSnippet
      : [];
  const passage = observation?.passage || repeatGroup?.label || pieceTitle || "passage pending";
  const repeatText = repeatGroup?.notationLabel
    || (repeatGroup?.repeatCount ? `${repeatGroup?.label || "fragment"} x${repeatGroup.repeatCount}` : "");
  const pattern = repeatGroup?.practicePattern || clip?.reason || observation?.frequency || "pattern pending";
  const problem = observation?.problem || clip?.reason || "specific observation pending";
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
      ${events.length ? renderNotationSheet(events.slice(0, 18), { repeatGroup }) : `<p class="empty">Transcription snippet pending.</p>`}
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
      pieceTitle: recordPieceText(record)
    }) : ""}
    <div class="clip-list">
      ${clips.map((clip) => {
        const start = Number(clip?.startSeconds) || 0;
        const url = timedUrl(clip?.url || "", start);
        return `
          <a href="${escapeHtml(url)}">
            <span>${escapeHtml(clipWindowLabel(clip))}</span>
            <strong>${escapeHtml(shortText(clip?.reason || clip?.label || "practice clip", 76))}</strong>
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

function recordPieceText(record) {
  const confirmed = Array.isArray(record?.pieces) ? record.pieces.map((piece) => piece.title).filter(Boolean) : [];
  if (confirmed.length) return confirmed.join(" / ");
  const uncertain = Array.isArray(record?.uncertainPieces) ? record.uncertainPieces.map((piece) => `${piece.title} uncertain`).filter(Boolean) : [];
  if (uncertain.length) return uncertain.join(" / ");
  return "Piece evidence pending";
}

function recordEvidenceLine(record, scoreSnippet) {
  const confirmed = Array.isArray(record?.pieces) && record.pieces.length;
  const uncertain = Array.isArray(record?.uncertainPieces) && record.uncertainPieces.length;
  const parts = [
    confirmed ? "source confirmed" : uncertain ? "piece uncertain" : "piece pending",
  ];
  if (record?.transcription?.status === "ready") {
    parts.push(transcriptionEvidenceLabel(record.transcription));
  } else if (record?.activeTimeStatus && record.activeTimeStatus !== "pending_media") {
    parts.push("active time measured");
  } else {
    parts.push("media pending");
  }
  if (scoreSnippet?.score?.imageUrl || scoreSnippet?.score?.assetId) {
    const readiness = String(scoreSnippet?.readiness || "").toLowerCase();
    parts.push(readiness.includes("exact measure") ? "score boxed, measure pending" : "score snippet ready");
  } else {
    parts.push("score pending");
  }
  return parts.join(" / ");
}

function renderDailyRecord(record, index = 0) {
  const playableClip = primaryPlayableClip(record);
  const events = transcriptionEventsForClip(record, playableClip);
  const scoreSnippet = scoreSnippetForRecord(record);
  const meta = [
    record.practiceDay,
    record.uploadedVideoLabel ? `${record.uploadedVideoLabel} uploaded` : "",
    record.activeViolinLabel ? `${record.activeViolinLabel} active` : record.activeTimeStatus === "pending_media" ? "active time pending" : "",
    record.transcription?.noteCount ? transcriptionEvidenceLabel(record.transcription) : "notation pending"
  ].filter(Boolean).join(" / ");
  return `
    <details class="record-card" data-status="${escapeHtml(record.status || "pending")}">
      <summary class="record-summary">
        <span>${escapeHtml(meta)}</span>
        <strong>${escapeHtml(recordPieceText(record))}</strong>
        <em>${escapeHtml(recordStatusLabel(record))}</em>
        <small class="row-evidence-line">${escapeHtml(recordEvidenceLine(record, scoreSnippet))}</small>
      </summary>
      <div class="record-card-body record-essentials-body">
        <div class="practice-essentials">
          ${renderEmbeddedMedia(record, playableClip)}
          <section class="essential-panel">
            <span>Transcription</span>
            ${renderNotationSheet(events, {
              qualityLabel: record?.transcription?.qualityLabel,
              qualityLimit: record?.transcription?.coverageLabel || record?.transcription?.qualityLimit
            })}
          </section>
          <section class="essential-panel">
            ${renderScoreHeatMap(record, scoreSnippet)}
          </section>
          <section class="essential-panel essential-state">
            <span>Limit</span>
            <strong>${escapeHtml(record?.transcription?.qualityLimit || record.mainCurtisBlocker || "Evidence pending.")}</strong>
            <small>${escapeHtml(record?.transcription?.coverageLimit || transcriptionCoverageText(record))}</small>
          </section>
        </div>
      </div>
    </details>
  `;
}

function renderStudy() {
  if (!elements.studyList) return;
  const records = dailyRecordList(backend.ops);
  const analyzed = analyzedRecordList(backend.ops);
  const pendingCount = Math.max(0, records.length - analyzed.length);
  if (!backend.online) {
    elements.studyList.innerHTML = `<p class="empty">Backend offline.</p>`;
    return;
  }
  if (!analyzed.length) {
    elements.studyList.innerHTML = records.length
      ? `<p class="empty">Indexed practice days are waiting for active-playing detection.</p>`
      : `<p class="empty">Daily records pending YouTube inventory.</p>`;
    return;
  }
  elements.studyList.innerHTML = [
    analyzed.map((record, index) => renderDailyRecord(record, index)).join(""),
    pendingCount
      ? `<p class="empty pending-index">${pendingCount} indexed practice days are waiting for active-playing detection. Uploaded video is still stored separately and is not counted as active practice.</p>`
      : ""
  ].join("");
}

function renderPieces() {
  if (!elements.pieceList) return;
  const list = repertoireEntries(backend.ops);
  if (!backend.online) {
    elements.pieceList.innerHTML = `<p class="empty">Backend offline.</p>`;
    return;
  }
  if (!list.length) {
    elements.pieceList.innerHTML = `<p class="empty">Confirmed repertoire evidence pending transcription or source confirmation.</p>`;
    return;
  }
  elements.pieceList.innerHTML = list.slice(0, 8).map((piece, index) => {
    const evidence = Array.isArray(piece.evidence) ? piece.evidence.slice(0, 2) : [];
    const leadEvidence = evidence[0] || {};
    const leadObservation = Array.isArray(piece.observations) ? piece.observations[0] : null;
    return `
    <details class="piece-row evidence-piece">
      <summary class="piece-summary">
        <span>${escapeHtml(piece.status || "confirmed")}</span>
        <strong>${escapeHtml(piece.title || "Piece")}</strong>
        <em>${escapeHtml(piece.totalActiveViolinLabel || "active pending")}</em>
        <small class="row-evidence-line">${escapeHtml(pieceEvidenceLine(piece, evidence))}</small>
      </summary>
      <div class="piece-card-body">
        <div class="piece-evidence-copy">
        <p>${escapeHtml(shortText(piece.reason || "Confirmed from daily practice evidence.", 150))}</p>
        <div class="blocker-line repertoire-blocker">
          <span>Current blocker</span>
          <strong>${escapeHtml(piece.mainCurtisBlocker || "Specific blocker pending.")}</strong>
        </div>
        <small class="piece-meta-line">Progress: ${escapeHtml(piece.currentProgressLabel || piece.progressStatus || "not scored")}</small>
        ${renderPieceEvidenceLedger(piece, evidence)}
        ${renderObservations(piece.observations)}
        ${renderHeatMap(piece)}
        ${index === 0 ? renderClipFrame(leadEvidence?.clip, "Repertoire evidence") : ""}
        ${index === 0 ? renderClipEvidencePair({
          clip: leadEvidence?.clip,
          observation: leadObservation,
          repeatGroup: null,
          notationEvents: leadEvidence?.transcriptionSnippet,
          pieceTitle: piece.title
        }) : ""}
        <div class="evidence-list">
          ${evidence.map((item, itemIndex) => {
            const clip = item.clip || {};
            const clipUrl = timedUrl(clip.url || "", Number(clip.startSeconds) || 0);
            return `
              <div class="evidence-row">
                <a href="${escapeHtml(clipUrl)}">${escapeHtml([item.practiceDay, clipWindowLabel(clip)].filter(Boolean).join(" / "))}</a>
                <span>${escapeHtml(item.confidence || "confirmed")}</span>
                <small>${escapeHtml(shortText(item.reason || "Confirmed source evidence.", 130))}</small>
                ${renderNotationSheet(item.transcriptionSnippet || [])}
                ${itemIndex === 0 ? renderEvidenceScore(item) : ""}
              </div>
            `;
          }).join("")}
        </div>
        ${piece.totalUploadedVideoLabel ? `<small class="piece-meta-line">Uploaded video evidence: ${escapeHtml(piece.totalUploadedVideoLabel)}</small>` : ""}
      </div>
      </div>
    </details>
  `;
  }).join("");
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
    elements.highlightMeta.textContent = backend.online ? "Clip pending." : "Backend offline.";
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
    elements.dayList.innerHTML = `<p class="empty">Backend offline.</p>`;
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
  if (elements.highlightFrame) renderHighlight();
  if (elements.dayList) renderDays();
  if (elements.inventoryList) renderInventory();
  if (elements.skillMap) renderSkillMap();
}

if (elements.runScanButton) elements.runScanButton.addEventListener("click", runBackendScan);
if (elements.probeMediaButton) elements.probeMediaButton.addEventListener("click", runMediaProbe);
if (elements.rejectPieceButton) elements.rejectPieceButton.addEventListener("click", rejectActiveTitle);

render();
loadBackendState();
