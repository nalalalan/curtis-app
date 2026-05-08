# Curtis Media Review

Static AO Labs app and Railway-ready backend for `curtis.aolabs.io`.

## Source State

- Curtis Institute of Music official admissions pages reviewed on 2026-05-07.
- Default public YouTube source: `https://www.youtube.com/@nalalan`.
- Stored working state is browser-local when the backend is offline; backend state is persisted in `CURTIS_STATE_PATH` when the service is running.
- Public custom-domain access is served by Railway at `https://curtis.aolabs.io`.

## Media Review Direction

- Backend inventories the public YouTube channel by default and exposes scan state through `/api/curtis/ops-check`.
- YouTube OAuth remains available for authenticated inventory later. The Data API returns metadata, not video media, so performance judgment remains blocked until a permitted media path exists.
- Media acquisition attempts short samples automatically after scans. When YouTube blocks server-side public fetching, the owner-media helper uploads multiple distributed windows per long practice video through the authenticated media endpoint and uses the backend sample index to avoid duplicate windows.
- The first screen has two main sections: analyzed practice days and repertoire.
- Daily records group same-day practice videos, preserve uploaded duration, attach active-playing evidence when media has been processed, render sheet-music-style notation from pYIN note/rhythm events, show clips, heat-map fragments, and keep uncertain evidence marked uncertain.
- Repertoire names require source-backed evidence before promotion. Possible, uncorroborated, or user-rejected model guesses stay daily uncertain evidence instead of becoming repertoire.
- Specific Curtis-level observations are generated only from extracted evidence such as uncertain repeated notes, longer pause/restart markers, slow windows, and repeated fragments. Generic advice and fake completion percentages are withheld.
- Practice-study packets remain as support data for score pages, boxed passage targets, and timed practice links, but the primary page is the daily record plus evidence-backed repertoire.
- Practice totals start at the public `violin 1` marker and count violin-numbered or date-titled practice logs, preserving video title, upload date, duration, and URL for the growing ledger.
- Instagram inventory uses the Instagram Graph API for authorized account media. Media URLs are queued for section processing when available.
- Skill claims stay `Unjudged` until a video section is processed against the rubric.

## Integration Sources

- YouTube channels: https://developers.google.com/youtube/v3/docs/channels/list
- YouTube videos: https://developers.google.com/youtube/v3/docs/videos/list
- YouTube playlist items: https://developers.google.com/youtube/v3/docs/playlistItems/list
- Instagram APIs: https://developers.facebook.com/products/instagram/apis/
- OpenAI models: https://developers.openai.com/api/docs/models
- Railway config: https://docs.railway.com/config-as-code/reference

## Local Static Preview

```powershell
python -m http.server 4177
```

Open `http://127.0.0.1:4177/`.

## Local Backend

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. The backend serves the same app and API.
