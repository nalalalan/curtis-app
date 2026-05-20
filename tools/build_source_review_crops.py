from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "assets" / "score" / "original" / "source-score-library.json"
PUBLIC_PREFIX = "/assets/score/original/source-library/"


def _dark_mask(image: Image.Image) -> np.ndarray:
    arr = np.asarray(image.convert("L"))
    return arr < 214


def _dark_row_regions(mask: np.ndarray) -> list[tuple[int, int, int]]:
    height, width = mask.shape
    row = mask.sum(axis=1)
    threshold = max(24, int(width * 0.035))
    ys = np.where(row > threshold)[0]
    if len(ys) == 0:
        return [(0, height - 1, int(row.max(initial=0)))]

    regions: list[tuple[int, int, int]] = []
    start = prev = int(ys[0])
    for raw_y in ys[1:]:
        y = int(raw_y)
        if y - prev > 24:
            if prev - start >= 20:
                regions.append((start, prev, int(row[start : prev + 1].max(initial=0))))
            start = y
        prev = y
    if prev - start >= 20:
        regions.append((start, prev, int(row[start : prev + 1].max(initial=0))))
    return regions


def _choose_music_region(mask: np.ndarray) -> tuple[int, int, int | None]:
    height, width = mask.shape
    regions = _dark_row_regions(mask)
    music_threshold = max(280, int(width * 0.24))
    for top, bottom, row_score in regions:
        if row_score >= music_threshold:
            next_top = next((region[0] for region in regions if region[0] > bottom), None)
            # A review target should be a snippet, not the whole page. Keep
            # the first real system and avoid cutting into the next system.
            return top, min(height - 1, top + 245, bottom + 42), next_top

    top, bottom, _ = max(regions, key=lambda region: region[2])
    next_top = next((region[0] for region in regions if region[0] > bottom), None)
    return top, min(height - 1, top + 245, bottom + 42), next_top


def _x_bounds(mask: np.ndarray, y0: int, y1: int, width: int) -> tuple[int, int]:
    band = mask[max(0, y0 - 8) : min(mask.shape[0], y1 + 9)]
    col = band.sum(axis=0)
    threshold = max(2, int(band.shape[0] * 0.012))
    xs = np.where(col > threshold)[0]
    if len(xs) == 0:
        return 0, width
    x0 = max(0, int(xs[0]) - 36)
    x1 = min(width, int(xs[-1]) + 37)
    if x1 - x0 < int(width * 0.40):
        center = (x0 + x1) // 2
        half = int(width * 0.22)
        x0 = max(0, center - half)
        x1 = min(width, center + half)
    target_width = min(x1 - x0, max(520, int((y1 - y0) * 4.35)))
    x1 = min(width, x0 + target_width)
    return x0, x1


def build_review_crop(source_path: Path, output_path: Path) -> tuple[int, int, int, int]:
    image = Image.open(source_path).convert("RGB")
    width, height = image.size
    mask = _dark_mask(image)
    y0, y1, next_top = _choose_music_region(mask)
    y0 = max(0, y0 - 34)
    y1 = min(height, y1 + 34)
    if next_top is not None:
        y1 = min(y1, max(y0 + 80, next_top - 8))
    x0, x1 = _x_bounds(mask, y0, y1, width)
    crop = image.crop((x0, y0, x1, y1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output_path)
    return x0, y0, x1, y1


def main() -> None:
    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    if not isinstance(library, list):
        raise TypeError("source-score-library.json must contain a list")

    for entry in library:
        if not isinstance(entry, dict):
            continue
        image_url = str(entry.get("imageUrl") or "")
        if not image_url.startswith(PUBLIC_PREFIX):
            continue
        source_path = ROOT / image_url.lstrip("/")
        if not source_path.exists():
            continue
        output_name = f"{source_path.stem}-review.png"
        output_path = source_path.with_name(output_name)
        x0, y0, x1, y1 = build_review_crop(source_path, output_path)
        entry["reviewImageUrl"] = f"{PUBLIC_PREFIX}{output_name}"
        entry["reviewCropKind"] = "detected_first_music_system"
        entry["reviewCropSourceImageUrl"] = image_url
        entry["reviewCropBox"] = [x0, y0, x1, y1]

    LIBRARY_PATH.write_text(json.dumps(library, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
