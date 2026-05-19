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
SYMBOLIC_STAFF_TOP = 40.0
SYMBOLIC_STAFF_LINE_GAP = 12.0
SYMBOLIC_STAFF_BOTTOM = SYMBOLIC_STAFF_TOP + (SYMBOLIC_STAFF_LINE_GAP * 4)
SYMBOLIC_G4_Y = SYMBOLIC_STAFF_TOP + (SYMBOLIC_STAFF_LINE_GAP * 3)
SYMBOLIC_STAFF_STEP_Y = SYMBOLIC_STAFF_LINE_GAP / 2
SYMBOLIC_LEDGER_HALF_WIDTH = 12.0
SYMBOLIC_KEY_SIGNATURE_START_X = 96
SYMBOLIC_KEY_SIGNATURE_STEP_X = 16
SYMBOLIC_NOTEHEAD_FONT_SIZE = 40
SYMBOLIC_ACCIDENTAL_FONT_SIZE = 38
SYMBOLIC_CLEF_FONT_SIZE = 66
SYMBOLIC_STEM_OFFSET_X = 6.6
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
        and not source_range_rejected(target, item.get("referenceStart"), item.get("referenceEnd"))
        and str(item.get("imageUrl") or "").strip()
        and item.get("visualRangeAgreement") is True
        and item.get("visibleScoreNoteSequenceVerified") is True
        and item.get("visibleScoreExactNoteSequenceVerified") is True
        and item.get("scoreBoxCenterAgreement") is True
        and item.get("audioTranscriptionAgreement") is True
        and item.get("transcriptionScoreAgreement") is True
        and item.get("truthEvidenceAccepted") is True
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


def source_range_rejected(target: dict[str, Any], reference_start: Any, reference_end: Any) -> bool:
    score_config = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    rejected = score_config.get("rejectedSourceSnippetRanges")
    if not isinstance(rejected, list):
        return False
    try:
        start = int(reference_start)
        end = int(reference_end)
    except (TypeError, ValueError):
        return False
    for item in rejected:
        if not isinstance(item, dict):
            continue
        try:
            rejected_start = int(item.get("referenceStart"))
            rejected_end = int(item.get("referenceEnd"))
        except (TypeError, ValueError):
            continue
        if rejected_start != start or rejected_end != end:
            continue
        status = str(item.get("status") or "").lower()
        if "rejected" in status or "mismatch" in status or "blocked" in status:
            return True
    return False


def source_image_url_rejected(
    target: dict[str, Any],
    reference_start: Any,
    reference_end: Any,
    image_url: Any,
) -> bool:
    image = str(image_url or "").strip()
    if not image:
        return False
    score_config = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    rejected = score_config.get("rejectedSourceSnippetRanges")
    if not isinstance(rejected, list):
        return False
    try:
        start = int(reference_start)
        end = int(reference_end)
    except (TypeError, ValueError):
        return False
    for item in rejected:
        if not isinstance(item, dict):
            continue
        try:
            rejected_start = int(item.get("referenceStart"))
            rejected_end = int(item.get("referenceEnd"))
        except (TypeError, ValueError):
            continue
        if rejected_start != start or rejected_end != end:
            continue
        blocked_images = [
            str(value or "").strip()
            for value in (
                item.get("blockedImageUrls")
                if isinstance(item.get("blockedImageUrls"), list)
                else []
            )
            if str(value or "").strip()
        ]
        blocked_image = str(item.get("blockedImageUrl") or "").strip()
        if blocked_image:
            blocked_images.append(blocked_image)
        if image in blocked_images:
            return True
    return False


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
    step = _natural_note_step(note_name)
    if step is None:
        return SYMBOLIC_STAFF_TOP + (SYMBOLIC_STAFF_LINE_GAP * 2)
    g4_step = (4 * 7) + TREBLE_NOTE_ORDER["G"]
    return SYMBOLIC_G4_Y - ((step - g4_step) * SYMBOLIC_STAFF_STEP_Y)


def _ledger_lines(y: float, x: float) -> str:
    lines: list[str] = []
    line_y = SYMBOLIC_STAFF_BOTTOM + SYMBOLIC_STAFF_LINE_GAP
    while line_y <= y + 0.1:
        lines.append(f'<line class="ledger" x1="{x - SYMBOLIC_LEDGER_HALF_WIDTH:.1f}" x2="{x + SYMBOLIC_LEDGER_HALF_WIDTH:.1f}" y1="{line_y:.1f}" y2="{line_y:.1f}" />')
        line_y += SYMBOLIC_STAFF_LINE_GAP
    line_y = SYMBOLIC_STAFF_TOP - SYMBOLIC_STAFF_LINE_GAP
    while line_y >= y - 0.1:
        lines.append(f'<line class="ledger" x1="{x - SYMBOLIC_LEDGER_HALF_WIDTH:.1f}" x2="{x + SYMBOLIC_LEDGER_HALF_WIDTH:.1f}" y1="{line_y:.1f}" y2="{line_y:.1f}" />')
        line_y -= SYMBOLIC_STAFF_LINE_GAP
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
    glyph = "&#xE260;" if accidental_type == "flat" else "&#xE262;" if accidental_type == "sharp" else ""
    if not glyph:
        return "", 0.0
    marks: list[str] = []
    for index, accidental in enumerate(accidentals[:7]):
        y = treble_positions.get(accidental)
        if y is None:
            continue
        x = SYMBOLIC_KEY_SIGNATURE_START_X + (index * SYMBOLIC_KEY_SIGNATURE_STEP_X)
        marks.append(f'<text class="key-signature" x="{x}" y="{y:.1f}">{glyph}</text>')
    return "".join(marks), float(len(marks) * SYMBOLIC_KEY_SIGNATURE_STEP_X)


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
        stem_x = x + (SYMBOLIC_STEM_OFFSET_X if stem_up else -SYMBOLIC_STEM_OFFSET_X)
        stem_y = max(15, y - 34) if stem_up else min(108, y + 34)
        marks.append(
            "".join(
                [
                    f'<g class="note" aria-label="{escape(str(note.get("note") or ""))}">',
                    _ledger_lines(y, x),
                    f'<text class="notehead" x="{x:.1f}" y="{y:.1f}">&#xE0A4;</text>',
                    f'<line x1="{stem_x:.1f}" x2="{stem_x:.1f}" y1="{y:.1f}" y2="{stem_y:.1f}" />',
                    "</g>",
                ]
            )
        )
    css = (
        "<style>"
        "svg{background:#fffdf8;color:#1b2524;font-family:Georgia,'Times New Roman',serif}"
        ".staff line,.ledger{stroke:#1f2928;stroke-width:1.45;stroke-linecap:square}"
        ".note line{fill:#1f2928;stroke:#1f2928;stroke-width:1.8;stroke-linecap:round}"
        f".clef{{font-family:'CurtisBravura','Bravura','Noto Music','Segoe UI Symbol',serif;font-size:{SYMBOLIC_CLEF_FONT_SIZE}px;fill:#1f2928;font-synthesis:none;text-rendering:geometricPrecision}}"
        f".key-signature{{font-family:'CurtisBravura','Bravura','Noto Music','Segoe UI Symbol',serif;font-size:{SYMBOLIC_ACCIDENTAL_FONT_SIZE}px;font-weight:400;fill:#1f2928;dominant-baseline:central;text-anchor:middle;font-synthesis:none;text-rendering:geometricPrecision}}"
        f".notehead{{font-family:'CurtisBravura','Bravura','Noto Music','Segoe UI Symbol',serif;font-size:{SYMBOLIC_NOTEHEAD_FONT_SIZE}px;fill:#1f2928;dominant-baseline:central;text-anchor:middle;font-synthesis:none;text-rendering:geometricPrecision}}"
        ".title{font-size:16px;font-weight:600}.label{font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}"
        "</style>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -24 {width} 148" role="img">'
        f"{css}{title_markup}{label_markup}<g class=\"staff\">{staff_lines}</g>"
        f'<text class="clef" x="48" y="78">&#xE050;</text>{key_marks}'
        f"{''.join(marks)}</svg>"
    )
