#!/usr/bin/env python3
# generate_shapes.py
import argparse
import json
import math
import random
from pathlib import Path
from typing import List, Tuple, Dict, Optional

from PIL import Image, ImageDraw

# ----------------------------- Utils -----------------------------

def ensure_out_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def rand_color_bright_not_white(rng: random.Random) -> Tuple[int, int, int]:
    """
    Generate a bright, saturated RGB color that contrasts with white background.
    Uses HSV sampling with high saturation, high-ish value.
    """
    # Sample hue freely, keep saturation/value high
    h = rng.random()
    s = rng.uniform(0.75, 1.0)
    v = rng.uniform(0.75, 1.0)
    return hsv_to_rgb(h, s, v)

def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    i = int(h * 6)
    f = (h * 6) - i
    p = int(255 * v * (1 - s))
    q = int(255 * v * (1 - f * s))
    t = int(255 * v * (1 - (1 - f) * s))
    v_ = int(255 * v)
    i = i % 6
    if i == 0: r, g, b = v_, t, p
    elif i == 1: r, g, b = q, v_, p
    elif i == 2: r, g, b = p, v_, t
    elif i == 3: r, g, b = p, q, v_
    elif i == 4: r, g, b = t, p, v_
    else:        r, g, b = v_, p, q
    return (r, g, b)

def clamp(x, a, b): return max(a, min(b, x))

def regular_polygon_points(cx: float, cy: float, r: float, sides: int, angle_rad: float) -> List[Tuple[int, int]]:
    pts = []
    for k in range(sides):
        theta = angle_rad + 2 * math.pi * k / sides
        x = cx + r * math.cos(theta)
        y = cy + r * math.sin(theta)
        pts.append((int(round(x)), int(round(y))))
    return pts

# ----------------------------- Drawing -----------------------------

def draw_shape(
    draw: ImageDraw.ImageDraw,
    shape: str,
    canvas_w: int,
    canvas_h: int,
    rng: random.Random,
    size_frac_range: Tuple[float, float],
    fill_mode: str,
    color: Tuple[int,int,int],
    stroke_px: int
) -> Dict:
    """
    Draw a single shape fully within the canvas. Returns metadata dict.
    Coordinates are in the *current* image scale.
    """
    min_dim = min(canvas_w, canvas_h)
    size_min = int(size_frac_range[0] * min_dim)
    size_max = int(size_frac_range[1] * min_dim)
    if size_max < size_min: size_max = size_min
    # Choose filled vs outline if "both"
    fm = fill_mode
    if fill_mode == "both":
        fm = rng.choice(["filled", "outline"])

    # Pick a general radius/side size
    size_px = rng.randint(max(4, size_min), max(4, size_max))
    meta: Dict = {"shape": shape, "mode": fm}

    if shape == "circle":
        r = size_px // 2
        cx = rng.randint(r, canvas_w - r)
        cy = rng.randint(r, canvas_h - r)
        bbox = [cx - r, cy - r, cx + r, cy + r]
        if fm == "filled":
            draw.ellipse(bbox, fill=color)
        else:
            draw.ellipse(bbox, outline=color, width=stroke_px)
        meta.update({"center": [cx, cy], "radius": r, "bbox": bbox})

    elif shape == "square":
        side = size_px
        x0 = rng.randint(0, canvas_w - side)
        y0 = rng.randint(0, canvas_h - side)
        x1, y1 = x0 + side, y0 + side
        if fm == "filled":
            draw.rectangle([x0, y0, x1, y1], fill=color)
        else:
            draw.rectangle([x0, y0, x1, y1], outline=color, width=stroke_px)
        meta.update({"bbox": [x0, y0, x1, y1], "side": side})

    elif shape == "rectangle":
        # random aspect ratio between 1.2 and 2.5, orientation varies
        ar = rng.uniform(1.2, 2.5)
        if rng.random() < 0.5:
            w = size_px
            h = max(4, int(round(size_px / ar)))
        else:
            h = size_px
            w = max(4, int(round(size_px / ar)))
        x0 = rng.randint(0, canvas_w - w)
        y0 = rng.randint(0, canvas_h - h)
        x1, y1 = x0 + w, y0 + h
        if fm == "filled":
            draw.rectangle([x0, y0, x1, y1], fill=color)
        else:
            draw.rectangle([x0, y0, x1, y1], outline=color, width=stroke_px)
        meta.update({"bbox": [x0, y0, x1, y1], "w": w, "h": h})

    elif shape == "triangle":
        # Equilateral, rotate randomly
        r = size_px / 2.0
        cx = rng.randint(int(r), int(canvas_w - r))
        cy = rng.randint(int(r), int(canvas_h - r))
        angle = rng.uniform(0, 2 * math.pi)
        pts = regular_polygon_points(cx, cy, r, 3, angle)
        if fm == "filled":
            draw.polygon(pts, fill=color)
        else:
            draw.polygon(pts, outline=color)
            if stroke_px > 1:
                # Emulate width by drawing multiple offset outlines for PIL polygon
                for off in range(1, stroke_px):
                    draw.polygon(pts, outline=color)
        xs, ys = zip(*pts)
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        meta.update({"points": pts, "bbox": bbox})

    elif shape in ("pentagon", "hexagon", "heptagon", "octagon"):
        sides_map = {
            "pentagon": 5, "hexagon": 6, "heptagon": 7, "octagon": 8
        }
        sides = sides_map[shape]
        r = size_px / 2.0
        cx = rng.randint(int(r), int(canvas_w - r))
        cy = rng.randint(int(r), int(canvas_h - r))
        angle = rng.uniform(0, 2 * math.pi)
        pts = regular_polygon_points(cx, cy, r, sides, angle)
        if fm == "filled":
            draw.polygon(pts, fill=color)
        else:
            draw.polygon(pts, outline=color)
            if stroke_px > 1:
                for _ in range(stroke_px - 1):
                    draw.polygon(pts, outline=color)
        xs, ys = zip(*pts)
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        meta.update({"points": pts, "bbox": bbox, "sides": sides})

    else:
        raise ValueError(f"Unsupported shape: {shape}")

    meta.update({"color": color, "stroke_px": stroke_px})
    return meta

# ----------------------------- Main -----------------------------

SUPPORTED = [
    "circle", "square", "rectangle", "triangle",
    "pentagon", "hexagon", "heptagon", "octagon"
]

def main():
    ap = argparse.ArgumentParser(
        description="Generate single geometric figures (different colors) on a white canvas."
    )
    ap.add_argument("--out_dir", type=str, default="shapes_out", help="Output directory for images + metadata.")
    ap.add_argument("--n", type=int, default=50, help="Number of images to generate.")
    ap.add_argument("--canvas", type=int, nargs=2, default=[256, 256], metavar=("W","H"), help="Canvas size WxH.")
    ap.add_argument("--shapes", type=str, nargs="+",
                    default=["circle", "square", "triangle", "rectangle", "pentagon", "hexagon"],
                    help=f"Shapes to sample from. Supported: {', '.join(SUPPORTED)}")
    ap.add_argument("--size_range", type=float, nargs=2, default=[0.25, 0.7],
                    metavar=("MIN_FRAC","MAX_FRAC"),
                    help="Min/Max size as fraction of min(canvas_w, canvas_h).")
    ap.add_argument("--fill_mode", type=str, choices=["filled", "outline", "both"], default="filled",
                    help="Draw filled, outline, or randomly choose per image.")
    ap.add_argument("--stroke_frac", type=float, default=0.02,
                    help="Outline width as fraction of min(canvas dim) (used when outline).")
    ap.add_argument("--antialias", action="store_true", help="Render 4x and downsample with LANCZOS.")
    ap.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    ensure_out_dir(out_dir)

    # Validate shapes
    shapes = []
    for s in args.shapes:
        s = s.lower().strip()
        if s not in SUPPORTED:
            raise SystemExit(f"Unsupported shape '{s}'. Supported: {', '.join(SUPPORTED)}")
        shapes.append(s)

    if args.seed is not None:
        rng = random.Random(args.seed)
    else:
        rng = random.Random()

    base_w, base_h = args.canvas
    scale = 4 if args.antialias else 1
    W, H = base_w * scale, base_h * scale

    # Prepare metadata files
    meta_csv = (out_dir / "metadata.csv").open("w", encoding="utf-8")
    meta_csv.write("filename,shape,mode,color_r,color_g,color_b,stroke_px,bbox_or_points,json_path,canvas_w,canvas_h\n")
    meta_jsonl = (out_dir / "metadata.jsonl").open("w", encoding="utf-8")

    for i in range(args.n):
        img = Image.new("RGB", (W, H), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        shape = rng.choice(shapes)
        color = rand_color_bright_not_white(rng)

        stroke_px = max(1, int(round(args.stroke_frac * min(W, H))))
        # Draw and collect metadata at high-res scale
        meta = draw_shape(
            draw=draw,
            shape=shape,
            canvas_w=W,
            canvas_h=H,
            rng=rng,
            size_frac_range=args.size_range,
            fill_mode=args.fill_mode,
            color=color,
            stroke_px=stroke_px
        )

        # Downsample to base canvas if antialiasing
        if args.antialias:
            img = img.resize((base_w, base_h), resample=Image.LANCZOS)
            # Scale metadata coordinates back down
            def down(v): return int(round(v / scale))
            if "bbox" in meta:
                x0,y0,x1,y1 = meta["bbox"]
                meta["bbox"] = [down(x0), down(y0), down(x1), down(y1)]
            if "points" in meta:
                meta["points"] = [(down(x), down(y)) for (x,y) in meta["points"]]
            if "center" in meta:
                cx, cy = meta["center"]
                meta["center"] = [down(cx), down(cy)]
            if "radius" in meta:
                meta["radius"] = int(round(meta["radius"] / scale))
            meta["stroke_px"] = max(1, int(round(meta["stroke_px"] / scale)))

        fname = f"{i:06d}_{shape}.png"
        fpath = out_dir / fname
        img.save(fpath, format="PNG", optimize=True)

        # Save per-image JSON too (optional but handy)
        per_json = {
            "filename": fname,
            "canvas_w": base_w,
            "canvas_h": base_h,
            **meta
        }
        per_json_path = out_dir / f"{i:06d}_{shape}.json"
        with per_json_path.open("w", encoding="utf-8") as jf:
            json.dump(per_json, jf, ensure_ascii=False, indent=2)

        # Write row in CSV (bbox or points as simple string)
        bp = meta.get("bbox", meta.get("points"))
        bp_str = json.dumps(bp, ensure_ascii=False)
        meta_csv.write(
            f"{fname},{shape},{meta['mode']},{color[0]},{color[1]},{color[2]},{meta['stroke_px']},"
            f"\"{bp_str}\",{per_json_path.name},{base_w},{base_h}\n"
        )

        # Write JSONL
        meta_jsonl.write(json.dumps(per_json, ensure_ascii=False) + "\n")

    meta_csv.close()
    meta_jsonl.close()
    print(f"Done. Images + metadata saved to: {out_dir.resolve()}")

if __name__ == "__main__":
    main()
