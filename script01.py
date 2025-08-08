import os
import glob
import json
import re
import unicodedata
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random

# try torchvision for RandomPerspective; fallback later if missing
try:
    import torchvision.transforms.functional as TVF
    _HAS_TORCHVISION = True
except Exception:
    _HAS_TORCHVISION = False

# ==== CONFIGURACIÓN MANUAL PARA SPYDER ====
image_folder = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/img"
text_folder  = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/gutenberg_dataset/texts"
font_dir     = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/fonts"
output_folder   = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/enhanced_03"
metadata_folder = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/output16/metadata"
num_samples  = 300

# ---- Tunables ----
INSERT_BLANKS = False
MAX_BLANKS    = 3
JPEG_QUALITY  = 95
MAX_ATTEMPTS_PER_SAMPLE = 6
MIN_FONT_SIZE = 8
MIN_SPACING   = 2
INITIAL_SPACING = 8

# Gentle perspective params (kept tiny to avoid OCR distortion)
PERSPECTIVE_P = 0.7             # probability to apply
PERSPECTIVE_DISTORTION = 0.03   # 3% corner jitter
# we apply: perspective -> skew -> rotate

# === TEXT UTILS ===
def normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    # keep spaces, drop control chars, collapse whitespace, remove newlines (we re-wrap)
    t = "".join(
        (" " if unicodedata.category(ch)[0] == "C" else ch)
        for ch in t.replace("\r", " ").replace("\n", " ")
    )
    t = re.sub(r"\s+", " ", t).strip()
    return t

def get_valid_paragraph(file_path, min_words=15, max_words=50, rng: random.Random = random):
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content)]
    candidates = [p for p in paragraphs if min_words <= len(p.split()) <= max_words]
    if not candidates:
        return None
    return rng.choice(candidates)

def list_book_folders(root):
    return [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]

def get_random_font(font_dir, size, rng: random.Random = random):
    font_files = [f for f in os.listdir(font_dir) if f.lower().endswith(".ttf")]
    if not font_files:
        raise FileNotFoundError("No .ttf fonts found in fonts folder.")
    font_file = rng.choice(font_files)
    font_path = os.path.join(font_dir, font_file)
    return ImageFont.truetype(font_path, size), os.path.basename(font_file), font_path

def _text_width(draw: ImageDraw.ImageDraw, txt: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), txt, font=font)
    return bbox[2] - bbox[0]

def wrap_text_lines(text, font, max_width, draw):
    words = text.strip().split()
    lines, current = [], ""

    for word in words:
        test = (current + " " + word) if current else word
        if _text_width(draw, test, font) <= max_width:
            current = test
            continue

        if current:
            lines.append(current)

        # handle too-long token by char-splitting
        if _text_width(draw, word, font) > max_width:
            chunk = ""
            for ch in word:
                t2 = chunk + ch
                if _text_width(draw, t2, font) <= max_width:
                    chunk = t2
                else:
                    if chunk:
                        lines.append(chunk)
                    chunk = ch
            current = chunk
        else:
            current = word

    if current:
        lines.append(current)
    return lines

def insert_blank_lines_randomly(lines, rng: random.Random, max_blanks=3):
    if len(lines) <= 1:
        return lines
    num_blanks = rng.randint(1, max_blanks)
    for _ in range(num_blanks):
        if len(lines) <= 1:
            break
        idx = rng.randint(1, len(lines) - 1)
        lines.insert(idx, "")
    return lines

def line_height_of(font):
    bbox = font.getbbox("Ag")
    return bbox[3] - bbox[1]

def fits(lines, font, canvas_w, canvas_h, spacing, margins=(10,10,10,10)):
    lh = line_height_of(font)
    total_h = lh * len(lines) + (len(lines) - 1) * spacing
    top, right, bottom, left = margins
    return total_h <= (canvas_h - top - bottom)

def autofit_or_trim(paragraph, font_path, base_font_size, draw, canvas_w, canvas_h,
                    spacing=INITIAL_SPACING, min_font=MIN_FONT_SIZE, min_spacing=MIN_SPACING,
                    margins=(10,10,10,10)):
    # 1) shrink font then spacing
    size = base_font_size
    while size >= min_font:
        f = ImageFont.truetype(font_path, size)
        lines = wrap_text_lines(paragraph, f, canvas_w - margins[1] - margins[3], draw)
        sp = spacing
        while sp >= min_spacing:
            if fits(lines, f, canvas_w, canvas_h, sp, margins):
                return f, lines, sp
            sp -= 2
        size -= 2

    # 2) trim text with binary search (min settings)
    f = ImageFont.truetype(font_path, max(min_font, base_font_size))
    lo, hi = 1, len(paragraph)
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = paragraph[:mid]
        lines = wrap_text_lines(cand, f, canvas_w - margins[1] - margins[3], draw)
        if fits(lines, f, canvas_w, canvas_h, min_spacing, margins):
            best = (lines, mid)
            lo = mid + 1
        else:
            hi = mid - 1
    if best:
        lines, cut = best
        if cut < len(paragraph) and lines:
            lines[-1] = (lines[-1].rstrip() + "…").strip()
        return f, lines, min_spacing

    # 3) last resort—single ellipsis
    return f, ["…"], min_spacing

# === TRANSFORMS ===
def rotate_canvas(canvas, rng: random.Random, angle_range=(-10, 10)):
    angle = rng.uniform(*angle_range)
    rotated = canvas.rotate(angle, resample=Image.BICUBIC, expand=True)
    return rotated, angle

def skew_canvas(canvas, rng: random.Random, magnitude_range=(-0.15, 0.15)):
    width, height = canvas.size
    magnitude = rng.uniform(*magnitude_range)
    xshift = abs(magnitude) * width
    new_width = width + int(round(xshift))
    if magnitude > 0:
        coeffs = (1, magnitude, -xshift, 0, 1, 0)
    else:
        coeffs = (1, magnitude, 0, 0, 1, 0)
    skewed = canvas.transform((new_width, height), Image.AFFINE, coeffs, Image.BICUBIC)
    return skewed, magnitude

def _pil_perspective_coeffs(src_pts, dst_pts):
    # Solve for perspective transform coefficients
    # src_pts/dst_pts: list of 4 (x, y) tuples in same order
    import numpy as np
    A = []
    B = []
    for (x, y), (u, v) in zip(src_pts, dst_pts):
        A.extend([
            [x, y, 1, 0, 0, 0, -u*x, -u*y],
            [0, 0, 0, x, y, 1, -v*x, -v*y]
        ])
        B.extend([u, v])
    A = np.asarray(A)
    B = np.asarray(B)
    res = np.linalg.lstsq(A, B, rcond=None)[0]
    return tuple(res.tolist())

def random_perspective_canvas(canvas, rng: random.Random,
                              distortion_scale=PERSPECTIVE_DISTORTION, p=PERSPECTIVE_P):
    """
    Apply a very gentle perspective to the text canvas.
    Uses torchvision if available; otherwise uses PIL perspective transform.
    """
    if rng.random() > p:
        return canvas, {
            "perspective_applied": False,
            "perspective_distortion": 0.0
        }

    w, h = canvas.size
    # small jitter (e.g., up to 3% of width/height)
    dx = distortion_scale * w
    dy = distortion_scale * h

    # source corners in PIL order: TL, TR, BR, BL
    src = [(0, 0), (w, 0), (w, h), (0, h)]

    # jittered destination corners (keep inside bounds)
    jitter = lambda a, b: (a + rng.uniform(-dx, dx), b + rng.uniform(-dy, dy))
    dst = [jitter(0, 0), jitter(w, 0), jitter(w, h), jitter(0, h)]

    if _HAS_TORCHVISION:
        # torchvision expects tensors; we’ll convert via TF ops
        # But TVF.perspective() needs startpoints & endpoints with order TL, TR, BR, BL
        try:
            # convert PIL -> tensor -> transform -> PIL
            import torchvision.transforms.functional as F
            import torchvision.transforms as T
            import torch
            pil_to_tensor = T.PILToTensor()
            tensor_to_pil = T.ToPILImage()
            img_t = pil_to_tensor(canvas)
            # torchvision expects list of lists of (x, y)
            startpoints = [list(pt) for pt in src]
            endpoints   = [list(pt) for pt in dst]
            warped_t = F.perspective(img_t, startpoints, endpoints, interpolation=F.InterpolationMode.BICUBIC, fill=None)
            warped = tensor_to_pil(warped_t)
            return warped, {
                "perspective_applied": True,
                "perspective_distortion": float(distortion_scale)
            }
        except Exception:
            # fallback to PIL method if anything goes sideways
            pass

    # PIL fallback
    try:
        coeffs = _pil_perspective_coeffs(src, dst)
        warped = canvas.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
        return warped, {
            "perspective_applied": True,
            "perspective_distortion": float(distortion_scale)
        }
    except Exception:
        # if still fails, just return original
        return canvas, {
            "perspective_applied": False,
            "perspective_distortion": 0.0
        }

# === BOOTSTRAP ===
os.makedirs(output_folder, exist_ok=True)
os.makedirs(metadata_folder, exist_ok=True)

# Preload any existing global annotations (optional)
annotations_file = os.path.join(os.path.dirname(output_folder), "synthdog_en_annotations.json")
output_records = []
if os.path.exists(annotations_file):
    try:
        with open(annotations_file, 'r', encoding='utf-8') as f:
            output_records = json.load(f)
    except Exception:
        output_records = []

# Count existing valid ids (both image + json present)
existing_images   = {Path(p).stem for p in glob.glob(os.path.join(output_folder, "*.jpg"))}
existing_metadata = {Path(p).stem for p in glob.glob(os.path.join(metadata_folder, "*.json"))}
existing_ids = sorted(existing_images.intersection(existing_metadata))
existing_count = len(existing_ids)

additional_needed = num_samples - existing_count
if additional_needed <= 0:
    print(f"No additional samples needed. Current count: {existing_count}, Requested count: {num_samples}")
    raise SystemExit

print(f"Generating {additional_needed} additional samples...")

all_images = glob.glob(os.path.join(image_folder, "*.jpg"))
total_images = len(all_images)
if total_images == 0:
    raise ValueError(f"No JPG images found in input folder: {image_folder}")

book_folders = list_book_folders(text_folder)
if not book_folders:
    raise ValueError(f"No subfolders found in text folder: {text_folder}")

produced = 0
global_img_idx = 0

while produced < additional_needed:
    target_index = existing_count + produced
    synthdog_id = f"synthdog_en_{target_index:05d}"

    success = False
    for attempt in range(MAX_ATTEMPTS_PER_SAMPLE):
        rng = random.Random(hash(f"{synthdog_id}:{attempt}") & 0xFFFFFFFF)

        # select base image (cycled)
        image_path = all_images[global_img_idx % total_images]
        global_img_idx += 1
        image = Image.open(image_path).convert("RGBA")
        width, height = image.size

        # select paragraph
        paragraph = None
        for _ in range(3):
            folder = rng.choice(book_folders)
            folder_path = os.path.join(text_folder, folder)
            txt_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".txt")]
            if not txt_files:
                continue
            txt_path = os.path.join(folder_path, rng.choice(txt_files))
            para_raw = get_valid_paragraph(txt_path, rng=rng)
            if para_raw:
                paragraph = normalize_text(para_raw)
                break
        if not paragraph:
            continue

        # layout
        scale = rng.uniform(0.5, 0.7)
        canvas_width  = max(32, int(width * scale))
        canvas_height = max(32, int(height * scale))
        x = rng.randint(0, max(0, width - canvas_width))
        y = rng.randint(0, max(0, height - canvas_height))

        canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        base_font_size = rng.randint(10, 28)
        font, font_name, font_path = get_random_font(font_dir, base_font_size, rng=rng)

        max_text_width = canvas_width - 20
        lines = wrap_text_lines(paragraph, font, max_text_width, draw)
        spacing = INITIAL_SPACING

        if INSERT_BLANKS:
            lines = insert_blank_lines_randomly(lines, rng, max_blanks=MAX_BLANKS)

        # ensure it fits (shrink/space/trim if needed)
        if not fits(lines, font, canvas_width, canvas_height, spacing):
            font, lines, spacing = autofit_or_trim(
                paragraph, font_path, base_font_size, draw,
                canvas_width, canvas_height, spacing=INITIAL_SPACING
            )

        # draw text
        wrapped_text = "\n".join(lines)
        draw.multiline_text((10, 10), wrapped_text, font=font, fill=(0, 0, 0), spacing=spacing)

        # === NEW: gentle RandomPerspective on the TEXT CANVAS only ===
        canvas, persp_meta = random_perspective_canvas(
            canvas, rng,
            distortion_scale=PERSPECTIVE_DISTORTION,
            p=PERSPECTIVE_P
        )

        # skew + rotate
        source_canvas_size = [canvas_width, canvas_height]
        canvas, skew_magnitude = skew_canvas(canvas, rng, magnitude_range=(-0.15, 0.15))
        rotated_canvas, rotation_angle = rotate_canvas(canvas, rng, angle_range=(-10, 10))

        # composite
        final_image = image.copy()
        paste_x = max(0, min(x, width - rotated_canvas.width))
        paste_y = max(0, min(y, height - rotated_canvas.height))
        final_image.alpha_composite(rotated_canvas, (paste_x, paste_y))

        # save image
        image_filename = synthdog_id + ".jpg"
        out_img_path = os.path.join(output_folder, image_filename)
        final_image.convert("RGB").save(out_img_path, quality=JPEG_QUALITY, subsampling=1, optimize=True)

        # Build expected OCR from what we actually drew
        visible_lines = [ln for ln in lines if ln.strip() != ""]
        expected_ocr = " ".join(visible_lines)

        # per-sample metadata (keep your relative path style in SynthDog record below)
        json_filename = synthdog_id + ".json"
        sample_meta = {
            "id": synthdog_id,
            "image": image_filename,
            "font": font_name,
            "font_size": font.size,
            "text_source": paragraph,
            "wrapped_text": wrapped_text,
            "expected_ocr": expected_ocr,
            "position": [paste_x, paste_y],
            "paste_bbox": [paste_x, paste_y, paste_x + rotated_canvas.width, paste_y + rotated_canvas.height],
            "source_canvas_size": source_canvas_size,
            "canvas_size": [rotated_canvas.width, rotated_canvas.height],
            "rotation_angle": rotation_angle,
            "skew_magnitude": skew_magnitude,
            "spacing": spacing,
            "perspective_applied": persp_meta.get("perspective_applied", False),
            "perspective_distortion": persp_meta.get("perspective_distortion", 0.0)
        }
        with open(os.path.join(metadata_folder, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(sample_meta, jf, indent=2, ensure_ascii=False)

        # === SYNTHDOG META — using your original relative-path pattern ===
        image_rel_path = os.path.join(output_folder, image_filename)
        image_abs_path = os.path.dirname(os.path.dirname(os.path.dirname(image_rel_path)))
        relative_path = os.path.relpath(image_rel_path, start=image_abs_path)

        synthdog_meta = {
            "id": synthdog_id,
            "conversations": [
                {
                    "from": "human",
                    "value": "<image>\nOCR this image section by section, from top to bottom, and left to right. Do not insert line breaks in the output text. If a word is split due to a line break in the image, use a space instead."
                },
                {
                    "from": "gpt",
                    "value": expected_ocr
                }
            ],
            "data source": "srt_synthdog_en",
            "image": relative_path
        }
        output_records.append(synthdog_meta)

        print(f"Generating sample {target_index + 1} of {num_samples}: {synthdog_id}")
        success = True
        break

    if not success:
        # extremely unlikely due to autofit, but ensure forward progress anyway
        print(f"[WARN] Fallback single-ellipsis for {synthdog_id}")
        canvas_width = 64
        canvas_height = 64
        image = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        # pick any font for consistency
        font_files = [f for f in os.listdir(font_dir) if f.lower().endswith(".ttf")]
        font_path = os.path.join(font_dir, sorted(font_files)[0]) if font_files else None
        if font_path:
            font = ImageFont.truetype(font_path, MIN_FONT_SIZE)
        else:
            font = ImageFont.load_default()
        draw.text((10, 10), "…", fill=(0, 0, 0), font=font)

        image_filename = synthdog_id + ".jpg"
        out_img_path = os.path.join(output_folder, image_filename)
        image.convert("RGB").save(out_img_path, quality=JPEG_QUALITY, subsampling=1, optimize=True)

        # meta
        json_filename = synthdog_id + ".json"
        sample_meta = {
            "id": synthdog_id,
            "image": image_filename,
            "font": Path(font_path).name if font_path else "default",
            "font_size": MIN_FONT_SIZE,
            "text_source": "",
            "wrapped_text": "…",
            "expected_ocr": "…",
            "position": [10, 10],
            "paste_bbox": [0, 0, canvas_width, canvas_height],
            "source_canvas_size": [canvas_width, canvas_height],
            "canvas_size": [canvas_width, canvas_height],
            "rotation_angle": 0.0,
            "skew_magnitude": 0.0,
            "spacing": MIN_SPACING,
            "perspective_applied": False,
            "perspective_distortion": 0.0
        }
        with open(os.path.join(metadata_folder, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(sample_meta, jf, indent=2, ensure_ascii=False)

        # keep your relative path logic
        image_rel_path = os.path.join(output_folder, image_filename)
        image_abs_path = os.path.dirname(os.path.dirname(os.path.dirname(image_rel_path)))
        relative_path = os.path.relpath(image_rel_path, start=image_abs_path)
        synthdog_meta = {
            "id": synthdog_id,
            "conversations": [
                {"from": "human", "value": "<image>\nOCR this image section by section..."},
                {"from": "gpt", "value": "…"}
            ],
            "data source": "srt_synthdog_en",
            "image": relative_path
        }
        output_records.append(synthdog_meta)

    produced += 1

# === SAVE GLOBAL METADATA ===
all_meta_path = os.path.join(metadata_folder, "all_metadata.json")
with open(all_meta_path, "w", encoding="utf-8") as f:
    json.dump(output_records, f, indent=2, ensure_ascii=False)

print(f"✅ Done! Generated {existing_count + produced} images and metadata entries.")
