# Curtis Media Review Backend

## Target

Autonomous practice-video review for Curtis preparation.

## Required Inputs

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`
- `INSTAGRAM_CLIENT_ID`
- `INSTAGRAM_CLIENT_SECRET`
- `INSTAGRAM_ACCESS_TOKEN`
- `OPENAI_API_KEY`
- Persistent database or object storage for source inventory, downloaded media, extracted audio, sampled frames, and judgments.

## Worker Loop

1. Pull source inventory from YouTube and Instagram.
2. Identify new practice videos.
3. Extract audio and representative frames.
4. Detect notable sections: strongest passages, regressions, repeated issues, clean starts, recoveries, missed shifts, intonation instability, rhythm drift, tone collapse, and audition-ready segments.
5. Score each section against the active instrument rubric.
6. Update the public record with:
   - reviewed video count
   - notable sections
   - current work
   - strongest signal
   - weakest recurring signal
   - next practice target

## Boundaries

- No scraping login-only Instagram pages.
- No Curtis-level readiness claim without video evidence.
- No single-video verdict unless the section evidence supports it.
- Store every judgment with video URL, timecode, rubric dimension, and model/human source.
