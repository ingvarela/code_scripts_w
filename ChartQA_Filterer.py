#!/usr/bin/env python3
"""
Create a commercial-use–safe subset of ChartQA by keeping only charts
sourced from OWID and OECD (default). The script:

- Recursively scans the ChartQA root folder for annotation JSON files.
- Determines the chart source via explicit fields (e.g., "source") or
  via URL/domain heuristics in the annotation (e.g., ourworldindata.org, oecd.org).
- Copies image, table CSV (if present), and annotation JSON for each kept item
  into a mirrored structure under the output folder.
- Ensures 1:1 records, de-duplicates safely, continues on errors, and logs a manifest.

Works with varied releases/structures of ChartQA (full/annotated variants).
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# ---- Domains we treat as commercial-safe by default
SAFE_DOMAIN_PATTERNS = {
    "owid": re.compile(r"(ourworldindata\.org)", re.I),
    "oecd": re.compile(r"(oecd\.org|stats\.oecd\.org)", re.I),
}

# ---- Fallback domain classifiers for excluded sources (never kept)
EXCLUDED_DOMAIN_PATTERNS = {
    "statista": re.compile(r"(statista\.com|statcdn\.com)", re.I),
    "pew": re.compile(r"(pewresearch\.org)", re.I),
}

KNOWN_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
KNOWN_ANN_EXTS = {".json", ".jsonl"}
KNOWN_TABLE_EXTS = {".csv", ".tsv"}


def infer_source_from_record(rec: dict) -> Optional[str]:
    """
    Try to infer the source from typical annotation fields.
    Priority:
      1) Explicit 'source'/'dataset' style fields.
      2) Known URL-bearing fields (url, page_url, data_url, metadata.url, etc.)
      3) Any string values containing a known domain.

    Returns canonical keys: 'owid', 'oecd', 'statista', 'pew', or None if unknown.
    """
    # 1) Direct fields commonly seen
    for key in ("source", "dataset", "origin", "provider"):
        v = rec.get(key)
        if isinstance(v, str):
            low = v.lower()
            if "owid" in low or "our world in data" in low:
                return "owid"
            if "oecd" in low:
                return "oecd"
            if "statista" in low:
                return "statista"
            if "pew" in low or "pew research" in low:
                return "pew"

    # 2) URL-ish fields to inspect
    url_keys = [
        "url", "page_url", "source_url", "data_url", "image_url", "chart_url",
        "reference", "ref_url", "origin_url",
    ]

    # include nested metadata containers if present
    candidates = []
    for k in url_keys:
        v = rec.get(k)
        if isinstance(v, str):
            candidates.append(v)

    # common nested places
    for container_key in ("meta", "metadata", "provenance", "chart_meta"):
        c = rec.get(container_key, {})
        if isinstance(c, dict):
            for k, v in c.items():
                if isinstance(v, str):
                    candidates.append(v)

    # scan candidates
    for s in candidates:
        if SAFE_DOMAIN_PATTERNS["owid"].search(s):
            return "owid"
        if SAFE_DOMAIN_PATTERNS["oecd"].search(s):
            return "oecd"
        if EXCLUDED_DOMAIN_PATTERNS["statista"].search(s):
            return "statista"
        if EXCLUDED_DOMAIN_PATTERNS["pew"].search(s):
            return "pew"

    # 3) last resort: scan any string field for domains
    for k, v in rec.items():
        if isinstance(v, str):
            if SAFE_DOMAIN_PATTERNS["owid"].search(v):
                return "owid"
            if SAFE_DOMAIN_PATTERNS["oecd"].search(v):
                return "oecd"
            if EXCLUDED_DOMAIN_PATTERNS["statista"].search(v):
                return "statista"
            if EXCLUDED_DOMAIN_PATTERNS["pew"].search(v):
                return "pew"
        elif isinstance(v, dict):
            # shallow scan nested dicts
            for kk, vv in v.items():
                if isinstance(vv, str):
                    if SAFE_DOMAIN_PATTERNS["owid"].search(vv):
                        return "owid"
                    if SAFE_DOMAIN_PATTERNS["oecd"].search(vv):
                        return "oecd"
                    if EXCLUDED_DOMAIN_PATTERNS["statista"].search(vv):
                        return "statista"
                    if EXCLUDED_DOMAIN_PATTERNS["pew"].search(vv):
                        return "pew"

    return None


def load_annotation(path: Path) -> Optional[dict]:
    try:
        with path.open("r", encoding="utf-8") as f:
            if path.suffix.lower() == ".json":
                return json.load(f)
            elif path.suffix.lower() == ".jsonl":
                # return only a list placeholder if jsonl; handled elsewhere if needed
                # but ChartQA annotations are generally per-chart JSON
                lines = [json.loads(line) for line in f if line.strip()]
                # if jsonl unexpectedly, try first record
                return lines[0] if lines else {}
    except Exception as e:
        print(f"[WARN] Failed to read annotation {path}: {e}", file=sys.stderr)
    return None


def guess_siblings(ann_path: Path, ann: dict) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Given an annotation file/path, try to find the image and table files.
    Strategy:
      - Look for explicit fields: image_path / img / filename / table_path / csv
      - Else, try same-stem search in nearby folders (images/, tables/) recursively up to a limit.
    """
    # 1) Direct fields
    candidates_img = []
    candidates_tbl = []

    for k in ("image_path", "img_path", "image", "imagefile", "image_file", "filename", "img"):
        v = ann.get(k)
        if isinstance(v, str):
            candidates_img.append(v)

    for k in ("table_path", "table", "csv", "data_path", "datafile", "table_file"):
        v = ann.get(k)
        if isinstance(v, str):
            candidates_tbl.append(v)

    # Convert relative candidates to absolute paths
    resolved_img = None
    for c in candidates_img:
        p = (ann_path.parent / c).resolve() if not os.path.isabs(c) else Path(c)
        if p.exists() and p.suffix.lower() in KNOWN_IMAGE_EXTS:
            resolved_img = p
            break

    resolved_tbl = None
    for c in candidates_tbl:
        p = (ann_path.parent / c).resolve() if not os.path.isabs(c) else Path(c)
        if p.exists() and p.suffix.lower() in KNOWN_TABLE_EXTS:
            resolved_tbl = p
            break

    # 2) Heuristic: same stem
    stem = ann_path.stem
    if resolved_img is None:
        # search sibling folders up to two levels up (common layouts: images/, charts/, tables/)
        possible_dirs = [ann_path.parent] + list(ann_path.parent.parents)[:2]
        for base in possible_dirs:
            for sub in ("", "images", "imgs", "charts", "figures"):
                d = base / sub
                if d.exists() and d.is_dir():
                    for ext in KNOWN_IMAGE_EXTS:
                        p = d / f"{stem}{ext}"
                        if p.exists():
                            resolved_img = p
                            break
                if resolved_img:
                    break
            if resolved_img:
                break

    if resolved_tbl is None:
        possible_dirs = [ann_path.parent] + list(ann_path.parent.parents)[:2]
        for base in possible_dirs:
            for sub in ("", "tables", "csv", "data"):
                d = base / sub
                if d.exists() and d.is_dir():
                    for ext in KNOWN_TABLE_EXTS:
                        p = d / f"{stem}{ext}"
                        if p.exists():
                            resolved_tbl = p
                            break
                if resolved_tbl:
                    break
            if resolved_tbl:
                break

    return resolved_img, resolved_tbl


def copy_unique(src: Optional[Path], dst: Path, dry_run: bool) -> bool:
    """
    Copy file if present and not already identical at destination.
    Returns True if file exists (or would exist in dry-run).
    """
    if src is None:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return True
    try:
        if not dst.exists():
            shutil.copy2(src, dst)
        else:
            # if sizes differ, overwrite
            if src.stat().st_size != dst.stat().st_size:
                shutil.copy2(src, dst)
        return True
    except Exception as e:
        print(f"[WARN] Failed to copy {src} -> {dst}: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description="Create a commercial-safe (OWID/OECD) subset of ChartQA.")
    ap.add_argument("--input", required=True, type=Path, help="Path to ChartQA root folder")
    ap.add_argument("--output", required=True, type=Path, help="Path to output subset folder")
    ap.add_argument("--allowed-sources", nargs="+", default=["owid", "oecd"],
                    help="Allowed sources (canonical keys): e.g., owid oecd")
    ap.add_argument("--dry-run", action="store_true", help="Preview actions without writing files")
    ap.add_argument("--manifest-name", default="manifest_commercial_subset.csv", help="Manifest CSV filename")
    args = ap.parse_args()

    chartqa_root: Path = args.input.resolve()
    out_root: Path = args.output.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    seen_keys = set()

    # find all annotation files
    ann_files = [p for p in chartqa_root.rglob("*") if p.suffix.lower() in KNOWN_ANN_EXTS]

    kept = skipped_src = broken = 0

    for ann_path in ann_files:
        ann = load_annotation(ann_path)
        if not isinstance(ann, dict):
            # skip non dict (unexpected jsonl, etc.)
            broken += 1
            continue

        # infer source
        src = infer_source_from_record(ann)
        if src is None or src not in args.allowed-sources:
            skipped_src += 1
            continue

        # locate siblings (image, table)
        img_path, tbl_path = guess_siblings(ann_path, ann)

        # require at least image + annotation; table is optional but preferred
        if img_path is None:
            broken += 1
            continue

        # build a stable key (by stem path under input + source)
        key = f"{src}::{ann_path.stem}"
        if key in seen_keys:
            # already handled
            continue
        seen_keys.add(key)

        # destination layout: mirror split-like folders if present
        # We’ll reconstruct /{src}/{relative_from_root}
        try:
            rel_ann = ann_path.relative_to(chartqa_root)
        except Exception:
            rel_ann = ann_path.name

        dst_ann = out_root / src / "annotations" / (Path(rel_ann).stem + ann_path.suffix.lower())

        # image filename mirrors annotation stem if possible; otherwise keep original name
        dst_img = out_root / src / "images" / (img_path.name if img_path else f"{ann_path.stem}.png")
        dst_tbl = out_root / src / "tables" / (tbl_path.name if tbl_path else f"{ann_path.stem}.csv")

        ok_ann = copy_unique(ann_path, dst_ann, args.dry_run)
        ok_img = copy_unique(img_path, dst_img, args.dry_run)
        ok_tbl = True
        if tbl_path is not None:
            ok_tbl = copy_unique(tbl_path, dst_tbl, args.dry_run)

        # Require at least ann+img to count as kept
        if ok_ann and ok_img:
            kept += 1
            manifest_rows.append({
                "source": src,
                "annotation_src": str(ann_path),
                "image_src": str(img_path) if img_path else "",
                "table_src": str(tbl_path) if tbl_path else "",
                "annotation_dst": str(dst_ann),
                "image_dst": str(dst_img),
                "table_dst": str(dst_tbl) if tbl_path else "",
                "has_table": bool(tbl_path),
            })
        else:
            broken += 1

    # write manifest
    if not args.dry_run:
        manifest_path = out_root / args.manifest-name
        with manifest_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "source",
                    "annotation_src", "image_src", "table_src",
                    "annotation_dst", "image_dst", "table_dst",
                    "has_table",
                ],
            )
            writer.writeheader()
            writer.writerows(manifest_rows)

    # final report
    print("==== Summary ====")
    print(f"Input root:  {chartqa_root}")
    print(f"Output root: {out_root}")
    print(f"Allowed:     {', '.join(args.allowed_sources)}")
    print(f"Annotations scanned: {len(ann_files)}")
    print(f"Kept (ok):           {kept}")
    print(f"Skipped (source):    {skipped_src}")
    print(f"Broken/missing:      {broken}")
    if not args.dry_run:
        print(f"Manifest:            {out_root / args.manifest_name}")
    print("Done.")
    

if __name__ == "__main__":
    main()
