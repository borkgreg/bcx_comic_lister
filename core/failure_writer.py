from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from .image_allocator import ComicRecord


FAILURE_REASON_COLUMN = "FailureReason"


def write_failure_csv(
    output_path: str,
    clz_header: List[str],
    failed_comics: List[ComicRecord],
) -> int:
    """
    Write a CSV containing all comics that failed to make it into the eBay upload CSV.

    Rules (LOCKED):
    - Uses the original CLZ row data verbatim
    - Appends a single column: FailureReason
    - One row per failed comic
    - No modification or filtering of original CLZ values

    Returns:
        Number of failure rows written.
    """
    if not failed_comics:
        return 0

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    header = list(clz_header) + [FAILURE_REASON_COLUMN]

    rows: List[List[str]] = []
    for comic in failed_comics:
        if not comic.clz_row:
            continue
        row = list(comic.clz_row)
        row.append(comic.failure_reason or "UNKNOWN")
        rows.append(row)

    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        writer.writerows(rows)

    return len(rows)