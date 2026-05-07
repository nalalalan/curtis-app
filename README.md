# Curtis Admission Record

Static AO Labs app for `curtis.aolabs.io`.

## Source State

- Curtis Institute of Music official admissions pages reviewed on 2026-05-07.
- Requirements vary by department; instrument and program remain explicit user inputs.
- Stored working state is browser-local in v1.
- DNS required for public custom-domain access: `curtis CNAME nalalalan.github.io`.

## Media Review Direction

- v1 records YouTube and Instagram sources, notable video sections, and skill-map judgments locally.
- Autonomous scanning requires a Railway-style backend worker, YouTube Data API/OAuth, Instagram Graph API permissions, media extraction, and model-based analysis.
- Skill claims stay `Unjudged` until a video section is actually processed or entered.

## Integration Sources

- YouTube Data API: https://developers.google.com/youtube/v3/docs/videos
- YouTube playlist items: https://developers.google.com/youtube/v3/docs/playlistItems
- Instagram APIs: https://developers.facebook.com/products/instagram/apis/
- OpenAI vision input: https://platform.openai.com/docs/guides/vision
- OpenAI speech-to-text: https://platform.openai.com/docs/guides/speech-to-text

## Local Preview

```powershell
python -m http.server 4177
```

Open `http://127.0.0.1:4177/`.
