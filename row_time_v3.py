import argparse
from pathlib import Path
import random
from typing import List
from PIL import Image, ImageColor, ImageDraw, ImageFont

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

def make_canvas_rgba(w: int, h: int, bg: str) -> Image.Image:
    if bg == "transparent":
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rgb = ImageColor.getrgb(bg)
    return Image.new("RGBA", (w, h), (*rgb, 255))

def save_with_format(img: Image.Image, out_path: Path, fmt: str, bg_for_jpeg: str):
    """
    Save with explicit format. If JPEG, flatten to RGB (no alpha).
    """
    fmt = fmt.lower()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt in ("jpg", "jpeg"):
        if bg_for_jpeg == "transparent":
            bg_for_jpeg = "white"  # JPEG can't be transparent
        rgb = ImageColor.getrgb(bg_for_jpeg)
        bg = Image.new("RGB", img.size, rgb)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1])  # alpha as mask
        bg.save(out_path, format="JPEG", quality=95, subsampling=0, optimize=True)
    else:
        img.save(out_path, format="PNG", optimize=True)

def resolve_output_paths(out_arg: Path, fmt: str, count: int) -> List[Path]:
    """
    Build a list of output paths:
      - If out_arg is a directory, use strip_0001.ext, strip_0002.ext, ...
      - If out_arg is a file and count==1, use it as-is (ensuring correct suffix).
      - If out_arg is a file and count>1, append _0001, _0002, ... to the stem.
    """
    fmt_ext = ".png" if fmt == "png" else ".jpg"
    paths = []

    if out_arg.is_dir() or out_arg.suffix == "":
        base = out_arg if out_arg.is_dir() else out_arg
        base.mkdir(parents=True, exist_ok=True)
        for i in range(1, count + 1):
            paths.append(base / f"strip_{i:04d}{fmt_ext}")
        return paths

    # out_arg is a file path with potential suffix
    if out_arg.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        out_arg = out_arg.with_suffix(fmt_ext)

    if count <= 1:
        return [out_arg]

    stem = out_arg.stem
    parent = out_arg.parent
    for i in range(1, count + 1):
        paths.append(parent / f"{stem}_{i:04d}{fmt_ext}")
    return paths

def choose_label_color() -> tuple:
    """
    Pick a readable random color (avoid very pale/near-white).
    Returns an (R,G,B) tuple.
    """
    for _ in range(10):
        r, g, b = random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
        if (r + g + b) < 680:  # keep it from being too close to white
            return (r, g, b)
    return (30, 144, 255)  # fallback: dodger blue

def get_font(px: int) -> ImageFont.ImageFont:
    """Try a truetype font; fallback to default."""
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", px)
    except Exception:
        try:
            return ImageFont.truetype("arial.ttf", px)
        except Exception:
            return ImageFont.load_default()

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=Path, default=Path("C://Users//svs26//Desktop//MS COCO 2017//iconqa//sample"),
                    help="Folder with PNG/JPG/JPEG images. (default: ./imgs)")
    ap.add_argument("--out", type=Path, default=Path("C://Users//svs26//Desktop//MS COCO 2017//iconqa//out"),
                    help="Output file OR directory. (default: ./out/)")
    ap.add_argument("--format", type=str, default="png", choices=["png", "jpg", "jpeg"],
                    help="Output format (default: png).")
    ap.add_argument("--count", type=int, default=50, help="How many strips to generate (default: 1).")
    ap.add_argument("--k", type=int, default=None, help="Number of images in the row (3–5).")
    ap.add_argument("--cell", nargs=2, type=int, default=[192, 192], help="Cell width height (default 192 192).")
    ap.add_argument("--gap", type=int, default=16, help="Gap between cells (px).")
    ap.add_argument("--margin", type=int, default=16, help="Left/right/top/bottom margin (px).")
    ap.add_argument("--bg", type=str, default="white",
                    help='Background: "white", "#RRGGBB", "transparent" (PNG only).')
    ap.add_argument("--seed", type=int, default=None, help="Random seed (optional).")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    fmt = "png" if args.format.lower() == "png" else "jpg"  # normalize jpg/jpeg
    # create default dirs if needed
    args.pool.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True) if args.out.suffix == "" else None

    paths_pool = list_images(args.pool)
    out_paths = resolve_output_paths(args.out, fmt, args.count)

    cell_w, cell_h = args.cell
    gap = args.gap
    margin = args.margin

    # label band above each cell (outside image). Smaller font by default.
    font = get_font(max(10, int(cell_h * 0.26)))  # ~26% of cell height
    # extra vertical space to reserve for labels (band height = font size + padding)
    label_pad = max(4, font.size // 6)
    label_band = font.size + 2 * label_pad

    for idx, out_path in enumerate(out_paths, start=1):
        # choose K
        if args.k is None:
            K = random.randint(3, 5)
        else:
            K = min(5, max(3, args.k))

        # sample paths (without replacement if enough, else with replacement)
        picks = random.sample(paths_pool, K) if len(paths_pool) >= K else [random.choice(paths_pool) for _ in range(K)]

        # compute canvas size (single row) — add label band ABOVE cells
        canvas_w = margin + K * cell_w + (K - 1) * gap + margin
        canvas_h = margin + label_band + cell_h + margin
        canvas = make_canvas_rgba(canvas_w, canvas_h, args.bg)
        draw = ImageDraw.Draw(canvas)

        # origin for images starts after the label band
        x = margin
        y_img_top = margin + label_band

        for i, p in enumerate(picks, start=1):
            im = load_rgba(p)
            thumb = fit_within(im, cell_w, cell_h)
            tw, th = thumb.size

            # cell box top-left for this slot
            cell_x = x
            cell_y = y_img_top

            # center image inside its cell
            ox = cell_x + (cell_w - tw) // 2
            oy = cell_y + (cell_h - th) // 2
            canvas.alpha_composite(thumb, dest=(ox, oy))

            # draw label centered ABOVE the cell (outside the image area)
            label = str(i)
            color = choose_label_color()
            # text size measurement
            try:
                bbox = draw.textbbox((0,0), label, font=font, stroke_width=2)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except Exception:
                text_w, text_h = draw.textlength(label, font=font), font.size

            tx = cell_x + (cell_w - text_w) // 2
            ty = margin + (label_band - text_h) // 2  # vertical center within band
            draw.text((tx, ty), label, font=font, fill=color,
                      stroke_width=2, stroke_fill=(0, 0, 0))

            x += cell_w + gap

        # save with explicit format
        if fmt in ("jpg", "jpeg") and args.bg == "transparent":
            print('[warn] JPEG does not support transparency; using white background for JPEG.')
        save_with_format(canvas, out_path, fmt, bg_for_jpeg=args.bg)
        print(f"[{idx}/{args.count}] Saved: {out_path} (K={K}, cell={cell_w}x{cell_h}, gap={gap}, margin={margin}, format={fmt.upper()}, label_band={label_band}px)")

if __name__ == "__main__":
    main()
