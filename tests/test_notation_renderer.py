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
          window: {},
          document: {
            addEventListener() {},
            querySelector() { return null; },
            querySelectorAll() { return []; },
            getElementById() { return null; },
            body: {},
          },
          navigator: {},
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
        assert(noKey.includes('data-abc='), "browser notation must carry ABC source for the real engraver");
        assert(noKey.includes('M:none'), "ABC snippets must not invent a visible time signature when rhythm is not accepted");
        assert(noKey.includes('K:C clef=treble'), "ABC source must force treble clef");
        assert(noKey.includes('^A ^d'), "ABC source must preserve sharp pitches instead of dropping accidentals");
        assert(noKey.includes('_B _e'), "ABC source must preserve flat pitches instead of dropping accidentals");
        assert(noKey.includes('notation-svg-fallback'), "manual SVG must remain only as a no-JavaScript fallback");
        assert((noKey.match(/accidental-glyph accidental-sharp/g) || []).length === 2, "A# and D# need visible sharp glyphs");
        assert((noKey.match(/accidental-glyph accidental-flat/g) || []).length === 2, "Bb and Eb need visible flat glyphs");
        assert((noKey.match(/&#xE262;/g) || []).length === 2, "sharps must use the Bravura/SMuFL sharp glyph");
        assert((noKey.match(/&#xE260;/g) || []).length === 2, "flats must use the Bravura/SMuFL flat glyph");
        assert((noKey.match(/class="notehead"/g) || []).length === 4, "notes must use music-font noteheads");
        assert((noKey.match(/&#xE0A4;/g) || []).length === 4, "quarter-note noteheads must use the Bravura/SMuFL black notehead glyph");
        assert(!noKey.includes("<ellipse"), "notation renderer must not use rough SVG ellipses for noteheads");
        assert(noKey.includes('class="treble-clef" x="24" y="67" aria-label="treble clef">&#xE050;</text>'), "treble clef must use the Bravura/SMuFL glyph and sit higher on the G line");
        assert(noKey.includes('viewBox="0 -18 720 150"'), "notation viewBox must leave room for high ledger notes and the full treble clef");
        assert(noKey.includes('&#119070;') === false, "notation renderer must not fall back to the generic G-clef glyph");
        assert(noKey.includes('font-size: 70px') === false, "notation renderer should not inline clef styling");
        assert(noKey.includes('aria-label="A#4"'), "A# must not render as natural A in aria label");
        assert(noKey.includes('aria-label="D#6"'), "D# must not render as natural D in aria label");
        assert(noKey.includes('class="note-accidental accidental-glyph accidental-sharp" x="92.0" y="55.0"'), "first-note A# sharp needs professional clearance before the notehead");
        assert(noKey.includes('class="note-accidental accidental-glyph accidental-sharp" x="282.7" y="5.0"'), "high D# sharp must stay vertically aligned with the high notehead");

        const flatKey = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'A#4'},
            {kind:'note',note:'D#6'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:2})`,
          context
        );
        assert(flatKey.includes('K:Bb clef=treble'), "ABC source must carry the flat-key treble signature");
        assert(flatKey.includes('B e'), "key-signature-covered flats should use the key signature, not duplicate local flats");
        assert(!flatKey.includes('_B'), "Bb covered by the key signature must not render as a separate local flat in ABC");
        assert(!flatKey.includes('_e'), "Eb covered by the key signature must not render as a separate local flat in ABC");
        assert((flatKey.match(/key-signature-mark accidental-glyph accidental-flat/g) || []).length === 2, "Bb/Eb key signature needs two flat glyphs");
        assert(flatKey.includes('class="key-signature-mark accidental-glyph accidental-flat" x="63.0" y="50.0"'), "key-signature Bb flat must sit on B, not A");
        assert(flatKey.includes('class="key-signature-mark accidental-glyph accidental-flat" x="79.0" y="35.0"'), "key-signature Eb flat must sit on E, not D");
        assert(!flatKey.includes('note-accidental'), "key-signature-covered Bb/Eb notes must not draw duplicate local accidentals");
        assert(flatKey.includes('aria-label="Bb4 / detected A#4"'), "A# must respell as Bb in a flat key");
        assert(flatKey.includes('aria-label="Eb6 / detected D#6"'), "D# must respell as Eb in a flat key");

        const naturalInFlatKey = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'B4'},
            {kind:'note',note:'E5'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:2})`,
          context
        );
        assert(naturalInFlatKey.includes('=B =e'), "natural B/E in a flat key must carry natural signs in ABC");
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
        assert(measureAccidentals.includes('^g =g ^g =g'), "same-measure G# G G# G must engrave sharp, natural, sharp, natural");
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
        assert(readableGoldReview.sheet.includes('K:Bb clef=treble'), "Scherzo-Tarantelle Gold Review snippets must engrave with G minor/two-flat context");
        assert(readableGoldReview.sheet.includes('^g'), "G# outside the G-minor key signature must render as a local sharp sign");
        assert(readableGoldReview.sheet.includes('^c'), "C# outside the G-minor key signature must render as a local sharp sign");
        assert(!readableGoldReview.sheet.includes('_d'), "C# must not render as Db in G-minor review notation");
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
        assert(unknownReview.sheet.includes('K:C clef=treble'), "unlabeled review notation should render literal accidentals in neutral treble context");
        assert(unknownReview.sheet.includes('^A') && unknownReview.sheet.includes('^c') && unknownReview.sheet.includes('^d'), "literal sharps must remain visible for unknown source context");
        """
    )
    completed = subprocess.run(["node", "-e", script], cwd=".", text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr


def test_notation_styles_use_local_music_font_and_professional_glyph_sizes():
    css = Path("styles.css").read_text(encoding="utf-8")
    assert 'url("/assets/fonts/Bravura.woff2") format("woff2")' in css
    assert ".notation-abc-target" in css
    assert "min-width: 520px;" in css
    assert "scrollbar-width: thin;" in css
    assert ".notation-sheet.notation-abc-ready .notation-svg-fallback" in css
    assert ".notation-svg-fallback svg" in css
    assert ".notation-sheet svg" not in css
    assert ".notation-sheet .treble-clef" in css
    assert "font-size: 68px;" in css
    assert ".notation-sheet .accidental-flat" in css
    assert "font-size: 38px;" in css
    assert ".notation-sheet .accidental-sharp" in css
    assert "font-size: 36px;" in css
    assert "font-synthesis: none;" in css
    assert "text-rendering: geometricPrecision;" in css


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
