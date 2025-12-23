from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .image_allocator import ComicRecord, normalize_series


REQUIRED_COLUMNS = ["Series", "Issue Nr"]

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


def _get(row: List[str], col_index: Dict[str, int], name: str) -> str:
    i = col_index.get(name)
    if i is None:
        return ""
    if i >= len(row):
        return ""
    return (row[i] or "").strip()


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

        comics: List[ComicRecord] = []

        for row in reader:
            if not any((cell or "").strip() for cell in row):
                continue

            series_raw = _get(row, col_index, "Series")
            issue_raw = _get(row, col_index, "Issue Nr")

            series_clean, volume = _parse_series_and_volume(series_raw)
            issue_number, issue_suffix = _parse_issue(issue_raw)

            if issue_number is None:
                comics.append(
                    ComicRecord(
                        id=len(comics) + 1,
                        series_raw=series_clean,
                        series_norm=normalize_series(series_clean),
                        volume=volume,
                        issue_number=0,
                        issue_suffix="",
                        raw_title="",
                        clz_row=row,
                        status="FAILED",
                        failure_reason="UNPARSEABLE_ISSUE",
                    )
                )
                continue

            variant_val = _get(row, col_index, "Variant").upper()
            title_val = _get(row, col_index, "Title")

            # ---- Optional metadata (names based on common CLZ export fields) ----
            publisher = _get(row, col_index, "Publisher")
            release_year = _get(row, col_index, "Release Year")
            publication_year = _get(row, col_index, "Publication Year")  # if it exists
            grade = _get(row, col_index, "Grade")
            era = _get(row, col_index, "Era")
            universe = _get(row, col_index, "Universe")
            cover_artist = _get(row, col_index, "Cover Artist")
            characters = _get(row, col_index, "Character") or _get(row, col_index, "Characters")
            value = _get(row, col_index, "Value")

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
                    publisher=publisher,
                    release_year=release_year,
                    publication_year=publication_year,
                    grade=grade,
                    era=era,
                    universe=universe,
                    cover_artist=cover_artist,
                    characters=characters,
                    value=value,
                )
            )

    return comics, header