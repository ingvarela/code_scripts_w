#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
row_strip_uniform.py
Create one horizontal strip with 3–5 images from a folder.
- Supports .png, .jpg, .jpeg inputs
- Picks K in [3, 5] randomly (or force with --k)
- All images are resized to the same target cell size and centered
- Saves a single PNG

Usage:
  python row_strip_uniform.py --pool ./imgs --out ./out/strip.png
  python row_strip_uniform.py --pool ./imgs --out ./out/strip.png --cell 192 192 --gap 20
  python row_strip_uniform.py --pool ./imgs --out ./out/strip.png --k 4
"""

import argparse
from pathlib import Path
import random
from typing import List, Tuple
from PIL import Image, ImageColor

# ---------- helpers ----------

def list_images(folder: Path) -> List[Path]:
    exts = {".png", ".jpg", ".jpeg"}
    files = [p for p in folder.rglob("*") if p.suffix.lower() in exts]
    if not files:
        raise SystemExit(f"No images found in {folder} (need PNG/JPG/JPEG).")
    return files

def load_rgba(p: Path) -> Image.Image:
    return Image.open(p).convert("RGBA")

def fit_within(im: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize im to fit entirely within target_w x target_h (preserve aspect)."""
    w, h = im.size
    scale = min(target_w / max(1, w), target_h / max(1, h))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return im.resize((nw, nh), Image.LANCZOS)

def make_canvas(w: int, h: int, bg: str) -> Image.Image:
    if bg == "transparent":
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # solid background
    rgb = ImageColor.getrgb(bg)
    return Image.new("RGBA", (w, h), (*rgb, 255))

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=Path, required=True, help="Folder with PNG/JPG/JPEG images.")
    ap.add_argument("--out", type=Path, required=True, help="Output PNG path.")
    ap.add_argument("--k", type=int, default=None, help="Number of images in the row (3–5).")
    ap.add_argument("--cell", nargs=2, type=int, default=[192, 192], help="Cell width height (default 192 192).")
    ap.add_argument("--gap", type=int, default=16, help="Gap between cells (px).")
    ap.add_argument("--margin", type=int, default=16, help="Left/right/top/bottom margin (px).")
    ap.add_argument("--bg", type=str, default="white", help='Background: "white", "#RRGGBB", "transparent", etc.')
    ap.add_argument("--seed", type=int, default=None, help="Random seed (optional).")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    paths = list_images(args.pool)

    # choose K
    if args.k is None:
        K = random.randint(3, 5)
    else:
        if args.k < 3 or args.k > 5:
            print(f"[warn] --k {args.k} out of [3,5], clamping.")
            K = min(5, max(3, args.k))
        else:
            K = args.k

    # sample paths (without replacement if enough, else with replacement)
    if len(paths) >= K:
        picks = random.sample(paths, K)
    else:
        picks = [random.choice(paths) for _ in range(K)]

    cell_w, cell_h = args.cell
    gap = args.gap
    margin = args.margin

    # compute canvas size (single row)
    canvas_w = margin + K * cell_w + (K - 1) * gap + margin
    canvas_h = margin + cell_h + margin

    canvas = make_canvas(canvas_w, canvas_h, args.bg)

    # lay out each cell: same target box for all; center inside its slot
    x = margin
    y = margin
    for p in picks:
        im = load_rgba(p)
        thumb = fit_within(im, cell_w, cell_h)
        tw, th = thumb.size
        # center inside the cell box
        ox = x + (cell_w - tw) // 2
        oy = y + (cell_h - th) // 2
        canvas.alpha_composite(thumb, dest=(ox, oy))
        x += cell_w + gap

    # save
    args.out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out)
    print(f"Saved: {args.out}  (K={K}, cell={cell_w}x{cell_h}, gap={gap}, margin={margin})")

if __name__ == "__main__":
    main()
