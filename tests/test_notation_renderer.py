import subprocess
import textwrap


def test_notation_renderer_draws_exact_accidentals():
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
        assert(noKey.includes('class="note-accidental accidental-glyph accidental-sharp" x="262.3" y="15.0"'), "high D# sharp must be kept inside the SVG viewBox");

        const flatKey = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'A#4'},
            {kind:'note',note:'D#6'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:2})`,
          context
        );
        assert((flatKey.match(/key-signature-mark accidental-glyph accidental-flat/g) || []).length === 2, "Bb/Eb key signature needs two flat glyphs");
        assert(flatKey.includes('class="key-signature-mark accidental-glyph accidental-flat" x="63.0" y="50.0"'), "key-signature Bb flat must sit on B, not A");
        assert(flatKey.includes('class="key-signature-mark accidental-glyph accidental-flat" x="79.0" y="35.0"'), "key-signature Eb flat must sit on E, not D");
        assert(!flatKey.includes('note-accidental'), "key-signature-covered Bb/Eb notes must not draw duplicate local accidentals");
        assert(flatKey.includes('aria-label="Bb4 / detected A#4"'), "A# must respell as Bb in a flat key");
        assert(flatKey.includes('aria-label="Eb6 / detected D#6"'), "D# must respell as Eb in a flat key");
        """
    )
    completed = subprocess.run(["node", "-e", script], cwd=".", text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
