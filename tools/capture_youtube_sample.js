const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return fallback;
  return process.argv[index + 1];
}

function fail(blocker, detail = "") {
  console.log(JSON.stringify({ status: "blocked", blocker, detail }));
  process.exitCode = 1;
}

function timedUrl(rawUrl, startSeconds) {
  const url = new URL(rawUrl);
  url.searchParams.set("t", `${Math.max(0, Math.floor(startSeconds))}s`);
  return url.toString();
}

async function waitForPlayer(page) {
  await page.waitForSelector("video", { timeout: 45000 });
  await page.waitForFunction(
    () => {
      const video = document.querySelector("video");
      return video && Number.isFinite(video.duration) && video.readyState >= 1;
    },
    null,
    { timeout: 45000 }
  );
}

async function captureInPage(page, startSeconds, durationSeconds) {
  return await page.evaluate(
    async ({ startSeconds, durationSeconds }) => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const video = document.querySelector("video");
      if (!video) return { ok: false, blocker: "youtube_player_missing" };

      video.playsInline = true;
      video.muted = false;
      video.volume = 1;

      if (Number.isFinite(video.duration) && startSeconds < video.duration) {
        video.currentTime = Math.max(0, startSeconds);
        await new Promise((resolve) => {
          const done = () => {
            video.removeEventListener("seeked", done);
            resolve();
          };
          video.addEventListener("seeked", done, { once: true });
          setTimeout(done, 6000);
        });
      }

      for (let attempt = 0; attempt < 4; attempt += 1) {
        try {
          await video.play();
          break;
        } catch (error) {
          if (attempt === 3) {
            return { ok: false, blocker: "youtube_playback_blocked", detail: error.message };
          }
          await sleep(1000);
        }
      }

      const beforeTime = video.currentTime;
      let afterTime = beforeTime;
      for (let wait = 0; wait < 15; wait += 1) {
        await sleep(1000);
        afterTime = video.currentTime;
        if (!video.paused && afterTime > beforeTime + 0.2) break;
      }
      if (video.paused || afterTime <= beforeTime) {
        return { ok: false, blocker: "youtube_playback_not_advancing" };
      }

      const stream = video.captureStream ? video.captureStream() : video.mozCaptureStream?.();
      if (!stream) return { ok: false, blocker: "browser_capture_unavailable" };

      const audioTracks = stream.getAudioTracks().length;
      const videoTracks = stream.getVideoTracks().length;
      if (!audioTracks && !videoTracks) return { ok: false, blocker: "browser_capture_no_tracks" };

      const mimeType = MediaRecorder.isTypeSupported("video/webm;codecs=vp8,opus")
        ? "video/webm;codecs=vp8,opus"
        : "video/webm";
      const chunks = [];
      const recorder = new MediaRecorder(stream, { mimeType });
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size) chunks.push(event.data);
      });
      recorder.start(1000);
      await sleep(Math.max(1, durationSeconds) * 1000);
      await new Promise((resolve) => {
        recorder.addEventListener("stop", resolve, { once: true });
        recorder.requestData();
        recorder.stop();
      });

      const blob = new Blob(chunks, { type: recorder.mimeType });
      const bytes = Array.from(new Uint8Array(await blob.arrayBuffer()));
      return {
        ok: true,
        bytes,
        mimeType: blob.type,
        sizeBytes: blob.size,
        audioTracks,
        videoTracks,
        startCurrentTime: beforeTime,
        endCurrentTime: video.currentTime,
        recordedSeconds: durationSeconds,
        startSeconds: Math.max(0, startSeconds),
      };
    },
    { startSeconds, durationSeconds }
  );
}

async function main() {
  const url = argValue("--url");
  const output = argValue("--output");
  const startSeconds = Number.parseInt(argValue("--start", "600"), 10);
  const durationSeconds = Number.parseInt(argValue("--duration", "90"), 10);

  if (!url || !output) {
    fail("missing_capture_arguments");
    return;
  }

  const browser = await chromium.launch({
    headless: true,
    args: [
      "--autoplay-policy=no-user-gesture-required",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
    ],
  });

  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 720 },
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    });
    await page.goto(timedUrl(url, startSeconds), { waitUntil: "domcontentloaded", timeout: 45000 });
    await waitForPlayer(page);
    const result = await captureInPage(page, startSeconds, durationSeconds);

    if (!result.ok) {
      fail(result.blocker || "browser_capture_failed", result.detail || "");
      return;
    }

    const target = path.resolve(output);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, Buffer.from(result.bytes));
    delete result.bytes;

    console.log(JSON.stringify({ status: "sample_ready", path: target, ...result }));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  fail("browser_capture_failed", error.message || String(error));
});
