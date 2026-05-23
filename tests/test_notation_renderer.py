import asyncio
import subprocess
import textwrap
from pathlib import Path


def test_notation_renderer_draws_exact_accidentals():
    assert Path("assets/fonts/Bravura.woff2").is_file(), "notation font must be local, not CDN-only"

    script = textwrap.dedent(
        r"""
        const fs = require("fs");
        const vm = require("vm");
        const code = fs.readFileSync("app.js", "utf8");
        const context = {
          console,
          window: { location: { search: "", hostname: "127.0.0.1", origin: "http://127.0.0.1" } },
          document: {
            addEventListener() {},
            querySelector() { return null; },
            querySelectorAll() { return []; },
            getElementById() { return null; },
            body: {},
          },
          navigator: {},
          localStorage: {
            getItem() { return ""; },
            setItem() {},
            removeItem() {},
          },
          setTimeout,
          clearTimeout,
          URLSearchParams,
          fetch: async () => ({ ok: false, json: async () => ({}) }),
        };
        vm.createContext(context);
        vm.runInContext(code, context);

        function assert(condition, message) {
          if (!condition) throw new Error(message);
        }

        const noKey = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'A#4'},
            {kind:'note',note:'D#6'},
            {kind:'note',note:'Bb4'},
            {kind:'note',note:'Eb5'}
          ], {keySignature:{}, maxNotes:4})`,
          context
        );
        assert(noKey.includes('class="notation-sheet notation-engraved'), "browser notation must use the engraved notation wrapper");
        assert(!noKey.includes('data-abc='), "unverified detected pitches must not hydrate into fake rhythmic ABC notation");
        assert(!noKey.includes('M:none'), "pitch-only snippets should not carry fake ABC rhythm metadata");
        assert(!noKey.includes('K:C clef=treble'), "pitch-only snippets should use the local staff renderer until rhythm is verified");
        assert(!noKey.includes(' |'), "unverified transcription snippets must not invent bar lines");
        assert(noKey.includes('notation-svg-fallback'), "manual SVG must remain only as a no-JavaScript fallback");
        assert((noKey.match(/accidental-glyph accidental-sharp/g) || []).length === 2, "A# and D# need visible sharp glyphs");
        assert((noKey.match(/accidental-glyph accidental-flat/g) || []).length === 2, "Bb and Eb need visible flat glyphs");
        assert((noKey.match(/&#xE262;/g) || []).length === 2, "sharps must use the Bravura/SMuFL sharp glyph");
        assert((noKey.match(/&#xE260;/g) || []).length === 2, "flats must use the Bravura/SMuFL flat glyph");
        assert((noKey.match(/class="notehead"/g) || []).length === 4, "notes must use music-font noteheads");
        assert((noKey.match(/&#xE0A4;/g) || []).length === 4, "pitch-only noteheads must use the Bravura/SMuFL black notehead glyph");
        assert(!noKey.includes('class="note-stem"'), "unverified detected pitches must render as noteheads only, not fake quarter notes");
        assert(!noKey.includes("<ellipse"), "notation renderer must not use rough SVG ellipses for noteheads");
        assert(noKey.includes('class="treble-clef" x="24" y="63" aria-label="treble clef">&#xE050;</text>'), "treble clef must use the Bravura/SMuFL glyph and sit higher on the G line");
        assert(noKey.includes('viewBox="0 -18 720 150"'), "notation viewBox must leave room for high ledger notes and the full treble clef");
        assert(noKey.includes('&#119070;') === false, "notation renderer must not fall back to the generic G-clef glyph");
        assert(noKey.includes('font-size: 70px') === false, "notation renderer should not inline clef styling");
        assert(noKey.includes('aria-label="A#4"'), "A# must not render as natural A in aria label");
        assert(noKey.includes('aria-label="D#6"'), "D# must not render as natural D in aria label");
        assert(noKey.includes('class="note-accidental accidental-glyph accidental-sharp" x="110.0" y="55.0"'), "first-note A# sharp needs professional clearance before the notehead");
        assert(noKey.includes('class="note-accidental accidental-glyph accidental-sharp" x="158.0" y="5.0"'), "high D# sharp must stay vertically aligned with the high notehead");

        const flatKey = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'A#4'},
            {kind:'note',note:'D#6'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:2})`,
          context
        );
        assert(!flatKey.includes('data-abc='), "flat-key pitch-only snippets should not hydrate into fake rhythmic ABC notation");
        assert(!flatKey.includes('_B'), "Bb covered by the key signature must not render as a separate local flat in ABC");
        assert(!flatKey.includes('_e'), "Eb covered by the key signature must not render as a separate local flat in ABC");
        assert((flatKey.match(/key-signature-mark accidental-glyph accidental-flat/g) || []).length === 2, "Bb/Eb key signature needs two flat glyphs");
        assert(flatKey.includes('class="key-signature-mark accidental-glyph accidental-flat" x="88.0" y="50.0"'), "key-signature Bb flat must sit on B, not A");
        assert(flatKey.includes('class="key-signature-mark accidental-glyph accidental-flat" x="108.0" y="35.0"'), "key-signature Eb flat must sit on E, not D");
        assert(!flatKey.includes('note-accidental'), "key-signature-covered Bb/Eb notes must not draw duplicate local accidentals");
        assert(flatKey.includes('aria-label="Bb4 / detected A#4"'), "A# must respell as Bb in a flat key");
        assert(flatKey.includes('aria-label="Eb6 / detected D#6"'), "D# must respell as Eb in a flat key");

        const crowdedFlatKey = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'G#4'},
            {kind:'note',note:'G#4'},
            {kind:'note',note:'A#4'},
            {kind:'note',note:'A#4'},
            {kind:'note',note:'B4'},
            {kind:'note',note:'E4'},
            {kind:'note',note:'E4'},
            {kind:'note',note:'G4'},
            {kind:'note',note:'F#4'},
            {kind:'note',note:'F#4'},
            {kind:'note',note:'F4'},
            {kind:'note',note:'D4'},
            {kind:'note',note:'D#4'},
            {kind:'note',note:'G#4'},
            {kind:'note',note:'G#4'},
            {kind:'note',note:'G#4'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:16})`,
          context
        );
        const viewWidth = Number((crowdedFlatKey.match(/viewBox="0 -18 ([0-9.]+) 150"/) || [])[1]);
        const keyXs = [...crowdedFlatKey.matchAll(/class="key-signature-mark[^"]*" x="([0-9.]+)"/g)].map((match) => Number(match[1]));
        const noteXs = [...crowdedFlatKey.matchAll(/class="notehead" x="([0-9.]+)"/g)].map((match) => Number(match[1]));
        assert(viewWidth > 720, "crowded fast-note review rows must widen instead of compressing the staff");
        assert(crowdedFlatKey.includes('--notation-svg-width:'), "notation SVG must expose its intrinsic width for CSS scrolling");
        assert(noteXs[0] - keyXs[keyXs.length - 1] >= 54, "first note must not collide with the key signature");
        assert(noteXs[1] - noteXs[0] >= 48, "fast detected notes need fixed horizontal clearance instead of squeezed spacing");

        const fittedReviewRow = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'A#4'},
            {kind:'note',note:'A#4'},
            {kind:'note',note:'G4'},
            {kind:'note',note:'F#4'},
            {kind:'note',note:'F#4'},
            {kind:'note',note:'G#4'},
            {kind:'note',note:'G#4'},
            {kind:'note',note:'G4'},
            {kind:'note',note:'G4'},
            {kind:'note',note:'D#4'},
            {kind:'note',note:'D#4'},
            {kind:'note',note:'D4'},
            {kind:'note',note:'C4'},
            {kind:'note',note:'D4'},
            {kind:'note',note:'D#4'},
            {kind:'note',note:'D4'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:16, fitToWidth:true})`,
          context
        );
        const fittedViewWidth = Number((fittedReviewRow.match(/viewBox="0 -18 ([0-9.]+) 150"/) || [])[1]);
        const fittedNoteXs = [...fittedReviewRow.matchAll(/class="notehead" x="([0-9.]+)"/g)].map((match) => Number(match[1]));
        assert(fittedReviewRow.includes("notation-fit"), "Gold Review notation should opt into fit-to-card rendering");
        assert(fittedViewWidth === 720, "Gold Review fit rows should use the base staff width instead of creating a horizontal scrollbar");
        assert(Math.max(...fittedNoteXs) <= 680, "Gold Review fit rows must keep every note inside the visible staff");

        const naturalInFlatKey = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'B4'},
            {kind:'note',note:'E5'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:2})`,
          context
        );
        assert(!naturalInFlatKey.includes('data-abc='), "naturalized pitch-only snippets should not carry fake ABC rhythm metadata");
        assert((naturalInFlatKey.match(/accidental-glyph accidental-natural/g) || []).length === 2, "manual fallback must draw natural signs when a flat-key note is naturalized");
        assert((naturalInFlatKey.match(/&#xE261;/g) || []).length === 2, "naturals must use the Bravura/SMuFL natural glyph");

        const measureAccidentals = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'G#5'},
            {kind:'note',note:'G5'},
            {kind:'note',note:'G#5'},
            {kind:'note',note:'G5'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:4})`,
          context
        );
        assert(!measureAccidentals.includes('data-abc='), "same-measure accidental pitch-only snippets should not hydrate into fake rhythmic ABC notation");
        assert(!measureAccidentals.includes(' |'), "same-measure accidental test must not rely on artificial bar lines");
        assert((measureAccidentals.match(/accidental-glyph accidental-sharp/g) || []).length === 2, "fallback SVG must redraw G# after an intervening natural");
        assert((measureAccidentals.match(/accidental-glyph accidental-natural/g) || []).length === 2, "fallback SVG must explicitly naturalize G after same-measure G#");
        const measureAccidentalText = vm.runInContext(
          `displayNoteTextWithMeasureAccidentals(['G#5', 'G5', 'G#5', 'G5'], {accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'})`,
          context
        );
        assert(measureAccidentalText === 'G#5 G♮5 G#5 G♮5', "review text must mark same-measure naturals so G# G G# is not ambiguous");

        const readableGoldReview = vm.runInContext(
          `(() => {
            const item = {
              detectedNotes: ['G#6', 'F6', 'D#6', 'C#6', 'D#6', 'D#6', 'E6', 'E5', 'G#5', 'G5'],
              pieceTitle: 'Wieniawski Scherzo-Tarantelle, Op. 16'
            };
            const readable = readableGoldReviewNotes(item);
            return {
              signature: readable.keySignature,
              display: readable.displayNotes,
              sheet: renderNotationSheet(goldReviewNotationEvents(item.detectedNotes), {keySignature: readable.keySignature, maxNotes: 10})
            };
          })()`,
          context
        );
        assert(readableGoldReview.signature.accidentalType === 'flat', "Scherzo-Tarantelle review snippets should prefer flat-key spelling");
        assert(readableGoldReview.signature.accidentals.includes('Bb'), "flat-key review display should include Bb in the key signature");
        assert(readableGoldReview.signature.accidentals.includes('Eb'), "flat-key review display should include Eb in the key signature");
        assert(readableGoldReview.signature.accidentals.length === 2, "Scherzo-Tarantelle review display must stay in G minor with two flats");
        assert(readableGoldReview.display[0] === 'G#6', "G# is not in the G-minor key signature and should stay a local sharp unless score evidence says Ab");
        assert(readableGoldReview.display[2] === 'Eb6', "D# should respell as Eb for readability");
        assert(readableGoldReview.display[3] === 'C#6', "C# in G-minor context should stay C# rather than respelling as Db");
        assert(!readableGoldReview.sheet.includes('data-abc='), "Scherzo-Tarantelle Gold Review snippets are pitch-only until rhythm is verified");
        assert(readableGoldReview.sheet.includes('aria-label="G#6"'), "fallback SVG should preserve G# when the key does not justify Ab");

        const unknownReview = vm.runInContext(
          `(() => {
            const item = {
              detectedNotes: ['A#4', 'C#5', 'D#5'],
              pieceTitle: 'Unlabeled technique exercise'
            };
            const readable = readableGoldReviewNotes(item);
            const sheet = renderNotationSheet(goldReviewNotationEvents(readable.displayNotes), {
              keySignature: readable.keySignature,
              maxNotes: readable.displayNotes.length
            });
            return {
              signature: readable.keySignature,
              display: readable.displayNotes,
              sheet,
            };
          })()`,
          context
        );
        assert(unknownReview.signature.accidentalType === 'none', "unlabeled exercises must not get a guessed key signature from pitch counts");
        assert(unknownReview.display.join(' ') === 'A#4 C#5 D#5', "unlabeled review notation must preserve detected spelling instead of respelling into flats");
        assert(!unknownReview.sheet.includes('data-abc='), "unlabeled review notation should stay pitch-only until rhythm is verified");
        const rhythmVerified = vm.runInContext(
          `renderNotationSheet([{kind:'note',note:'A#4',durationKind:'quarter'}], {keySignature:{}, maxNotes:1, rhythmVerified:true})`,
          context
        );
        assert(rhythmVerified.includes('data-abc='), "verified-rhythm snippets may use ABC engraving");
        assert(rhythmVerified.includes('^A'), "verified-rhythm ABC must preserve accidentals");
        assert(rhythmVerified.includes('class="note-stem"'), "verified-rhythm fallback may draw stems");

        const sourceCopy = vm.runInContext(
          `renderNotationSheet([{kind:'note',note:'G5',durationKind:'eighth'}], {
            keySignature:{accidentalType:'flat',accidentals:['Bb','Eb']},
            maxNotes:1,
            fitToWidth:true,
            rhythmVerified:true,
            abcSource:'X:1\\nM:2/4\\nL:1/8\\nK:Gm clef=treble\\n(3G^FG B2 |'
          })`,
          context
        );
        assert(sourceCopy.includes('notation-fit'), "source-copy notation should fit inside the review card");
        assert(sourceCopy.includes('(3G^FG B2'), "source-copy notation must preserve tuplets and durations from the source ABC");
        assert(sourceCopy.includes('data-abc-staffwidth') === false, "default source-copy notation should not invent a fixed staff width unless requested");

        const noteReading = vm.runInContext(
          `(() => {
            const item = {
              reviewItemId: 'note-eight',
              noteReadingVisibleNoteCount: 8,
              noteLetterAnswer: 'a b c d e f g a b',
              noteReadingSourceScope: 'first_visible_source_notes',
              noteReadingScopeLabel: 'first 8 visible notes',
              sourceReviewImageUrl: '/score.png',
              scoreLocation: 'page 2 / staff 4',
              pieceTitle: 'Wieniawski Scherzo-Tarantelle, Op. 16'
            };
            return {
              target: noteReadingTargetLetterCount(item),
              limited: noteReadingFormatLetters(noteReadingLimitedLetters(item.noteLetterAnswer, 8)),
              html: renderNoteReadingItem(item, 0)
            };
          })()`,
          context
        );
        assert(noteReading.target === 8, "note-reading cards must carry the visible target count");
        assert(noteReading.limited === "A B C D E F G A", "note-reading drafts must be capped at the requested count");
        assert(noteReading.html.includes('data-note-reading-target-count="8"'), "note-reading form must expose the target count");
        assert(noteReading.html.includes('data-note-reading-save'), "note-reading save button must be addressable separately from keypad keys");
        assert(noteReading.html.includes('8/8 ready'), "completed note-reading draft should show ready state instead of making the user count");
        assert(noteReading.html.includes('value="A B C D E F G A"'), "rendered note-reading input must drop extra notes");
        """
    )
    completed = subprocess.run(["node", "-e", script], cwd=".", text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr


def test_notation_styles_use_local_music_font_and_professional_glyph_sizes():
    css = Path("styles.css").read_text(encoding="utf-8")
    assert 'url("/assets/fonts/Bravura.woff2") format("woff2")' in css
    assert ".notation-abc-target" in css
    assert "min-width: 520px;" in css
    assert ".notation-sheet.notation-fit .notation-abc-target" in css
    assert "min-width: 0;" in css
    assert "scrollbar-width: thin;" in css
    assert ".notation-sheet.notation-abc-ready .notation-svg-fallback" in css
    assert ".notation-svg-fallback svg" in css
    assert ".notation-sheet svg" not in css
    assert ".notation-sheet .treble-clef" in css
    assert "width: max(100%, var(--notation-svg-width, 720px));" in css
    assert "min-width: var(--notation-svg-width, 720px);" in css
    assert ".notation-sheet.notation-fit" in css
    assert ".notation-sheet.notation-fit .notation-svg-fallback svg" in css
    assert ".gold-review-notation .notation-svg-fallback svg" in css
    assert "font-size: 62px;" in css
    assert ".notation-sheet .accidental-flat" in css
    assert "font-size: 33px;" in css
    assert ".notation-sheet .accidental-sharp" in css
    assert "font-size: 31px;" in css
    assert ".notation-sheet .key-signature-mark.accidental-flat" in css
    assert "font-size: 29px;" in css
    assert ".notation-sheet .key-signature-mark.accidental-sharp" in css
    assert "font-synthesis: none;" in css
    assert "text-rendering: geometricPrecision;" in css


def test_gold_review_training_lanes_use_user_facing_names():
    app = Path("app.js").read_text(encoding="utf-8")
    index = Path("index.html").read_text(encoding="utf-8")
    assert '"transcription-alan"' in app
    assert '"score-transcription"' in app
    assert "/app.js?v=20260523-note-reading-save-fix" in index
    assert '[(isScoreCopy ? "" : item.practiceDay), lane, agreement' in app
    assert "No review cards ready." in app
    assert "Refill pending." not in app
    assert "data-rejection-reason" in app
    assert "noteReadingTargetLetterCount" in app
    assert "data-note-reading-target-count" in app
    assert "data-note-reading-save" in app
    assert "function applyOps" in app
    assert "Need ${targetCount} note letters." in app
    assert "blocked source/audio match" in app
    assert "No user action." in app
    assert "Machine audit plots" in app
    assert "activeTrainingReason" in app
    assert "Audio transcription" not in app
    assert "Notation copy" not in app
    assert "Accept if copy matches source" not in app


def test_local_music_font_serves_as_font_file():
    from backend.app.main import static_assets

    response = asyncio.run(static_assets("fonts/Bravura.woff2"))
    assert response.media_type == "font/woff2"


def test_engraving_runtime_is_vendored_and_loaded_before_app_code():
    vendor = Path("assets/vendor/abcjs-basic-min.js")
    license_file = Path("assets/vendor/abcjs-basic-min.js.LICENSE")
    index = Path("index.html").read_text(encoding="utf-8")

    assert vendor.is_file(), "ABC engraver must be vendored locally for stable notation rendering"
    assert license_file.is_file(), "vendored ABC engraver license must ship with the asset"
    assert "MIT" in license_file.read_text(encoding="utf-8")
    assert "/assets/vendor/abcjs-basic-min.js" in index
    assert index.index("/assets/vendor/abcjs-basic-min.js") < index.index("/app.js"), "ABC engraver must load before app.js hydrates notation"
