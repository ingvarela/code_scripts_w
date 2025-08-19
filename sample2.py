#!/usr/bin/env python3
"""
Pew-style infographic generator — COMPLETE
(edge-to-edge, no key-points, OCR in reading order, subtitle splitting)
- Only pie and horizontal bar charts (alternating for equal count)
- Reads title/description from datapackage.json (same folder as each CSV)
- Skips datasets with too few categories (configurable)
- Document-first (plot -> transparent PNG -> composed canvas with text)
- Subtitle: italic + light grey (smaller size)
- If subtitle > 5 lines, overflow is moved to the Notes section
- NO "Key points" section
- Yellow–Brown–Black palette
- CHART AREA STRETCHES FULL WIDTH OF CANVAS (no left/right padding)
- OCR text saved strictly in reading order: Title -> (up to 5 lines of Subtitle) -> Note (incl. overflow) -> Source
- Batch driver that saves outputs + metadata.json
"""

import os
import io
import gc
import json
import warnings
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

from PIL import Image, ImageDraw, ImageFont

# =================== CONFIG ===================
ROOT_FOLDER = "C://Users//svs26//Desktop//MS COCO 2017//UREADER//owid-datasets-master//owid-datasets-master//datasets"
OUTPUT_DIR = "ChartQA"
MAX_ROWS = 300
N_IMAGES = 20  # total images (half pies, half bars)

# Alternate to ensure equal numbers: pie, bar, pie, bar, ...
STRATEGIES = ["pie_infographic", "horizontal_bar_infographic"]

# Typography / layout
FONT_FAMILY = "DejaVu Sans"
FONTS = {"title": 36, "subtitle": 18, "section": 16, "body": 14, "small": 12}  # subtitle smaller now

CANVAS_W, CANVAS_H = 1800, 1200
MARGIN, GUTTER, FOOTER_H = 64, 28, 110
TEXT_COLOR = (20, 20, 20)
SUBTITLE_COLOR = (120, 120, 120)  # lighter grey subtitle
BG_COLOR = (255, 255, 255)

# Chart render size (portrait-like); actual paste is full-width scaling
CHART_PX = (600, 800)  # width, height (pre-render size; will be scaled to canvas width)

# Palette: Yellow–Brown–Black
PALETTE = ["#F2C200", "#7A4E2D", "#000000"]
PALETTE_LIGHT = ["#F7D95A", "#A36C49", "#444444"]  # for extra slices

# Pie tuning
MAX_PIE_CATEGORIES = 10
PIE_LABEL_MIN_ANGLE = 10
PIE_LABEL_MAX_SHOWN = 8
PIE_AUTOPCT_MIN = 8.0

# Minimum category thresholds (skip if not met)
MIN_PIE_SLICES = 3       # skip pies with < 3 non-zero categories
MIN_HBAR_BARS  = 3       # skip bars with < 3 categories

warnings.filterwarnings("ignore", category=UserWarning)

# =================== UTILS ===================
def log(msg: str):
    print(msg, flush=True)

def ensure_dir_for(path: str):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)

def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def find_csvs(root: str) -> List[str]:
    csvs = []
    for r, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".csv"):
                csvs.append(os.path.join(r, f))
    return csvs

def safe_read_csv(path: str, max_rows: int) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path, low_memory=False)
        if df.empty:
            return None
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty:
            return None
        if len(df) > max_rows:
            df = df.sample(n=max_rows, random_state=42).sort_index()
        return df
    except Exception as e:
        log(f"⚠️ Failed reading CSV: {path} | {e}")
        return None

def datapackage_meta_for(csv_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Look for datapackage.json in the SAME folder as the CSV.
    Returns (title, description) or (None, None) if not available.
    """
    try:
        folder = os.path.dirname(csv_path)
        dp_path = os.path.join(folder, "datapackage.json")
        if os.path.exists(dp_path):
            with open(dp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            title = data.get("title") or data.get("name") or None
            description = data.get("description") or None
            # Normalize empty strings to None
            if isinstance(title, str) and not title.strip():
                title = None
            if isinstance(description, str) and not description.strip():
                description = None
            return title, description
    except Exception as e:
        log(f"⚠️ datapackage.json read error for {csv_path}: {e}")
    return None, None

# =================== FONTS & TEXT ===================
_FONT_CACHE: Dict[Tuple[int,str], ImageFont.FreeTypeFont] = {}

def _load_font(size: int, style: str = "normal") -> ImageFont.FreeTypeFont:
    key = (size, style)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    try:
        from matplotlib import font_manager
        query = f"{FONT_FAMILY}:style={style}"
        path = font_manager.findfont(query, fallback_to_default=True)
        ft = ImageFont.truetype(path, size=size)
    except Exception:
        ft = ImageFont.load_default()
    _FONT_CACHE[key] = ft
    return ft

def _wrap_lines(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, width_px: int) -> List[str]:
    """Return wrapped lines as actually drawn (for OCR order)."""
    if not text:
        return []
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + (" " if cur else "") + w)
        if draw.textlength(t, font=font) <= width_px:
            cur = t
        else:
            if cur:
                lines.append(cur); cur = w
            else:
                lines.append(w); cur = ""
    if cur:
        lines.append(cur)
    return lines

def _measure_text_h(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, width_px: int, lh_mult=1.12) -> int:
    lines = _wrap_lines(draw, text, font, width_px)
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * lh_mult)
    return line_h * len(lines)

def _draw_wrapped(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont,
                  box: Tuple[int, int, int, int], fill=(0,0,0), lh_mult=1.12) -> List[str]:
    """Draw text with wrapping; return the list of lines drawn (for OCR order)."""
    x0, y0, x1, _ = box
    width = x1 - x0
    lines = _wrap_lines(draw, text, font, width)
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * lh_mult)
    for i, line in enumerate(lines):
        draw.text((x0, y0 + i*line_h), line, font=font, fill=fill)
    return lines

def _draw_lines(draw: ImageDraw.Draw, lines: List[str], font: ImageFont.FreeTypeFont,
                start_xy: Tuple[int,int], fill=(0,0,0), lh_mult=1.12) -> int:
    """Draw pre-wrapped lines (no re-wrapping). Returns total pixel height used."""
    x, y = start_xy
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * lh_mult)
    for i, line in enumerate(lines):
        draw.text((x, y + i*line_h), line, font=font, fill=fill)
    return line_h * len(lines)

# =================== CHART RENDERERS ===================
@dataclass
class ChartConfig:
    chart_type: str  # 'pie' | 'hbar'
    mapping: Dict[str, str]
    size_px: Tuple[int, int] = CHART_PX

def _aggregate_for_pie(df: pd.DataFrame, m: Dict[str, str]) -> pd.Series:
    labels = df[m['label']].astype(str)
    values = pd.to_numeric(df[m['value']], errors='coerce').fillna(0.0)
    if values.sum() == 0 or values.nunique() <= 1:
        counts = labels.value_counts()
    else:
        counts = values.groupby(labels).sum()
    counts = counts.sort_values(ascending=False)
    if len(counts) > MAX_PIE_CATEGORIES:
        top = counts.iloc[:MAX_PIE_CATEGORIES - 1]
        other = counts.iloc[MAX_PIE_CATEGORIES - 1:].sum()
        counts = pd.concat([top, pd.Series({'Other': other})])
    counts = counts[counts > 0]  # remove zeros
    return counts

def _aggregate_for_hbar(df: pd.DataFrame, m: Dict[str, str]) -> pd.Series:
    labels = df[m['label']].astype(str)
    values = pd.to_numeric(df[m['value']], errors='coerce') if m['value'] in df.columns else None
    if values is not None and values.notna().any():
        s = values.groupby(labels).sum()
    else:
        s = labels.value_counts()
    s = s[s > 0].sort_values(ascending=True).tail(12)  # keep up to 12
    return s

def _render_chart_png(df: pd.DataFrame, ccfg: ChartConfig) -> Optional[Image.Image]:
    """Returns chart image or None if not enough categories (thresholds)."""
    w_in, h_in = ccfg.size_px[0] / 100.0, ccfg.size_px[1] / 100.0
    dpi = 100
    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=dpi)
    ax.grid(True, axis='y', linewidth=0.6, alpha=0.25)

    m, ct = ccfg.mapping, ccfg.chart_type

    if ct == 'pie':
        counts = _aggregate_for_pie(df, m)
        if counts.index.nunique() < MIN_PIE_SLICES:
            plt.close(fig)
            return None

        pcts = counts / max(counts.sum(), 1) * 100
        min_angle = (pcts.min() / 100.0) * 360.0 if len(pcts) else 360.0
        radial = (len(pcts) <= PIE_LABEL_MAX_SHOWN) and (min_angle >= PIE_LABEL_MIN_ANGLE)
        autopct = (lambda pct: f"{pct:.1f}%" if pct >= PIE_AUTOPCT_MIN else "")
        colors = (PALETTE + PALETTE_LIGHT)[:len(counts)]

        if radial:
            ax.pie(counts.values, labels=counts.index.tolist(), autopct=autopct,
                   startangle=90, counterclock=False, colors=colors)
        else:
            ax.pie(counts.values, labels=None, autopct=autopct, pctdistance=0.7,
                   startangle=90, counterclock=False, colors=colors)
            circle = plt.Circle((0, 0), 0.55, color='white')
            ax.add_artist(circle)
        ax.axis('equal')

    elif ct == 'hbar':
        s = _aggregate_for_hbar(df, m)
        if s.index.nunique() < MIN_HBAR_BARS:
            plt.close(fig)
            return None

        bars = ax.barh(s.index.astype(str), s.values, color=PALETTE[0])
        for rect in bars:
            w = rect.get_width()
            ax.text(w, rect.get_y() + rect.get_height()/2, f" {int(w)}",
                    va='center', ha='left', color=PALETTE[2], fontsize=10)

        for spine in ['top','right']:
            ax.spines[spine].set_visible(False)
        ax.set_xlabel('Value')

    else:
        plt.close(fig)
        raise ValueError(f"Unsupported chart_type: {ct}")

    plt.tight_layout(pad=0.2)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert('RGBA')

# =================== CANVAS COMPOSITION ===================
@dataclass
class InfographicConfig:
    title: str = ""
    subtitle: str = ""
    note: str = ""
    source: str = ""
    logo_path: Optional[str] = None

class InfographicComposer:
    def __init__(self, width=CANVAS_W, height=CANVAS_H):
        self.width, self.height = width, height
        self.bg, self.text_color = BG_COLOR, TEXT_COLOR
        self.margin, self.gutter, self.footer_h = MARGIN, GUTTER, FOOTER_H
        self.fonts = {
            'title': _load_font(FONTS['title'], 'normal'),
            'subtitle': _load_font(FONTS['subtitle'], 'italic'),
            'small': _load_font(FONTS['small'], 'normal'),
        }

    def compose(self, chart_img: Image.Image, cfg: InfographicConfig, out_path: str) -> Tuple[str, List[str]]:
        """
        Draws the document and returns (out_path, ocr_lines).
        ocr_lines is a list of strings in the exact reading order left->right, top->bottom.
        """
        img = Image.new('RGB', (self.width, self.height), color=self.bg)
        draw = ImageDraw.Draw(img)

        # Text band uses horizontal margins; chart is edge-to-edge
        x_left, x_right = self.margin, self.width - self.margin
        y = self.margin

        ocr_lines: List[str] = []

        # Title
        if cfg.title:
            title_lines = _draw_wrapped(draw, cfg.title, self.fonts['title'], (x_left, y, x_right, y), fill=self.text_color)
            ocr_lines.extend(title_lines)
            h = _measure_text_h(draw, cfg.title, self.fonts['title'], x_right - x_left)
            y += h + self.gutter

        # Subtitle (lighter grey + italic) with overflow -> Notes
        overflow_to_notes = ""
        if cfg.subtitle:
            # Pre-wrap to know true number of lines
            pre_lines = _wrap_lines(draw, cfg.subtitle, self.fonts['subtitle'], x_right - x_left)
            if len(pre_lines) > 5:
                # Draw first 5 lines as subtitle
                used_h = _draw_lines(draw, pre_lines[:5], self.fonts['subtitle'], (x_left, y), fill=SUBTITLE_COLOR)
                ocr_lines.extend(pre_lines[:5])
                y += used_h + self.gutter
                # Collect overflow for notes (preserve words order)
                overflow_to_notes = " ".join(pre_lines[5:])
            else:
                sub_lines = _draw_wrapped(draw, cfg.subtitle, self.fonts['subtitle'], (x_left, y, x_right, y), fill=SUBTITLE_COLOR)
                ocr_lines.extend(sub_lines)
                h = _measure_text_h(draw, cfg.subtitle, self.fonts['subtitle'], x_right - x_left)
                y += h + self.gutter

        footer_top = self.height - self.footer_h

        # ---- CHART: EDGE-TO-EDGE FULL WIDTH (no left/right padding) ----
        chart_top = y
        chart_w_target = self.width                      # full canvas width
        chart_h_target = footer_top - chart_top - self.gutter

        cw, ch = chart_img.width, chart_img.height
        # Fit to full width first
        ratio_w = chart_w_target / max(cw, 1)
        new_w = chart_w_target
        new_h = int(ch * ratio_w)

        # If too tall for remaining height, cap by height (maintain width = full)
        if new_h > chart_h_target:
            new_h = chart_h_target

        chart_img = chart_img.resize((max(1, new_w), max(1, new_h)), Image.Resampling.LANCZOS)

        paste_x = 0   # absolute left edge
        paste_y = chart_top
        img.paste(chart_img, (paste_x, paste_y), chart_img)

        # Footer (Note + Source), with subtitle overflow appended to Note
        foot_y = footer_top + int(self.gutter * 0.3)

        note_text = cfg.note.strip()
        if overflow_to_notes:
            note_text = (note_text + ("\n" if note_text else "") + overflow_to_notes).strip()

        if note_text:
            note_lines = _draw_wrapped(draw, note_text, self.fonts['small'], (x_left, foot_y, x_right, foot_y), fill=self.text_color)
            ocr_lines.extend(note_lines)
            nh = _measure_text_h(draw, note_text, self.fonts['small'], x_right - x_left)
            foot_y += nh + int(self.gutter * 0.5)

        if cfg.source:
            src = f"Source: {cfg.source}"
            src_lines = _draw_wrapped(draw, src, self.fonts['small'], (x_left, foot_y, x_right, foot_y), fill=self.text_color)
            ocr_lines.extend(src_lines)

        ensure_dir_for(out_path)
        ensure_output_dir()
        img.save(out_path, format='PNG')
        return out_path, ocr_lines

# =================== HIGH-LEVEL RENDER ===================
@dataclass
class ChartChoice:
    chart_type: str  # 'pie' or 'hbar'
    label_col: str
    value_col: Optional[str] = None  # numeric column (optional)

def choose_columns(df: pd.DataFrame, strategy: str) -> Optional[ChartChoice]:
    # Pick one categorical-like column for labels; pick one numeric for values if available
    categorical = df.select_dtypes(exclude=[np.number]).columns.tolist()
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()

    label = categorical[0] if categorical else (df.columns[0] if len(df.columns) else None)
    if label is None:
        return None

    value = numeric[0] if numeric else None
    if strategy == "pie_infographic":
        return ChartChoice("pie", label, value)
    if strategy == "horizontal_bar_infographic":
        return ChartChoice("hbar", label, value)
    return None

def render_infographic(
    df: pd.DataFrame,
    out_path: str,
    choice: ChartChoice,
    headline: Optional[str] = None,
    subhead: Optional[str] = None,
    notes: Optional[str] = None,
    source: Optional[str] = None,
) -> Optional[dict]:
    # Chart to PNG (returns None if below thresholds)
    mapping = {'label': choice.label_col, 'value': choice.value_col or choice.label_col}
    cc = ChartConfig(chart_type=choice.chart_type, mapping=mapping)
    chart_img = _render_chart_png(df, cc)
    if chart_img is None:
        return None  # skip this dataset

    # Compose document
    comp = InfographicComposer(CANVAS_W, CANVAS_H)
    info = InfographicConfig(
        title=headline or "",
        subtitle=subhead or "",
        note=notes or "",
        source=source or "",
        logo_path=None,
    )
    image_path, ocr_lines = comp.compose(chart_img, info, out_path)

    # OCR: exact reading order
    return {"image": image_path.replace("\\", "/"), "ocr": "\n".join(ocr_lines)}

# =================== BATCH DRIVER ===================
def generate_images(n: int = N_IMAGES, manifest_path: str = os.path.join(OUTPUT_DIR, "metadata.json")):
    ensure_output_dir()
    ensure_dir_for(manifest_path)
    csvs = find_csvs(ROOT_FOLDER)
    if not csvs:
        log("⚠️ No CSV files found.")
        return

    results = []
    idx_global = 0
    log(f"🚀 Generating {n} images from {len(csvs)} CSVs...\n")

    # Iterate CSVs and alternate strategies (pie/bar) for an even split
    # Skip datasets that don't meet min-category thresholds
    while len(results) < n and idx_global < n * 40:
        csv_path = csvs[idx_global % len(csvs)]
        idx_global += 1

        df = safe_read_csv(csv_path, MAX_ROWS)
        if df is None or df.empty:
            continue

        # Pull metadata for title/subtitle from datapackage.json (same folder as CSV)
        meta_title, meta_desc = datapackage_meta_for(csv_path)

        strategy = STRATEGIES[len(results) % len(STRATEGIES)]  # alternate pie/bar
        choice = choose_columns(df, strategy)
        if not choice:
            continue

        base = os.path.splitext(os.path.basename(csv_path))[0]
        out_path = os.path.join(OUTPUT_DIR, f"{base}_{len(results):05}.png")

        # Fallbacks if datapackage metadata not present
        fallback_headline = f"{choice.label_col} Distribution" if strategy == "pie_infographic" else f"{choice.label_col} (Top categories)"
        fallback_subhead = "Auto-generated pie infographic" if strategy == "pie_infographic" else "Auto-generated horizontal bar infographic"
        headline = meta_title or fallback_headline
        subhead = meta_desc or fallback_subhead

        log(f"🎨 {len(results)+1}/{n} | {strategy} | File: {os.path.basename(csv_path)}")

        try:
            item = render_infographic(
                df, out_path, choice,
                headline=headline,
                subhead=subhead,
                notes=None,           # composer will add subtitle overflow here
                source="AutoGen",
            )
            if item is None:
                log("↪️  Skipped (too few categories for this chart).")
                continue

            results.append(item)

        except Exception as e:
            log(f"⚠️ Generation error for {csv_path}: {e}")
            gc.collect()
            continue

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log(f"\n✅ Done! {len(results)} images generated.")
    log(f"📁 Manifest saved to: {manifest_path}")

# =================== MAIN ===================
if __name__ == "__main__":
    generate_images()