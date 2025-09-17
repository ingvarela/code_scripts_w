#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, random, math, re
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from PIL import Image, ImageDraw, ImageOps, ImageColor

# -------------------------- IO utils --------------------------

def list_icons(pool: Path, allow_svg=False) -> List[Path]:
    exts = {".png", ".jpg", ".jpeg"}
    if allow_svg:
        exts.add(".svg")
    files = [p for p in pool.rglob("*") if p.suffix.lower() in exts]
    if not files:
        raise SystemExit(f"No icons found in {pool} (expected PNG/JPG/JPEG"
                         f"{'+SVG' if allow_svg else ''}).")
    return files

def load_png_or_jpg(path: Path) -> Image.Image:
    # JPG/JPEG have no alpha; convert to RGBA with full opacity
    im = Image.open(path).convert("RGBA")
    return im

def load_icon_any(path: Path, allow_svg=False) -> Image.Image:
    suf = path.suffix.lower()
    if suf in (".png", ".jpg", ".jpeg"):
        return load_png_or_jpg(path)
    if suf == ".svg" and allow_svg:
        try:
            import cairosvg, io
            png_bytes = cairosvg.svg2png(url=str(path))
            return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        except Exception as e:
            raise RuntimeError(f"Failed to render SVG {path}: {e}")
    raise RuntimeError(f"Unsupported file: {path}")

def ensure_out(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

# -------------------------- geometry helpers --------------------------

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

def try_place_nonoverlap(w: int, h: int, box_w: int, box_h: int,
                         placed: List[Tuple[int,int,int,int]],
                         max_tries=250, margin=2) -> Optional[Tuple[int,int]]:
    for _ in range(max_tries):
        x = random.randint(margin, max(0, w - box_w - margin))
        y = random.randint(margin, max(0, h - box_h - margin))
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

def rotate_and_scale(icon: Image.Image, scale: float, rot_deg: float) -> Image.Image:
    w, h = icon.size
    nw, nh = int(max(1, w * scale)), int(max(1, h * scale))
    tmp = icon.resize((nw, nh), Image.LANCZOS)
    if rot_deg != 0:
        tmp = tmp.rotate(rot_deg, expand=True, resample=Image.BICUBIC)
    return tmp

def file_label(path: Path) -> str:
    return path.stem

# -------------------------- layouts --------------------------

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
        im = rotate_and_scale(base, random.uniform(*scale_range),
                              random.uniform(*rot_range))
        w, h = im.size
        if x + w + right_margin > W:
            break
        y = mid_y - (h // 2) if v_center else random.randint(0, max(0, H - h))
        paste_rgba(canvas, im, (x, y))
        bbox = (x, y, x + w, y + h)
        placed_meta.append({"label": file_label(pth), "source": str(pth), "bbox": bbox})
        x += w + random.randint(*gap_range)
    return placed_meta  # no overlap by construction

def layout_scatter(canvas: Image.Image, icons: List[Image.Image], src_paths: List[Path],
                   k_range: Tuple[int,int], scale_range: Tuple[float,float],
                   rot_range: Tuple[float,float]) -> List[Dict]:
    # hard-enforce non-overlap
    W, H = canvas.size
    k = random.randint(*k_range)
    placed_boxes: List[Tuple[int,int,int,int]] = []
    placed_meta: List[Dict] = []
    tries = 0
    max_attempts = k * 60
    while len(placed_meta) < k and tries < max_attempts:
        tries += 1
        idx = random.randrange(len(icons))
        base = icons[idx]
        pth = src_paths[idx]
        im = rotate_and_scale(base, random.uniform(*scale_range),
                              random.uniform(*rot_range))
        w, h = im.size
        if w > W or h > H:
            continue
        pos = try_place_nonoverlap(W, H, w, h, placed_boxes)
        if pos is None:
            continue
        x, y = pos
        paste_rgba(canvas, im, (x, y))
        bbox = (x, y, x + w, y + h)
        placed_boxes.append(bbox)
        placed_meta.append({"label": file_label(pth), "source": str(pth), "bbox": bbox})
    return placed_meta

def draw_cell_border(draw: ImageDraw.ImageDraw, box: Tuple[int,int,int,int], width=2, color=(200,200,210,255)):
    x1,y1,x2,y2 = box
    for i in range(width):
        draw.rectangle((x1+i, y1+i, x2-i, y2-i), outline=color)

def choose_grid_icons(src_count: int, total_cells: int,
                      k_min: int, k_max: int) -> List[int]:
    """
    Decide how many distinct icons to use (k), then return a list of indices
    (length = total_cells) allowing repetitions. This enables:
      - k=1  -> all same icon
      - k in [2..4] -> a few icons repeated
    """
    k_max_eff = max(1, min(k_max, src_count, total_cells))
    k_min_eff = max(1, min(k_min, k_max_eff))
    k = random.randint(k_min_eff, k_max_eff)
    distinct = random.sample(range(src_count), k) if k <= src_count else \
               [random.randrange(src_count) for _ in range(k)]
    # fill cells by sampling from the chosen set
    picks = [random.choice(distinct) for _ in range(total_cells)]
    return picks

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

    picks = choose_grid_icons(len(icons), total, distinct_k_range[0], distinct_k_range[1])

    for idx_cell in range(total):
        r = idx_cell // C
        c = idx_cell % C
        idx_icon = picks[idx_cell]
        base = icons[idx_icon]
        pth = src_paths[idx_icon]
        # slightly vary fill per cell
        scale_fill = random.uniform(*scale_fill_range)
        max_w = int((cell_w - 2*cell_pad) * scale_fill)
        max_h = int((cell_h - 2*cell_pad) * scale_fill)
        w0, h0 = base.size
        scale = min(max_w / w0, max_h / h0)
        im = rotate_and_scale(base, scale, random.uniform(*rot_range))
        w, h = im.size
        x1 = c * cell_w + (cell_w - w)//2
        y1 = r * cell_h + (cell_h - h)//2
        paste_rgba(canvas, im, (x1, y1))
        bbox = (x1, y1, x1 + w, y1 + h)
        placed_meta.append({"label": file_label(pth), "source": str(pth), "bbox": bbox})
        if box_borders:
            cell_box = (c*cell_w, r*cell_h, (c+1)*cell_w-1, (r+1)*cell_h-1)
            draw_cell_border(draw, cell_box, width=2)
    return placed_meta  # no overlap by construction

# -------------------------- main generation --------------------------

def parse_templates(arg: List[str]) -> List[Tuple[str,Tuple[int,int]]]:
    """
    Supported:
      row, scatter, grid4, grid:RxC, grid:auto
    """
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

def pick_auto_grid(min_r, max_r, min_c, max_c) -> Tuple[int,int]:
    R = random.randint(min_r, max_r)
    C = random.randint(min_c, max_c)
    return R, C

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

    # scatter options (non-overlap enforced)
    ap.add_argument("--scatter-min", type=int, default=8)
    ap.add_argument("--scatter-max", type=int, default=12)

    # scaling / rotation
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

    ensure_out(args.out)
    meta_path = args.out / "metadata.jsonl"
    icons_paths = list_icons(args.pool, allow_svg=args.allow_svg)
    preloaded: Dict[Path, Image.Image] = {p: load_icon_any(p, allow_svg=args.allow_svg)
                                          for p in icons_paths}

    templates = parse_templates(args.templates)
    W, H = args.canvas

    with meta_path.open("w", encoding="utf-8") as fmeta:
        for i in range(args.n):
            kind, rc = random.choice(templates)
            # choose canvas per template
            if kind == "grid4" and args.grid4_canvas:
                Wt, Ht = args.grid4_canvas
            else:
                Wt, Ht = W, H
            canvas = rand_bg(args.bg, (Wt, Ht))
            icons = list(preloaded.values())
            srcs = list(preloaded.keys())

            placed = []
            if kind == "row":
                placed = layout_row(
                    canvas, icons, srcs,
                    row_min=args.row_min, row_max=args.row_max,
                    scale_range=(args.scale_min, args.scale_max),
                    rot_range=(args.rot_min, args.rot_max),
                    gap_range=(args.row_gap_min, args.row_gap_max)
                )
            elif kind == "scatter":
                placed = layout_scatter(
                    canvas, icons, srcs,
                    k_range=(args.scatter_min, args.scatter_max),
                    scale_range=(args.scale_min, args.scale_max),
                    rot_range=(args.rot_min, args.rot_max)
                )
            elif kind == "grid4":
                placed = layout_grid(
                    canvas, icons, srcs, R=1, C=4, cell_pad=args.cell_pad,
                    scale_fill_range=(0.82, 0.92),
                    rot_range=(args.rot_min, args.rot_max), box_borders=True,
                    distinct_k_range=(args.grid_k_min, args.grid_k_max)
                )
            elif kind == "gridRC":
                R, C = rc
                placed = layout_grid(
                    canvas, icons, srcs, R=R, C=C, cell_pad=args.cell_pad,
                    scale_fill_range=(0.85, 0.95),
                    rot_range=(args.rot_min, args.rot_max), box_borders=True,
                    distinct_k_range=(args.grid_k_min, args.grid_k_max)
                )
            elif kind == "grid:auto":
                R, C = pick_auto_grid(args.grid_min_rows, args.grid_max_rows,
                                      args.grid_min_cols, args.grid_max_cols)
                placed = layout_grid(
                    canvas, icons, srcs, R=R, C=C, cell_pad=args.cell_pad,
                    scale_fill_range=(0.85, 0.95),
                    rot_range=(args.rot_min, args.rot_max), box_borders=True,
                    distinct_k_range=(args.grid_k_min, args.grid_k_max)
                )
            else:
                raise RuntimeError("unknown template dispatch")

            fname = f"comp_{i:06d}.png"
            out_img = args.out / fname
            canvas.convert("RGBA").save(out_img)

            record = {
                "id": Path(fname).stem,
                "image": fname,
                "layout": (kind if kind not in ("gridRC","grid:auto")
                           else (f"grid:auto" if kind=="grid:auto" else f"grid:{rc[0]}x{rc[1]}")),
                "canvas_size": [Wt, Ht],
                "objects": placed,  # each: label/source/bbox[x1,y1,x2,y2]
            }
            fmeta.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Done. Images in: {args.out}\nMetadata: {meta_path}")
    print("Tips: use --bg random and --rot-max 25 for more variety; "
          "tune --grid-k-min/--grid-k-max to control repetitions.")

if __name__ == "__main__":
    main()
