#!/usr/bin/env python3
# random_shapes.py
import argparse, random, math
from pathlib import Path
from PIL import Image, ImageDraw

# --- shapes ---
def draw_square(draw, cx, cy, s, fill, outline=None, rot=0):
    half = s/2
    pts = [(-half,-half),(half,-half),(half,half),(-half,half)]
    draw_polygon(draw, cx, cy, pts, fill, outline, rot)

def draw_rectangle(draw, cx, cy, w, h, fill, outline=None, rot=0):
    pts = [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]
    draw_polygon(draw, cx, cy, pts, fill, outline, rot)

def draw_circle(draw, cx, cy, r, fill, outline=None):
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=fill, outline=outline)

def draw_triangle(draw, cx, cy, s, fill, outline=None, rot=0):
    h = s*math.sqrt(3)/2
    pts = [(0,-2*h/3), (-s/2,h/3), (s/2,h/3)]
    draw_polygon(draw, cx, cy, pts, fill, outline, rot)

def draw_pentagon(draw, cx, cy, r, fill, outline=None, rot=0):
    pts = []
    for k in range(5):
        a = rot + math.radians(90) + 2*math.pi*k/5
        pts.append((r*math.cos(a), r*math.sin(a)))
    draw_polygon(draw, cx, cy, pts, fill, outline)

def draw_polygon(draw, cx, cy, pts_local, fill, outline=None, rot=0):
    if rot:
        cr, sr = math.cos(rot), math.sin(rot)
        pts = [(x*cr - y*sr, x*sr + y*cr) for (x,y) in pts_local]
    else:
        pts = pts_local
    pts = [(cx+x, cy+y) for (x,y) in pts]
    draw.polygon(pts, fill=fill, outline=outline)

# --- palette ---
PALETTE = [
    (240, 92, 48),   # orange
    (102, 170, 255), # sky blue
    (214, 112, 255), # magenta
    (255, 200, 64),  # amber
    (120, 220, 130), # green
    (255, 130, 170), # pink
    (160, 160, 255)  # lavender
]

def make_one_image(W, H, n_rows, n_cols, margin, out_path, rotated_image: bool):
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    cell_w = (W - 2*margin) / n_cols
    cell_h = (H - 2*margin) / n_rows
    size_min = int(0.45 * min(cell_w, cell_h))
    size_max = int(0.75 * min(cell_w, cell_h))

    shapes = ["square","rect","circle","triangle","pentagon"]
    main_shape = random.choice(shapes)
    main_color = random.choice(PALETTE)

    # choose a few empty cells to mimic gaps
    num_gaps = random.randint(2, max(2, (n_rows*n_cols)//6))
    gaps = set(random.sample(range(n_rows*n_cols), num_gaps))

    for r in range(n_rows):
        for c in range(n_cols):
            idx = r*n_cols + c
            if idx in gaps:
                continue

            cx = int(margin + c*cell_w + cell_w/2 + random.uniform(-0.08, 0.08)*cell_w)
            cy = int(margin + r*cell_h + cell_h/2 + random.uniform(-0.08, 0.08)*cell_h)
            s = random.randint(size_min, size_max)

            # mostly same shape/color with occasional variation
            if random.random() < 0.2:
                shape = random.choice(shapes)
                color = random.choice(PALETTE)
            else:
                shape = main_shape
                color = main_color

            # rotation is allowed only if this image was selected for rotation
            if rotated_image and shape in ("triangle","pentagon","rect","square"):
                rot = random.uniform(0, math.tau)
            else:
                rot = 0

            if shape == "square":
                draw_square(draw, cx, cy, s, color, None, rot)
            elif shape == "rect":
                w = int(s * 1.2)
                h = int(s * 0.8)
                draw_rectangle(draw, cx, cy, w, h, color, None, rot)
            elif shape == "circle":
                draw_circle(draw, cx, cy, s//2, color)
            elif shape == "triangle":
                draw_triangle(draw, cx, cy, s, color, None, rot)
            else: # pentagon
                draw_pentagon(draw, cx, cy, s//2, color, None, rot)

    img.save(out_path)

def main():
    p = argparse.ArgumentParser(description="Generate simple random grids of geometric figures.")
    p.add_argument("--out_dir", type=Path, default=Path("out_shapes"), help="output folder")
    p.add_argument("--num_images", type=int, default=10, help="how many images to create")
    p.add_argument("--size", type=str, default="800x500", help="canvas WxH, e.g., 800x500")
    p.add_argument("--grid", type=str, default="2x5", help="rows x cols, e.g., 2x5")
    p.add_argument("--margin", type=int, default=40, help="outer margin in pixels")
    p.add_argument("--rotated_image_prob", type=float, default=0.5,
                   help="probability that an image will allow rotated shapes (0..1)")
    args = p.parse_args()

    W, H = map(int, args.size.lower().split("x"))
    n_rows, n_cols = map(int, args.grid.lower().split("x"))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.num_images + 1):
        allow_rot = random.random() < args.rotated_image_prob
        out_path = args.out_dir / f"shapes_{i:04d}.png"
        make_one_image(W, H, n_rows, n_cols, args.margin, out_path, rotated_image=allow_rot)

if __name__ == "__main__":
    main()
