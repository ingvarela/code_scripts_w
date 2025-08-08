import os
import glob
import json
import re
import unicodedata
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import random
import numpy as np
from io import BytesIO

# Try torchvision for RandomPerspective; fallback to PIL if missing
try:
    import torchvision.transforms.functional as TVF
    from torchvision.transforms.functional import InterpolationMode
    import torchvision.transforms as T
    _HAS_TORCHVISION = True
except Exception:
    _HAS_TORCHVISION = False

# ==== CONFIGURACIÓN MANUAL PARA SPYDER ====
image_folder = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/img"
text_folder  = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/gutenberg_dataset/texts"
font_dir     = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/fonts"
output_folder   = "C:/Users/svs26/Desktop/MS COCO 2017/Synthdog_en/new_set_40000"
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
FONT_SIZE_RANGE = (10, 40)
AUTO_FILL_VERTICAL = True

# Gentle perspective params (kept tiny to avoid OCR distortion)
PERSPECTIVE_P = 0.7
PERSPECTIVE_DISTORTION = 0.03

# Background blur (on BG image, not on text canvas)
BG_BLUR_PROB = 0.35
BG_BLUR_RADIUS_RANGE = (0.5, 1.8)

# Text canvas “grit”
CANVAS_BLUR_RANGE = (0.25, 0.8)
CANVAS_NOISE_SIGMA = 3.0

# Intra-word spacing (image shows spacing; OCR ignores those extra gaps)
INTRA_WORD_SPACE_PROB = 0.25
LETTER_SPACE_PROB     = 0.25

# Layout modes to cover canvas
LAYOUT_MODES = ["paragraph", "word_lines", "phrase_lines", "char_spread"]
PHRASE_LEN_RANGE = (2, 5)
CHAR_SPREAD_NEWLINE_EVERY = (10, 18)

# Whole-image gentle tone adjustments (randomly applied)
TONE_ADJUST_P = 0.6
SAT_RANGE     = (0.92, 1.08)
BRI_RANGE     = (0.95, 1.05)
CON_RANGE     = (0.95, 1.06)
GAMMA_RANGE   = (0.95, 1.05)

# NEW: Low-res “sticker” effect (text canvas only)
LOWRES_P = 0.5                        # 50/50 chance
LOWRES_SCALE_RANGE = (0.35, 0.7)      # downscale to 35–70%, then back up
LOWRES_JPEG_P = 0.7                   # often add a JPEG roundtrip
LOWRES_JPEG_QUALITY_RANGE = (28, 60)  # mild blockiness

# === TEXT UTILS ===
def normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\r", " ").replace("\n", " ")
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

def random_dark_font_color(rng: random.Random):
    mode = rng.random()
    if mode < 0.6:
        g = rng.randint(0, 80)
        return (g, g, g)
    else:
        r = rng.randint(0, 80)
        g = rng.randint(0, 80)
        b = rng.randint(0, 80)
        return (r, g, b)

def _text_width(draw: ImageDraw.ImageDraw, txt: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), txt, font=font)
    return bbox[2] - bbox[0]

def wrap_text_lines(text, font, max_width, draw):
    words = text.strip().split(" ")
    lines, current = [], ""
    for word in words:
        test = (current + " " + word) if current else word
        if _text_width(draw, test, font) <= max_width:
            current = test
            continue
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

def auto_line_spacing_to_fill(lines, font, canvas_w, canvas_h, margins=(10,10,10,10)):
    lh = line_height_of(font)
    top, right, bottom, left = margins
    avail_h = canvas_h - top - bottom
    if len(lines) <= 1:
        return INITIAL_SPACING
    spacing = int((avail_h - lh * len(lines)) / max(1, len(lines) - 1))
    return max(MIN_SPACING, min(spacing, 24))

def autofit_or_trim(paragraph, font_path, base_font_size, draw, canvas_w, canvas_h,
                    spacing=INITIAL_SPACING, min_font=MIN_FONT_SIZE, min_spacing=MIN_SPACING,
                    margins=(10,10,10,10)):
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
    return f, ["…"], min_spacing

# === Random spacing & layout modes ===
def inject_intra_word_spaces(text, rng: random.Random,
                             word_prob=INTRA_WORD_SPACE_PROB, letter_prob=LETTER_SPACE_PROB):
    out_words = []
    for w in text.split(" "):
        if len(w) > 2 and rng.random() < word_prob:
            chars = [w[0]]
            for ch in w[1:]:
                if rng.random() < letter_prob:
                    chars.append(" ")
                chars.append(ch)
            out_words.append("".join(chars))
        else:
            out_words.append(w)
    return " ".join(out_words)

def restructure_paragraph_for_coverage(paragraph, rng: random.Random, mode="paragraph",
                                       phrase_len_range=PHRASE_LEN_RANGE):
    words = paragraph.split(" ")
    if mode == "paragraph":
        return paragraph
    if mode == "word_lines":
        return "\n".join(words)
    if mode == "phrase_lines":
        i = 0
        lines = []
        while i < len(words):
            k = rng.randint(phrase_len_range[0], phrase_len_range[1])
            lines.append(" ".join(words[i:i+k]))
            i += k
        return "\n".join(lines)
    if mode == "char_spread":
        s = paragraph
        target = rng.randint(CHAR_SPREAD_NEWLINE_EVERY[0], CHAR_SPREAD_NEWLINE_EVERY[1])
        acc = []
        count = 0
        for ch in s:
            acc.append(ch)
            count += 1
            if count >= target and ch == " ":
                acc.append("\n")
                count = 0
        return "".join(acc)
    return paragraph

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
    if rng.random() > p:
        return canvas, {"perspective_applied": False, "perspective_distortion": 0.0}
    w, h = canvas.size
    dx = distortion_scale * w
    dy = distortion_scale * h
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    jitter = lambda a, b: (a + rng.uniform(-dx, dx), b + rng.uniform(-dy, dy))
    dst = [jitter(0, 0), jitter(w, 0), jitter(w, h), jitter(0, h)]
    if _HAS_TORCHVISION:
        try:
            pil_to_tensor = T.PILToTensor()
            tensor_to_pil = T.ToPILImage()
            img_t = pil_to_tensor(canvas)
            warped_t = TVF.perspective(
                img_t, [list(pt) for pt in src], [list(pt) for pt in dst],
                interpolation=InterpolationMode.BICUBIC, fill=None
            )
            return tensor_to_pil(warped_t), {"perspective_applied": True, "perspective_distortion": float(distortion_scale)}
        except Exception:
            pass
    try:
        coeffs = _pil_perspective_coeffs(src, dst)
        warped = canvas.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
        return warped, {"perspective_applied": True, "perspective_distortion": float(distortion_scale)}
    except Exception:
        return canvas, {"perspective_applied": False, "perspective_distortion": 0.0}

# === Image perturbations ===
def random_bg_blur(img_rgba, rng: random.Random, p=BG_BLUR_PROB, rad_range=BG_BLUR_RADIUS_RANGE):
    if rng.random() < p:
        r = rng.uniform(*rad_range)
        return img_rgba.filter(ImageFilter.GaussianBlur(radius=r)), True, r
    return img_rgba, False, 0.0

def add_canvas_grit(canvas_rgba, rng: random.Random,
                    blur_range=CANVAS_BLUR_RANGE, noise_sigma=CANVAS_NOISE_SIGMA):
    r = rng.uniform(*blur_range)
    blurred = canvas_rgba.filter(ImageFilter.GaussianBlur(radius=r))
    arr = np.array(blurred).astype(np.int16)
    if noise_sigma > 0:
        np_rng = np.random.default_rng(rng.randrange(1 << 30))
        noise_map = np_rng.normal(0, noise_sigma, size=arr[..., :3].shape)
        arr[..., :3] = np.clip(arr[..., :3] + noise_map, 0, 255)
    return Image.fromarray(arr.astype(np.uint8)), float(r), float(noise_sigma)

# NEW: low-res degradation (text canvas only)
def degrade_canvas_quality(canvas_rgba, rng: random.Random,
                           p=LOWRES_P,
                           scale_range=LOWRES_SCALE_RANGE,
                           jpeg_p=LOWRES_JPEG_P,
                           jpeg_q_range=LOWRES_JPEG_QUALITY_RANGE):
    meta = {
        "lowres_applied": False,
        "lowres_scale_factor": 1.0,
        "lowres_jpeg_applied": False,
        "lowres_jpeg_quality": 0
    }
    if rng.random() > p:
        return canvas_rgba, meta

    w, h = canvas_rgba.size
    # Downscale then upscale to original size (pixelation)
    sf = rng.uniform(*scale_range)
    w2 = max(1, int(w * sf))
    h2 = max(1, int(h * sf))

    # Process RGB and alpha separately to preserve transparency shape
    rgb = canvas_rgba.convert("RGB")
    a   = canvas_rgba.getchannel("A")

    # Resize down (BOX/BILINEAR) then up (NEAREST) to accentuate low-res look
    rgb_small = rgb.resize((w2, h2), resample=Image.BILINEAR)
    rgb_pix   = rgb_small.resize((w, h), resample=Image.NEAREST)

    a_small = a.resize((w2, h2), resample=Image.BILINEAR)
    a_pix   = a_small.resize((w, h), resample=Image.NEAREST)

    # Optional JPEG roundtrip on RGB only
    jpeg_applied = False
    jpeg_q = 0
    if rng.random() < jpeg_p:
        q = int(rng.uniform(*jpeg_q_range))
        buf = BytesIO()
        rgb_pix.save(buf, format="JPEG", quality=q, optimize=True)
        buf.seek(0)
        rgb_pix = Image.open(buf).convert("RGB")
        jpeg_applied = True
        jpeg_q = q

    degraded = Image.merge("RGBA", (rgb_pix.split()[0], rgb_pix.split()[1], rgb_pix.split()[2], a_pix))

    meta.update({
        "lowres_applied": True,
        "lowres_scale_factor": round(float(sf), 4),
        "lowres_jpeg_applied": jpeg_applied,
        "lowres_jpeg_quality": int(jpeg_q)
    })
    return degraded, meta

# --- Whole-image gentle tone adjustments ---
def _adjust_gamma(img_rgb, gamma):
    inv = 1.0 / max(1e-6, gamma)
    lut = [int(pow(i / 255.0, inv) * 255.0 + 0.5) for i in range(256)]
    return img_rgb.point(lut * 3)

def apply_global_tone(rgb_img, rng: random.Random):
    meta = {
        "tone_applied": False,
        "tone_saturation": 1.0,
        "tone_brightness": 1.0,
        "tone_contrast":   1.0,
        "tone_gamma":      1.0
    }
    if rng.random() > TONE_ADJUST_P:
        return rgb_img, meta

    sat = 1.0; bri = 1.0; con = 1.0; gam = 1.0
    out = rgb_img
    if rng.random() < 0.8:
        sat = rng.uniform(*SAT_RANGE); out = ImageEnhance.Color(out).enhance(sat)
    if rng.random() < 0.8:
        bri = rng.uniform(*BRI_RANGE); out = ImageEnhance.Brightness(out).enhance(bri)
    if rng.random() < 0.8:
        con = rng.uniform(*CON_RANGE); out = ImageEnhance.Contrast(out).enhance(con)
    if rng.random() < 0.6:
        gam = rng.uniform(*GAMMA_RANGE); out = _adjust_gamma(out, gam)

    meta.update({
        "tone_applied": True,
        "tone_saturation": round(float(sat), 4),
        "tone_brightness": round(float(bri), 4),
        "tone_contrast":   round(float(con), 4),
        "tone_gamma":      round(float(gam), 4)
    })
    return out, meta

# === BOOTSTRAP ===
os.makedirs(output_folder, exist_ok=True)
os.makedirs(metadata_folder, exist_ok=True)

annotations_file = os.path.join(os.path.dirname(output_folder), "synthdog_en_annotations.json")
output_records = []
if os.path.exists(annotations_file):
    try:
        with open(annotations_file, 'r', encoding='utf-8') as f:
            output_records = json.load(f)
    except Exception:
        output_records = []

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

        # base image (possibly blurred)
        image_path = all_images[global_img_idx % total_images]
        global_img_idx += 1
        bg = Image.open(image_path).convert("RGBA")
        bg, bg_blurred, bg_blur_radius = random_bg_blur(bg, rng, BG_BLUR_PROB, BG_BLUR_RADIUS_RANGE)
        width, height = bg.size

        # pick paragraph
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

        # choose layout mode and text manipulations
        layout_mode = rng.choice(LAYOUT_MODES)

        # For drawing: apply intra-word spacing, then restructure
        paragraph_spaced = inject_intra_word_spaces(paragraph, rng)
        render_text = restructure_paragraph_for_coverage(paragraph_spaced, rng, mode=layout_mode)

        # For OCR: same restructure but WITHOUT intra-word spacing
        render_text_no_intra = restructure_paragraph_for_coverage(paragraph, rng, mode=layout_mode)

        # layout sizing & position
        scale = rng.uniform(0.5, 0.7)
        canvas_width  = max(32, int(width * scale))
        canvas_height = max(32, int(height * scale))
        x = rng.randint(0, max(0, width - canvas_width))
        y = rng.randint(0, max(0, height - canvas_height))

        canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        base_font_size = rng.randint(*FONT_SIZE_RANGE)
        font, font_name, font_path = get_random_font(font_dir, base_font_size, rng=rng)
        font_color = random_dark_font_color(rng)

        # wrap according to VISIBLE render_text (with intra-word spacing)
        max_text_width = canvas_width - 20
        lines = []
        for block in render_text.split("\n"):
            lines.extend(wrap_text_lines(block, font, max_text_width, draw))
        if INSERT_BLANKS:
            lines = insert_blank_lines_randomly(lines, rng, max_blanks=MAX_BLANKS)

        spacing = INITIAL_SPACING
        if not fits(lines, font, canvas_width, canvas_height, spacing):
            f2, lines2, sp2 = autofit_or_trim(render_text, font_path, base_font_size, draw,
                                              canvas_width, canvas_height, spacing=INITIAL_SPACING)
            font = f2
            lines = lines2
            spacing = sp2

        if AUTO_FILL_VERTICAL:
            spacing = auto_line_spacing_to_fill(lines, font, canvas_width, canvas_height)

        drawn_lines = list(lines)
        drawn_text = "\n".join(drawn_lines)

        # draw text
        draw.multiline_text((10, 10), drawn_text, font=font, fill=font_color, spacing=spacing)

        # perspective + grit
        canvas, persp_meta = random_perspective_canvas(canvas, rng, PERSPECTIVE_DISTORTION, PERSPECTIVE_P)
        canvas, grit_blur_r, grit_noise_sigma = add_canvas_grit(canvas, rng, CANVAS_BLUR_RANGE, CANVAS_NOISE_SIGMA)

        # skew + rotate
        source_canvas_size = [canvas_width, canvas_height]
        canvas, skew_magnitude = skew_canvas(canvas, rng, magnitude_range=(-0.15, 0.15))
        rotated_canvas, rotation_angle = rotate_canvas(canvas, rng, angle_range=(-10, 10))

        # NEW: low-res degradation on rotated text canvas (50/50)
        rotated_canvas, lowres_meta = degrade_canvas_quality(rotated_canvas, rng,
                                                             p=LOWRES_P,
                                                             scale_range=LOWRES_SCALE_RANGE,
                                                             jpeg_p=LOWRES_JPEG_P,
                                                             jpeg_q_range=LOWRES_JPEG_QUALITY_RANGE)

        # composite
        final_image = bg.copy()
        paste_x = max(0, min(x, width - rotated_canvas.width))
        paste_y = max(0, min(y, height - rotated_canvas.height))
        final_image.alpha_composite(rotated_canvas, (paste_x, paste_y))

        # Whole-image tone adjustments (sometimes)
        rgb = final_image.convert("RGB")
        rgb, tone_meta = apply_global_tone(rgb, rng)

        # save image
        image_filename = synthdog_id + ".jpg"
        out_img_path = os.path.join(output_folder, image_filename)
        rgb.save(out_img_path, quality=JPEG_QUALITY, subsampling=1, optimize=True)

        # Build OCR label WITHOUT intra-word spacing, preserving normal spaces
        lines_ocr = []
        draw_tmp = ImageDraw.Draw(Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0)))
        for block in render_text_no_intra.split("\n"):
            lines_ocr.extend(wrap_text_lines(block, font, max_text_width, draw_tmp))
        visible_ocr_lines = [ln for ln in lines_ocr if ln.strip() != ""]
        expected_ocr = re.sub(r"\s+", " ", " ".join(visible_ocr_lines)).strip()

        # per-sample JSON
        json_filename = synthdog_id + ".json"
        sample_meta = {
            "id": synthdog_id,
            "image": image_filename,
            "font": font_name,
            "font_size": font.size,
            "font_color_rgb": font_color,

            "text_source": paragraph,
            "text_after_spacing": paragraph_spaced,
            "layout_mode": layout_mode,

            "drawn_lines": drawn_lines,
            "drawn_text": drawn_text,
            "spacing": spacing,

            "expected_ocr": expected_ocr,

            "position": [paste_x, paste_y],
            "paste_bbox": [paste_x, paste_y, paste_x + rotated_canvas.width, paste_y + rotated_canvas.height],
            "source_canvas_size": source_canvas_size,
            "canvas_size": [rotated_canvas.width, rotated_canvas.height],
            "rotation_angle": rotation_angle,
            "skew_magnitude": skew_magnitude,
            "perspective_applied": persp_meta.get("perspective_applied", False),
            "perspective_distortion": persp_meta.get("perspective_distortion", 0.0),

            "bg_blurred": bg_blurred,
            "bg_blur_radius": bg_blur_radius,
            "canvas_grit_blur_radius": grit_blur_r,
            "canvas_grit_noise_sigma": grit_noise_sigma,

            "lowres_applied": lowres_meta["lowres_applied"],
            "lowres_scale_factor": lowres_meta["lowres_scale_factor"],
            "lowres_jpeg_applied": lowres_meta["lowres_jpeg_applied"],
            "lowres_jpeg_quality": lowres_meta["lowres_jpeg_quality"],

            "tone_applied": tone_meta["tone_applied"],
            "tone_saturation": tone_meta["tone_saturation"],
            "tone_brightness": tone_meta["tone_brightness"],
            "tone_contrast":   tone_meta["tone_contrast"],
            "tone_gamma":      tone_meta["tone_gamma"],
        }
        with open(os.path.join(metadata_folder, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(sample_meta, jf, indent=2, ensure_ascii=False)

        # SYNTHDOG META — relative path like your original
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
        print(f"[WARN] Fallback single-ellipsis for {synthdog_id}")
        canvas_width = 64
        canvas_height = 64
        image = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        font_files = [f for f in os.listdir(font_dir) if f.lower().endswith(".ttf")]
        font_path = os.path.join(font_dir, sorted(font_files)[0]) if font_files else None
        if font_path:
            font = ImageFont.truetype(font_path, MIN_FONT_SIZE)
        else:
            font = ImageFont.load_default()
        draw.text((10, 10), "…", fill=(0, 0, 0), font=font)

        image_filename = synthdog_id + ".jpg"
        out_img_path = os.path.join(output_folder, image_filename)
        rgb, tone_meta = apply_global_tone(image.convert("RGB"), random.Random())
        rgb.save(out_img_path, quality=JPEG_QUALITY, subsampling=1, optimize=True)

        json_filename = synthdog_id + ".json"
        sample_meta = {
            "id": synthdog_id,
            "image": image_filename,
            "font": Path(font_path).name if font_path else "default",
            "font_size": MIN_FONT_SIZE,
            "font_color_rgb": (0,0,0),
            "text_source": "",
            "text_after_spacing": "",
            "layout_mode": "fallback",
            "drawn_lines": ["…"],
            "drawn_text": "…",
            "spacing": MIN_SPACING,
            "expected_ocr": "…",
            "position": [10, 10],
            "paste_bbox": [0, 0, canvas_width, canvas_height],
            "source_canvas_size": [canvas_width, canvas_height],
            "canvas_size": [canvas_width, canvas_height],
            "rotation_angle": 0.0,
            "skew_magnitude": 0.0,
            "perspective_applied": False,
            "perspective_distortion": 0.0,
            "bg_blurred": False,
            "bg_blur_radius": 0.0,
            "canvas_grit_blur_radius": 0.0,
            "canvas_grit_noise_sigma": 0.0,
            "lowres_applied": False,
            "lowres_scale_factor": 1.0,
            "lowres_jpeg_applied": False,
            "lowres_jpeg_quality": 0,
            "tone_applied": tone_meta["tone_applied"],
            "tone_saturation": tone_meta["tone_saturation"],
            "tone_brightness": tone_meta["tone_brightness"],
            "tone_contrast":   tone_meta["tone_contrast"],
            "tone_gamma":      tone_meta["tone_gamma"],
        }
        with open(os.path.join(metadata_folder, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(sample_meta, jf, indent=2, ensure_ascii=False)

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
