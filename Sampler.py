#!/usr/bin/env python3
"""
sampler_select_copy.py

Equitably sample images across FULL subfolder paths (tasks) to reach a target total,
copy the selected images, write filtered annotations for the selection,
AND also copy/write the NOT-SELECTED remainder.

Defaults (all args have defaults):
- Inputs (annotations): if none provided, use ["input.json"]
- --target: 1366
- --path-field: image
- Grouping: full directory path (distinct by full path). You can override with --top/--tail.
- Copy selected to: ./picked_images
- Selected annotations: ./picked_annotations.json
- Copy remainder to: ./remainder_images
- Remainder annotations: ./remainder_annotations.json
- CSVs: none by default (set --out-csv/--out-rest-csv if you want them)

Usage examples
--------------
# Run with all defaults (expects input.json in CWD)
python sampler_select_copy.py

# Custom target and outputs
python sampler_select_copy.py anns1.json anns2.jsonl --target 1000 \
  --copy-to ./picked --out-ann picked.json \
  --copy-rest-to ./rest --out-rest-ann rest.json

# Shuffle within groups (reproducible)
python sampler_select_copy.py data.json --shuffle --seed 123

# Group by top-2 path segments (e.g., "stageA/chart_qa")
python sampler_select_copy.py data.json --top 2
"""

import argparse
import json
import os
import random
import shutil
import sys
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set

# -------------------- IO helpers --------------------

def is_jsonl(path: str) -> bool:
    return path.lower().endswith(".jsonl")

def load_json_array(path: str) -> List[Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array (list of objects).")
    return data

def load_jsonl(path: str) -> List[Any]:
    out: List[Any] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip("\n")
            if not s.strip():
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            out.append(obj)
    return out

def save_json_array(path: str, records: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def save_jsonl(path: str, records: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def norm_path(p: str) -> str:
    return os.path.normpath(p).replace("\\", "/")

def path_segments(p: str) -> List[str]:
    q = norm_path(p)
    return [seg for seg in q.split("/") if seg]

# -------------------- Grouping helpers --------------------

def full_dir_path_without_filename(p: str) -> str:
    q = norm_path(p)
    segs = path_segments(q)
    if not segs:
        return ""
    if "." in segs[-1]:
        segs = segs[:-1]
    return "/".join(segs) if segs else ""

def group_key_from_path(p: str, top: Optional[int], tail: Optional[int]) -> str:
    """
    Default: FULL directory path (distinct even if last segment name is shared elsewhere).
    Overrides:
      --top N  : first N segments
      --tail N : last  N segments
    """
    full_dir = full_dir_path_without_filename(p)
    if not full_dir:
        return ""
    segs = path_segments(full_dir)
    if top is not None:
        segs = segs[:max(0, top)]
    elif tail is not None:
        segs = segs[-max(0, tail):]
    return "/".join(segs) if segs else ""

# -------------------- Selection logic --------------------

def equitable_take_per_group(group_to_items: Dict[str, List[str]], target_total: int) -> Dict[str, List[str]]:
    """
    Near-equal allocation to reach target_total.
    - base = target_total // G
    - rem  = target_total % G
    - take min(base, size) from each; then round-robin one more from groups with spare.
    """
    groups = list(group_to_items.keys())
    G = len(groups)
    if G == 0 or target_total <= 0:
        return {g: [] for g in groups}

    base = target_total // G
    rem  = target_total % G

    selected: Dict[str, List[str]] = {g: [] for g in groups}
    spare: Dict[str, deque] = {}

    deficit = 0
    for g in groups:
        items = group_to_items[g]
        take = min(base, len(items))
        selected[g] = items[:take]
        spare[g] = deque(items[take:])
        if take < base:
            deficit += (base - take)

    to_alloc = rem + deficit
    if to_alloc > 0:
        ring = deque(groups)
        while to_alloc > 0 and ring:
            g = ring.popleft()
            if spare[g]:
                selected[g].append(spare[g].popleft())
                to_alloc -= 1
                ring.append(g)
            # if no spare for g, it drops out

    return selected

# -------------------- Copying --------------------

def resolve_source_path(image_path: str, images_root: Optional[str]) -> Optional[str]:
    cand1 = image_path
    if os.path.isabs(cand1) and os.path.isfile(cand1):
        return cand1
    if os.path.isfile(cand1):
        return os.path.abspath(cand1)
    if images_root:
        cand2 = os.path.join(images_root, image_path)
        if os.path.isfile(cand2):
            return os.path.abspath(cand2)
    return None

def copy_images(paths: List[str], copy_to: str, group_map: Dict[str, str], *,
                preserve_group_path: bool, images_root: Optional[str], dry_run: bool = False) -> (int, int):
    ensure_dir(copy_to)
    copied = 0
    missing = 0
    for p in paths:
        g = group_map.get(p, "unknown")
        src = resolve_source_path(p, images_root)
        if not src:
            missing += 1
            continue
        basename = os.path.basename(p)
        if preserve_group_path and g:
            dst_dir = os.path.join(copy_to, g)
        else:
            dst_dir = copy_to
        ensure_dir(dst_dir)
        dst = os.path.join(dst_dir, basename)
        if dry_run:
            copied += 1
            continue
        try:
            shutil.copy2(src, dst)
            copied += 1
        except Exception:
            missing += 1
    return copied, missing

# -------------------- Main --------------------

def main():
    ap = argparse.ArgumentParser(description="Equitably sample across FULL subfolder paths, copy selected and remainder, and write filtered annotations.")
    # Positional: allow zero or more; default to ["input.json"] if nothing passed
    ap.add_argument("annotations", nargs="*", help="Annotation files (.json array or .jsonl lines). Default: input.json")

    # Defaults set for every arg:
    ap.add_argument("--target", type=int, default=1366, help="Target total number of images to sample (default: 1366).")
    ap.add_argument("--path-field", default="image", help="Field that holds the image path (default: image).")

    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--top", type=int, default=None, help="Group by top N path segments (default: None).")
    grp.add_argument("--tail", type=int, default=None, help="Group by last N path segments (default: None).")

    ap.add_argument("--shuffle", action="store_true", default=False, help="Shuffle within each group (default: off).")
    ap.add_argument("--seed", type=int, default=42, help="Random seed when --shuffle is set (default: 42).")

    # Selected outputs (defaults)
    ap.add_argument("--copy-to", default="./picked_images", help="Destination dir to copy SELECTED images (default: ./picked_images).")
    ap.add_argument("--out-ann", default="./picked_annotations.json", help="Selected annotations path (.json or .jsonl) (default: ./picked_annotations.json).")
    ap.add_argument("--out-csv", default=None, help="Optional CSV listing selected images and groups (default: None).")

    # Remainder outputs (defaults)
    ap.add_argument("--copy-rest-to", default="./remainder_images", help="Destination dir to copy NOT-SELECTED images (default: ./remainder_images).")
    ap.add_argument("--out-rest-ann", default="./remainder_annotations.json", help="Annotations for NOT-SELECTED (.json or .jsonl) (default: ./remainder_annotations.json).")
    ap.add_argument("--out-rest-csv", default=None, help="Optional CSV listing NOT-SELECTED images and groups (default: None).")

    # Copy resolution & layout
    ap.add_argument("--images-root", default=None, help="Optional images root to resolve relative paths (default: None).")
    ap.add_argument("--flat", action="store_true", default=False, help="Do NOT preserve group path at destination (default: False).")
    ap.add_argument("--dry-run", action="store_true", default=False, help="Do everything except actual file copies (default: False).")

    args = ap.parse_args()

    inputs = args.annotations if args.annotations else ["input.json"]

    # Load all records
    all_records: List[Dict[str, Any]] = []
    for ann_path in inputs:
        try:
            recs = load_jsonl(ann_path) if is_jsonl(ann_path) else load_json_array(ann_path)
        except Exception as e:
            print(f"[WARN] {ann_path}: {e}. Skipping.", file=sys.stderr)
            continue
        for r in recs:
            if isinstance(r, dict):
                all_records.append(r)

    if not all_records:
        print("No valid records found from inputs:", inputs, file=sys.stderr)
        sys.exit(2)

    # Build groups (FULL PATH by default)
    image_to_group: Dict[str, str] = {}
    group_to_images: Dict[str, List[str]] = defaultdict(list)

    for r in all_records:
        p = r.get(args.path_field)
        if not isinstance(p, str) or not p.strip():
            continue
        p_norm = norm_path(p)
        g = group_key_from_path(p_norm, args.top, args.tail)
        if not g:
            continue
        image_to_group[p_norm] = g
        group_to_images[g].append(p_norm)

    # Deduplicate & order within each group
    for g, items in group_to_images.items():
        dedup = sorted(set(items))
        if args.shuffle:
            random.seed(args.seed)
            random.shuffle(dedup)
        group_to_images[g] = dedup

    # Equitable selection
    selected_by_group = equitable_take_per_group(group_to_images, args.target)
    selected_images: List[str] = [p for g in selected_by_group for p in selected_by_group[g]]
    selected_set: Set[str] = set(selected_images)

    # Remainder
    all_images_set: Set[str] = set()
    for items in group_to_images.values():
        all_images_set.update(items)
    remainder_set: Set[str] = all_images_set - selected_set
    remainder_images: List[str] = sorted(remainder_set)

    # Copy SELECTED
    copied_sel, missing_sel = copy_images(
        selected_images,
        args.copy_to,
        image_to_group,
        preserve_group_path=not args.flat,
        images_root=args.images_root,
        dry_run=args.dry_run,
    )

    # Copy REMAINDER
    copied_rest, missing_rest = copy_images(
        remainder_images,
        args.copy_rest_to,
        image_to_group,
        preserve_group_path=not args.flat,
        images_root=args.images_root,
        dry_run=args.dry_run,
    )

    # Filter annotations
    selected_records: List[Dict[str, Any]] = []
    remainder_records: List[Dict[str, Any]] = []
    for r in all_records:
        p = r.get(args.path_field)
        if not isinstance(p, str):
            continue
        pn = norm_path(p)
        if pn in selected_set:
            selected_records.append(r)
        elif pn in remainder_set:
            remainder_records.append(r)

    # Write out annotations
    def write_ann(path: str, records: List[Dict[str, Any]]):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".jsonl":
            save_jsonl(path, records)
        else:
            save_json_array(path, records)

    write_ann(args.out_ann, selected_records)
    write_ann(args.out_rest_ann, remainder_records)

    # Optional CSVs
    def write_csv(path: Optional[str], images: List[str]):
        if not path:
            return
        import csv
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["image", "group"])
            for p in images:
                w.writerow([p, image_to_group.get(p, "")])

    write_csv(args.out_csv, sorted(selected_images))
    write_csv(args.out_rest_csv, remainder_images)

    # Report
    total_groups = len(group_to_images)
    taken_total = len(selected_images)
    rest_total  = len(remainder_images)
    print("\n=== Sampler Summary ===")
    print(f"Inputs                : {inputs}")
    print(f"Groups (full subpaths): {total_groups}")
    for g in sorted(group_to_images.keys()):
        sel = len(selected_by_group.get(g, []))
        avail = len(group_to_images[g])
        print(f"  {g}: {sel} selected (of {avail} available)")
    print(f"\nSelected total        : {taken_total} (target {args.target})")
    print(f"Remainder total       : {rest_total}")
    print(f"\nSelected copies       : OK {copied_sel} | Missing {missing_sel} | Dest {args.copy_to}")
    print(f"Remainder copies      : OK {copied_rest} | Missing {missing_rest} | Dest {args.copy_rest_to}")
    print(f"\nSelected annotations  : {args.out_ann}")
    print(f"Remainder annotations : {args.out_rest_ann}")
    if args.out_csv:
        print(f"Selected CSV          : {args.out_csv}")
    if args.out_rest_csv:
        print(f"Remainder CSV         : {args.out_rest_csv}")

if __name__ == "__main__":
    main()
