# Curtis Media Review Backend

## Target

Autonomous practice-video review for Curtis preparation.

## Required Inputs

- `OPENAI_API_KEY`
- `OPENAI_MODEL=gpt-5.5`
- `OPENAI_REASONING_EFFORT=xhigh`
- `YOUTUBE_API_KEY` for public YouTube channel inventory.
- Default public source is `https://www.youtube.com/@nalalan`; override with `CURTIS_YOUTUBE_SOURCE` only if the channel changes.
- `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` from a Google OAuth web client for persistent authenticated channel access.
- `YOUTUBE_REFRESH_TOKEN` only when importing an existing token manually; the app stores it after `/api/auth/youtube/callback` when OAuth is connected.
- Google OAuth authorized redirect URI:
  - `https://curtis.aolabs.io/api/auth/youtube/callback`
- Google OAuth scope:
  - `https://www.googleapis.com/auth/youtube.readonly`
- `PUBLIC_BASE_URL=https://curtis.aolabs.io`
- `CURTIS_STATE_PATH=/data/curtis_state.json` with the Railway volume mounted at `/data`.
- `CURTIS_ALLOWED_ORIGINS=https://curtis.aolabs.io,https://curtis-app-production.up.railway.app`
- For Instagram Graph automation:
  - `INSTAGRAM_USER_ID`
  - `INSTAGRAM_ACCESS_TOKEN`

## YouTube Persistent Login

1. Create a Google OAuth client with application type `Web application`.
2. Add `https://curtis.aolabs.io/api/auth/youtube/callback` as an authorized redirect URI.
3. Set `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `PUBLIC_BASE_URL`, and `CURTIS_STATE_PATH` in Railway.
4. Open `https://curtis.aolabs.io/api/auth/youtube/start` and approve the `youtube.readonly` scope once.
5. The backend stores the refresh token in Railway volume state and scans `mine`, which resolves the authenticated channel uploads playlist.

The YouTube Data API and OAuth provide channel and upload inventory. They do not provide raw video media files, so performance-level scoring still needs a permitted media extraction path.

## Legacy Manual Token Inputs

If OAuth callback storage is not used, set all of:
  - `YOUTUBE_CLIENT_ID`
  - `YOUTUBE_CLIENT_SECRET`
  - `YOUTUBE_REFRESH_TOKEN`

## Optional Inputs

- `CURTIS_AUTORUN=1`
- `CURTIS_SCAN_INTERVAL_SECONDS=86400`
- `CURTIS_YOUTUBE_SOURCE=https://www.youtube.com/@nalalan`
- `CURTIS_INSTAGRAM_SOURCE`
- `YOUTUBE_MAX_RESULTS=200`
- `INSTAGRAM_MAX_RESULTS=12`
- `INSTAGRAM_GRAPH_VERSION=v20.0`

## API

- `GET /health`
- `GET /api/curtis/ops-check`
- `GET /api/curtis/media-status`
- `POST /api/curtis/sources`
- `POST /api/curtis/scan/run`
- `GET /api/auth/youtube/status`
- `GET /api/auth/youtube/start`
- `GET /api/auth/youtube/callback`

## Current Implementation

- YouTube automation inventories channel, playlist, or video metadata through the official Data API.
- Authenticated YouTube mode uses OAuth `mine=true` channel access and the uploads playlist for the connected account.
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
