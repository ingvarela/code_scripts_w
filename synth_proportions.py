# Synthdog Generator — full pipeline with 1:1 OCR guarantee + effect mix
# - Argparse for paths/config
# - Text wrapping + vertical trim (prevents overflow)
# - Visual intra-word spacing (OCR uses clean words)
# - Canvas grit, optional low-res canvas, background blur, global tone tweaks
# - Skew + rotate + mild perspective (always applied)
# - NO CROPPING: skip sample if transformed canvas exceeds background
# - Metadata saves ONLY what’s visible
# - NEW: Mutually exclusive effect mix per sample (configurable fractions)

import argparse
import os
import glob
import json
import re
import random
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# TorchVision (optional, for perspective)
try:
    import torchvision.transforms as T
    import torchvision.transforms.functional as F
    _HAS_TV = True
except Exception:
    _HAS_TV = False

# === ARGUMENTS ===
parser = argparse.ArgumentParser(description="Synthetic OCR dataset generator with robust visual effects and exact OCR labels.")
parser.add_argument("--image_folder", type=str, default="C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/img")
parser.add_argument("--text_folder", type=str, default="C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/gutenberg_dataset/texts")
parser.add_argument("--font_dir", type=str, default="C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/fonts")
parser.add_argument("--output_folder", type=str, default="C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/new_set_40000")
parser.add_argument("--metadata_folder", type=str, default="C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/output16/metadata")
parser.add_argument("--num_samples", type=int, default=300)
# NEW: effect mix fractions
parser.add_argument("--mix_grit",   type=float, default=0.25, help="Fraction of samples with canvas noise/blur (grit).")
parser.add_argument("--mix_lowres", type=float, default=0.25, help="Fraction with low-res canvas degradation.")
parser.add_argument("--mix_tone",   type=float, default=0.25, help="Fraction with global tone adjustments.")
parser.add_argument("--mix_bgblur", type=float, default=0.25, help="Fraction with background blur.")
args = parser.parse_args()

# === CONFIG ===
image_folder     = args.image_folder
text_folder      = args.text_folder
font_dir         = args.font_dir
output_folder    = args.output_folder
metadata_folder  = args.metadata_folder
num_samples      = args.num_samples

# Mix
MIX = {
    "canvas_grit": args.mix_grit,
    "lowres":      args.mix_lowres,
    "tone":        args.mix_tone,
    "bg_blur":     args.mix_bgblur,
}
total_mix = sum(MIX.values())
if total_mix <= 0:
    raise ValueError("All mix fractions are zero. Provide positive fractions.")
for k in list(MIX.keys()):
    MIX[k] = MIX[k] / total_mix  # normalize to sum=1.0

# Tunables
JPEG_QUALITY  = 95
FONT_SIZE_RANGE = (10, 40)
INITIAL_SPACING = 8
MIN_SPACING   = 2
AUTO_FILL_VERTICAL = True
CANVAS_SCALE_RANGE = (0.5, 0.7)

# Perspective (kept mild to not harm OCR)
PERSPECTIVE_P = 0.7
PERSPECTIVE_DISTORTION = 0.03

# Background blur (used only in bg_blur mode)
BG_BLUR_RADIUS_RANGE = (0.5, 1.8)

# Canvas grit
CANVAS_BLUR_RANGE = (0.25, 0.8)
CANVAS_NOISE_SIGMA = 3.0

# Low-res canvas effect
LOWRES_P = 1.0               # forced when mode == "lowres"
LOWRES_SCALE_RANGE = (0.35, 0.7)

# Tone tweaks (used only in tone mode)
SAT_RANGE     = (0.92, 1.08)
BRI_RANGE     = (0.95, 1.05)
CON_RANGE     = (0.95, 1.06)
GAMMA_RANGE   = (0.95, 1.05)

# Intra-word spacing (visual only)
INTRA_WORD_SPACE_PROB = 0.25
LETTER_SPACE_PROB     = 0.25

# Layout modes
LAYOUT_MODES = ["paragraph", "word_lines", "phrase_lines", "char_spread"]
PHRASE_LEN_RANGE = (2, 5)
CHAR_SPREAD_NEWLINE_EVERY = (10, 18)

# === HELPERS ===
def list_book_folders(root):
    return [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]

def get_random_font(font_dir, size, rng=random):
    font_files = [f for f in os.listdir(font_dir) if f.lower().endswith(".ttf")]
    if not font_files:
        raise FileNotFoundError("No .ttf fonts found in fonts folder.")
    fp = os.path.join(font_dir, rng.choice(font_files))
    return ImageFont.truetype(fp, size), os.path.basename(fp), fp

def random_dark_font_color(rng=random):
    if rng.random() < 0.6:
        g = rng.randint(0, 80)
        return (g, g, g)
    return (rng.randint(0, 80), rng.randint(0, 80), rng.randint(0, 80))

def _text_width(draw, txt, font):
    if not txt:
        return 0
    bbox = draw.textbbox((0, 0), txt, font=font)
    return bbox[2] - bbox[0]

def wrap_text_lines(text, font, max_width, draw):
    words = text.strip().split(" ")
    lines, current = [], ""
    for word in words:
        test = (current + " " + word) if current else word
        if _text_width(draw, test, font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
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

def line_height_of(font):
    bbox = font.getbbox("Ag")
    return bbox[3] - bbox[1]

def auto_line_spacing_to_fill(lines, font, canvas_h, margins=(10,10,10,10)):
    lh = line_height_of(font)
    top, right, bottom, left = margins
    avail_h = canvas_h - top - bottom
    if len(lines) <= 1:
        return INITIAL_SPACING
    spacing = int((avail_h - lh * len(lines)) / max(1, len(lines) - 1))
    return max(MIN_SPACING, min(spacing, 24))

def inject_intra_word_spaces(text, rng):
    out = []
    for w in text.split(" "):
        if len(w) > 2 and rng.random() < INTRA_WORD_SPACE_PROB:
            chars = [w[0]]
            for ch in w[1:]:
                if rng.random() < LETTER_SPACE_PROB:
                    chars.append(" ")
                chars.append(ch)
            out.append("".join(chars))
        else:
            out.append(w)
    return " ".join(out)

def restructure_paragraph_for_coverage(paragraph, rng, mode="paragraph"):
    words = paragraph.split(" ")
    if mode == "paragraph":
        return paragraph
    if mode == "word_lines":
        return "\n".join(words)
    if mode == "phrase_lines":
        i = 0; lines = []
        while i < len(words):
            k = rng.randint(PHRASE_LEN_RANGE[0], PHRASE_LEN_RANGE[1])
            lines.append(" ".join(words[i:i+k])); i += k
        return "\n".join(lines)
    if mode == "char_spread":
        s = paragraph
        target = rng.randint(CHAR_SPREAD_NEWLINE_EVERY[0], CHAR_SPREAD_NEWLINE_EVERY[1])
        acc = []; count = 0
        for ch in s:
            acc.append(ch); count += 1
            if count >= target and ch == " ":
                acc.append("\n"); count = 0
        return "".join(acc)
    return paragraph

# Preserve existing spaces/newlines while injecting intra-word spaces INSIDE tokens only
def inject_intra_preserve_separators(s: str, rng) -> str:
    parts = re.split(r'(\s+)', s)  # keep separators as tokens
    out = []
    for tok in parts:
        if tok.isspace():
            out.append(tok)
        else:
            if not tok:
                out.append(tok)
                continue
            chars = [tok[0]]
            for ch in tok[1:]:
                if ch.isalpha() and rng.random() < LETTER_SPACE_PROB:
                    chars.append(" ")
                chars.append(ch)
            out.append("".join(chars))
    return "".join(out)

# Build OCR from what was actually drawn (drawn_text) but using clean paragraph spacing
def derive_expected_ocr_from_drawn(paragraph_clean: str, drawn_text: str) -> str:
    clean = re.sub(r"\s+", " ", paragraph_clean).strip()
    vis_chars = re.sub(r"\s+", "", drawn_text)   # all visible non-space glyphs painted
    target_len = len(vis_chars)

    out = []
    taken = 0
    for ch in clean:
        if ch.isspace():
            out.append(" ")
        else:
            if taken < target_len:
                out.append(ch)
                taken += 1
            else:
                break

    return re.sub(r"\s+", " ", "".join(out)).strip()

# Perturbations
def add_canvas_grit(canvas_rgba, rng, blur_range=CANVAS_BLUR_RANGE, noise_sigma=CANVAS_NOISE_SIGMA):
    r = rng.uniform(*blur_range)
    blurred = canvas_rgba.filter(ImageFilter.GaussianBlur(radius=r))
    arr = np.array(blurred).astype(np.int16)
    if noise_sigma > 0:
        np_rng = np.random.default_rng(rng.randrange(1 << 30))
        noise_map = np_rng.normal(0, noise_sigma, size=arr[..., :3].shape)
        arr[..., :3] = np.clip(arr[..., :3] + noise_map, 0, 255)
    return Image.fromarray(arr.astype(np.uint8)), float(r), float(noise_sigma)

def degrade_canvas_quality(canvas_rgba, rng,
                           p=LOWRES_P, scale_range=LOWRES_SCALE_RANGE):
    if rng.random() < p:
        w, h = canvas_rgba.size
        sf = rng.uniform(*scale_range)
        w2 = max(1, int(w * sf)); h2 = max(1, int(h * sf))
        rgb = canvas_rgba.convert("RGB"); a = canvas_rgba.getchannel("A")
        rgb_small = rgb.resize((w2, h2), resample=Image.BILINEAR)
        rgb_pix   = rgb_small.resize((w, h), resample=Image.NEAREST)
        a_small = a.resize((w2, h2), resample=Image.BILINEAR)
        a_pix   = a_small.resize((w, h), resample=Image.NEAREST)
        canvas_rgba = Image.merge("RGBA", (*rgb_pix.split(), a_pix))
    return canvas_rgba

def rotate_canvas(canvas, rng, angle_range=(-10, 10)):
    angle = rng.uniform(*angle_range)
    return canvas.rotate(angle, resample=Image.BICUBIC, expand=True)

def skew_canvas(canvas, rng, magnitude_range=(-0.15, 0.15)):
    width, height = canvas.size
    magnitude = rng.uniform(*magnitude_range)
    xshift = abs(magnitude) * width
    new_width = width + int(round(xshift))
    coeffs = (1, magnitude, -xshift if magnitude > 0 else 0, 0, 1, 0)
    return canvas.transform((new_width, height), Image.AFFINE, coeffs, Image.BICUBIC)

def random_perspective_canvas(canvas, rng):
    if not _HAS_TV or rng.random() > PERSPECTIVE_P:
        return canvas, {"perspective_applied": False, "perspective_distortion": 0.0}
    t = T.RandomPerspective(distortion_scale=PERSPECTIVE_DISTORTION, p=1.0)
    tens = F.to_tensor(canvas)
    warped = t(tens)
    out = F.to_pil_image(warped)
    return out, {"perspective_applied": True, "perspective_distortion": float(PERSPECTIVE_DISTORTION)}

# Tone
def _adjust_gamma(img_rgb, gamma):
    inv = 1.0 / max(1e-6, gamma)
    lut = [int(pow(i / 255.0, inv) * 255.0 + 0.5) for i in range(256)]
    return img_rgb.point(lut * 3)

def apply_global_tone(rgb_img, rng):
    sat = random.uniform(*SAT_RANGE)
    bri = random.uniform(*BRI_RANGE)
    con = random.uniform(*CON_RANGE)
    gam = random.uniform(*GAMMA_RANGE)
    out = ImageEnhance.Color(rgb_img).enhance(sat)
    out = ImageEnhance.Brightness(out).enhance(bri)
    out = ImageEnhance.Contrast(out).enhance(con)
    out = _adjust_gamma(out, gam)
    meta = {
        "tone_applied": True,
        "tone_saturation": round(float(sat),4),
        "tone_brightness": round(float(bri),4),
        "tone_contrast":   round(float(con),4),
        "tone_gamma":      round(float(gam),4),
    }
    return out, meta

# Build an exclusive feature schedule
def build_feature_schedule(n, mix_dict, rng):
    keys = ["canvas_grit", "lowres", "tone", "bg_blur"]
    weights = [mix_dict[k] for k in keys]
    counts = [int(round(w * n)) for w in weights]
    diff = n - sum(counts)
    order = sorted(range(len(keys)), key=lambda i: weights[i], reverse=True)
    idx = 0
    step = 1 if diff > 0 else -1
    for _ in range(abs(diff)):
        counts[order[idx % len(order)]] += step
        idx += 1
    schedule = []
    for k, c in zip(keys, counts):
        schedule += [k] * max(0, c)
    if len(schedule) < n:
        schedule += [keys[0]] * (n - len(schedule))
    elif len(schedule) > n:
        schedule = schedule[:n]
    rng.shuffle(schedule)
    return schedule

# === BOOTSTRAP ===
os.makedirs(output_folder, exist_ok=True)
os.makedirs(metadata_folder, exist_ok=True)

existing_images   = {Path(p).stem for p in glob.glob(os.path.join(output_folder, "*.jpg"))}
existing_metadata = {Path(p).stem for p in glob.glob(os.path.join(metadata_folder, "*.json"))}
existing_ids = sorted(existing_images.intersection(existing_metadata))
existing_count = len(existing_ids)

all_images = glob.glob(os.path.join(image_folder, "*.jpg"))
if not all_images:
    raise ValueError(f"No JPG images found in input folder: {image_folder}")

book_folders = list_book_folders(text_folder)
if not book_folders:
    raise ValueError(f"No subfolders found in text folder: {text_folder}")

additional_needed = num_samples - existing_count
if additional_needed <= 0:
    print(f"No additional samples needed. Current count: {existing_count}, Requested count: {num_samples}")
    raise SystemExit

# Build the exclusive effect schedule
feature_rng = random.Random(12345)  # deterministic per run; change seed if desired
feature_schedule = build_feature_schedule(additional_needed, MIX, feature_rng)

output_records = []
produced = 0
img_idx = 0

while produced < additional_needed:
    target_index = existing_count + produced
    synthdog_id = f"synthdog_en_{target_index:05d}"
    rng = random.Random(hash(f"{synthdog_id}") & 0xFFFFFFFF)

    # Choose mode for this sample
    mode = feature_schedule[produced]  # one of: 'canvas_grit','lowres','tone','bg_blur'

    # Background
    image_path = all_images[img_idx % len(all_images)]; img_idx += 1
    bg = Image.open(image_path).convert("RGBA")
    W, H = bg.size

    # Apply background blur ONLY if mode == 'bg_blur'
    if mode == "bg_blur":
        r = rng.uniform(*BG_BLUR_RADIUS_RANGE)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=r))
        bg_blurred, bg_blur_radius = True, r
    else:
        bg_blurred, bg_blur_radius = False, 0.0

    # Pick paragraph
    paragraph = None
    for _ in range(3):
        folder = rng.choice(book_folders)
        folder_path = os.path.join(text_folder, folder)
        txt_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.txt')]
        if not txt_files:
            continue
        txt_path = os.path.join(folder_path, rng.choice(txt_files))
        with open(txt_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        paras = [p.strip() for p in re.split(r'\n\s*\n', content) if 15 <= len(p.split()) <= 50]
        if paras:
            paragraph = rng.choice(paras)
            break
    if not paragraph:
        continue

    # Layout selection
    layout_mode = rng.choice(LAYOUT_MODES)

    # Build a single layout plan once on CLEAN text
    render_text_plan = restructure_paragraph_for_coverage(paragraph, rng, mode=layout_mode)
    # Visible text: inject intra-word spaces but preserve existing spaces/newlines
    render_text_draw = inject_intra_preserve_separators(render_text_plan, rng)
    # OCR text uses the clean plan
    render_text_ocr  = render_text_plan

    # Prepare canvas size & font
    scale = rng.uniform(*CANVAS_SCALE_RANGE)
    CW, CH = max(32, int(W*scale)), max(32, int(H*scale))
    canvas = Image.new("RGBA", (CW, CH), (255,255,255,255))
    draw = ImageDraw.Draw(canvas)

    base_font_size = rng.randint(*FONT_SIZE_RANGE)
    font, font_name, font_path = get_random_font(font_dir, base_font_size, rng=rng)
    font_color = random_dark_font_color(rng)

    max_text_width = CW - 20
    # Wrap visible (with spacing)
    lines_draw = []
    for block in render_text_draw.split("\n"):
        lines_draw.extend(wrap_text_lines(block, font, max_text_width, draw))
    # Wrap OCR (no intra spacing)
    lines_ocr = []
    for block in render_text_ocr.split("\n"):
        lines_ocr.extend(wrap_text_lines(block, font, max_text_width, draw))

    # Vertical trim BEFORE transforms
    spacing = INITIAL_SPACING
    if AUTO_FILL_VERTICAL:
        spacing = auto_line_spacing_to_fill(lines_draw, font, CH)
    lh = line_height_of(font)
    max_text_h = CH - 20
    max_lines = int((max_text_h + spacing) // (lh + spacing)) if (lh + spacing) > 0 else len(lines_draw)
    max_lines = max(1, max_lines)

    lines_draw = lines_draw[:max_lines]
    lines_ocr  = lines_ocr[:max_lines]

    # Draw EXACT lines
    drawn_text = "\n".join(lines_draw)
    draw.multiline_text((10,10), drawn_text, font=font, fill=font_color, spacing=spacing)

    # Geometric transforms (always on)
    canvas, persp_meta = random_perspective_canvas(canvas, rng)
    canvas = skew_canvas(canvas, rng)
    canvas = rotate_canvas(canvas, rng)

    # Apply the exclusive effect
    grit_blur_r, grit_noise_sigma = 0.0, 0.0
    if mode == "canvas_grit":
        canvas, grit_blur_r, grit_noise_sigma = add_canvas_grit(canvas, rng)
    elif mode == "lowres":
        canvas = degrade_canvas_quality(canvas, rng, p=1.0, scale_range=LOWRES_SCALE_RANGE)
    # 'tone' and 'bg_blur' don't touch the canvas here

    # === NO CROPPING: if canvas exceeds background, skip sample ===
    cW, cH = canvas.size
    if cW > W or cH > H:
        print(f"[skip] Canvas {cW}x{cH} exceeds background {W}x{H} for {synthdog_id}; retrying.")
        continue

    # Paste
    px = rng.randint(0, W - cW) if (W - cW) > 0 else 0
    py = rng.randint(0, H - cH) if (H - cH) > 0 else 0
    final = bg.copy()
    final.alpha_composite(canvas, (px, py))

    # Global tone: apply ONLY if mode == "tone"
    rgb = final.convert("RGB")
    if mode == "tone":
        rgb, tone_meta = apply_global_tone(rgb, rng)
    else:
        tone_meta = {
            "tone_applied": False,
            "tone_saturation": 1.0,
            "tone_brightness": 1.0,
            "tone_contrast":   1.0,
            "tone_gamma":      1.0,
        }

    # Save image
    image_filename = synthdog_id + ".jpg"
    out_img_path = os.path.join(output_folder, image_filename)
    rgb.save(out_img_path, quality=JPEG_QUALITY, subsampling=1, optimize=True)

    # OCR 1:1 from drawn content using clean paragraph spacing
    expected_ocr = derive_expected_ocr_from_drawn(paragraph, drawn_text)

    # Per-sample JSON
    json_filename = synthdog_id + ".json"
    sample_meta = {
        "id": synthdog_id,
        "image": image_filename,
        "font": font_name,
        "font_size": font.size,
        "font_color_rgb": font_color,
        "text_source": paragraph,
        "text_after_spacing": render_text_draw,
        "layout_mode": layout_mode,
        "drawn_lines": lines_draw,
        "drawn_text": drawn_text,
        "spacing": spacing,
        "expected_ocr": expected_ocr,
        "position": [px, py],
        "canvas_size": [cW, cH],
        "effect_mode": mode,
        "perspective_applied": persp_meta.get("perspective_applied", False),
        "perspective_distortion": persp_meta.get("perspective_distortion", 0.0),
        "bg_blurred": bg_blurred,
        "bg_blur_radius": bg_blur_radius,
        "canvas_grit_blur_radius": grit_blur_r,
        "canvas_grit_noise_sigma": grit_noise_sigma,
        "tone_applied": tone_meta["tone_applied"],
        "tone_saturation": tone_meta["tone_saturation"],
        "tone_brightness": tone_meta["tone_brightness"],
        "tone_contrast":   tone_meta["tone_contrast"],
        "tone_gamma":      tone_meta["tone_gamma"],
    }
    with open(os.path.join(metadata_folder, json_filename), 'w', encoding='utf-8') as jf:
        json.dump(sample_meta, jf, indent=2, ensure_ascii=False)

    # Global metadata entry (SynthDog style)
    image_rel_path = os.path.join(output_folder, image_filename)
    image_abs_path = os.path.dirname(os.path.dirname(os.path.dirname(image_rel_path)))
    relative_path = os.path.relpath(image_rel_path, start=image_abs_path)

    synthdog_meta = {
        "id": synthdog_id,
        "conversations": [
            {"from": "human", "value": "<image>\nOCR this image section by section, from top to bottom, and left to right. Do not insert line breaks in the output text. If a word is split due to a line break in the image, use a space instead."},
            {"from": "gpt", "value": expected_ocr}
        ],
        "data source": "srt_synthdog_en",
        "image": relative_path
    }
    output_records.append(synthdog_meta)

    print(f"Generating sample {target_index + 1} of {num_samples}: {synthdog_id} (mode={mode})")
    produced += 1

# Save global metadata
all_meta_path = os.path.join(metadata_folder, "all_metadata.json")
with open(all_meta_path, "w", encoding="utf-8") as f:
    json.dump(output_records, f, indent=2, ensure_ascii=False)

print(f"✅ Done! Generated {existing_count + produced} images and metadata entries.")
