#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compose icon-based images for ICONQA-like data.
Inputs: a pool dir of PNG icons (transparent preferred).
Outputs: composed PNGs + JSONL with per-object bboxes and provenance.

Layouts:
  - row
  - scatter
  - grid4
  - grid:RxC   (e.g., grid:3x3)

Usage examples:
  python icon_composer.py --pool ./icons --out ./out --n 100 --templates row scatter grid4
  python icon_composer.py --pool ./icons --out ./out --n 50 --templates grid:2x2 --canvas 640 320
  python icon_composer.py --pool ./icons --out ./out --n 40 --templates row --row-min 8 --row-max 12

Notes:
  * PNG recommended. SVGs are ignored unless --allow-svg and cairosvg is installed.
  * Labels default to the file stem (before extension).
"""

import argparse, json, random, math, re
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from PIL import Image, ImageDraw, ImageOps, ImageColor

# -------------------------- IO utils --------------------------

def list_icons(pool: Path, allow_svg=False) -> List[Path]:
    exts = {".png"}
    if allow_svg:
        exts.add(".svg")
    files = [p for p in pool.rglob("*") if p.suffix.lower() in exts]
    if not files:
        raise SystemExit(f"No icons found in {pool} (expected PNG{'+SVG' if allow_svg else ''}).")
    return files

def load_png(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    return im

def load_icon_any(path: Path, allow_svg=False) -> Image.Image:
    if path.suffix.lower() == ".png":
        return load_png(path)
    if path.suffix.lower() == ".svg" and allow_svg:
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

def try_place_nonoverlap(w: int, h: int, box_w: int, box_h: int, placed: List[Tuple[int,int,int,int]],
                         max_tries=200, margin=2) -> Optional[Tuple[int,int]]:
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
        # soft random pastel
        h = random.randint(180, 255)
        s = random.randint(180, 255)
        l = random.randint(220, 255)
        r, g, b = random.randint(220,255), random.randint(220,255), random.randint(220,255)
        return Image.new("RGBA", size, (r, g, b, 255))
    return Image.new("RGBA", size, (255, 255, 255, 255))

def rotate_and_scale(icon: Image.Image, scale: float, rot_deg: float, keep_aspect=True) -> Image.Image:
    w, h = icon.size
    if keep_aspect:
        nw, nh = int(w * scale), int(h * scale)
    else:
        sx, sy = scale, scale
        nw, nh = int(w * sx), int(h * sy)
    tmp = icon.resize((max(1,nw), max(1,nh)), Image.LANCZOS)
    if rot_deg != 0:
        tmp = tmp.rotate(rot_deg, expand=True, resample=Image.BICUBIC)
    return tmp

def file_label(path: Path) -> str:
    return path.stem

# -------------------------- layouts --------------------------

def layout_row(canvas: Image.Image, icons: List[Image.Image], src_paths: List[Path],
               row_min: int, row_max: int, scale_range: Tuple[float,float], rot_range: Tuple[float,float],
               left_margin=16, right_margin=16, v_center=True) -> List[Dict]:
    W, H = canvas.size
    n = random.randint(row_min, row_max)
    # choose from provided icons (sample with replacement)
    placed_meta = []
    x = left_margin
    mid_y = H // 2
    for i in range(n):
        idx = random.randrange(len(icons))
        base = icons[idx]
        pth = src_paths[idx]
        scale = random.uniform(*scale_range)
        rot = random.uniform(*rot_range)
        im = rotate_and_scale(base, scale, rot)
        w, h = im.size
        if x + w + right_margin > W:
            break
        y = mid_y - (h // 2) if v_center else random.randint(0, max(0, H - h))
        paste_rgba(canvas, im, (x, y))
        bbox = (x, y, x + w, y + h)
        placed_meta.append({"label": file_label(pth), "source": str(pth), "bbox": bbox})
        x += w + random.randint(6, 18)
    return placed_meta

def layout_scatter(canvas: Image.Image, icons: List[Image.Image], src_paths: List[Path],
                   k_range: Tuple[int,int], scale_range: Tuple[float,float], rot_range: Tuple[float,float],
                   no_overlap=True) -> List[Dict]:
    W, H = canvas.size
    k = random.randint(*k_range)
    placed_boxes: List[Tuple[int,int,int,int]] = []
    placed_meta: List[Dict] = []
    tries = 0
    max_attempts = k * 50
    while len(placed_meta) < k and tries < max_attempts:
        tries += 1
        idx = random.randrange(len(icons))
        base = icons[idx]
        pth = src_paths[idx]
        scale = random.uniform(*scale_range)
        rot = random.uniform(*rot_range)
        im = rotate_and_scale(base, scale, rot)
        w, h = im.size
        if w > W or h > H:
            continue
        if no_overlap:
            pos = try_place_nonoverlap(W, H, w, h, placed_boxes)
            if pos is None:
                continue
            x, y = pos
        else:
            x, y = random.randint(0, W - w), random.randint(0, H - h)
        paste_rgba(canvas, im, (x, y))
        bbox = (x, y, x + w, y + h)
        placed_boxes.append(bbox)
        placed_meta.append({"label": file_label(pth), "source": str(pth), "bbox": bbox})
    return placed_meta

def draw_cell_border(draw: ImageDraw.ImageDraw, box: Tuple[int,int,int,int], width=2, color=(200,200,210,255)):
    x1,y1,x2,y2 = box
    for i in range(width):
        draw.rectangle((x1+i, y1+i, x2-i, y2-i), outline=color)

def layout_grid(canvas: Image.Image, icons: List[Image.Image], src_paths: List[Path],
                R: int, C: int, cell_pad: int, scale_fill=0.8, rot_range: Tuple[float,float]=(0,0),
                box_borders=True) -> List[Dict]:
    W, H = canvas.size
    cell_w = W // C
    cell_h = H // R
    draw = ImageDraw.Draw(canvas)
    placed_meta: List[Dict] = []
    total = R * C
    # sample with replacement if needed
    picks = [random.randrange(len(icons)) for _ in range(total)]
    for r in range(R):
        for c in range(C):
            idx = picks[r*C + c]
            base = icons[idx]
            pth = src_paths[idx]
            # scale to fit cell
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
    return placed_meta

# -------------------------- main generation --------------------------

def parse_templates(arg: List[str]) -> List[Tuple[str,Tuple[int,int]]]:
    """
    Returns list of (kind, (R,C)) for grid kinds; (None) for others.
    """
    out = []
    for t in arg:
        if t == "row" or t == "scatter" or t == "grid4":
            out.append((t, (0,0)))
        else:
            m = re.match(r"grid:(\d+)x(\d+)$", t)
            if m:
                R, C = int(m.group(1)), int(m.group(2))
                out.append(("gridRC", (R, C)))
            else:
                raise SystemExit(f"Unknown template: {t}")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, type=Path, help="Folder with PNG (and optional SVG) icons.")
    ap.add_argument("--out", required=True, type=Path, help="Output folder for images and metadata.jsonl")
    ap.add_argument("--n", type=int, default=50, help="Number of images to generate.")
    ap.add_argument("--templates", nargs="+", default=["row","scatter","grid4"],
                    help="Which templates to sample from: row scatter grid4 grid:RxC")
    ap.add_argument("--canvas", nargs=2, type=int, default=[768, 256], help="Canvas size WxH.")
    ap.add_argument("--bg", type=str, default="white", help="Background: white | random | #RRGGBB | css name.")
    ap.add_argument("--seed", type=int, default=None, help="Random seed.")
    ap.add_argument("--allow-svg", action="store_true", help="Allow SVG pool (requires cairosvg).")

    # row options
    ap.add_argument("--row-min", type=int, default=8)
    ap.add_argument("--row-max", type=int, default=14)

    # scatter options
    ap.add_argument("--scatter-min", type=int, default=8)
    ap.add_argument("--scatter-max", type=int, default=12)
    ap.add_argument("--no-overlap", action="store_true", help="Avoid overlaps in scatter.")

    # scaling / rotation
    ap.add_argument("--scale-min", type=float, default=0.6)
    ap.add_argument("--scale-max", type=float, default=1.2)
    ap.add_argument("--rot-min", type=float, default=0.0)
    ap.add_argument("--rot-max", type=float, default=0.0, help="Allow rotations (e.g., 0 25).")

    # grid options
    ap.add_argument("--grid4-canvas", nargs=2, type=int, default=None,
                    help="Override canvas WxH for grid4 (e.g., 768 192).")
    ap.add_argument("--cell-pad", type=int, default=10)

    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    ensure_out(args.out)
    meta_path = args.out / "metadata.jsonl"
    icons_paths = list_icons(args.pool, allow_svg=args.allow_svg)
    # Preload PNGs only once (converted to RGBA)
    preloaded: Dict[Path, Image.Image] = {}
    for p in icons_paths:
        preloaded[p] = load_icon_any(p, allow_svg=args.allow_svg)

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
                )
            elif kind == "scatter":
                placed = layout_scatter(
                    canvas, icons, srcs,
                    k_range=(args.scatter_min, args.scatter_max),
                    scale_range=(args.scale_min, args.scale_max),
                    rot_range=(args.rot_min, args.rot_max),
                    no_overlap=args.no_overlap
                )
            elif kind == "grid4":
                placed = layout_grid(
                    canvas, icons, srcs, R=1, C=4, cell_pad=args.cell_pad, scale_fill=0.85,
                    rot_range=(args.rot_min, args.rot_max), box_borders=True
                )
            elif kind == "gridRC":
                R, C = rc
                placed = layout_grid(
                    canvas, icons, srcs, R=R, C=C, cell_pad=args.cell_pad, scale_fill=0.9,
                    rot_range=(args.rot_min, args.rot_max), box_borders=True
                )
            else:
                raise RuntimeError("unknown template dispatch")

            fname = f"comp_{i:06d}.png"
            out_img = args.out / fname
            canvas.convert("RGBA").save(out_img)

            record = {
                "id": Path(fname).stem,
                "image": fname,
                "layout": kind if kind != "gridRC" else f"grid:{rc[0]}x{rc[1]}",
                "canvas_size": [Wt, Ht],
                "objects": placed,  # each: label/source/bbox[x1,y1,x2,y2]
            }
            fmeta.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Done. Images in: {args.out}\nMetadata: {meta_path}")
    print("Tip: set --bg random and --rot-max 25 for more variation.")

if __name__ == "__main__":
    main()
