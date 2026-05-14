from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TREBLE_STEPS = ["E", "F", "G", "A", "B", "C", "D"]
PITCH_CLASS_VALUES = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}
PITCH_CLASS_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_KEY_STEPS = {"B", "E", "A", "D", "G", "C", "F"}
SHARP_KEY_STEPS = {"F", "C", "G", "D", "A", "E", "B"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an unaccepted score-glyph verification queue from a local score PDF page."
    )
    parser.add_argument("--pdf", required=True, help="Local score PDF path.")
    parser.add_argument("--page", type=int, default=2, help="1-based PDF page number.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--source-asset-id", default="", help="Curtis score asset id.")
    parser.add_argument("--source-title", default="", help="Human title for the source score.")
    parser.add_argument("--dpi", type=int, default=300, help="Render DPI.")
    parser.add_argument("--key-fifths", type=int, default=-2, help="Key signature fifths for pitch hypotheses.")
    return parser.parse_args()


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def render_pdf_page(pdf_path: Path, page: int, dpi: int) -> Path:
    executable = shutil.which("pdftoppm")
    if not executable:
        raise RuntimeError("pdftoppm is required to render score pages for candidate extraction.")
    with tempfile.TemporaryDirectory(prefix="curtis-score-page-") as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(
            [
                executable,
                "-f",
                str(page),
                "-l",
                str(page),
                "-png",
                "-r",
                str(dpi),
                str(pdf_path),
                str(prefix),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        rendered = sorted(Path(tmp).glob("page-*.png"))
        if not rendered:
            raise RuntimeError(f"No rendered page image produced for {pdf_path} page {page}.")
        persistent = Path(tmp + ".png")
        shutil.copyfile(rendered[0], persistent)
        return persistent


def row_line_runs(binary: np.ndarray, threshold_fraction: float = 0.15) -> list[tuple[int, int, float]]:
    height, width = binary.shape
    threshold = width * threshold_fraction
    row_counts = binary.sum(axis=1)
    runs: list[tuple[int, int, float]] = []
    start: int | None = None
    for row, count in enumerate(row_counts):
        if count > threshold and start is None:
            start = row
        if (count <= threshold or row == height - 1) and start is not None:
            end = row if count <= threshold else row + 1
            if 1 <= end - start <= 10:
                runs.append((start, end, (start + end - 1) / 2.0))
            start = None
    return runs


def staff_groups_from_runs(runs: list[tuple[int, int, float]]) -> list[dict[str, Any]]:
    centers = [run[2] for run in runs]
    groups: list[dict[str, Any]] = []
    used_until = -999
    for index in range(len(centers) - 4):
        gaps = [centers[index + offset + 1] - centers[index + offset] for offset in range(4)]
        average_gap = sum(gaps) / 4.0
        if not (12 <= average_gap <= 32):
            continue
        if max(abs(gap - average_gap) for gap in gaps) > 5:
            continue
        if index <= used_until:
            continue
        used_until = index + 4
        groups.append(
            {
                "staffId": len(groups) + 1,
                "lineCenters": [round(value, 2) for value in centers[index : index + 5]],
                "lineGap": round(average_gap, 2),
            }
        )
    return groups


def candidate_glyphs_for_staff(binary: np.ndarray, staff: dict[str, Any]) -> list[dict[str, Any]]:
    height, width = binary.shape
    line_centers = [float(value) for value in staff["lineCenters"]]
    line_gap = float(staff["lineGap"])
    top = max(0, int(line_centers[0] - line_gap * 5))
    bottom = min(height, int(line_centers[-1] + line_gap * 5))
    crop = binary[top:bottom, :].copy()
    for center in line_centers:
        row = int(round(center - top))
        crop[max(0, row - 1) : min(crop.shape[0], row + 2), :] = False
    labels, _ = ndimage.label(crop)
    objects = ndimage.find_objects(labels)
    glyphs: list[dict[str, Any]] = []
    for label, slices in enumerate(objects, start=1):
        if slices is None:
            continue
        y_slice, x_slice = slices
        y0, y1 = y_slice.start, y_slice.stop
        x0, x1 = x_slice.start, x_slice.stop
        box_width = x1 - x0
        box_height = y1 - y0
        area = int((labels[slices] == label).sum())
        center_x = (x0 + x1) / 2.0
        center_y = top + ((y0 + y1) / 2.0)
        if center_x < 250:
            continue
        if not (5 <= box_width <= 70 and 5 <= box_height <= 85 and 35 <= area <= 1400):
            continue
        if center_y < line_centers[0] - line_gap * 3.5 or center_y > line_centers[-1] + line_gap * 3.5:
            continue
        bottom_line = line_centers[-1]
        staff_step_estimate = int(round((bottom_line - center_y) / (line_gap / 2.0)))
        glyphs.append(
            {
                "glyphId": f"s{staff['staffId']}-g{len(glyphs) + 1}",
                "staffId": staff["staffId"],
                "bbox": {
                    "x": int(x0),
                    "y": int(top + y0),
                    "width": int(box_width),
                    "height": int(box_height),
                },
                "center": {"x": round(center_x, 2), "y": round(center_y, 2)},
                "area": area,
                "staffStepEstimate": staff_step_estimate,
                "status": "unverified_source_glyph",
            }
        )
    glyphs.sort(key=lambda item: (item["staffId"], item["center"]["x"], item["center"]["y"]))
    return glyphs


def note_name_for_staff_step(staff_step: int, key_fifths: int) -> tuple[str, str]:
    octave = 4 + ((staff_step + 2) // 7)
    step = TREBLE_STEPS[staff_step % len(TREBLE_STEPS)]
    accidental = ""
    if key_fifths < 0:
        flats = list("BEADGCF")[: min(7, abs(key_fifths))]
        if step in flats:
            accidental = "b"
    elif key_fifths > 0:
        sharps = list("FCGDAEB")[: min(7, key_fifths)]
        if step in sharps:
            accidental = "#"
    note_name = f"{step}{accidental}{octave}"
    pitch_key = f"{step}{accidental}"
    pitch_value = PITCH_CLASS_VALUES.get(pitch_key)
    pitch_class = PITCH_CLASS_NAMES[pitch_value] if pitch_value is not None else ""
    return note_name, pitch_class


def likely_notehead_glyph(glyph: dict[str, Any]) -> bool:
    bbox = glyph.get("bbox") if isinstance(glyph.get("bbox"), dict) else {}
    width = int(bbox.get("width") or 0)
    height = int(bbox.get("height") or 0)
    area = int(glyph.get("area") or 0)
    if not (10 <= width <= 48 and 10 <= height <= 30):
        return False
    if not (160 <= area <= 700):
        return False
    aspect = width / max(1, height)
    if not (0.65 <= aspect <= 2.8):
        return False
    return True


def note_hypotheses_from_glyphs(glyphs: list[dict[str, Any]], key_fifths: int) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    for glyph in glyphs:
        if not likely_notehead_glyph(glyph):
            continue
        staff_step = int(glyph.get("staffStepEstimate") or 0)
        note_name, pitch_class = note_name_for_staff_step(staff_step, key_fifths)
        if not note_name or not pitch_class:
            continue
        hypotheses.append(
            {
                "hypothesisId": f"{glyph['glyphId']}-note",
                "glyphId": glyph["glyphId"],
                "staffId": glyph["staffId"],
                "bbox": glyph["bbox"],
                "center": glyph["center"],
                "staffStepEstimate": staff_step,
                "writtenNoteHypothesis": note_name,
                "pitchClassHypothesis": pitch_class,
                "status": "unverified_notehead_hypothesis",
                "limit": "Staff-position pitch label only; not accepted score evidence until source-reviewed into MusicXML.",
            }
        )
    hypotheses.sort(key=lambda item: (item["staffId"], item["center"]["x"], item["center"]["y"]))
    return hypotheses


def build_candidate_map(args: argparse.Namespace) -> dict[str, Any]:
    pdf_path = resolve_path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    rendered_path = render_pdf_page(pdf_path, args.page, args.dpi)
    try:
        image = Image.open(rendered_path).convert("L")
        array = np.array(image)
        binary = array < 180
        staff_groups = staff_groups_from_runs(row_line_runs(binary))
        glyphs: list[dict[str, Any]] = []
        for staff in staff_groups:
            staff_glyphs = candidate_glyphs_for_staff(binary, staff)
            staff["candidateGlyphCount"] = len(staff_glyphs)
            glyphs.extend(staff_glyphs)
        note_hypotheses = note_hypotheses_from_glyphs(glyphs, args.key_fifths)
        note_hypothesis_staves = len({item["staffId"] for item in note_hypotheses})
        sequence_preview = [
            str(item["pitchClassHypothesis"])
            for item in note_hypotheses
            if str(item.get("pitchClassHypothesis") or "").strip()
        ][:80]
        return {
            "schema": "curtis_score_map_candidates_v2",
            "status": "candidate_not_accepted",
            "acceptedEvidence": False,
            "sourceAssetId": args.source_asset_id,
            "sourceTitle": args.source_title,
            "sourcePdfLocalPath": str(args.pdf),
            "sourcePdfPage": args.page,
            "dpi": args.dpi,
            "keyFifths": args.key_fifths,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "extractionMethod": "staff-line-connected-glyph-and-notehead-hypothesis-queue-v2",
            "verificationLimit": (
                "These are unverified score glyph coordinates from the local score page. "
                "Notehead hypotheses use staff position and key signature only. They must be "
                "source-reviewed into MusicXML before any pitch label, score crop, or audio match "
                "can be shown as accepted Curtis evidence."
            ),
            "staffCount": len(staff_groups),
            "candidateGlyphCount": len(glyphs),
            "noteHypothesisCount": len(note_hypotheses),
            "noteHypothesisStaffCount": note_hypothesis_staves,
            "noteHypothesisSequencePreview": " ".join(sequence_preview),
            "staffGroups": staff_groups,
            "candidateGlyphs": glyphs,
            "noteHypotheses": note_hypotheses,
            "nextVerificationStep": (
                "Review the notehead hypotheses against the local IMSLP PDF, convert verified notes into "
                "MusicXML, then run source-target matching against verified symbolic notes only."
            ),
        }
    finally:
        try:
            rendered_path.unlink()
        except OSError:
            pass


def main() -> None:
    args = parse_args()
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = build_candidate_map(args)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {data['candidateGlyphCount']} unaccepted score glyph candidates "
        f"and {data['noteHypothesisCount']} unaccepted note hypotheses "
        f"across {data['staffCount']} staves to {output}"
    )


if __name__ == "__main__":
    main()
