from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


PIPELINE_BASE_DIR = Path.home() / "BCX_Image_Pipeline"
STAGING_DIR = PIPELINE_BASE_DIR / "staging"
EXPORT_DIR = PIPELINE_BASE_DIR / "export"


def ensure_pipeline_dirs() -> None:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ExportReport:
    source_export_dir: Path
    source_staging_dir: Path
    downloads_dir: Path
    series_exports: Dict[str, Path]   # series_name -> destination folder
    copied_files: int
    skipped_files: int
    errors: List[str]


def _has_series_subfolders(export_dir: Path) -> bool:
    if not export_dir.exists():
        return False
    for p in export_dir.iterdir():
        if p.is_dir():
            return True
    return False


def _derive_series_folder_from_filename(filename: str) -> str:
    """Derive a Downloads folder name from a processed image filename.

    Example:
      image_batman_v1_233_a.png  ->  Batman v1

    Rules:
      - Drop extension
      - Replace underscores with spaces
      - Remove the issue number chunk (and any trailing variant tokens)
      - Keep volume token vN if present
      - Title-case normal words; keep vN lowercase
    """
    stem = Path(filename).stem
    parts = stem.split("_")

    # Remove common leading tokens that aren't series words
    if parts and parts[0].lower() in {"image", "cover", "front"}:
        parts = parts[1:]

    # Identify volume token if present (v1, v2, etc.)
    vol_idx = None
    for i, tok in enumerate(parts):
        if tok.lower().startswith("v") and tok[1:].isdigit():
            vol_idx = i
            break

    # Identify issue token: first all-digit token after volume if volume exists, else first all-digit token
    start_i = (vol_idx + 1) if vol_idx is not None else 0
    issue_idx = None
    for i in range(start_i, len(parts)):
        if parts[i].isdigit():
            issue_idx = i
            break

    if issue_idx is not None:
        series_parts = parts[:issue_idx]
    else:
        series_parts = parts

    words: List[str] = []
    for tok in series_parts:
        if not tok:
            continue
        t = tok.strip()
        if t.lower().startswith("v") and t[1:].isdigit():
            words.append(t.lower())
        else:
            words.append(t.replace("-", " ").title())

    name = " ".join(words).strip()
    return name or "BCX Export"


def _list_files_recursive(folder: Path) -> List[Path]:
    files: List[Path] = []
    if not folder.exists():
        return files
    for p in folder.rglob("*"):
        if p.is_file():
            files.append(p)
    return files


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def export_processed_images_to_downloads(
    *,
    export_dir: Path | None = None,
    staging_dir: Path | None = None,
    downloads_root: Path | None = None,
) -> ExportReport:
    """Copy everything under export/ into ~/Downloads/<Series Name>/...

    - If export/ contains subfolders, uses those names directly.
    - If export/ is flat, derives series folder from each filename.
    - Verifies by checking destination exists and non-zero size.

    Does NOT delete anything.
    """
    ensure_pipeline_dirs()

    export_dir = export_dir or EXPORT_DIR
    staging_dir = staging_dir or STAGING_DIR
    downloads_root = downloads_root or (Path.home() / "Downloads")

    errors: List[str] = []
    series_exports: Dict[str, Path] = {}
    copied = 0
    skipped = 0

    if not export_dir.exists():
        return ExportReport(export_dir, staging_dir, downloads_root, {}, 0, 0, ["Export folder does not exist."])

    all_export_files = _list_files_recursive(export_dir)
    if not all_export_files:
        return ExportReport(export_dir, staging_dir, downloads_root, {}, 0, 0, ["No files found in export folder."])

    if _has_series_subfolders(export_dir):
        for series_folder in [p for p in export_dir.iterdir() if p.is_dir()]:
            series_name = series_folder.name
            dest_series_dir = downloads_root / series_name
            series_exports[series_name] = dest_series_dir

            files = _list_files_recursive(series_folder)
            for src in files:
                rel = src.relative_to(series_folder)
                dst = dest_series_dir / rel
                try:
                    _copy_file(src, dst)
                    if dst.exists() and dst.stat().st_size > 0:
                        copied += 1
                    else:
                        errors.append(f"Copy verification failed: {dst}")
                except Exception as e:
                    errors.append(f"Failed to copy {src} -> {dst}: {e}")
    else:
        for src in [p for p in export_dir.iterdir() if p.is_file()]:
            series_name = _derive_series_folder_from_filename(src.name)
            dest_series_dir = downloads_root / series_name
            series_exports[series_name] = dest_series_dir

            dst = dest_series_dir / src.name
            try:
                _copy_file(src, dst)
                if dst.exists() and dst.stat().st_size > 0:
                    copied += 1
                else:
                    errors.append(f"Copy verification failed: {dst}")
            except Exception as e:
                errors.append(f"Failed to copy {src} -> {dst}: {e}")

    return ExportReport(
        source_export_dir=export_dir,
        source_staging_dir=staging_dir,
        downloads_dir=downloads_root,
        series_exports=series_exports,
        copied_files=copied,
        skipped_files=skipped,
        errors=errors,
    )


def clear_pipeline_temp_folders(*, staging_dir: Path | None = None, export_dir: Path | None = None) -> List[str]:
    """Delete ALL contents inside staging/ and export/ (but keep the folders)."""
    ensure_pipeline_dirs()
    staging_dir = staging_dir or STAGING_DIR
    export_dir = export_dir or EXPORT_DIR

    errors: List[str] = []

    def _clear_dir(folder: Path):
        if not folder.exists():
            return
        for p in folder.iterdir():
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
            except Exception as e:
                errors.append(f"Failed to delete {p}: {e}")

    _clear_dir(staging_dir)
    _clear_dir(export_dir)

    return errors
