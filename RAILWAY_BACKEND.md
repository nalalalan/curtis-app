# Curtis Media Review Backend

## Target

Autonomous practice-video review for Curtis preparation.

## Required Inputs

- `OPENAI_API_KEY`
- `OPENAI_MODEL=gpt-5.5`
- `OPENAI_REASONING_EFFORT=xhigh`
- `YOUTUBE_API_KEY` or all of:
  - `YOUTUBE_CLIENT_ID`
  - `YOUTUBE_CLIENT_SECRET`
  - `YOUTUBE_REFRESH_TOKEN`
- `INSTAGRAM_USER_ID`
- `INSTAGRAM_ACCESS_TOKEN`
- `CURTIS_STATE_PATH=/data/curtis_state.json` when Railway volume storage is attached.
- `CURTIS_ALLOWED_ORIGINS=https://curtis.aolabs.io`

## Optional Inputs

- `CURTIS_AUTORUN=1`
- `CURTIS_SCAN_INTERVAL_SECONDS=86400`
- `CURTIS_YOUTUBE_SOURCE`
- `CURTIS_INSTAGRAM_SOURCE`
- `YOUTUBE_MAX_RESULTS=12`
- `INSTAGRAM_MAX_RESULTS=12`
- `INSTAGRAM_GRAPH_VERSION=v20.0`

## API

- `GET /health`
- `GET /api/curtis/ops-check`
- `GET /api/curtis/media-status`
- `POST /api/curtis/sources`
- `POST /api/curtis/scan/run`

## Current Implementation

- YouTube automation inventories channel, playlist, or video metadata through the official Data API.
- YouTube media judgment is blocked until a permitted video media path exists; the Data API does not provide raw video content.
- Instagram automation inventories authorized account media through Graph API and marks media URLs for section processing when present.
- OpenAI defaults to `gpt-5.5` with `xhigh` reasoning for future media-section scoring.

## Still Required For Full Judgment

- Authorized media extraction path.
- Audio/frame sampling.
- Stable instrument rubric.
- Section scoring records with video URL, timecode, dimension, model, and source.
- Persistent database or object storage for downloaded media, extracted audio, sampled frames, and judgments.

## Worker Loop

1. Pull source inventory from YouTube and Instagram.
2. Identify new practice videos.
3. Extract audio and representative frames when the platform provides permitted media access.
4. Detect notable sections: strongest passages, regressions, repeated issues, clean starts, recoveries, missed shifts, intonation instability, rhythm drift, tone collapse, and audition-ready segments.
5. Score each section against the active instrument rubric.
6. Update the public record with reviewed video count, notable sections, current work, strongest signal, and weakest recurring signal.

## Boundaries

- No scraping login-only Instagram pages.
- No Curtis-level readiness claim without processed video evidence.
- No single-video verdict unless the section evidence supports it.
- Store every judgment with video URL, timecode, rubric dimension, and model source.
