#!/usr/bin/env python3
"""
Randomly sample images from a folder and filter metadata.csv accordingly,
optionally excluding any images listed in previous metadata files.

- Picks up to N images at random (without replacement).
- Copies selected images into an output folder.
- Writes a second metadata.csv with only the selected rows.
- Supports exclusions from prior runs via --exclude (repeatable).

Assumptions:
- Your metadata CSV has a column named 'image_id'.
- 'image_id' can be a filename (with or without extension) or a relative path.
- Images live under the provided --images folder (search is recursive).

Usage example:
    python sample_images_and_metadata.py \
        --images /data/images \
        --metadata /data/metadata.csv \
        --num 500 \
        --outdir /data/sample_out \
        --seed 42 \
        --exclude /data/past_sample_1/metadata.csv \
        --exclude /data/past_sample_2/metadata.csv \
        --overwrite
"""

import argparse
import os
import random
import shutil
import sys
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".tif"}


def build_file_index(image_dir: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """
    Index images under image_dir (recursive).

    Returns:
        id_to_path: maps lowercase basename (with extension) -> absolute path
        stem_to_paths: maps lowercase stem (no extension) -> list of absolute paths
    """
    id_to_path: Dict[str, str] = {}
    stem_to_paths: Dict[str, List[str]] = {}

    for root, _, files in os.walk(image_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTS:
                p = os.path.join(root, f)
                base = os.path.basename(p)
                key = base.lower()
                id_to_path[key] = p

                stem = os.path.splitext(base)[0].lower()
                stem_to_paths.setdefault(stem, []).append(p)

    return id_to_path, stem_to_paths


def resolve_image_path(
    name: str,
    id_to_path: Dict[str, str],
    stem_to_paths: Dict[str, List[str]],
) -> Optional[str]:
    """
    Resolve an image filename (with or without extension) to a path in the index.
    Case-insensitive. If no extension, picks a sensible first match (prefers PNG/JPG).
    """
    base = os.path.basename(str(name).strip())
    if not base:
        return None
    stem, ext = os.path.splitext(base)
    if ext:
        return id_to_path.get(base.lower())

    # No extension provided: try stem lookup
    candidates = stem_to_paths.get(stem.lower())
    if not candidates:
        return None

    preference = {".png": 0, ".jpg": 1, ".jpeg": 2, ".webp": 3, ".bmp": 4, ".gif": 5, ".tiff": 6, ".tif": 7}
    candidates = sorted(candidates, key=lambda p: preference.get(os.path.splitext(p)[1].lower(), 99))
    return candidates[0]


def collect_exclusions(
    exclude_csv_paths: List[str],
    id_to_path: Dict[str, str],
    stem_to_paths: Dict[str, List[str]],
) -> Set[str]:
    """
    Read prior metadata.csv files and collect a set of basenames (lowercased)
    to exclude from the new sample. Resolution uses the same logic as selection.
    """
    excluded: Set[str] = set()
    for csv_path in exclude_csv_paths:
        if not os.path.isfile(csv_path):
            print(f"WARNING: exclude file not found: {csv_path}", file=sys.stderr)
            continue
        try:
            df_ex = pd.read_csv(csv_path, dtype=str, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df_ex = pd.read_csv(csv_path, dtype=str, encoding="utf-8")

        if "image_id" not in df_ex.columns:
            print(f"WARNING: exclude file missing 'image_id' column: {csv_path}", file=sys.stderr)
            continue

        resolved_paths = df_ex["image_id"].apply(lambda x: resolve_image_path(str(x), id_to_path, stem_to_paths))
        hits = resolved_paths.dropna().tolist()
        for p in hits:
            excluded.add(os.path.basename(p).lower())

        misses = resolved_paths.isna().sum()
        if misses:
            print(f"NOTE: {misses} exclude entries in {os.path.basename(csv_path)} did not resolve in --images.", file=sys.stderr)

    return excluded


def main():
    parser = argparse.ArgumentParser(description="Randomly sample images and filter metadata (with optional exclusions).")
    parser.add_argument("--images", required=True, help="Path to folder containing images (searches recursively).")
    parser.add_argument("--metadata", required=True, help="Path to metadata.csv (must include 'image_id' column).")
    parser.add_argument("--num", type=int, required=True, help="Target number of images to copy (max = available).")
    parser.add_argument("--outdir", default=None, help="Output folder (default: <images>_sampled).")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite files/metadata if already present.")
    parser.add_argument("--exclude", action="append", default=[], help="Path to a prior metadata.csv to exclude. Repeatable.")
    args = parser.parse_args()

    image_dir = os.path.abspath(args.images)
    meta_csv = os.path.abspath(args.metadata)
    out_dir = os.path.abspath(args.outdir or (image_dir.rstrip(os.sep) + "_sampled"))

    if not os.path.isdir(image_dir):
        print(f"ERROR: images folder not found: {image_dir}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(meta_csv):
        print(f"ERROR: metadata.csv not found: {meta_csv}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    out_meta_path = os.path.join(out_dir, "metadata.csv")
    if os.path.exists(out_meta_path) and not args.overwrite:
        print(f"ERROR: {out_meta_path} exists. Use --overwrite to replace.", file=sys.stderr)
        sys.exit(1)

    if args.seed is not None:
        random.seed(args.seed)

    # Index the image files available
    id_to_path, stem_to_paths = build_file_index(image_dir)
    if not id_to_path:
        print(f"ERROR: No image files with supported extensions found under: {image_dir}", file=sys.stderr)
        sys.exit(1)

    # Load main metadata
    try:
        df = pd.read_csv(meta_csv, dtype=str, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(meta_csv, dtype=str, encoding="utf-8")  # fallback

    if "image_id" not in df.columns:
        print("ERROR: metadata.csv must contain a column named 'image_id'.", file=sys.stderr)
        sys.exit(1)

    # Resolve each metadata row to an actual file present in image_dir
    df["__resolved_path__"] = df["image_id"].apply(lambda x: resolve_image_path(str(x), id_to_path, stem_to_paths))
    matched = df[~df["__resolved_path__"].isna()].copy()
    matched["__resolved_base__"] = matched["__resolved_path__"].apply(lambda p: os.path.basename(p).lower())

    if matched.empty:
        print("ERROR: None of the metadata rows matched an image in the folder.", file=sys.stderr)
        sys.exit(1)

    # Collect exclusions (from prior metadata.csv files)
    excluded_basenames: Set[str] = set()
    if args.exclude:
        excluded_basenames = collect_exclusions(args.exclude, id_to_path, stem_to_paths)

    # Apply exclusions
    before = len(matched)
    if excluded_basenames:
        matched = matched[~matched["__resolved_base__"].isin(excluded_basenames)].copy()
    removed = before - len(matched)

    if matched.empty:
        print("ERROR: After applying exclusions, no images remain to sample.", file=sys.stderr)
        sys.exit(1)

    # Sample up to N rows
    target = min(args.num, len(matched))
    sampled = matched.sample(n=target, random_state=args.seed if args.seed is not None else None)

    # Copy selected images
    copied = 0
    for src in sampled["__resolved_path__"]:
        dst = os.path.join(out_dir, os.path.basename(src))
        if os.path.exists(dst) and not args.overwrite:
            # skip silently unless overwrite requested
            continue
        shutil.copy2(src, dst)
        copied += 1

    # Write filtered metadata
    sampled.drop(columns=["__resolved_path__","__resolved_base__"]).to_csv(out_meta_path, index=False, encoding="utf-8")

    # Report
    print("Done.")
    print(f" - Matchable rows in main metadata: {before}")
    print(f" - Excluded due to prior sets:     {removed} (from {len(excluded_basenames)} unique basenames)")
    print(f" - Remaining candidates:           {len(matched)}")
    print(f" - Selected rows:                  {len(sampled)}")
    print(f" - Images copied:                  {copied} → {out_dir}")
    print(f" - New filtered metadata:          {out_meta_path}")


if __name__ == "__main__":
    main()