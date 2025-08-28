#!/usr/bin/env python3
"""
DVQA — Pew-style bars with footer legend fallback for long labels
-----------------------------------------------------------------
- Toggle:
    USE_CANVAS = False  -> save pure Matplotlib figures (title via ax.set_title)
    USE_CANVAS = True   -> compose on a PIL "document" canvas (Title + Chart + optional footer legend)
- Single-series & grouped bars, vertical & horizontal (alternating)
- Color pools: tab20, tab20b, tab20c, Set3, plus HSV wheel (many distinct hues)
- Random background per image (figure facecolor if Matplotlib-only)
- Random bar thickness & random number of bars (subset of categories)
- Legends:
    * Single-series -> legend = categories (axis category labels hidden)
    * Grouped -> legend = series names (axis category labels shown for H, compact for V)
    * If ANY legend label > 3 words -> legend moved to footer:
        - Canvas mode: drawn under the image with colored squares
        - Matplotlib-only: drawn below the axes (outside plot)
- Uses datapackage.json "title" when found
- ASCII sanitization for all text
"""

import os
import io
import gc
import json
import warnings
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from PIL import Image, ImageDraw, ImageFont  # used only if USE_CANVAS=True
import unicodedata
import random
import colorsys

# =================== CONFIG ===================
ROOT_FOLDER = "C://Users//svs26//Desktop//MS COCO 2017//UREADER//owid-datasets-master//owid-datasets-master//datasets"
OUTPUT_DIR = "ChartQA_DVQA"
MAX_ROWS = 300
N_IMAGES = 20

# Toggle: Matplotlib-only vs PIL canvas
USE_CANVAS = False   # False = only Matplotlib figure is saved. True = compose canvas.

# Canvas (if USE_CANVAS=True)
CANVAS_W, CANVAS_H = 600, 900
MARGIN, GUTTER = 28, 16
RESERVED_BOTTOM = 20
CHART_PX = (300, 400)
CHART_SIDE_PAD = 12

# Typography
FONT_FAMILY = "DejaVu Sans"
FONTS = {"title": 28, "small": 12}
TEXT_COLOR_LIGHT = (20, 20, 20)
TEXT_COLOR_DARK = (245, 245, 245)

# Randomization knobs
RANDOM_SEED = None
MIN_BARS = 3
MAX_BARS = 10
H_BAR_HEIGHT_RANGE = (0.55, 0.95)
V_BAR_WIDTH_RANGE  = (0.55, 0.95)
BAR_ORIENTATIONS = ["v", "h"]  # start vertical like examples
SCAN_MULTIPLIER = 200

# Backgrounds (light & dark choices)
BACKGROUND_POOL = [
    "#FFFFFF", "#FAFAFA", "#F7F7F7", "#F4F4F4", "#FFF8E1", "#F1F6FF",  # light
    "#111111", "#1A1A1A", "#202124"  # dark
]

warnings.filterwarnings("ignore", category=UserWarning)

# =================== UTILS ===================
def log(msg: str):
    print(msg, flush=True)

def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def ensure_dir_for(path: str):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)

def find_csvs(root: str) -> List[str]:
    out = []
    for r, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".csv"):
                out.append(os.path.join(r, f))
    return out

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
    except Exception:
        return None

def datapackage_meta_for(csv_path: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        folder = os.path.dirname(csv_path)
        dp_path = os.path.join(folder, "datapackage.json")
        if os.path.exists(dp_path):
            with open(dp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            title = data.get("title") or data.get("name") or None
            desc = data.get("description") or None
            if isinstance(title, str) and not title.strip():
                title = None
            if isinstance(desc, str) and not desc.strip():
                desc = None
            return title, desc
    except Exception:
        pass
    return None, None

# ASCII sanitizer
def ascii_only(s) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    return s.encode("ascii", "ignore").decode("ascii").strip()

# =================== TEXT/WRAP HELPERS (canvas only) ===================
_FONT_CACHE: Dict[Tuple[int,str], ImageFont.FreeTypeFont] = {}

def _load_font(size: int, style: str = "normal") -> ImageFont.FreeTypeFont:
    key = (size, style)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    try:
        from matplotlib import font_manager
        path = font_manager.findfont(f"{FONT_FAMILY}:style={style}", fallback_to_default=True)
        ft = ImageFont.truetype(path, size=size)
    except Exception:
        ft = ImageFont.load_default()
    _FONT_CACHE[key] = ft
    return ft

def _wrap_lines(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, width_px: int) -> List[str]:
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
                  box: Tuple[int,int,int,int], fill=(0,0,0), lh_mult=1.12) -> List[str]:
    x0, y0, x1, _ = box
    lines = _wrap_lines(draw, text, font, x1 - x0)
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * lh_mult)
    for i, line in enumerate(lines):
        draw.text((x0, y0 + i*line_h), line, font=font, fill=fill)
    return lines

# =================== COLORS ===================
def _hex_to_rgb(hexstr: str) -> Tuple[int,int,int]:
    hexstr = hexstr.lstrip("#")
    return tuple(int(hexstr[i:i+2], 16) for i in (0, 2, 4))

def _rgb_to_hex(rgb: Tuple[int,int,int]) -> str:
    return "#%02x%02x%02x" % rgb

def _tab_cmap(name: str, n: int) -> List[str]:
    base = plt.get_cmap(name).colors
    cols = [ "#%02x%02x%02x" % (int(r*255), int(g*255), int(b*255)) for (r,g,b) in base ]
    out = []
    while len(out) < n:
        out.extend(cols)
    return out[:n]

def _hsv_wheel(n: int, s: float = 0.6, v: float = 0.95) -> List[str]:
    hues = np.linspace(0, 1, n, endpoint=False)
    out = []
    for h in hues:
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        out.append("#%02x%02x%02x" % (int(r*255), int(g*255), int(b*255)))
    return out

def many_colors(n: int) -> List[str]:
    if n <= 0:
        return []
    pools = []
    pools += _tab_cmap("tab20", min(n, 20))
    pools += _tab_cmap("tab20b", min(n, 20))
    pools += _tab_cmap("tab20c", min(n, 20))
    try:
        pools += _tab_cmap("Set3", min(n, 12))
    except Exception:
        pass
    if n > len(pools):
        pools += _hsv_wheel(n - len(pools), s=0.65, v=0.95)
    random.shuffle(pools)
    return pools[:n]

def choose_background() -> Tuple[Tuple[int,int,int], bool, str]:
    """Return (bg_rgb, is_dark, axis_color_hex)."""
    bg_hex = random.choice(BACKGROUND_POOL)
    r, g, b = _hex_to_rgb(bg_hex)
    lum = 0.2126*r + 0.7152*g + 0.0722*b
    is_dark = lum < 128
    axis = "#FFFFFF" if is_dark else "#000000"
    return (r, g, b), is_dark, axis

# =================== DATA SHAPING ===================
def ascii_series(s: pd.Series) -> pd.Series:
    return s.astype(str).map(ascii_only)

def numeric_series(df: pd.DataFrame) -> List[str]:
    return df.select_dtypes(include=[np.number]).columns.tolist()

def nonnumeric_series(df: pd.DataFrame) -> List[str]:
    return df.select_dtypes(exclude=[np.number]).columns.tolist()

def pick_bars_subset(s: pd.Series) -> pd.Series:
    if len(s) < MIN_BARS:
        return pd.Series(dtype=float)
    k = random.randint(MIN_BARS, min(MAX_BARS, len(s)))
    return s.sort_values(ascending=False).iloc[:k]

# =================== LEGEND POLICY ===================
def needs_footer_legend(labels: List[str]) -> bool:
    """If ANY label has > 3 words → move legend to footer."""
    for lab in labels:
        if len(str(lab).split()) > 3:
            return True
    return False

# =================== RENDER (MATPLOTLIB) ===================
def render_single_hbar(categories: List[str], values: List[float],
                       fg_colors: List[str], axis_color: str, title: str,
                       fig_facecolor: Tuple[int,int,int],
                       force_footer_legend: bool) -> Tuple[Image.Image, List[Tuple[str,str]]]:
    w_in, h_in, dpi = CHART_PX[0]/100.0, CHART_PX[1]/100.0, 100
    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=dpi)
    fig.patch.set_facecolor(np.array(fig_facecolor)/255.0)
    ax.grid(True, axis='y', linewidth=0.6, alpha=0.25, color=axis_color)

    heights = np.clip(np.random.uniform(*H_BAR_HEIGHT_RANGE, size=len(values)), 0.2, 0.98)
    y = np.arange(len(values))
    bars = ax.barh(y, values, color=fg_colors, height=heights)

    ax.set_yticks(y); ax.set_yticklabels([""]*len(values))
    for rect, v in zip(bars, values):
        ax.text(rect.get_width(), rect.get_y()+rect.get_height()/2, f" {int(v)}",
                va='center', ha='left', color=axis_color, fontsize=9)

    for spine in ['top','right']:
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color(axis_color)
    ax.spines['bottom'].set_color(axis_color)
    ax.tick_params(axis='both', colors=axis_color, labelsize=9)
    ax.set_xlabel('Value', fontsize=9, color=axis_color)

    legend_pairs = list(zip(categories, fg_colors))

    if not force_footer_legend:
        handles = [Patch(facecolor=fg_colors[i], edgecolor='white', label=categories[i])
                   for i in range(len(categories))]
        ax.legend(handles=handles, loc='center left', bbox_to_anchor=(1.02, 0.5),
                  frameon=False, fontsize=8, borderaxespad=0.0, labelcolor=axis_color)
    else:
        # Put legend under axes area (bottom) if we are not using a canvas
        if not USE_CANVAS:
            handles = [Patch(facecolor=c, edgecolor='white', label=l) for l, c in legend_pairs]
            plt.subplots_adjust(bottom=0.28)  # room for footer legend
            leg = ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.18),
                            ncol=1, frameon=False, fontsize=8)
            for text in leg.get_texts():
                text.set_color(axis_color)

    if not USE_CANVAS and title:
        ax.set_title(title, fontsize=12, color=axis_color, pad=10)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig); buf.seek(0)
    return Image.open(buf).convert('RGBA'), legend_pairs

def render_single_vbar(categories: List[str], values: List[float],
                       fg_colors: List[str], axis_color: str, title: str,
                       fig_facecolor: Tuple[int,int,int],
                       force_footer_legend: bool) -> Tuple[Image.Image, List[Tuple[str,str]]]:
    w_in, h_in, dpi = CHART_PX[0]/100.0, CHART_PX[1]/100.0, 100
    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=dpi)
    fig.patch.set_facecolor(np.array(fig_facecolor)/255.0)
    ax.grid(True, axis='y', linewidth=0.6, alpha=0.25, color=axis_color)

    widths = np.clip(np.random.uniform(*V_BAR_WIDTH_RANGE, size=len(values)), 0.2, 0.98)
    x = np.arange(len(values))
    bars = ax.bar(x, values, color=fg_colors, width=widths)

    ax.set_xticks(x); ax.set_xticklabels([""]*len(values))
    ax.tick_params(axis='y', colors=axis_color, labelsize=9)
    ax.set_ylabel('Value', fontsize=9, color=axis_color)

    for rect, v in zip(bars, values):
        ax.text(rect.get_x()+rect.get_width()/2, rect.get_height(), f"{int(v)}",
                ha='center', va='bottom', color=axis_color, fontsize=8)

    for spine in ['top','right']:
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color(axis_color)
    ax.spines['bottom'].set_color(axis_color)

    legend_pairs = list(zip(categories, fg_colors))

    if not force_footer_legend:
        handles = [Patch(facecolor=fg_colors[i], edgecolor='white', label=categories[i])
                   for i in range(len(categories))]
        ax.legend(handles=handles, loc='center left', bbox_to_anchor=(1.02, 0.5),
                  frameon=False, fontsize=8, borderaxespad=0.0, labelcolor=axis_color)
    else:
        if not USE_CANVAS:
            handles = [Patch(facecolor=c, edgecolor='white', label=l) for l, c in legend_pairs]
            plt.subplots_adjust(bottom=0.28)
            leg = ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.18),
                            ncol=1, frameon=False, fontsize=8)
            for text in leg.get_texts():
                text.set_color(axis_color)

    if not USE_CANVAS and title:
        ax.set_title(title, fontsize=12, color=axis_color, pad=10)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig); buf.seek(0)
    return Image.open(buf).convert('RGBA'), legend_pairs

def render_grouped_vbar(cat_labels: List[str], series_names: List[str],
                        matrix_values: np.ndarray, axis_color: str, title: str,
                        fig_facecolor: Tuple[int,int,int],
                        force_footer_legend: bool) -> Tuple[Image.Image, List[Tuple[str,str]]]:
    n_cat, n_ser = matrix_values.shape
    colors = many_colors(n_ser)

    w_in, h_in, dpi = CHART_PX[0]/100.0, CHART_PX[1]/100.0, 100
    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=dpi)
    fig.patch.set_facecolor(np.array(fig_facecolor)/255.0)
    ax.grid(True, axis='y', linewidth=0.6, alpha=0.25, color=axis_color)

    x = np.arange(n_cat)
    width = max(0.2, min(0.9, 0.8 / n_ser))
    for i in range(n_ser):
        ax.bar(x + (i - (n_ser-1)/2)*width, matrix_values[:, i],
               width=width, label=series_names[i], color=colors[i])

    ax.set_xticks(x)
    ax.set_xticklabels([lbl if len(lbl)<=8 else lbl[:8] for lbl in cat_labels],
                       rotation=35, ha='right', color=axis_color, fontsize=8)
    ax.tick_params(axis='y', colors=axis_color, labelsize=9)
    ax.set_ylabel('Value', fontsize=9, color=axis_color)

    for spine in ['top','right']:
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color(axis_color)
    ax.spines['bottom'].set_color(axis_color)

    legend_pairs = list(zip(series_names, colors))

    if not force_footer_legend:
        leg = ax.legend(title="categories", loc='best', frameon=True, fontsize=8)
        plt.setp(leg.get_title(), color=axis_color)
        for text in leg.get_texts():
            text.set_color(axis_color)
    else:
        if not USE_CANVAS:
            handles = [Patch(facecolor=c, edgecolor='white', label=l) for l, c in legend_pairs]
            plt.subplots_adjust(bottom=0.28)
            leg = ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.18),
                            ncol=1, frameon=False, fontsize=8)
            for text in leg.get_texts():
                text.set_color(axis_color)

    if not USE_CANVAS and title:
        ax.set_title(title, fontsize=12, color=axis_color, pad=10)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig); buf.seek(0)
    return Image.open(buf).convert('RGBA'), legend_pairs

def render_grouped_hbar(cat_labels: List[str], series_names: List[str],
                        matrix_values: np.ndarray, axis_color: str, title: str,
                        fig_facecolor: Tuple[int,int,int],
                        force_footer_legend: bool) -> Tuple[Image.Image, List[Tuple[str,str]]]:
    n_cat, n_ser = matrix_values.shape
    colors = many_colors(n_ser)

    w_in, h_in, dpi = CHART_PX[0]/100.0, CHART_PX[1]/100.0, 100
    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=dpi)
    fig.patch.set_facecolor(np.array(fig_facecolor)/255.0)
    ax.grid(True, axis='x', linewidth=0.6, alpha=0.25, color=axis_color)

    y = np.arange(n_cat)
    height = max(0.2, min(0.9, 0.8 / n_ser))
    for i in range(n_ser):
        ax.barh(y + (i - (n_ser-1)/2)*height, matrix_values[:, i],
                height=height, label=series_names[i], color=colors[i])

    ax.set_yticks(y)
    ax.set_yticklabels(cat_labels, color=axis_color, fontsize=9)
    ax.tick_params(axis='x', colors=axis_color, labelsize=9)
    ax.set_xlabel('Value', fontsize=9, color=axis_color)

    for spine in ['top','right']:
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color(axis_color)
    ax.spines['bottom'].set_color(axis_color)

    legend_pairs = list(zip(series_names, colors))

    if not force_footer_legend:
        leg = ax.legend(title="categories", loc='upper center', bbox_to_anchor=(0.5, -0.12),
                        ncol=min(3, n_ser), frameon=True, fontsize=8)
        plt.setp(leg.get_title(), color=axis_color)
        for text in leg.get_texts():
            text.set_color(axis_color)
    else:
        if not USE_CANVAS:
            handles = [Patch(facecolor=c, edgecolor='white', label=l) for l, c in legend_pairs]
            plt.subplots_adjust(bottom=0.28)
            leg = ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.18),
                            ncol=1, frameon=False, fontsize=8)
            for text in leg.get_texts():
                text.set_color(axis_color)

    if not USE_CANVAS and title:
        ax.set_title(title, fontsize=12, color=axis_color, pad=10)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig); buf.seek(0)
    return Image.open(buf).convert('RGBA'), legend_pairs

# =================== CANVAS (OPTIONAL) ===================
@dataclass
class InfographicConfig:
    title: str = ""

class InfographicComposer:
    def __init__(self, width=CANVAS_W, height=CANVAS_H, bg_rgb=(255,255,255), axis_is_dark=False):
        self.width, self.height = width, height
        self.bg = bg_rgb
        self.axis_is_dark = axis_is_dark
        self.text_color = TEXT_COLOR_DARK if axis_is_dark else TEXT_COLOR_LIGHT
        self.margin, self.gutter = MARGIN, GUTTER
        self.fonts = {
            'title': _load_font(FONTS['title'], 'normal'),
            'small': _load_font(FONTS['small'], 'normal'),
        }

    def _draw_footer_legend(self, draw: ImageDraw.Draw, legend_pairs: List[Tuple[str,str]],
                            x_left: int, y_top: int, x_right: int) -> int:
        """Draw colored squares + labels as footer legend. Returns height used."""
        if not legend_pairs:
            return 0
        x, y = x_left, y_top
        line_h = int(FONTS['small'] * 1.3)
        square = line_h - 4
        max_w = x_right - x_left
        for label, color in legend_pairs:
            # one item per line for simplicity/fit
            draw.rectangle([x, y, x + square, y + square], fill=color, outline=None)
            draw.text((x + square + 8, y), label, font=self.fonts['small'], fill=self.text_color)
            y += line_h
            if y > (y_top + 300):  # safety cap
                break
        return y - y_top

    def compose(self, chart_img: Image.Image, cfg: InfographicConfig,
                out_path: str, footer_legend: List[Tuple[str,str]] = None) -> Tuple[str, List[str]]:
        img = Image.new('RGB', (self.width, self.height), color=self.bg)
        draw = ImageDraw.Draw(img)

        x_left, x_right = self.margin, self.width - self.margin
        y = self.margin
        ocr_lines: List[str] = []

        if cfg.title:
            title_lines = _draw_wrapped(draw, cfg.title, self.fonts['title'],
                                        (x_left, y, x_right, y), fill=self.text_color)
            ocr_lines.extend(title_lines)
            h = _measure_text_h(draw, cfg.title, self.fonts['title'], x_right - x_left)
            y += h + int(self.gutter * 0.5)

        chart_top = y
        chart_w_target = max(10, self.width - 2 * CHART_SIDE_PAD)
        # leave room for footer legend if present
        footer_room = 140 if footer_legend else 0
        chart_h_target = (self.height - RESERVED_BOTTOM - footer_room) - chart_top - self.gutter
        if chart_h_target <= 0:
            chart_h_target = max(1, int(self.height * 0.25))

        cw, ch = chart_img.width, chart_img.height
        ratio_w = chart_w_target / max(cw, 1)
        new_w = chart_w_target
        new_h = int(ch * ratio_w)
        if new_h > chart_h_target:
            new_h = chart_h_target

        chart_img = chart_img.resize((max(1, new_w), max(1, new_h)), Image.Resampling.LANCZOS)
        img.paste(chart_img, (CHART_SIDE_PAD, chart_top), chart_img)
        y_after_chart = chart_top + new_h + int(self.gutter * 0.8)

        # Footer legend (if requested)
        if footer_legend:
            self._draw_footer_legend(draw, footer_legend, x_left, y_after_chart, x_right)

        ensure_dir_for(out_path)
        ensure_output_dir()
        img.save(out_path, format='PNG')
        return out_path, ocr_lines

# =================== HIGH-LEVEL LOGIC ===================
def choose_structure(df: pd.DataFrame) -> Tuple[str, Dict]:
    cat_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if cat_cols and len(num_cols) >= 2:
        return "grouped", {"label": cat_cols[0], "series": num_cols[:min(3, len(num_cols))]}
    if cat_cols:
        return "single", {"label": cat_cols[0], "value": (num_cols[0] if num_cols else cat_cols[0])}
    cols = df.columns.tolist()
    if len(cols) >= 2:
        return "single", {"label": cols[0], "value": cols[1]}
    return "none", {}

def render_infographic(df: pd.DataFrame, out_path: str, title: str, orientation: str) -> Optional[dict]:
    mode, info = choose_structure(df)
    if mode == "none":
        return None

    bg_rgb, is_dark_bg, axis_color = choose_background()

    # ---- Single-series ----
    if mode == "single":
        labels = ascii_series(df[info["label"]])
        if info["value"] in df.columns and info["value"] != info["label"]:
            vals = pd.to_numeric(df[info["value"]], errors="coerce")
            s = vals.groupby(labels).sum()
        else:
            s = labels.value_counts()
        s = s[s > 0]
        s = pick_bars_subset(s)
        if s.empty or s.index.nunique() < MIN_BARS:
            return None
        cats = s.index.astype(str).tolist()
        values = s.values.astype(float).tolist()
        colors = many_colors(len(values))

        footer_needed = needs_footer_legend(cats)

        if orientation == "h":
            chart, legend_pairs = render_single_hbar(cats, values, colors, axis_color, title, bg_rgb, footer_needed)
        else:
            chart, legend_pairs = render_single_vbar(cats, values, colors, axis_color, title, bg_rgb, footer_needed)

    # ---- Grouped ----
    else:
        label_col = info["label"]
        series_cols = info["series"]
        g = df.groupby(ascii_series(df[label_col]))[series_cols].sum()
        g = g.replace([np.inf, -np.inf], np.nan).dropna(how="all")
        g = g[(g > 0).any(axis=1)]
        if g.empty:
            return None
        sums = g.sum(axis=1).sort_values(ascending=False)
        keep = pick_bars_subset(sums)
        if keep.empty or keep.index.nunique() < MIN_BARS:
            return None
        g = g.loc[keep.index].iloc[:MAX_BARS]

        cat_labels = g.index.astype(str).tolist()
        series_names = [ascii_only(c) for c in g.columns.tolist()]
        matrix_values = g.fillna(0).values.astype(float)

        footer_needed = needs_footer_legend(series_names)

        if orientation == "h":
            chart, legend_pairs = render_grouped_hbar(cat_labels, series_names, matrix_values, axis_color, title, bg_rgb, footer_needed)
        else:
            chart, legend_pairs = render_grouped_vbar(cat_labels, series_names, matrix_values, axis_color, title, bg_rgb, footer_needed)

    # ---- Save (with or without canvas) ----
    if USE_CANVAS:
        comp = InfographicComposer(CANVAS_W, CANVAS_H, bg_rgb=bg_rgb, axis_is_dark=is_dark_bg)
        info_cfg = InfographicConfig(title=ascii_only(title or ""))
        footer = legend_pairs if needs_footer_legend([lp[0] for lp in legend_pairs]) else None
        image_path, ocr_lines = comp.compose(chart, info_cfg, out_path, footer_legend=footer)
    else:
        # chart already has fig facecolor and title; legend is rendered in-plot or below axes
        chart.save(out_path)
        image_path, ocr_lines = out_path, [ascii_only(title or "")]

    return {"image": image_path.replace("\\", "/"), "ocr": "\n".join(ocr_lines)}

# =================== DRIVER ===================
def generate_images(n: int = N_IMAGES, manifest_path: str = os.path.join(OUTPUT_DIR, "metadata.json")):
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)
        np.random.seed(RANDOM_SEED)

    ensure_output_dir()
    ensure_dir_for(manifest_path)
    csvs = find_csvs(ROOT_FOLDER)
    log(f"Found {len(csvs)} CSV files under ROOT_FOLDER.")
    if not csvs:
        log("⚠️ No CSV files found. Check ROOT_FOLDER path.")
        return

    results: List[dict] = []
    idx = 0

    log(f"🚀 Target: generate {n} bar charts (single & grouped).")

    while len(results) < n and idx < n * SCAN_MULTIPLIER:
        csv_path = csvs[idx % len(csvs)]
        idx += 1

        df = safe_read_csv(csv_path, MAX_ROWS)
        if df is None or df.empty:
            continue

        title, _ = datapackage_meta_for(csv_path)
        title = ascii_only(title) if title else "Title"

        base = os.path.splitext(os.path.basename(csv_path))[0]
        out_path = os.path.join(OUTPUT_DIR, f"{base}_{len(results):05}.png")

        orientation = BAR_ORIENTATIONS[len(results) % len(BAR_ORIENTATIONS)]

        try:
            item = render_infographic(df, out_path, title, orientation)
            if item is None:
                continue
            results.append(item)
            log(f"  ✅ saved: {out_path} ({orientation}, {len(results)}/{n})")
        except Exception as e:
            log(f"  - skip: error {e}")
            gc.collect()
            continue

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log(f"\n✅ Done! {len(results)} images generated.")
    log(f"📁 Manifest: {manifest_path}")

# =================== MAIN ===================
if __name__ == "__main__":
    generate_images()
