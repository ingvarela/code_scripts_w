#!/usr/bin/env python3
"""
Pew-style infographic generator (pie + bar only)
------------------------------------------------

- Loads CSV data and datapackage.json
- Creates document-like infographic canvas (title, subtitle, chart, notes, source)
- Chart is full-width, edge-to-edge, no side padding
- Tight spacing between subtitle and chart
- Skips charts with too few categories
- Records OCR text (left→right, top→bottom order)

"""

import os
import gc
import json
import warnings
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

from PIL import Image, ImageDraw, ImageFont

# ============== CONFIG ==============
ROOT_FOLDER = "C://Users//svs26//Desktop//MS COCO 2017//UREADER//owid-datasets-master//owid-datasets-master//datasets"
OUTPUT_DIR = "ChartQA"
MAX_ROWS = 300
N_IMAGES = 20

STRATEGIES = [
    "pie_chart",
    "horizontal_bar_infographic",
]

FONT_FAMILY = "DejaVu Sans"  # shipped with matplotlib; widely available
FONTS = {
    "title": 36,
    "subtitle": 20,
    "section": 16,
    "body": 14,
    "small": 12,
}

# Canvas + layout
CANVAS_W, CANVAS_H = 1800, 1200
MARGIN = 64
GUTTER = 28
FOOTER_H = 110
TEXT_COLOR = (20, 20, 20)
SUBTITLE_COLOR = (100, 100, 100)  # lighter grey
BG_COLOR = (255, 255, 255)

# Chart render size
CHART_PX = (800, 1000)  # vertical-shaped

# Color palette (yellow, brown, black)
COLOR_PALETTE = [
    "#FFD700",  # gold/yellow
    "#DAA520",  # goldenrod
    "#8B4513",  # saddle brown
    "#5C4033",  # dark brown
    "#000000",  # black
]

warnings.filterwarnings("ignore", category=UserWarning)


# ------------------ Utility Functions ------------------
def ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _load_font(size: int, style: str = "normal") -> ImageFont.FreeTypeFont:
    try:
        from matplotlib import font_manager
        path = font_manager.findfont(FONT_FAMILY)
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()


def _measure_text_h(draw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> int:
    lines = []
    words = text.split()
    while words:
        line = words.pop(0)
        while words and draw.textlength(line + ' ' + words[0], font=font) <= max_w:
            line += ' ' + words.pop(0)
        lines.append(line)
    return sum(font.getbbox(l)[3] for l in lines)


def _draw_wrapped(draw, text: str, font: ImageFont.FreeTypeFont, box: tuple, fill=(0, 0, 0)):
    x0, y0, x1, y1 = box
    words = text.split()
    line = ''
    y = y0
    while words:
        test_line = line + (' ' if line else '') + words[0]
        if draw.textlength(test_line, font=font) <= (x1 - x0):
            line = test_line
            words.pop(0)
        else:
            draw.text((x0, y), line, font=font, fill=fill)
            y += font.getbbox(line)[3]
            line = ''
    if line:
        draw.text((x0, y), line, font=font, fill=fill)
        y += font.getbbox(line)[3]
    return y - y0


# ------------------ Chart Functions ------------------
def render_pie(df: pd.DataFrame, title_col: str, value_col: str) -> Optional[Image.Image]:
    if len(df) < 3:  # skip too few slices
        return None
    fig, ax = plt.subplots(figsize=(CHART_PX[0]/100, CHART_PX[1]/100), dpi=100)
    ax.pie(df[value_col], labels=df[title_col], autopct='%1.0f%%',
           colors=COLOR_PALETTE[:len(df)], startangle=90,
           wedgeprops=dict(edgecolor='white'))
    plt.tight_layout()
    buf = os.path.join(OUTPUT_DIR, "temp_pie.png")
    fig.savefig(buf, transparent=True)
    plt.close(fig)
    return Image.open(buf).convert("RGBA")


def render_bar(df: pd.DataFrame, title_col: str, value_col: str) -> Optional[Image.Image]:
    if len(df) < 3:  # skip too few bars
        return None
    fig, ax = plt.subplots(figsize=(CHART_PX[0]/100, CHART_PX[1]/100), dpi=100)
    ax.barh(df[title_col], df[value_col], color=COLOR_PALETTE[:len(df)])
    plt.tight_layout()
    buf = os.path.join(OUTPUT_DIR, "temp_bar.png")
    fig.savefig(buf, transparent=True)
    plt.close(fig)
    return Image.open(buf).convert("RGBA")


# ------------------ Data + Composition ------------------
@dataclass
class InfographicConfig:
    title: str
    subtitle: Optional[str]
    note: Optional[str]
    source: Optional[str]


class InfographicComposer:
    def __init__(self, width=CANVAS_W, height=CANVAS_H):
        self.width, self.height = width, height
        self.bg, self.text_color = BG_COLOR, TEXT_COLOR
        self.margin, self.gutter, self.footer_h = MARGIN, GUTTER, FOOTER_H
        self.fonts = {
            'title': _load_font(FONTS['title']),
            'subtitle': _load_font(FONTS['subtitle']),
            'small': _load_font(FONTS['small']),
        }

    def compose(self, chart_img: Image.Image, cfg: InfographicConfig, out_path: str) -> str:
        img = Image.new('RGB', (self.width, self.height), color=self.bg)
        draw = ImageDraw.Draw(img)

        x_left, x_right = self.margin, self.width - self.margin
        y = self.margin

        ocr_texts = []

        # Title
        if cfg.title:
            h = _measure_text_h(draw, cfg.title, self.fonts['title'], x_right - x_left)
            _draw_wrapped(draw, cfg.title, self.fonts['title'], (x_left, y, x_right, y + h), fill=self.text_color)
            y += h + int(self.gutter * 0.5)
            ocr_texts.append(cfg.title)

        # Subtitle
        if cfg.subtitle:
            h = _measure_text_h(draw, cfg.subtitle, self.fonts['subtitle'], x_right - x_left)
            _draw_wrapped(draw, cfg.subtitle, self.fonts['subtitle'], (x_left, y, x_right, y + h), fill=SUBTITLE_COLOR)
            y += h + int(self.gutter * 0.5)  # tighter spacing
            ocr_texts.append(cfg.subtitle)

        footer_top = self.height - self.footer_h

        # ---- Chart placement: full width, tight under subtitle ----
        if chart_img is not None:
            chart_top = y
            chart_w_target = self.width
            chart_h_target = footer_top - chart_top - self.gutter

            cw, ch = chart_img.width, chart_img.height
            ratio_w = chart_w_target / max(cw, 1)
            new_w = chart_w_target
            new_h = int(ch * ratio_w)

            if new_h > chart_h_target:
                new_h = chart_h_target

            chart_img = chart_img.resize((new_w, max(1, new_h)), Image.Resampling.LANCZOS)

            img.paste(chart_img, (0, chart_top), chart_img)

        # Footer
        foot_y = footer_top + int(self.gutter * 0.3)
        if cfg.note:
            nh = _draw_wrapped(draw, cfg.note, self.fonts['small'],
                               (x_left, foot_y, x_right, foot_y + self.footer_h // 2),
                               fill=self.text_color)
            foot_y += nh + int(self.gutter * 0.5)
            ocr_texts.append(cfg.note)
        if cfg.source:
            src = f"Source: {cfg.source}"
            _draw_wrapped(draw, src, self.fonts['small'],
                          (x_left, foot_y, x_right, foot_y + self.fonts['small'].size + 6),
                          fill=self.text_color)
            ocr_texts.append(src)

        ensure_dir(out_path)
        img.save(out_path, format='PNG')

        # Save OCR text file
        ocr_path = out_path.replace(".png", ".txt")
        with open(ocr_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ocr_texts))

        return out_path