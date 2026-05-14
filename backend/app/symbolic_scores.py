from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


NOTE_CLASS_VALUES = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}

PITCH_CLASS_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
TREBLE_NOTE_ORDER = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if _local_name(child.tag) == name:
            return child
    return None


def _child_text(element: ET.Element, name: str, default: str = "") -> str:
    child = _child(element, name)
    return (child.text or "").strip() if child is not None and child.text is not None else default


def _int_text(element: ET.Element | None, name: str, default: int = 0) -> int:
    if element is None:
        return default
    raw = _child_text(element, name, "")
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def normalize_pitch_class(value: Any) -> str:
    raw = str(value or "").strip().upper().replace("FLAT", "B").replace("SHARP", "#")
    if not raw:
        return ""
    if len(raw) >= 2 and raw[1] in {"#", "B"}:
        pitch = raw[:2]
    else:
        pitch = raw[:1]
    note_value = NOTE_CLASS_VALUES.get(pitch)
    return PITCH_CLASS_NAMES[note_value] if note_value is not None else ""


def pitch_class_from_components(step: str, alter: int = 0) -> str:
    step = str(step or "").strip().upper()
    if step not in TREBLE_NOTE_ORDER:
        return ""
    value = (NOTE_CLASS_VALUES[step] + int(alter or 0)) % 12
    return PITCH_CLASS_NAMES[value]


def note_name_from_components(step: str, alter: int, octave: int) -> str:
    step = str(step or "").strip().upper()
    if step not in TREBLE_NOTE_ORDER:
        return ""
    suffix = ""
    if int(alter or 0) > 0:
        suffix = "#" * int(alter or 0)
    elif int(alter or 0) < 0:
        suffix = "b" * abs(int(alter or 0))
    return f"{step}{suffix}{int(octave)}"


def midi_from_components(step: str, alter: int, octave: int) -> int | None:
    pitch_class = pitch_class_from_components(step, alter)
    value = NOTE_CLASS_VALUES.get(pitch_class.upper())
    if value is None:
        return None
    return (int(octave) + 1) * 12 + value


def _score_title(root: ET.Element, fallback: str = "") -> str:
    for name in ("movement-title", "work-title"):
        for element in root.iter():
            if _local_name(element.tag) == name and element.text:
                value = element.text.strip()
                if value:
                    return value
    return fallback


def parse_musicxml_score(xml_text: str, *, source_id: str = "", title: str = "", part_id: str = "") -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    selected_part = None
    for part in root.iter():
        if _local_name(part.tag) != "part":
            continue
        current_id = str(part.attrib.get("id") or "").strip()
        if part_id and current_id != part_id:
            continue
        if any(_local_name(note.tag) == "note" and _child(note, "pitch") is not None for note in part.iter()):
            selected_part = part
            break
    if selected_part is None:
        return {"sourceId": source_id, "title": _score_title(root, title), "partId": part_id, "notes": []}

    notes: list[dict[str, Any]] = []
    divisions = 1
    note_index = 0
    part_identifier = str(selected_part.attrib.get("id") or part_id or "").strip()
    for measure_order, measure in enumerate(_children(selected_part, "measure"), start=1):
        measure_number = str(measure.attrib.get("number") or measure_order)
        attributes = _child(measure, "attributes")
        if attributes is not None:
            divisions = max(1, _int_text(attributes, "divisions", divisions))
        for note in _children(measure, "note"):
            if _child(note, "rest") is not None:
                continue
            pitch = _child(note, "pitch")
            if pitch is None:
                continue
            step = _child_text(pitch, "step", "").upper()
            alter = _int_text(pitch, "alter", 0)
            octave = _int_text(pitch, "octave", 4)
            pitch_class = pitch_class_from_components(step, alter)
            display_note = note_name_from_components(step, alter, octave)
            midi = midi_from_components(step, alter, octave)
            if not pitch_class or not display_note or midi is None:
                continue
            duration = _int_text(note, "duration", 0)
            duration_kind = _child_text(note, "type", "quarter") or "quarter"
            note_index += 1
            notes.append(
                {
                    "note": display_note,
                    "pitchClass": pitch_class,
                    "midi": midi,
                    "step": step,
                    "alter": alter,
                    "octave": octave,
                    "measure": measure_number,
                    "measureOrder": measure_order,
                    "noteIndex": note_index,
                    "partId": part_identifier,
                    "durationDivisions": duration,
                    "divisions": divisions,
                    "durationKind": duration_kind,
                    "chord": _child(note, "chord") is not None,
                    "grace": _child(note, "grace") is not None,
                }
            )
    return {"sourceId": source_id, "title": _score_title(root, title), "partId": part_identifier, "notes": notes}


def symbolic_score_from_target(target: dict[str, Any]) -> dict[str, Any]:
    score = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    if not score:
        return {}
    if isinstance(score.get("notes"), list):
        notes = [note for note in score["notes"] if isinstance(note, dict) and note.get("pitchClass")]
        return {
            "sourceId": score.get("sourceId") or target.get("scoreAssetId") or "",
            "title": score.get("title") or target.get("work") or "",
            "partId": score.get("partId") or target.get("part") or "",
            "notes": notes,
        }
    xml_text = _musicxml_text_from_score(score)
    if not xml_text:
        return {}
    try:
        return parse_musicxml_score(
            xml_text,
            source_id=str(score.get("sourceId") or target.get("scoreAssetId") or ""),
            title=str(score.get("title") or target.get("work") or ""),
            part_id=str(score.get("partId") or ""),
        )
    except ET.ParseError:
        return {}


def _read_musicxml_path(path_value: str) -> str:
    raw_path = Path(path_value)
    path = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
    if not path.exists() or not path.is_file():
        return ""
    if path.suffix.lower() == ".mxl":
        try:
            with ZipFile(path) as archive:
                candidates = [
                    name
                    for name in archive.namelist()
                    if name.lower().endswith(".xml") and not name.lower().startswith("meta-inf/")
                ]
                if not candidates:
                    return ""
                return archive.read(candidates[0]).decode("utf-8", errors="replace").strip()
        except (BadZipFile, OSError):
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_json_path(path_value: str) -> dict[str, Any]:
    raw_path = Path(path_value)
    path = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _musicxml_text_from_score(score: dict[str, Any]) -> str:
    inline = str(score.get("musicXml") or score.get("musicXML") or score.get("xml") or "").strip()
    if inline:
        return inline
    path_value = str(score.get("musicXmlPath") or score.get("musicXMLPath") or score.get("xmlPath") or "").strip()
    return _read_musicxml_path(path_value) if path_value else ""


def symbolic_score_audit(target: dict[str, Any]) -> dict[str, Any]:
    score = symbolic_score_from_target(target)
    notes = score.get("notes") if isinstance(score.get("notes"), list) else []
    score_config = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    source_snippets = [
        item
        for item in score_config.get("sourceSnippets", [])
        if isinstance(item, dict)
        and str(item.get("imageUrl") or "").strip()
        and "verified" in str(item.get("status") or item.get("verification") or "").lower()
    ] if isinstance(score_config.get("sourceSnippets"), list) else []
    return {
        "status": "symbolic_score_ready" if notes else "symbolic_score_missing",
        "symbolicScoreNoteCount": len(notes),
        "symbolicScoreSourceSnippetCount": len(source_snippets),
        "symbolicScoreSourceId": score.get("sourceId") or "",
        "symbolicScoreTitle": score.get("title") or "",
        "symbolicScorePartId": score.get("partId") or "",
    }


def score_map_candidate_audit(target: dict[str, Any]) -> dict[str, Any]:
    score_config = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    path_value = str(
        score_config.get("candidateMapPath")
        or score_config.get("scoreMapCandidatePath")
        or target.get("scoreMapCandidatePath")
        or ""
    ).strip()
    if not path_value:
        return {
            "status": "score_map_candidates_missing",
            "scoreMapCandidateGlyphCount": 0,
            "scoreMapCandidateStaffCount": 0,
            "scoreMapCandidatesAccepted": False,
            "scoreMapCandidatePath": "",
        }
    data = _read_json_path(path_value)
    glyphs = data.get("candidateGlyphs") if isinstance(data.get("candidateGlyphs"), list) else []
    note_hypotheses = data.get("noteHypotheses") if isinstance(data.get("noteHypotheses"), list) else []
    review_packets = data.get("reviewPackets") if isinstance(data.get("reviewPackets"), list) else []
    staff_groups = data.get("staffGroups") if isinstance(data.get("staffGroups"), list) else []
    accepted = bool(data.get("acceptedEvidence"))
    count = int(data.get("candidateGlyphCount") or len(glyphs) or 0)
    staff_count = int(data.get("staffCount") or len(staff_groups) or 0)
    note_hypothesis_count = int(data.get("noteHypothesisCount") or len(note_hypotheses) or 0)
    note_hypothesis_staff_count = int(
        data.get("noteHypothesisStaffCount")
        or len({item.get("staffId") for item in note_hypotheses if isinstance(item, dict)})
        or 0
    )
    return {
        "status": "score_map_candidates_ready" if count else "score_map_candidates_empty",
        "scoreMapCandidateGlyphCount": count,
        "scoreMapCandidateStaffCount": staff_count,
        "scoreMapNoteHypothesisCount": note_hypothesis_count,
        "scoreMapNoteHypothesisStaffCount": note_hypothesis_staff_count,
        "scoreMapNoteHypothesisSequencePreview": str(data.get("noteHypothesisSequencePreview") or ""),
        "scoreMapReviewPacketCount": int(data.get("reviewPacketCount") or len(review_packets) or 0),
        "scoreMapCandidatesAccepted": accepted,
        "scoreMapCandidatePath": path_value,
        "scoreMapCandidateSourcePage": data.get("sourcePdfPage") or 0,
        "scoreMapCandidateExtractionMethod": str(data.get("extractionMethod") or ""),
        "scoreMapCandidateLimit": str(data.get("verificationLimit") or ""),
    }


def compact_pitch_classes(values: list[str]) -> list[str]:
    compact: list[str] = []
    for value in values:
        current = normalize_pitch_class(value)
        if current and (not compact or compact[-1] != current):
            compact.append(current)
    return compact


def longest_common_contiguous_run(query: list[str], reference: list[str]) -> dict[str, int]:
    best = {"length": 0, "queryStart": 0, "referenceStart": 0}
    if not query or not reference:
        return best
    previous = [0] * (len(reference) + 1)
    for query_index, query_value in enumerate(query, start=1):
        current = [0] * (len(reference) + 1)
        for reference_index, reference_value in enumerate(reference, start=1):
            if query_value != reference_value:
                continue
            length = previous[reference_index - 1] + 1
            current[reference_index] = length
            if length > best["length"]:
                best = {
                    "length": length,
                    "queryStart": query_index - length,
                    "referenceStart": reference_index - length,
                }
        previous = current
    return best


def _natural_note_step(note_name: str) -> int | None:
    raw = str(note_name or "").strip()
    if len(raw) < 2:
        return None
    step = raw[0].upper()
    octave_char = raw[-1]
    if step not in TREBLE_NOTE_ORDER or not octave_char.isdigit():
        return None
    return (int(octave_char) * 7) + TREBLE_NOTE_ORDER[step]


def _staff_y(note_name: str) -> float:
    staff_top = 40.0
    line_gap = 12.0
    g4_y = staff_top + (line_gap * 3)
    step_y = line_gap / 2
    step = _natural_note_step(note_name)
    if step is None:
        return staff_top + (line_gap * 2)
    g4_step = (4 * 7) + TREBLE_NOTE_ORDER["G"]
    return g4_y - ((step - g4_step) * step_y)


def _ledger_lines(y: float, x: float) -> str:
    lines: list[str] = []
    staff_top = 40.0
    line_gap = 12.0
    staff_bottom = staff_top + (line_gap * 4)
    line_y = staff_bottom + line_gap
    while line_y <= y + 0.1:
        lines.append(f'<line class="ledger" x1="{x - 13:.1f}" x2="{x + 13:.1f}" y1="{line_y:.1f}" y2="{line_y:.1f}" />')
        line_y += line_gap
    line_y = staff_top - line_gap
    while line_y >= y - 0.1:
        lines.append(f'<line class="ledger" x1="{x - 13:.1f}" x2="{x + 13:.1f}" y1="{line_y:.1f}" y2="{line_y:.1f}" />')
        line_y -= line_gap
    return "".join(lines)


def _key_signature_marks(key_signature: dict[str, Any] | None) -> tuple[str, float]:
    if not isinstance(key_signature, dict):
        return "", 0.0
    accidentals = [
        str(item or "").strip()
        for item in key_signature.get("accidentals", [])
        if str(item or "").strip()
    ]
    accidental_type = str(key_signature.get("accidentalType") or "").strip().lower()
    if not accidentals:
        return "", 0.0
    treble_positions = {
        "Bb": _staff_y("B4"),
        "Eb": _staff_y("E5"),
        "Ab": _staff_y("A4"),
        "Db": _staff_y("D5"),
        "Gb": _staff_y("G4"),
        "Cb": _staff_y("C5"),
        "Fb": _staff_y("F4"),
        "F#": _staff_y("F5"),
        "C#": _staff_y("C5"),
        "G#": _staff_y("G5"),
        "D#": _staff_y("D5"),
        "A#": _staff_y("A4"),
        "E#": _staff_y("E5"),
        "B#": _staff_y("B4"),
    }
    glyph = "♭" if accidental_type == "flat" else "♯" if accidental_type == "sharp" else ""
    if not glyph:
        return "", 0.0
    marks: list[str] = []
    for index, accidental in enumerate(accidentals[:7]):
        y = treble_positions.get(accidental)
        if y is None:
            continue
        x = 96 + (index * 16)
        marks.append(f'<text class="key-signature" x="{x}" y="{y + 7:.1f}">{escape(glyph)}</text>')
    return "".join(marks), float(len(marks) * 16)


def render_symbolic_score_svg(
    notes: list[dict[str, Any]],
    *,
    title: str = "",
    label: str = "",
    key_signature: dict[str, Any] | None = None,
) -> str:
    visible_notes = notes[:16]
    key_marks, key_width = _key_signature_marks(key_signature)
    width = max(520, int(182 + key_width + (len(visible_notes) * 46)))
    staff_lines = "".join(f'<line x1="44" x2="{width - 36}" y1="{y}" y2="{y}" />' for y in (40, 52, 64, 76, 88))
    title_markup = f'<text class="title" x="{width - 40}" y="22" text-anchor="end">{escape(title)}</text>' if title else ""
    label_markup = f'<text class="label" x="44" y="22">{escape(label)}</text>' if label else ""
    marks: list[str] = []
    start_x = 118 + key_width
    step_x = 46 if len(visible_notes) > 1 else 0
    for index, note in enumerate(visible_notes):
        x = start_x + (index * step_x)
        y = _staff_y(str(note.get("note") or ""))
        stem_up = y >= 64
        stem_x = x + (6 if stem_up else -6)
        stem_y = max(15, y - 34) if stem_up else min(108, y + 34)
        marks.append(
            "".join(
                [
                    f'<g class="note" aria-label="{escape(str(note.get("note") or ""))}">',
                    _ledger_lines(y, x),
                    f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="7.0" ry="4.6" transform="rotate(-16 {x:.1f} {y:.1f})" />',
                    f'<line x1="{stem_x:.1f}" x2="{stem_x:.1f}" y1="{y:.1f}" y2="{stem_y:.1f}" />',
                    "</g>",
                ]
            )
        )
    css = (
        "<style>"
        "svg{background:#fffdf8;color:#1b2524;font-family:Georgia,'Times New Roman',serif}"
        ".staff line,.ledger{stroke:#1f2928;stroke-width:1.45;stroke-linecap:square}"
        ".note ellipse,.note line{fill:#1f2928;stroke:#1f2928;stroke-width:1.2}"
        ".clef{font-family:'Bravura','Noto Music','Segoe UI Symbol',serif;font-size:76px;fill:#1f2928}"
        ".key-signature{font-family:Georgia,'Times New Roman',serif;font-size:34px;font-weight:700;fill:#1f2928}"
        ".title{font-size:16px;font-weight:600}.label{font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}"
        "</style>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 124" role="img">'
        f"{css}{title_markup}{label_markup}<g class=\"staff\">{staff_lines}</g>"
        f'<text class="clef" x="48" y="88">&#119070;</text>{key_marks}'
        f"{''.join(marks)}</svg>"
    )
