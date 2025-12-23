from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import re
import uuid


# ============================================================
# Data model (authoritative)
# ============================================================

@dataclass
class ComicRecord:
    """
    Canonical comic record used across BOTH workflows.

    Strict matching keys:
      - series_norm
      - volume (int)
      - issue_number (int)

    issue_suffix is preserved for reference/debugging but NOT used for matching.
    """
    id: int
    series_raw: str
    series_norm: str
    volume: int
    issue_number: int
    issue_suffix: str = ""
    raw_title: str = ""
    clz_row: Optional[List[str]] = None

    # --- CLZ metadata (optional, used for eBay mapping) ---
    publisher: str = ""
    release_year: str = ""
    publication_year: str = ""
    grade: str = ""
    era: str = ""
    universe: str = ""
    cover_artist: str = ""
    characters: str = ""
    value: str = ""

    # Workflow A (local image pipeline)
    status: str = "PENDING"  # PENDING | MATCHED | FAILED
    failure_reason: str = ""
    allocated_image_ids: List[str] = field(default_factory=list)

    # Workflow B (eBay CSV builder)
    image_url: str = ""
    unused_image_urls: str = ""
    title_suffix: str = ""

    def with_image(self, *, image_url: str, title_suffix: str = "") -> "ComicRecord":
        """Return a COPY marked MATCHED with a hosted image URL."""
        return replace(
            self,
            status="MATCHED",
            image_url=image_url or "",
            title_suffix=title_suffix or "",
        )

    def with_failure(self, *, reason: str, unused_urls: str = "") -> "ComicRecord":
        """Return a COPY marked FAILED with failure metadata."""
        return replace(
            self,
            status="FAILED",
            failure_reason=reason or "UNKNOWN",
            unused_image_urls=unused_urls or "",
        )

    def to_ebay_row(self) -> Dict[int, str]:
        """
        Map this comic into eBay template column indices.

        NOTE:
          - core/ebay_writer.py applies template-derived fixed values afterward.
          - PicURL is handled in core/ebay_writer.py and always ends with a trailing '|'.
          - CustomLabel issue number is padded to 4 digits: 0001..9999
        """
        # CustomLabel (SKU) — stable and deterministic
        sku_base = re.sub(r"[^a-z0-9]+", "_", (self.series_norm or "").lower()).strip("_")

        # 4-digit numeric portion ONLY here
        issue_padded = f"{int(self.issue_number):04d}"
        issue_part = f"{issue_padded}{(self.issue_suffix or '').upper()}"

        sku = f"{sku_base}_v{self.volume}_{issue_part}"

        # Title (fallback only; ebay_writer overrides *Title)
        suffix = (self.title_suffix or "").strip()
        if not suffix and self.issue_suffix:
            suffix = f"Cvr {self.issue_suffix.upper()}"

        title = f"{self.series_raw} Vol. {self.volume} #{self.issue_number}".strip()
        if suffix:
            title = f"{title} {suffix}".strip()

        title = re.sub(r"\s+", " ", title).strip()
        title = "".join(ch for ch in title if ch.isprintable())
        if len(title) > 80:
            title = title[:80].rstrip()

        out: Dict[int, str] = {
            1: sku,                       # CustomLabel
            4: title,                     # *Title (will be overridden by ebay_writer)
            10: self.series_raw or "",    # C:Series Title
            43: str(self.issue_number),   # C:Issue Number
            57: "1",                      # *Quantity
        }

        if self.raw_title:
            out[33] = self.raw_title      # C:Story Title

        return out


@dataclass
class ImageAsset:
    id: str
    filename: str
    path: str

    series_norm: str
    volume: int
    issue_number: int
    issue_suffix: str = ""

    used: bool = False


@dataclass
class AllocationResult:
    matched: List[ComicRecord]
    failed: List[ComicRecord]
    ledger_image_to_comic: Dict[str, int]
    ledger_comic_to_images: Dict[int, List[str]]
    images: List[ImageAsset]


# ============================================================
# Normalization + parsing helpers (canonical)
# ============================================================

_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+", flags=re.IGNORECASE)
_MULTI_SPACE_RE = re.compile(r"\s+")
_VOL_TOKEN_RE = re.compile(r"^v(\d+)$", flags=re.IGNORECASE)
_YEAR_TOKEN_RE = re.compile(r"^(19\d{2}|20\d{2})$")
_ISSUE_RE = re.compile(r"^(\d+)([a-zA-Z]*)$")


def normalize_series(text: str) -> str:
    """
    Normalize series names into a stable strict-match key.
    """
    if not text:
        return ""

    s = text.lower()
    s = s.replace("_", " ").replace("-", " ")
    s = _NON_ALNUM_RE.sub("", s)
    s = _MULTI_SPACE_RE.sub(" ", s).strip()
    return s


def parse_issue_token(issue_token: str) -> Optional[Tuple[int, str]]:
    m = _ISSUE_RE.match(issue_token or "")
    if not m:
        return None
    return int(m.group(1)), (m.group(2) or "").upper()


def parse_image_filename(file_path: str) -> Optional[Tuple[str, int, int, str]]:
    """
    Canonical filename parser used by BOTH workflows.

    Supports:
      - Series_V1_233A.png
      - Series_2016_12C.webp (year token)
      - Series_233A.png (no volume token; defaults to V1)

    Returns:
      (series_norm, volume, issue_number, issue_suffix)
    """
    name = Path(file_path).stem
    if not name:
        return None

    parts = [p for p in name.split("_") if p]
    if len(parts) < 2:
        return None

    vol_idx = None
    volume = 1
    for i, p in enumerate(parts):
        m = _VOL_TOKEN_RE.match(p)
        if m:
            vol_idx = i
            volume = int(m.group(1))
            break

    issue_idx = (vol_idx + 1) if vol_idx is not None else (len(parts) - 1)
    if issue_idx >= len(parts):
        return None

    issue_parsed = parse_issue_token(parts[issue_idx])
    if not issue_parsed:
        return None
    issue_number, issue_suffix = issue_parsed

    if vol_idx is not None:
        series_tokens = parts[:vol_idx]
    else:
        series_tokens = parts[:-1]

    # Drop year tokens from the series key.
    series_tokens = [t for t in series_tokens if not _YEAR_TOKEN_RE.match(t)]
    if not series_tokens:
        return None

    series_raw = " ".join(series_tokens)
    series_norm = normalize_series(series_raw)
    return series_norm, volume, issue_number, issue_suffix


def index_images(image_paths: Iterable[str]) -> List[ImageAsset]:
    assets: List[ImageAsset] = []
    for path in image_paths:
        p = Path(path)
        parsed = parse_image_filename(p.name)
        if not parsed:
            continue
        series_norm, volume, issue_number, issue_suffix = parsed
        assets.append(
            ImageAsset(
                id=str(uuid.uuid4()),
                filename=p.name,
                path=str(p),
                series_norm=series_norm,
                volume=volume,
                issue_number=issue_number,
                issue_suffix=issue_suffix,
                used=False,
            )
        )
    return assets


def allocate_images(
    comics: List[ComicRecord],
    images: List[ImageAsset],
) -> AllocationResult:
    """
    Workflow A allocator (local images). Workflow B does NOT use this.
    """
    buckets: Dict[Tuple[str, int, int], List[ImageAsset]] = {}
    for img in images:
        key = (img.series_norm, img.volume, img.issue_number)
        buckets.setdefault(key, []).append(img)

    for key in buckets:
        buckets[key].sort(key=lambda x: (x.issue_suffix, x.filename.lower()))

    matched: List[ComicRecord] = []
    failed: List[ComicRecord] = []
    ledger_image_to_comic: Dict[str, int] = {}
    ledger_comic_to_images: Dict[int, List[str]] = {}

    for comic in comics:
        key = (comic.series_norm, comic.volume, comic.issue_number)
        bucket = buckets.get(key, [])

        chosen: Optional[ImageAsset] = None
        for img in bucket:
            if not img.used:
                chosen = img
                break

        if not chosen:
            comic.status = "FAILED"
            comic.failure_reason = "NO_MATCHING_IMAGE"
            failed.append(comic)
            continue

        chosen.used = True
        comic.status = "MATCHED"
        comic.allocated_image_ids.append(chosen.id)
        matched.append(comic)

        ledger_image_to_comic[chosen.id] = comic.id
        ledger_comic_to_images.setdefault(comic.id, []).append(chosen.id)

    return AllocationResult(
        matched=matched,
        failed=failed,
        ledger_image_to_comic=ledger_image_to_comic,
        ledger_comic_to_images=ledger_comic_to_images,
        images=images,
    )