from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .image_allocator import ComicRecord, normalize_series


REQUIRED_COLUMNS = ["Series", "Issue Nr"]

# Optional CLZ columns we support when present
OPTIONAL_COLUMNS = [
    "Variant",
    "Release Year",
    "Grade",
    "Title",
    "Publisher",
    "Characters",
    "Cover Artist",
    "Value",
    "Era",
    "Universe",
]

_VOL_RE = re.compile(r"\bvol\.?\s*(\d+)\b", flags=re.IGNORECASE)
_ISSUE_RE = re.compile(r"#?\s*(\d+)\s*([A-Za-z]?)")


def _parse_series_and_volume(series_raw: str) -> Tuple[str, int]:
    if not series_raw:
        return "", 1

    volume = 1
    m = _VOL_RE.search(series_raw)
    if m:
        volume = int(m.group(1))

    series_clean = re.sub(r"[,()]*\s*\bvol\.?\s*\d+\b", "", series_raw, flags=re.IGNORECASE).strip()
    series_clean = re.sub(r"\s+", " ", series_clean).strip()
    return series_clean, volume


def _parse_issue(issue_raw: str) -> Tuple[Optional[int], str]:
    if not issue_raw:
        return None, ""

    m = _ISSUE_RE.search(issue_raw.strip())
    if not m:
        return None, ""

    num = int(m.group(1))
    suffix = (m.group(2) or "").upper()
    return num, suffix


def _safe_cell(row: List[str], col_index: Dict[str, int], col_name: str) -> str:
    idx = col_index.get(col_name)
    if idx is None:
        return ""
    if idx < 0 or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _safe_cell_by_index(row: List[str], header: List[str], idx0: int, expected_name: str) -> str:
    """
    Strict index-based read with a safety check: only return if header matches expected_name.
    This enforces: CLZ column I (index0=8) is Value, etc.
    """
    if idx0 < 0 or idx0 >= len(header) or idx0 >= len(row):
        return ""
    if (header[idx0] or "").strip() != expected_name:
        return ""
    return (row[idx0] or "").strip()


@dataclass
class CLZParseResult:
    header: List[str]
    rows: List[List[str]]
    column_index: Dict[str, int]
    comics: List[ComicRecord]


def load_clz_csv(path: str) -> Tuple[List[ComicRecord], List[str]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CLZ CSV not found: {path}")

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            raise ValueError("CLZ CSV has no header row.")

        col_index: Dict[str, int] = {h.strip(): i for i, h in enumerate(header)}

        for req in REQUIRED_COLUMNS:
            if req not in col_index:
                raise ValueError(f"CLZ CSV missing required column: {req}")

        rows: List[List[str]] = []
        comics: List[ComicRecord] = []

        for row in reader:
            if not any((cell or "").strip() for cell in row):
                continue

            rows.append(row)

            series_raw = _safe_cell(row, col_index, "Series")
            issue_raw = _safe_cell(row, col_index, "Issue Nr")

            series_clean, volume = _parse_series_and_volume(series_raw)
            issue_number, issue_suffix = _parse_issue(issue_raw)

            # Optional fields (by name)
            variant_val = _safe_cell(row, col_index, "Variant").upper()
            title_val = _safe_cell(row, col_index, "Title")
            publisher_val = _safe_cell(row, col_index, "Publisher")
            characters_val = _safe_cell(row, col_index, "Characters")
            cover_artist_val = _safe_cell(row, col_index, "Cover Artist")
            grade_val = _safe_cell(row, col_index, "Grade")
            release_year_val = _safe_cell(row, col_index, "Release Year")
            era_val = _safe_cell(row, col_index, "Era")
            universe_val = _safe_cell(row, col_index, "Universe")

            # Value MUST come from CLZ column I (index0=8) when that column is named "Value"
            value_val = _safe_cell_by_index(row, header, 8, "Value")
            if not value_val:
                # fallback if user exports differ, still safe
                value_val = _safe_cell(row, col_index, "Value")

            if issue_number is None:
                comics.append(
                    ComicRecord(
                        id=len(comics) + 1,
                        series_raw=series_clean,
                        series_norm=normalize_series(series_clean),
                        volume=volume,
                        issue_number=0,
                        issue_suffix="",
                        raw_title=title_val,
                        clz_row=row,
                        status="FAILED",
                        failure_reason="UNPARSEABLE_ISSUE",
                        publisher=publisher_val,
                        release_year=release_year_val,
                        grade=grade_val,
                        characters=characters_val,
                        cover_artist=cover_artist_val,
                        value=value_val,
                        era=era_val,
                        universe=universe_val,
                    )
                )
                continue

            comics.append(
                ComicRecord(
                    id=len(comics) + 1,
                    series_raw=series_clean,
                    series_norm=normalize_series(series_clean),
                    volume=volume,
                    issue_number=issue_number,
                    issue_suffix=(variant_val or issue_suffix),
                    raw_title=title_val,
                    clz_row=row,
                    publisher=publisher_val,
                    release_year=release_year_val,
                    grade=grade_val,
                    characters=characters_val,
                    cover_artist=cover_artist_val,
                    value=value_val,  # <-- BA StartPrice source
                    era=era_val,
                    universe=universe_val,
                )
            )

    return comics, header