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
        assert((noKey.match(/accidental-sharp-bar/g) || []).length === 4, "sharp glyphs need filled engraved crossbars");
        assert((noKey.match(/accidental-sharp-stem/g) || []).length === 4, "sharp glyphs need separate narrow stems");
        assert((noKey.match(/accidental-flat-stem/g) || []).length === 2, "flat glyphs need separate curved stems");
        assert((noKey.match(/accidental-flat-bowl/g) || []).length === 2, "flat glyphs need filled engraved bowls");
        assert(noKey.includes('class="treble-clef" x="24" y="72"'), "treble clef baseline must put the G-loop on the G line");
        assert(noKey.includes('viewBox="0 0 720 128"'), "notation viewBox must leave room for the full treble clef");
        assert(noKey.includes('font-size: 76px') === false, "notation renderer should not inline clef styling");
        assert(noKey.includes('aria-label="A#4"'), "A# must not render as natural A in aria label");
        assert(noKey.includes('aria-label="D#6"'), "D# must not render as natural D in aria label");
        assert(noKey.includes('translate(261.3 15.0)'), "high D# sharp must be kept inside the SVG viewBox");

        const flatKey = vm.runInContext(
          `renderNotationSheet([
            {kind:'note',note:'A#4'},
            {kind:'note',note:'D#6'}
          ], {keySignature:{accidentalType:'flat',accidentals:['Bb','Eb'],label:'G minor / 2 flats'}, maxNotes:2})`,
          context
        );
        assert((flatKey.match(/key-signature-mark accidental-glyph accidental-flat/g) || []).length === 2, "Bb/Eb key signature needs two flat glyphs");
        assert((flatKey.match(/key-signature-mark accidental-glyph accidental-flat/g) || []).length === (flatKey.match(/accidental-flat-bowl/g) || []).length, "every key-signature flat must use the professional flat glyph");
        assert(!flatKey.includes('note-accidental'), "key-signature-covered Bb/Eb notes must not draw duplicate local accidentals");
        assert(flatKey.includes('aria-label="Bb4 / detected A#4"'), "A# must respell as Bb in a flat key");
        assert(flatKey.includes('aria-label="Eb6 / detected D#6"'), "D# must respell as Eb in a flat key");
        """
    )
    completed = subprocess.run(["node", "-e", script], cwd=".", text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
