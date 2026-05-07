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
