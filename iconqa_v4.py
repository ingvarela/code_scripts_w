#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compose icon-based images for ICONQA-like data.

Fixes in this version:
- Always scale to the *rotated* bounding box so icons never exceed their box.
- Applies that fit logic to grid cells, scatter placements, and row items.
- JPG/JPEG/PNG (and optional SVG) input support, strict non-overlap, grid:auto,
  repeated icons per grid, and min/max range auto-normalization.

Usage example:
  python icon_composer.py --pool ./icons --out ./out --n 100 \
    --templates row scatter grid:auto --grid-min-rows 1 --grid-max-rows 3 \
    --grid-min-cols 3 --grid-max-cols 5 --grid-k-min 1 --grid-k-max 4 \
    --scatter-min 8 --scatter-max 12 --rot-max 8 --bg random
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
    avail_w = canvas_w - 2*margin - box_w
    avail_h = canvas_h - 2*margin - box_h
    if avail_w < 0 or avail_h < 0:
        return None
    for _ in range(max_tries):
        x = random.randint(margin, margin + avail_w)
        y = random.randint(margin, margin + avail_h)
        box = (x, y, x + box_w, y + box_h)
        if all(iou(box, b) == 0.0 for b in placed):
            return (x, y)
    return None

def paste_rgba(dst: Image.Image, src: Image.Image, xy: Tuple[int,int]):
    dst.alpha_composite(src, dest=xy)

def rand_bg(color: Optional[str], size: Tuple[int,int]) -> Image.Image:
    if color and color != "random":
        return Image.new("RGBA", size, ImageColor.getrgb(color) + (255,))
    if color == "random":
        r, g, b = random.randint(220,255), random.randint(220,255), random.randint(220,255)
        return Image.new("RGBA", size, (r, g, b, 255))
    return Image.new("RGBA", size, (255, 255, 255, 255))

def rotated_bbox_scale_limit(w0: int, h0: int, max_w: int, max_h: int, rot_deg: float) -> float:
    """
    Given original size (w0,h0), the available box (max_w,max_h), and rotation,
    return the largest scale s so that the *rotated* bounding box fits.
    Rotated bbox of a w×h rectangle by angle θ has:
      W_rot = |w*cosθ| + |h*sinθ|
      H_rot = |w*sinθ| + |h*cosθ|
    We need s * W_rot <= max_w and s * H_rot <= max_h.
    """
    if max_w <= 0 or max_h <= 0 or w0 <= 0 or h0 <= 0:
        return 0.0
    theta = abs(rot_deg) * math.pi / 180.0
    c = abs(math.cos(theta))
    s = abs(math.sin(theta))
    denom_w = w0 * c + h0 * s
    denom_h = w0 * s + h0 * c
    if denom_w <= 0 or denom_h <= 0:
        return 0.0
    return min(max_w / denom_w, max_h / denom_h)

def rotate_and_scale_fit(icon: Image.Image,
                         scale_min: float, scale_max: float,
                         rot_min: float, rot_max: float,
                         max_w: int, max_h: int) -> Optional[Tuple[Image.Image, float, float]]:
    """
    Pick a rotation, compute the maximum allowed scale so that the rotated bbox fits
    within (max_w,max_h), then pick a scale <= that limit. Returns (image, scale, rot).
    """
    if max_w <= 0 or max_h <= 0:
        return None
    rot_deg = random.uniform(rot_min, rot_max)
    w0, h0 = icon.size
    # hard scale cap due to the rotated bbox
    s_fit = rotated_bbox_scale_limit(w0, h0, max_w, max_h, rot_deg)
    if s_fit <= 0:
        return None
    # choose scale within user range but not exceeding s_fit
    s_hi = min(scale_max, s_fit)
    if s_hi <= 0:
        return None
    s_lo = min(scale_min, s_hi)  # if s_fit < scale_min, we still shrink to fit
    scale = random.uniform(s_lo, s_hi)
    # apply
    nw, nh = max(1, int(round(w0 * scale))), max(1, int(round(h0 * scale)))
    tmp = icon.resize((nw, nh), Image.LANCZOS)
    if abs(rot_deg) > 0.01:
        tmp = tmp.rotate(rot_deg, expand=True, resample=Image.BICUBIC)
    return tmp, scale, rot_deg

def file_label(path: Path) -> str:
    return path.stem

# -------------------------- layouts (fit-aware) --------------------------

def layout_row(canvas: Image.Image, icons: List[Image.Image], src_paths: List[Path],
               row_min: int, row_max: int, scale_range: Tuple[float,float],
               rot_range: Tuple[float,float], left_margin=16, right_margin=16,
               gap_range: Tuple[int,int]=(6,18), v_center=True) -> List[Dict]:
    W, H = canvas.size
    n = random.randint(row_min, row_max)
    placed_meta = []
    x = left_margin
    mid_y = H // 2
    for _ in range(n):
        idx = random.randrange(len(icons))
        base = icons[idx]
        pth = src_paths[idx]

        # space left in this row
        max_w = max(1, W - right_margin - x)
        max_h = H - 4  # small top/bottom buffer

        rs = rotate_and_scale_fit(
            base, scale_min=scale_range[0], scale_max=scale_range[1],
            rot_min=rot_range[0], rot_max=rot_range[1],
            max_w=max_w, max_h=max_h
        )
        if rs is None:
            break  # nothing else fits
        im, _, _ = rs
        w, h = im.size
        y = mid_y - (h // 2) if v_center else random.randint(0, max(0, H - h))
        paste_rgba(canvas, im, (x, y))
        bbox = (x, y, x + w, y + h)
        placed_meta.append({"label": file_label(pth), "source": str(pth), "bbox": bbox})
        x += w + random.randint(*gap_range)
        if x + right_margin >= W:
            break
    return placed_meta

def layout_scatter(canvas: Image.Image, icons: List[Image.Image], src_paths: List[Path],
                   k_range: Tuple[int,int], scale_range: Tuple[float,float],
                   rot_range: Tuple[float,float]) -> List[Dict]:
    W, H = canvas.size
    k = random.randint(*k_range)
    placed_boxes: List[Tuple[int,int,int,int]] = []
    placed_meta: List[Dict] = []
    tries = 0
    max_attempts = k * 80
    while len(placed_meta) < k and tries < max_attempts:
        tries += 1
        idx = random.randrange(len(icons))
        base = icons[idx]
        pth = src_paths[idx]

        # fit to whole canvas (with a bit of safety margin in placement fn)
        rs = rotate_and_scale_fit(
            base, scale_min=scale_range[0], scale_max=scale_range[1],
            rot_min=rot_range[0], rot_max=rot_range[1],
            max_w=W - 6, max_h=H - 6
        )
        if rs is None:
            continue
        im, _, _ = rs
        w, h = im.size

        pos = try_place_nonoverlap(W, H, w, h, placed_boxes)
        if pos is None:
            continue
        x, y = pos
        paste_rgba(canvas, im, (x, y))
        bbox = (x, y, x + w, y + h)
        placed_boxes.append(bbox)
        placed_meta.append({"label": file_label(pth), "source": str(pth), "bbox": bbox})
    return placed_meta

def draw_cell_border(draw: ImageDraw.ImageDraw, box: Tuple[int,int,int,int],
                     width=2, color=(200,200,210,255)):
    x1,y1,x2,y2 = box
    for i in range(width):
        draw.rectangle((x1+i, y1+i, x2-i, y2-i), outline=color)

def choose_grid_icons(src_count: int, total_cells: int,
                      k_min: int, k_max: int) -> List[int]:
    k_max_eff = max(1, min(k_max, src_count, total_cells))
    k_min_eff = max(1, min(k_min, k_max_eff))
    k = random.randint(k_min_eff, k_max_eff)
    if k <= src_count:
        distinct = random.sample(range(src_count), k)
    else:
        distinct = [random.randrange(src_count) for _ in range(k)]
    return [random.choice(distinct) for _ in range(total_cells)]

def layout_grid(canvas: Image.Image, icons: List[Image.Image], src_paths: List[Path],
                R: int, C: int, cell_pad: int, scale_fill_range=(0.8, 0.95),
                rot_range: Tuple[float,float]=(0,0), box_borders=True,
                distinct_k_range: Tuple[int,int]=(1,4)) -> List[Dict]:
    W, H = canvas.size
    cell_w = W // C
    cell_h = H // R
    draw = ImageDraw.Draw(canvas)
    placed_meta: List[Dict] = []
    total = R * C

    picks = choose_grid_icons(len(icons), total,
                              distinct_k_range[0], distinct_k_range[1])

    for idx_cell in range(total):
        r = idx_cell // C
        c = idx_cell % C
        idx_icon = picks[idx_cell]
        base = icons[idx_icon]
        pth = src_paths[idx_icon]

        # max allowed interior per cell (with padding)
        max_w = max(1, cell_w - 2*cell_pad)
        max_h = max(1, cell_h - 2*cell_pad)

        # vary fill target but still honor rotated-fit
        # We'll map scale_fill_range to a target fraction of the cell box—we enforce
        # fit to the actual box anyway via rotate_and_scale_fit.
        rs = rotate_and_scale_fit(
            base,
            scale_min=0.05,  # allow shrinking hard if needed
            scale_max=10.0,  # allow growing but bounded by fit
            rot_min=rot_range[0], rot_max=rot_range[1],
            max_w=int(max_w * random.uniform(*scale_fill_range)),
            max_h=int(max_h * random.uniform(*scale_fill_range))
        )
        if rs is None:
            continue
        im, _, _ = rs
        w, h = im.size

        # center within cell
        x1 = c * cell_w + (cell_w - w)//2
        y1 = r * cell_h + (cell_h - h)//2
        paste_rgba(canvas, im, (x1, y1))
        bbox = (x1, y1, x1 + w, y1 + h)
        placed_meta.append({"label": file_label(pth), "source": str(pth), "bbox": bbox})

        if box_borders:
            cell_box = (c*cell_w, r*cell_h, (c+1)*cell_w-1, (r+1)*cell_h-1)
            draw_cell_border(draw, cell_box, width=2)
    return placed_meta

# -------------------------- templates & main --------------------------

def parse_templates(arg: List[str]) -> List[Tuple[str,Tuple[int,int]]]:
    out = []
    for t in arg:
        if t in ("row", "scatter", "grid4", "grid:auto"):
            out.append((t, (0,0)))
        else:
            m = re.match(r"grid:(\d+)x(\d+)$", t)
            if m:
                R, C = int(m.group(1)), int(m.group(2))
                out.append(("gridRC", (R, C)))
            else:
                raise SystemExit(f"Unknown template: {t}")
    return out

def pick_auto_grid(min_r: int, max_r: int, min_c: int, max_c: int) -> Tuple[int,int]:
    min_r, max_r = fix_pair("grid rows(auto)", min_r, max_r, lo_floor=1)
    min_c, max_c = fix_pair("grid cols(auto)", min_c, max_c, lo_floor=1)
    return random.randint(min_r, max_r), random.randint(min_c, max_c)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, type=Path, help="Folder with PNG/JPG/JPEG (and optional SVG) icons.")
    ap.add_argument("--out", required=True, type=Path, help="Output folder for images and metadata.jsonl")
    ap.add_argument("--n", type=int, default=50, help="Number of images to generate.")
    ap.add_argument("--templates", nargs="+", default=["row","scatter","grid4","grid:auto"],
                    help="Templates: row scatter grid4 grid:RxC grid:auto")
    ap.add_argument("--canvas", nargs=2, type=int, default=[768, 256], help="Canvas WxH.")
    ap.add_argument("--bg", type=str, default="white", help="Background: white | random | #RRGGBB | css name.")
    ap.add_argument("--seed", type=int, default=None, help="Random seed.")
    ap.add_argument("--allow-svg", action="store_true", help="Also load SVG (needs cairosvg).")

    # row options
    ap.add_argument("--row-min", type=int, default=8)
    ap.add_argument("--row-max", type=int, default=14)
    ap.add_argument("--row-gap-min", type=int, default=6)
    ap.add_argument("--row-gap-max", type=int, default=18)

    # scatter options
    ap.add_argument("--scatter-min", type=int, default=8)
    ap.add_argument("--scatter-max", type=int, default=12)

    # scaling / rotation (user prefs; actual scale is capped by fit)
    ap.add_argument("--scale-min", type=float, default=0.6)
    ap.add_argument("--scale-max", type=float, default=1.2)
    ap.add_argument("--rot-min", type=float, default=0.0)
    ap.add_argument("--rot-max", type=float, default=0.0, help="Allow rotations (e.g., 0 25).")

    # grid options
    ap.add_argument("--grid4-canvas", nargs=2, type=int, default=None,
                    help="Override canvas WxH for grid4 (e.g., 768 192).")
    ap.add_argument("--cell-pad", type=int, default=10)
    ap.add_argument("--grid-k-min", type=int, default=1, help="Min distinct icons per grid.")
    ap.add_argument("--grid-k-max", type=int, default=4, help="Max distinct icons per grid.")
    ap.add_argument("--grid-min-rows", type=int, default=1)
    ap.add_argument("--grid-max-rows", type=int, default=3)
    ap.add_argument("--grid-min-cols", type=int, default=3)
    ap.add_argument("--grid-max-cols", type=int, default=5)

    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    # normalize ranges
    args.row_min, args.row_max           = fix_pair("row count", args.row_min, args.row_max, lo_floor=1)
    args.row_gap_min, args.row_gap_max   = fix_pair("row gap", args.row_gap_min, args.row_gap_max, lo_floor=0)
    args.scatter_min, args.scatter_max   = fix_pair("scatter count", args.scatter_min, args.scatter_max, lo_floor=1)
    args.scale_min, args.scale_max       = fix_pair("scale", args.scale_min, args.scale_max)
    args.rot_min, args.rot_max           = fix_pair("rotation", args.rot_min, args.rot_max)
    args.grid_min_rows, args.grid_max_rows = fix_pair("grid rows", args.grid_min_rows, args.grid_max_rows, lo_floor=1)
    args.grid_min_cols, args.grid_max_cols = fix_pair("grid cols", args.grid_min_cols, args.grid_max_cols, lo_floor=1)
    args.grid_k_min, args.grid_k_max     = fix_pair("grid distinct-k", args.grid_k_min, args.grid_k_max, lo_floor=1)

    ensure_out(args.out)
    meta_path = args.out / "metadata.jsonl"

    # load icons
    icons_paths = list_icons(args.pool, allow_svg=args.allow_svg)
    preloaded: Dict[Path, Image.Image] = {p: load_icon_any(p, allow_svg=args.allow_svg) for p in icons_paths}

    templates = parse_templates(args.templates)
    W, H = args.canvas

    with meta_path.open("w", encoding="utf-8") as fmeta:
        for i in range(args.n):
            kind, rc = random.choice(templates)

            if kind == "grid4" and args.grid4_canvas:
                Wt, Ht = args.grid4_canvas
            else:
                Wt, Ht = W, H

            canvas = rand_bg(args.bg, (Wt, Ht))
            icons = list(preloaded.values())
            srcs  = list(preloaded.keys())

            if kind == "row":
                placed = layout_row(
                    canvas, icons, srcs,
                    row_min=args.row_min, row_max=args.row_max,
                    scale_range=(args.scale_min, args.scale_max),
                    rot_range=(args.rot_min, args.rot_max),
                    gap_range=(args.row_gap_min, args.row_gap_max)
                )
                layout_name = "row"

            elif kind == "scatter":
                placed = layout_scatter(
                    canvas, icons, srcs,
                    k_range=(args.scatter_min, args.scatter_max),
                    scale_range=(args.scale_min, args.scale_max),
                    rot_range=(args.rot_min, args.rot_max)
                )
                layout_name = "scatter"

            elif kind == "grid4":
                placed = layout_grid(
                    canvas, icons, srcs, R=1, C=4, cell_pad=args.cell_pad,
                    scale_fill_range=(0.82, 0.92),
                    rot_range=(args.rot_min, args.rot_max), box_borders=True,
                    distinct_k_range=(args.grid_k_min, args.grid_k_max)
                )
                layout_name = "grid:1x4"

            elif kind == "gridRC":
                R, C = rc
                placed = layout_grid(
                    canvas, icons, srcs, R=R, C=C, cell_pad=args.cell_pad,
                    scale_fill_range=(0.85, 0.95),
                    rot_range=(args.rot_min, args.rot_max), box_borders=True,
                    distinct_k_range=(args.grid_k_min, args.grid_k_max)
                )
                layout_name = f"grid:{R}x{C}"

            elif kind == "grid:auto":
                R, C = pick_auto_grid(args.grid_min_rows, args.grid_max_rows,
                                      args.grid_min_cols, args.grid_max_cols)
                placed = layout_grid(
                    canvas, icons, srcs, R=R, C=C, cell_pad=args.cell_pad,
                    scale_fill_range=(0.85, 0.95),
                    rot_range=(args.rot_min, args.rot_max), box_borders=True,
                    distinct_k_range=(args.grid_k_min, args.grid_k_max)
                )
                layout_name = f"grid:{R}x{C}"

            else:
                raise RuntimeError("Unknown template dispatch")

            fname = f"comp_{i:06d}.png"
            out_img = args.out / fname
            canvas.convert("RGBA").save(out_img)

            record = {
                "id": Path(fname).stem,
                "image": fname,
                "layout": layout_name,
                "canvas_size": [Wt, Ht],
                "objects": placed,
            }
            fmeta.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Done. Images in: {args.out}\nMetadata: {meta_path}")
    print("Tip: --rot-max 25 and --bg random increase variety; "
          "use --grid-k-min/--grid-k-max to control repetitions per grid.")

if __name__ == "__main__":
    main()
