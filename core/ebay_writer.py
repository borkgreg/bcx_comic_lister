import csv
import re
from pathlib import Path


DESCRIPTION_TEXT = (
    "This listing is part of a large comic book inventory upload. To efficiently process and make "
    "thousands of books available, the image shown is a stock photo used for cataloging and "
    "identification purposes. Higher value Near Mint (NM) books and key issues will be updated with "
    "an image of the actual book in the order they are uploaded. If you happen to view a listing "
    "before we get a chance to update the image, feel free to message me for actual photos and I’ll "
    "get them over to you as fast as I can. Buy with confidence. Books are packaged securely with "
    "protective materials to ensure safe delivery. Combined shipping is available when purchasing "
    "multiple items. Your satisfaction is important. If you are unhappy for any reason, simply "
    "return the comic within 30 days for a no-questions-asked refund."
)

# -------------------------------
# Column indices (0-based)
# -------------------------------
TITLE_COLUMN_INDEX = 4          # *Title
PICURL_COLUMN_INDEX = 46        # PicURL
START_PRICE_INDEX = 52          # BA *StartPrice
DISPATCH_TIME_MAX_INDEX = 65    # *DispatchTimeMax must remain blank

# Requested dynamic indices (0-based)
CHARACTER_INDEX = 11          # L  C:Character
PUBLISHER_INDEX = 14          # O  C:Publisher
PUBLICATION_YEAR_INDEX = 16   # Q  C:Publication Year
ERA_INDEX = 18                # S  C:Era
GRADE_INDEX = 20              # U  C:Grade
UNIVERSE_INDEX = 24           # Y  C:Universe
COVER_ARTIST_INDEX = 26       # AA C:Cover Artist

# Fixed values applied last by index
FIXED_BY_COLUMN_INDEX = {
    0: "Add ",
    2: "259104",
    9: "3000",            # *ConditionID

    12: "Superheroes",
    17: "Single Issue",   # R  C:Format
    19: "Comic Book",     # T  C:Type
    22: "US Comics",
    25: "Boarded",        # Z  C:Features

    28: "Single Issue",
    29: "No",
    30: "No",
    31: "No",
    34: "Color",
    36: "English",
    37: "United States ",
    40: "General Audience",

    49: DESCRIPTION_TEXT,  # *Description

    50: "FixedPrice",
    51: "GTC",
    59: "19014",
    73: "Single Book - (ID: 261714543021)",
    74: "Returns Accepted,Seller,30 Days,Money Back,In - (ID: 227092209021)",
}

_VOL_STRIP_RE = re.compile(r"[,()\-]*\s*\bvol\.?\s*\d+\b", flags=re.IGNORECASE)


def _load_template_rows(template_csv_path: str):
    with open(template_csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        info_row = next(reader, None)
        header_row = next(reader, None)
        _sample_row = next(reader, None)

    if not info_row or not header_row:
        raise ValueError("Invalid eBay template CSV (missing info/header rows).")

    if len(info_row) != len(header_row):
        raise ValueError("Invalid eBay template CSV (row length mismatch).")

    if header_row[TITLE_COLUMN_INDEX] != "*Title":
        raise ValueError("*Title column mismatch (expected at index 4).")
    if header_row[PICURL_COLUMN_INDEX] != "PicURL":
        raise ValueError("PicURL column mismatch (expected at index 46).")
    if header_row[START_PRICE_INDEX] != "*StartPrice":
        raise ValueError("*StartPrice column mismatch (expected at index 52).")
    if header_row[DISPATCH_TIME_MAX_INDEX] != "*DispatchTimeMax":
        raise ValueError("*DispatchTimeMax column mismatch (expected at index 65).")

    return info_row, header_row


def _series_display_name(series_raw: str) -> str:
    s = (series_raw or "").strip()
    s = _VOL_STRIP_RE.sub("", s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(",").strip()
    return s


def _format_money(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return f"{float(val):.2f}"

    s = str(val).strip()
    if not s:
        return ""
    s2 = s.replace("$", "").replace(",", "").strip()
    try:
        return f"{float(s2):.2f}"
    except Exception:
        return ""


def _parse_money_to_float(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return None


def _get_attr_str(row, name: str) -> str:
    v = getattr(row, name, "")
    if v is None:
        return ""
    return str(v).strip()


def _build_title(row) -> str:
    series = _series_display_name(_get_attr_str(row, "series_raw"))
    volume = _get_attr_str(row, "volume")
    issue = _get_attr_str(row, "issue_number")
    title_suffix = _get_attr_str(row, "title_suffix")  # e.g. "Cvr A"
    year = _get_attr_str(row, "release_year") or _get_attr_str(row, "publication_year")
    publisher = _get_attr_str(row, "publisher")

    parts = []
    if series:
        parts.append(series)
    if volume:
        parts.append(f"Vol. {volume}")
    if issue:
        parts.append(f"#{issue}")
    if title_suffix:
        parts.append(title_suffix)
    if year:
        parts.append(f"({year})")
    if publisher:
        parts.append(publisher)

    title = " ".join(parts).strip()
    return title[:80].rstrip() if len(title) > 80 else title


def _compute_start_price(row_value, min_start_price: float | None) -> str:
    """
    If min_start_price is set:
      - blank/unparseable -> min
      - < min -> min
      - >= min -> keep value
    If min_start_price is None:
      - use row_value as-is (formatted)
    """
    if min_start_price is None:
        return _format_money(row_value)

    v = _parse_money_to_float(row_value)
    if v is None:
        return _format_money(min_start_price)
    if v < min_start_price:
        return _format_money(min_start_price)
    return _format_money(v)


def write_ebay_csvs(*, ebay_rows, failed_rows, template_csv_path, output_dir, min_start_price: float | None = None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ebay_path = output_dir / "ebay_ready.csv"
    failed_path = output_dir / "failed.csv"

    info_row, headers = _load_template_rows(str(template_csv_path))
    column_count = len(headers)

    # ---------------- eBay READY ----------------
    with open(ebay_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(info_row)
        writer.writerow(headers)

        for row in ebay_rows:
            out = [""] * column_count

            # Base dynamic mapping from ComicRecord
            dynamic = row.to_ebay_row()
            for idx, val in dynamic.items():
                if 0 <= idx < column_count:
                    out[idx] = val

            # Title (dynamic, includes title_suffix if present)
            out[TITLE_COLUMN_INDEX] = _build_title(row)

            # Requested dynamics
            out[CHARACTER_INDEX] = _get_attr_str(row, "characters") or _get_attr_str(row, "character")
            out[PUBLISHER_INDEX] = _get_attr_str(row, "publisher")
            out[PUBLICATION_YEAR_INDEX] = _get_attr_str(row, "release_year") or _get_attr_str(row, "publication_year")
            out[ERA_INDEX] = _get_attr_str(row, "era")
            out[GRADE_INDEX] = _get_attr_str(row, "grade")
            out[UNIVERSE_INDEX] = _get_attr_str(row, "universe")
            out[COVER_ARTIST_INDEX] = _get_attr_str(row, "cover_artist")

            # BA StartPrice with minimum enforcement
            out[START_PRICE_INDEX] = _compute_start_price(getattr(row, "value", ""), min_start_price)

            # PicURL forced with trailing '|'
            out[PICURL_COLUMN_INDEX] = (_get_attr_str(row, "image_url") or "") + "|"

            # Fixed overrides LAST
            for idx, val in FIXED_BY_COLUMN_INDEX.items():
                if 0 <= idx < column_count:
                    out[idx] = val

            # Must remain blank
            out[DISPATCH_TIME_MAX_INDEX] = ""

            writer.writerow(out)

    # ---------------- FAILED ----------------
    failed_headers = ["Reason", "Unused_Image_URLs"] + headers
    with open(failed_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(failed_headers)

        for row in failed_rows:
            out = [""] * column_count
            dynamic = row.to_ebay_row()
            for idx, val in dynamic.items():
                if 0 <= idx < column_count:
                    out[idx] = val
            writer.writerow([row.failure_reason, row.unused_image_urls, *out])