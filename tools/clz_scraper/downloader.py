import traceback
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests

try:
    from .utils import build_filename, build_series_folder_name, ensure_directory
except Exception:
    from utils import build_filename, build_series_folder_name, ensure_directory  # type: ignore


def download_comics(
    items,
    output_dir,
    progress_callback: Optional[Callable[[str], None]] = None,
    progress_update: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[int, int]:
    """
    Downloads into:
      output_dir/<SeriesFolder>/<filename>

    progress_update: (current, total, label) for progress bars
    """
    out_root = Path(output_dir)
    ensure_directory(str(out_root))

    total = len(items)
    downloaded = 0
    skipped = 0

    for idx, item in enumerate(items, start=1):
        series = (item.get("series") or "").strip()
        issue = (item.get("issue") or "").strip()
        image_url = (item.get("image") or "").strip()

        label = f"{series} {issue}".strip() or "Unknown"

        if progress_update:
            progress_update(idx, total, label)

        if not image_url:
            skipped += 1
            if progress_callback:
                progress_callback(f"[{idx}/{total}] Skipping {label}: no image URL.")
            continue

        series_folder = build_series_folder_name(series)
        series_dir = out_root / series_folder
        ensure_directory(str(series_dir))

        filename = build_filename(series, issue, image_url)
        dest_path = series_dir / filename

        if dest_path.exists():
            skipped += 1
            if progress_callback:
                progress_callback(
                    f"[{idx}/{total}] Skipping {label}: file already exists ({series_folder}/{filename})."
                )
            continue

        try:
            if progress_callback:
                progress_callback(f"[{idx}/{total}] Downloading {label} -> {series_folder}/{filename}")

            resp = requests.get(image_url, stream=True, timeout=30)
            resp.raise_for_status()

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)

            downloaded += 1

        except Exception as e:
            skipped += 1
            if progress_callback:
                progress_callback(f"[{idx}/{total}] ERROR downloading {label}: {e}")
                progress_callback(traceback.format_exc())

    return downloaded, skipped