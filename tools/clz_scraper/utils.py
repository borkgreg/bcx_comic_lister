import os
import re
from urllib.parse import urlparse


def ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def sanitize_text_for_filename(text: str) -> str:
    text = (text or "").strip()
    text = text.lstrip("#")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("_")
    return text or "Unknown"


def parse_series(series: str):
    series = series or ""
    vol_match = re.search(r"Vol\.?\s*([0-9]+)", series, flags=re.IGNORECASE)
    year_match = re.search(r"\b(19[0-9]{2}|20[0-9]{2})\b", series)

    base = series

    if vol_match:
        base = series[:vol_match.start()]
        volume = vol_match.group(1)
        return sanitize_text_for_filename(base), f"V{volume}"

    if year_match:
        base = series[:year_match.start()]
        year = year_match.group(1)
        return sanitize_text_for_filename(base), year

    return sanitize_text_for_filename(series), None


def clean_issue(issue: str) -> str:
    issue = issue or ""
    return sanitize_text_for_filename(issue)


def get_extension_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
        if "." in path:
            ext = path.split(".")[-1]
            if ext and len(ext) <= 5:
                return ext.lower()
    except Exception:
        pass
    return "jpg"


def build_series_folder_name(series: str) -> str:
    """
    Folder name under 'Staged Images/'.

    Examples:
      "Wolverine, Vol. 1" -> "Wolverine_V1"
      "Batman (2016)"     -> "Batman_2016"
    """
    base, mid = parse_series(series or "Unknown")
    if mid:
        return f"{base}_{mid}"
    return base


def build_filename(series: str, issue: str, image_url: str) -> str:
    base, mid = parse_series(series or "Unknown")
    issue_clean = clean_issue(issue or "NoIssue")
    ext = get_extension_from_url(image_url)

    parts = [base]
    if mid:
        parts.append(mid)
    parts.append(issue_clean)

    name = "_".join([p for p in parts if p])
    return f"{name}.{ext}"