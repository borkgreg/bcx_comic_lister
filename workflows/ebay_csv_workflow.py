from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import List
from urllib.parse import urlparse, unquote

from core.clz_parser import load_clz_csv
from core.ebay_writer import write_ebay_csvs
from core.image_allocator import parse_image_filename


def _parse_hosted_url(url: str):
    if not url:
        return None

    parsed = urlparse(url)
    filename = Path(unquote(parsed.path)).name
    if not filename:
        return None

    p = Path(filename)
    if p.stem.lower().endswith("-vi"):
        filename = f"{p.stem[:-3]}{p.suffix}"

    parsed_name = parse_image_filename(filename)
    if not parsed_name:
        return None

    series_norm, volume, issue_number, issue_suffix = parsed_name
    variant = (issue_suffix or "").upper()
    return series_norm, volume, issue_number, variant


def _select_images_for_group(images: List[dict], group_size: int) -> List[dict] | None:
    if group_size <= 0:
        return None
    if not images:
        return None

    if group_size == 1:
        if len(images) == 1:
            return [images[0]]
        a_imgs = [img for img in images if (img.get("variant") or "").upper() == "A"]
        if len(a_imgs) == 1:
            return [a_imgs[0]]
        return None

    if len(images) < group_size:
        return None

    selected = images[:group_size]
    variants = [(img.get("variant") or "").upper() for img in selected]
    if "" in variants:
        return None
    if len(set(variants)) != len(variants):
        return None

    return selected


def run_ebay_csv_workflow(
    *,
    clz_csv_path: str,
    image_paths: List[str],  # kept for signature compatibility; workflow B ignores local images
    ebay_template_csv_path: str,
    hosted_image_urls_by_image_id: dict | None,
    output_dir: str,
    min_start_price: float | None = None,
):
    comics, _header = load_clz_csv(clz_csv_path)

    hosted_urls: List[str] = []
    if hosted_image_urls_by_image_id:
        for v in hosted_image_urls_by_image_id.values():
            if isinstance(v, list):
                hosted_urls.extend(v)
            elif isinstance(v, str) and v.strip():
                hosted_urls.append(v)

    images_by_key = defaultdict(list)

    for url in hosted_urls:
        parsed = _parse_hosted_url(url)
        if not parsed:
            continue
        series_norm, volume, issue_number, variant = parsed
        images_by_key[(series_norm, volume, issue_number)].append({"url": url, "variant": variant})

    for key in images_by_key:
        images_by_key[key].sort(key=lambda x: (x["variant"] or ""))

    groups = []
    current = []
    prev_key = None

    for comic in comics:
        key = (comic.series_norm, comic.volume, comic.issue_number)
        if prev_key is None or key == prev_key:
            current.append(comic)
        else:
            groups.append((prev_key, current))
            current = [comic]
        prev_key = key

    if current:
        groups.append((prev_key, current))

    ebay_rows = []
    failed_rows = []
    used_urls = set()

    for key, group in groups:
        images = images_by_key.get(key, [])
        selected = _select_images_for_group(images, len(group))

        if selected:
            multi_variant_group = len(group) > 1

            for comic, img in zip(group, selected):
                used_urls.add(img["url"])
                v = (img.get("variant") or "").upper()
                suffix = f"Cvr {v}" if (multi_variant_group and v) else ""
                ebay_rows.append(comic.with_image(image_url=img["url"], title_suffix=suffix))
        else:
            unused_urls = [img["url"] for img in images if img["url"] not in used_urls]
            unused_str = "|".join(unused_urls)
            for comic in group:
                failed_rows.append(
                    comic.with_failure(reason="No safe image variant match", unused_urls=unused_str)
                )

    write_ebay_csvs(
        ebay_rows=ebay_rows,
        failed_rows=failed_rows,
        template_csv_path=ebay_template_csv_path,
        output_dir=output_dir,
        min_start_price=min_start_price,
    )

    return {
        "total_clz_rows": len(comics),
        "images_parsed": sum(len(v) for v in images_by_key.values()),
        "comics_matched": len(ebay_rows),
        "comics_failed": len(failed_rows),
        "unused_image_urls": (len(hosted_urls) - len(used_urls)) if hosted_urls else 0,
    }