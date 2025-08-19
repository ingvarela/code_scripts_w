"""
Pew-style infographic generator — COMPLETE (edge-to-edge charts)
- Only pie and horizontal bar charts (alternating for equal count)
- Skips datasets with too few categories (configurable)
- Document-first (plot -> transparent PNG -> composed canvas with text)
- Subtitle: italic + light grey
- "Key points" above or below the plot (never left/right)
- Yellow–Brown–Black palette
- CHART AREA STRETCHES FULL WIDTH OF CANVAS (no left/right padding)
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
# Update this to your datasets root
ROOT_FOLDER = "C://Users//svs26//Desktop//MS COCO 2017//UREADER//owid-datasets-master//owid-datasets-master//datasets"
OUTPUT_DIR = "ChartQAtest05"
MAX_ROWS = 300
N_IMAGES = 60  # total images (half pies, half bars)

# Alternate to ensure equal numbers: pie, bar, pie, bar, ...
STRATEGIES = ["pie_infographic", "horizontal_bar_infographic"]

# Typography / layout
FONT_FAMILY = "DejaVu Sans"
FONTS = {"title": 36, "subtitle": 20, "section": 16, "body": 14, "small": 12}

CANVAS_W, CANVAS_H = 600, 800
MARGIN, GUTTER, FOOTER_H = 64, 28, 110
TEXT_COLOR = (20, 20, 20)
SUBTITLE_COLOR = (120, 120, 120)  # lighter grey subtitle
BG_COLOR = (255, 255, 255)

# Place Key points above or below chart ("top" or "bottom")
BULLETS_POSITION = "bottom"

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

def _measure_text_h(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, width_px: int, lh_mult=1.12) -> int:
    if not text:
        return 0
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
    ascent, descent = font.getmetrics()
    return int((ascent + descent) * lh_mult) * len(lines)

def _draw_wrapped(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont,
                  box: Tuple[int, int, int, int], fill=(0,0,0), lh_mult=1.12, bullet=False) -> int:
    x0, y0, x1, _ = box
    width = x1 - x0
    if not text:
        return 0
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + (" " if cur else "") + w)
        if draw.textlength(t, font=font) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur); cur = w
            else:
                lines.append(w); cur = ""
    if cur:
        lines.append(cur)

    used = 0
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * lh_mult)
    for i, line in enumerate(lines):
        prefix = "• " if bullet and i == 0 else ("   " if bullet else "")
        draw.text((x0, y0 + used), prefix + line, font=font, fill=fill)
        used += line_h
    return used

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
        # Label the bars
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
    bullets: List[str] = field(default_factory=list)
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
            'section': _load_font(FONTS['section'], 'normal'),
            'body': _load_font(FONTS['body'], 'normal'),
            'small': _load_font(FONTS['small'], 'normal'),
        }

    def compose(self, chart_img: Image.Image, cfg: InfographicConfig, out_path: str) -> str:
        img = Image.new('RGB', (self.width, self.height), color=self.bg)
        draw = ImageDraw.Draw(img)

        # Text band uses horizontal margins; chart will be edge-to-edge
        x_left, x_right = self.margin, self.width - self.margin
        y = self.margin

        # Title
        if cfg.title:
            h = _measure_text_h(draw, cfg.title, self.fonts['title'], x_right - x_left)
            _draw_wrapped(draw, cfg.title, self.fonts['title'], (x_left, y, x_right, y + h), fill=self.text_color)
            y += h + self.gutter

        # Subtitle (lighter grey + italic)
        if cfg.subtitle:
            h = _measure_text_h(draw, cfg.subtitle, self.fonts['subtitle'], x_right - x_left)
            _draw_wrapped(draw, cfg.subtitle, self.fonts['subtitle'], (x_left, y, x_right, y + h), fill=SUBTITLE_COLOR)
            y += h + self.gutter

        footer_top = self.height - self.footer_h

        # Key points (top or bottom)
        pending_bullets = False
        if cfg.bullets:
            if BULLETS_POSITION.lower() == "top":
                y = self._draw_bullets(draw, cfg.bullets, x_left, x_right, y)
            else:
                pending_bullets = True

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
            new_h = chart_h_target  # we keep full width; pixel-aspect preserved by resizing height

        chart_img = chart_img.resize((max(1, new_w), max(1, new_h)), Image.Resampling.LANCZOS)

        paste_x = 0   # absolute left edge
        paste_y = chart_top
        img.paste(chart_img, (paste_x, paste_y), chart_img)

        # Key points at bottom (optional)
        if pending_bullets:
            y_block = chart_top + new_h + self.gutter
            _ = self._draw_bullets(draw, cfg.bullets, x_left, x_right, y_block)

        # Footer (note + source)
        foot_y = footer_top + int(self.gutter * 0.3)
        if cfg.note:
            nh = _draw_wrapped(draw, cfg.note, self.fonts['small'], (x_left, foot_y, x_right, foot_y + self.footer_h // 2), fill=self.text_color)
            foot_y += nh + int(self.gutter * 0.5)
        if cfg.source:
            src = f"Source: {cfg.source}"
            _draw_wrapped(draw, src, self.fonts['small'], (x_left, foot_y, x_right, foot_y + self.fonts['small'].size + 6), fill=self.text_color)

        ensure_dir_for(out_path)
        ensure_output_dir()
        img.save(out_path, format='PNG')
        return out_path

    def _draw_bullets(self, draw: ImageDraw.Draw, bullets: List[str], x_left: int, x_right: int, y_start: int) -> int:
        header = "Key points"
        hh = _measure_text_h(draw, header, self.fonts['section'], x_right - x_left)
        _draw_wrapped(draw, header, self.fonts['section'], (x_left, y_start, x_right, y_start + hh), fill=self.text_color)
        y_b = y_start + hh + int(self.gutter * 0.6)
        for b in bullets:
            if not b:
                continue
            bh = _measure_text_h(draw, b, self.fonts['body'], x_right - x_left)
            _draw_wrapped(draw, b, self.fonts['body'], (x_left, y_b, x_right, y_b + bh), fill=self.text_color, bullet=True)
            y_b += bh + int(self.gutter * 0.5)
        return y_b + self.gutter

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
    bullets: Optional[List[str]] = None,
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
        bullets=bullets or [],
        note=notes or "",
        source=source or "",
        logo_path=None,
    )
    image_path = comp.compose(chart_img, info, out_path)

    # OCR-ish manifest text
    ocr_rows = []
    if headline: ocr_rows.append(headline)
    if subhead: ocr_rows.append(subhead)
    if bullets:
        for b in bullets:
            ocr_rows.append("• " + b)
    if notes: ocr_rows.append(notes)
    if source: ocr_rows.append("Source: " + source)

    return {"image": image_path.replace("\\", "/"), "ocr": "\n".join(ocr_rows)}

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

        strategy = STRATEGIES[len(results) % len(STRATEGIES)]  # alternate pie/bar
        choice = choose_columns(df, strategy)
        if not choice:
            continue

        base = os.path.splitext(os.path.basename(csv_path))[0]
        out_path = os.path.join(OUTPUT_DIR, f"{base}_{len(results):05}.png")

        log(f"🎨 {len(results)+1}/{n} | {strategy} | File: {os.path.basename(csv_path)}")

        try:
            if strategy == "pie_infographic":
                item = render_infographic(
                    df, out_path, choice,
                    headline=f"{choice.label_col} Distribution",
                    subhead="Auto-generated pie infographic",
                    bullets=["Top categories displayed", "Remainder grouped as ‘Other’"],
                    notes=None,
                    source="AutoGen",
                )
            else:  # horizontal_bar_infographic
                item = render_infographic(
                    df, out_path, choice,
                    headline=f"{choice.label_col} (Top categories)",
                    subhead="Auto-generated horizontal bar infographic",
                    bullets=["Top values highlighted", "Sorted categories"],
                    notes=None,
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
