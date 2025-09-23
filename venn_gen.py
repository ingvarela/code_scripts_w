from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import argparse, random, math
from typing import Tuple, List

# --------------------- layout ---------------------
W, H = 900, 520
R = 185                        # venn circle radius
CX_L, CY = 340, 260            # left circle center
CX_R, CY_R = 560, 260          # right circle center (same Y)
OUTLINE = (60, 200, 240)
EDGE_PAD = 6                   # stay this many px away from circle borders

PALETTE = {
    "green":  (46, 184, 99),
    "blue":   (100, 180, 255),
    "orange": (255, 138,  64),
    "purple": (142, 122, 255),
    "red":    (235,  80, 80),
}
SHAPES = ["circle", "square", "triangle", "rectangle"]

# --------------- text utilities -------------------
def text_box(draw: ImageDraw.ImageDraw, xy: Tuple[int,int], text: str, pad=8,
             bg=(230, 250, 255), fg=(0, 140, 170), radius=8, font=None):
    x, y = xy
    l, t, r, b = draw.textbbox((x, y), text, font=font)
    w, h = r - l, b - t
    box = [x - pad, y - pad, x + w + pad, y + h + pad]
    try:
        draw.rounded_rectangle(box, radius=radius, fill=bg, outline=OUTLINE, width=2)
    except Exception:
        draw.rectangle(box, fill=bg, outline=OUTLINE, width=2)
    draw.text((x, y), text, fill=fg, font=font)
    return box

# --------------- shape drawing --------------------
def draw_circle(draw, center, size, fill):
    cx, cy = center; r = size // 2
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=fill)

def draw_square(draw, center, size, fill):
    cx, cy = center; s = size
    draw.rectangle([cx-s//2, cy-s//2, cx+s//2, cy+s//2], fill=fill)

def draw_rectangle(draw, center, size, fill):
    cx, cy = center; w = size; h = int(size*0.65)
    draw.rectangle([cx-w//2, cy-h//2, cx+w//2, cy+h//2], fill=fill)

def draw_triangle(draw, center, size, fill):
    cx, cy = center
    h = size * math.sqrt(3) / 2
    p1 = (cx, cy - h/2)
    p2 = (cx - size/2, cy + h/2)
    p3 = (cx + size/2, cy + h/2)
    draw.polygon([p1, p2, p3], fill=fill)

DRAWERS = {
    "circle":    draw_circle,
    "square":    draw_square,
    "rectangle": draw_rectangle,
    "triangle":  draw_triangle,
}

# ------------- geometry / constraints --------------
def circumradius(shape: str, size: int) -> float:
    if shape == "circle":
        return size / 2
    if shape == "square":
        return (size * math.sqrt(2)) / 2
    if shape == "rectangle":
        w = size; h = int(size * 0.65)
        return math.hypot(w/2, h/2)
    if shape == "triangle":
        return size / math.sqrt(3)   # equilateral
    raise ValueError("unknown shape")

def inside_canvas(cx, cy, rad: float, top_clear=40, margin=6):
    return (rad+margin <= cx <= W - rad - margin) and (rad+margin + top_clear <= cy <= H - rad - margin)

def fits_left_only(cx, cy, rad):
    dL = math.hypot(cx - CX_L, cy - CY)
    dR = math.hypot(cx - CX_R, cy - CY_R)
    return (dL <= R - rad - EDGE_PAD) and (dR >= R + rad + EDGE_PAD)

def fits_right_only(cx, cy, rad):
    dL = math.hypot(cx - CX_L, cy - CY)
    dR = math.hypot(cx - CX_R, cy - CY_R)
    return (dR <= R - rad - EDGE_PAD) and (dL >= R + rad + EDGE_PAD)

def fits_intersection(cx, cy, rad):
    dL = math.hypot(cx - CX_L, cy - CY)
    dR = math.hypot(cx - CX_R, cy - CY_R)
    return (dL <= R - rad - EDGE_PAD) and (dR <= R - rad - EDGE_PAD)

def non_overlap(cx, cy, rad, placed: List[Tuple[int,int,float]], gap=6):
    return all(math.hypot(cx-px, cy-py) >= (rad + prad + gap) for px, py, prad in placed)

def sample_center(fit_fn, rad, placed, max_tries=4000):
    tries = 0
    while tries < max_tries:
        tries += 1
        cx = random.randint(int(rad)+6, int(W - rad - 6))
        cy = random.randint(int(rad)+6 + 40, int(H - rad - 6))
        if inside_canvas(cx, cy, rad) and fit_fn(cx, cy, rad) and non_overlap(cx, cy, rad, placed):
            return (cx, cy)
    raise RuntimeError("Could not place a shape without overlap or border violation; consider reducing counts or sizes.")

# ---------------- single image ----------------------
def generate_one(out_path: Path, n_inter: int, n_left: int, n_right: int, rng_seed: int|None):
    if rng_seed is not None:
        random.seed(rng_seed)

    shape_label = random.choice(SHAPES)
    color_label_name, color_label_rgb = random.choice(list(PALETTE.items()))
    distractor_colors = [c for n, c in PALETTE.items() if n != color_label_name]

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse([CX_L-R, CY-R, CX_L+R, CY+R], outline=OUTLINE, width=4)
    draw.ellipse([CX_R-R, CY_R-R, CX_R+R, CY_R+R], outline=OUTLINE, width=4)

    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    text_box(draw, (CX_L - 36, CY - R - 40), f"{color_label_name}", font=font)
    text_box(draw, (CX_R - 36, CY_R - R - 40), f"{shape_label}", font=font)

    placed: List[Tuple[int,int,float]] = []

    # Intersection (match both)
    for _ in range(n_inter):
        size = random.randint(46, 64)
        rad = circumradius(shape_label, size)
        pt = sample_center(fits_intersection, rad, placed)
        DRAWERS[shape_label](draw, pt, size, color_label_rgb)
        placed.append((*pt, rad))

    # Left-only (match color only)
    for _ in range(n_left):
        shape = random.choice([s for s in SHAPES if s != shape_label])
        size = random.randint(46, 64)
        rad = circumradius(shape, size)
        pt = sample_center(fits_left_only, rad, placed)
        DRAWERS[shape](draw, pt, size, color_label_rgb)
        placed.append((*pt, rad))

    # Right-only (match shape only)
    for _ in range(n_right):
        size = random.randint(46, 64)
        rad = circumradius(shape_label, size)
        pt = sample_center(fits_right_only, rad, placed)
        color = random.choice(distractor_colors)
        DRAWERS[shape_label](draw, pt, size, color)
        placed.append((*pt, rad))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)

# ---------------------- CLI --------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Generate many Venn-diagram images with non-overlapping shapes strictly inside their regions."
    )
    p.add_argument("--outdir", type=Path, default=Path("./venn_outputs"),
                   help="Directory to save images (default: ./venn_outputs)")
    p.add_argument("--prefix", type=str, default="venn_",
                   help="Filename prefix (default: venn_)")
    p.add_argument("--count", type=int, default=10,
                   help="Number of images to generate (default: 10)")
    p.add_argument("--start-index", type=int, default=1,
                   help="Starting index for filenames (default: 1)")
    p.add_argument("--seed", type=int, default=None,
                   help="Base random seed. If set, image i uses seed = base + i.")
    p.add_argument("--n-intersection", type=int, default=2,
                   help="Items in the intersection")
    p.add_argument("--n-left-only", type=int, default=2,
                   help="Items in the left-only region")
    p.add_argument("--n-right-only", type=int, default=3,
                   help="Items in the right-only region")
    return p.parse_args()

def main():
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    # zero-pad width based on final index
    end_index = args.start_index + args.count - 1
    pad = max(3, len(str(end_index)))

    for i in range(args.count):
        idx = args.start_index + i
        seed_i = (args.seed + i) if args.seed is not None else None
        out_path = args.outdir / f"{args.prefix}{idx:0{pad}d}.png"
        generate_one(
            out_path=out_path,
            n_inter=args.__dict__["n_intersection"],
            n_left=args.__dict__["n_left_only"],
            n_right=args.__dict__["n_right_only"],
            rng_seed=seed_i
        )
        print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
