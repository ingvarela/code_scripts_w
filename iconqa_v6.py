#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compose icon-based images for ICONQA-like data.

What’s new in this version
- Grid now enforces **per-icon uniformity**: within a single grid image,
  every occurrence of the same source icon uses the exact same rotation and size.
- Keeps earlier guarantees: rotated-fit (no spill), strict non-overlap in scatter,
  PNG/JPG/JPEG (optional SVG), random grids (grid:auto) with repetitions,
  range auto-fixing, and optional --grid-uniform-size for same size across ALL cells.

Usage example:
  python icon_composer.py --pool ./icons --out ./out --n 100 \
    --templates grid:auto --grid-min-rows 2 --grid-max-rows 3 \
    --grid-min-cols 3 --grid-max-cols 4 --grid-k-min 1 --grid-k-max 4 \
    --rot-max 8 --bg random \
    --grid-uniform-size --grid-uniform-fill 0.9
"""

import argparse
import json
import math
import random
import re
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Union

from PIL import Image, ImageDraw, ImageColor

Number = Union[int, float]

# -------------------------- range & IO helpers --------------------------

def fix_pair(name: str, lo: Number, hi: Number,
             lo_floor: Optional[Number] = None,
             hi_ceiling: Optional[Number] = None) -> Tuple[Number, Number]:
    """Swap reversed ranges and clamp within optional bounds."""
    if hi < lo:
        print(f"[warn] swapping {name}: ({lo}, {hi}) -> ({hi}, {lo})")
        lo, hi = hi, lo
    if lo_floor is not None and lo < lo_floor:
        print(f"[warn] clamping {name} low from {lo} to {lo_floor}")
        lo = lo_floor
    if hi_ceiling is not None and hi > hi_ceiling:
        print(f"[warn] clamping {name} high from {hi} to {hi_ceiling}")
        hi = hi_ceiling
    return lo, hi

def list_icons(pool: Path, allow_svg=False) -> List[Path]:
    exts = {".png", ".jpg", ".jpeg"}
    if allow_svg:
        exts.add(".svg")
    files = [p for p in pool.rglob("*") if p.suffix.lower() in exts]
    if not files:
        raise SystemExit(f"No icons found in {pool} (PNG/JPG/JPEG"
                         f"{' + SVG' if allow_svg else ''}).")
    return files

def load_icon_any(path: Path, allow_svg=False) -> Image.Image:
    suf = path.suffix.lower()
    if suf in (".png", ".jpg", ".jpeg"):
        return Image.open(path).convert("RGBA")
    if suf == ".svg" and allow_svg:
        try:
            import cairosvg, io
            png_bytes = cairosvg.svg2png(url=str(path))
            return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        except Exception as e:
            raise RuntimeError(f"Failed to render SVG {path}: {e}")
    raise RuntimeError(f"Unsupported file type: {path}")

def ensure_out(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

# -------------------------- geometry & scaling --------------------------

def iou(a: Tuple[int,int,int,int], b: Tuple[int,int,int,int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    aarea = (ax2 - ax1) * (ay2 - ay1)
    barea = (bx2 - bx1) * (by2 - by1)
    return inter / float(aarea + barea - inter + 1e-9)

def try_place_nonoverlap(canvas_w: int, canvas_h: int,
                         box_w: int, box_h: int,
                         placed: List[Tuple[int,int,int,int]],
                         max_tries: int = 250, margin: int = 2) -> Optional[Tuple[int,int]]:
    """Find a non-overlapping (x,y) or return None if impossible."""
    avail_w = canvas_w - 2*margin - box_w
    avail_h = canvas_h - 2*margin - box_h
    if avail_w < 0 or avail_h < 0:
        return None
    for _ in range(max_tries):
        x = random.randint(margin, margin + avail_w)
        y = random.randint(margin, margin + avail_h)
        box = (x, y, x + box_w, y + box_h)
        if all(iou(b
