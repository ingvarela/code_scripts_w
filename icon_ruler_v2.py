#!/usr/bin/env python3
"""
simple_ruler_6in_textbbox.py
Adds a 0–6 inch horizontal ruler under images, using textbbox for text sizing.

Usage:
  python simple_ruler_6in_textbbox.py /path/to/image_or_folder [--dpi 300]
"""

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

def load_font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

def text_wh(d: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    # textbbox returns (left, top, right, bottom)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    return (r - l, b - t)

def draw_6in_ruler(width_px: int, height_px: int, dpi: int) -> Image.Image:
    """Create a 6-inch horizontal ruler (major ticks each 1 in, minor ticks each 1/8 in)."""
    ruler = Image.new("RGB", (width_px, height_px), (255, 255, 255))
    d = ImageDraw.Draw(ruler)
    font = load_font(16)

    # Spine along top edge
    d.line([(0, 0), (width_px - 1, 0)], fill=(0, 0, 0), width=2)

    inch_px = dpi
    total_in = 6
    total_px = total_in * inch_px

    # Center the 6-inch segment if canvas is wider
    x0 = (width_px - total_px) // 2 if width_px > total_px else 0
    x1 = x0 + min(total_px, width_px)

    # Minor ticks: every 1/8 in
    minor_step_px = max(1, inch_px // 8)
    for i in range(0, total_in * 8 + 1):
        x = x0 + i * minor_step_px
        if x > x1:
            break

        if i % 8 == 0:
            # Major (inch) tick
            d.line([(x, 0), (x, int(height_px * 0.65))], fill=(0, 0, 0), width=2)
            label = f'{i // 8}"'
            tw, th = text_wh(d, label, font)
            d.text((x - tw // 2, int(height_px * 0.65) + 4), label, font=font, fill=(0, 0, 0))
        elif i % 2 == 0:
            # Quarter-inch tick
            d.line([(x, 0), (x, int(height_px * 0.45))], fill=(0, 0, 0), width=1)
        else:
            # Eighth-inch tick
            d.line([(x, 0), (x, int(height_px * 0.3))], fill=(0, 0, 0), width=1)

    # Small title
    title = f"0–6 inches @ {dpi} DPI"
    tw, th = text_wh(d, title, font)
    d.text(((width_px - tw) // 2, height_px - th - 4), title, font=font, fill=(0, 0, 0))
    return ruler

def compose_under(img: Image.Image, ruler: Image.Image, gap: int = 8) -> Image.Image:
    """Stack image on top of ruler, centered; white background."""
    W = max(img.width, ruler.width)
    H = img.height + gap + ruler.height
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    x_img = (W - img.width) // 2
    x_rul = (W - ruler.width) // 2
    canvas.paste(img, (x_img, 0))
    canvas.paste(ruler, (x_rul, img.height + gap))
    return canvas

def process_one(path: Path, dpi: int):
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        print(f"[skip] {path.name}: {e}")
        return
    ruler_width = max(img.width, 6 * dpi)
    ruler_height = 100
    ruler = draw_6in_ruler(ruler_width, ruler_height, dpi)
    out = compose_under(img, ruler, gap=12)
    out_path = path.with_name(f"{path.stem}_measured{path.suffix}")
    try:
        out.save(out_path, dpi=(dpi, dpi))
        print(f"[ok] {path.name} -> {out_path.name}")
    except Exception as e:
        print(f"[fail] {path.name}: {e}")

def main():
    ap = argparse.ArgumentParser(description="Add a fixed 0–6 inch ruler below images (textbbox).")
    ap.add_argument("path", help="Path to an image file OR a folder of images")
    ap.add_argument("--dpi", type=int, default=300, help="DPI used to render the 6-inch ruler (default 300)")
    args = ap.parse_args()

    p = Path(args.path)
    if p.is_dir():
        for f in sorted(p.iterdir()):
            if f.suffix.lower() in EXTS:
                process_one(f, args.dpi)
    else:
        if p.suffix.lower() not in EXTS:
            print("Unsupported file type.")
            return
        process_one(p, args.dpi)

if __name__ == "__main__":
    main()
