from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional
import re

import numpy as np
import cv2
from PIL import Image, ImageEnhance

try:
    from core.paths import processed_root_dir
    PROCESSED_ROOT = processed_root_dir(prefer_legacy=True)
except Exception:
    PROCESSED_ROOT = Path.home() / "BCX" / "processed"
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)

TARGET_LONG_EDGE = 1600
OUTPUT_FORMAT = "PNG"
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Issue token examples: 1, 10, 1A, 12C, 001B
_ISSUE_TOKEN_RE = re.compile(r"^\d+[A-Za-z]{0,3}$")


@dataclass
class PipelineRunResult:
    processed_count: int
    error_count: int
    output_dirs: List[Path]


def _looks_like_issue_token(token: str) -> bool:
    t = (token or "").strip()
    if not t:
        return False
    t = t.lstrip("#").strip()
    return bool(_ISSUE_TOKEN_RE.match(t))


def extract_series_title(filename: str) -> str:
    """
    Folder grouping rule:
      - Always treat the LAST underscore token as the issue token *if it looks like an issue*.
      - Otherwise keep full stem.

    Examples:
      Artifacts_10A.webp            -> Artifacts
      Alpha_Girl_1.webp             -> Alpha_Girl
      Back_To_Brooklyn_1A.webp      -> Back_To_Brooklyn
      Batman_2016_12C.webp          -> Batman_2016
      Spider_Man_V2_12C.webp        -> Spider_Man_V2
      Chew_19A.webp                 -> Chew
      Chew_10.webp                  -> Chew
    """
    stem = Path(filename).stem
    parts = [p for p in stem.split("_") if p]

    if len(parts) <= 1:
        return stem

    last = parts[-1]
    if _looks_like_issue_token(last):
        parts = parts[:-1]
        if not parts:
            return stem
        return "_".join(parts)

    return stem


def _resize_long_edge(img: np.ndarray, target_long: int) -> np.ndarray:
    h, w = img.shape[:2]
    long_edge = max(h, w)
    if long_edge <= target_long:
        return img

    scale = target_long / float(long_edge)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)


def enhance_image(in_path: Path, out_path: Path) -> None:
    img = cv2.imread(str(in_path))
    if img is None:
        raise ValueError("Could not read image")

    img = _resize_long_edge(img, TARGET_LONG_EDGE)

    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    pil = ImageEnhance.Contrast(pil).enhance(1.08)
    pil = ImageEnhance.Sharpness(pil).enhance(1.10)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(str(out_path), OUTPUT_FORMAT)


def process_paths(
    paths: Iterable[str],
    *,
    log: Optional[Callable[[str], None]] = None,
    progress_update: Optional[Callable[[int, int, str], None]] = None,
) -> PipelineRunResult:
    valid_paths: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.suffix.lower() in VALID_EXTENSIONS:
            valid_paths.append(p)

    total = len(valid_paths)
    processed = 0
    errors = 0
    touched_dirs: List[Path] = []

    for idx, path in enumerate(valid_paths, start=1):
        if progress_update:
            progress_update(idx, total, path.name)

        try:
            series_title = extract_series_title(path.name)
            series_dir = PROCESSED_ROOT / series_title
            series_dir.mkdir(parents=True, exist_ok=True)

            out_path = series_dir / f"{path.stem}.{OUTPUT_FORMAT.lower()}"
            enhance_image(path, out_path)

            if series_dir not in touched_dirs:
                touched_dirs.append(series_dir)

            processed += 1
            if log:
                log(f"Processed → {series_dir.name}/{out_path.name}")

        except Exception as e:
            errors += 1
            if log:
                log(f"ERROR processing {path.name}: {e}")

    return PipelineRunResult(
        processed_count=processed,
        error_count=errors,
        output_dirs=touched_dirs,
    )