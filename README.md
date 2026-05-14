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
- Media acquisition attempts short samples automatically after scans. When YouTube blocks server-side public fetching, the owner-media helper uploads multiple distributed windows per long practice video through the authenticated media endpoint, probes deeper practice windows before extra early-window checks, expands around already-found violin-positive windows, reuses locally cached owner-captured samples, prioritizes cached violin-positive windows before blind new captures, and uses the backend sample index to avoid duplicate windows. Setting `CURTIS_OWNER_WINDOWS_PER_VIDEO` above 8 switches the owner helper into full-check mode, walking every 90-second window in order so total practice time can be measured across the archive instead of sampled windows only.
- The first screen has three top-level surfaces: a paper card, analyzed practice days, and repertoire.
- The top paper card links to `Score-linked practice intelligence from long-form violin training video`.
- Daily records group same-day practice videos and preserve uploaded duration separately from total practice time. Total practice time means footage where violin playing is detected; it is independent from transcription and score matching. When the full archive is not checked, Curtis can show a low-cost estimate by applying the checked-window active-playing ratio to the unchecked archive while keeping the measured time and unchecked duration visible. Every sampled media window now passes through a conservative violin-presence sampler before analysis: it must show active audio, violin-range pitched frames, onset density, and spectral evidence before it can become playable evidence. Room/setup/laptop/noise windows are withheld instead of counted as practice evidence.
- Machine note/rhythm evidence combines onset-aware pYIN with an onset-bounded spectral pitch rescue for fast passages, while repeated single-note traces such as D-D-D-D remain out of final score-verified notation. The transcription PDF lists stored detected note series for the day, even when a series is not accepted as visible notation.
- Note matching separates score-derived notes from reference-audio traces. Rhythm and octave are ignored for loose reference matching, but Curtis does not call that score detection. A scanned PDF plus guessed `scorePitchClassSequences` is now ignored unless the sequence has an explicit symbolic-score source, manual source confirmation, MusicXML/source-confirmed status, or exact score-location metadata. The backend can parse inline, local `.musicxml`, or local `.mxl` symbolic scores, extract the solo-violin note sequence, keep written flats such as B-flat on the correct staff position while matching their pitch class, and accept a score match only when the played pitch-class sequence meets the target-specific source-score run gate. Scherzo-Tarantelle now has a source-backed four-note symbolic opening motif from the local IMSLP solo part; it can create one verified measure-level score/audio group, but it is not counted as solved long-phrase transcription until the accepted run reaches the longer phrase gate. Reference-audio phrase candidates are now collected across the full detected-series set and ranked by exact score status, score-derived status, distinct pitch-class content, and length, so longer useful candidates are no longer hidden behind early repeated-pitch runs. The tracker exposes the top pending phrase candidate as the next source-score verification target, while these phrase candidates remain pending evidence and are not accepted as score evidence. Single-pitch score crops are withheld unless the highlighted score note has explicit visual note verification; one-note audio overlaps are not accepted as score evidence. When a symbolic phrase match exists, Curtis renders the displayed score snippet from the exact matched score notes instead of guessing a scanned-image crop. All current Scherzo-Tarantelle single-pitch crops, including the later A4 crop, are rejected after visual review because the highlighted score note did not match the displayed A pitch. Detected D4/A4 audio fragments remain audio-checked transcription evidence only unless they match accepted symbolic score notes. Broader sheet-music snippets stay hidden until the played notes have exact score-location agreement; proportional score-region estimates are not emitted or rendered as score evidence. Violin-playing evidence without a confirmed score is treated as possible repertoire or a score-free technique exercise rather than as a failed score match.
- Recognition training now has three separated inputs: Alan-confirmed source labels, explicit calibration uploads such as titled scales/arpeggios/open strings, and public labeled violin YouTube reference metadata discovered through the official Data API. Public YouTube references seed labels and targets only; they do not become audio fingerprints, repertoire, or performance evidence until Curtis has a permitted media path and score/pattern alignment.
- Repertoire names require source-backed evidence before promotion. Possible, uncorroborated, or user-rejected model guesses stay daily uncertain evidence instead of becoming repertoire.
- Specific Curtis-level observations render only when they are grounded in reliable score-linked evidence or clear repeated score-free technique-pattern evidence. Generic advice, fake notation, random heat-map fragments, and fake completion percentages stay out of the interface.
- Practice-study packets remain as support data for score pages, boxed passage targets, and timed practice links, but the primary page is the daily record plus evidence-backed repertoire.
- Uploaded-video totals start at the public `violin 1` marker and count violin-numbered or date-titled practice logs, preserving video title, upload date, duration, and URL for the growing ledger. These totals are not practice time; total practice time comes only from detected violin-playing footage. Video checked for practice time is tracked separately from both uploaded-video duration and transcription coverage.
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
