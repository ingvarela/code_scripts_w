#!/usr/bin/env python3
"""
figureQA — generate synthetic charts where the *color is the data*.

- No CSVs. Categories = color names; values = luminance of that color (± jitter).
- Chart types: vertical bar, horizontal bar, pie.
- Titles/axis labels match the style in your examples ("title", "xaxis_label", "yaxis_label").
- Legends are color-coded; for bars the x/y tick labels show color names too.
- Saves PNGs and a JSON manifest with the colors/values used.
"""

import os, io, json, random, re
from typing import List, Dict, Tuple
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors

# ========================== CONFIG ==========================
OUTPUT_DIR = "FigureQA_out"
N_IMAGES   = 24
CHART_TYPES = ["vbar", "hbar", "pie"]

MIN_CATS, MAX_CATS = 3, 9
SIZE_VBAR = (10.0, 4.0)
SIZE_HBAR = (7.5, 4.0)
SIZE_PIE  = (6.0, 4.0)
DPI = 100
RANDOM_SEED = None  # set for reproducibility

# ========================== UTILITIES =======================
def ensure_dir(d: str):
    os.makedirs(d, exist_ok=True)

def prettify_color_name(name: str) -> str:
    """Turn CSS4 color keys like 'royalblue' -> 'Royal Blue'."""
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)  # split camel case
    s = s.replace("_", " ")
    return s.title()

def luminance(rgb: Tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126*r + 0.7152*g + 0.0722*b

def value_from_color(hexcolor: str) -> float:
    rgb = mcolors.to_rgb(hexcolor)
    lum = luminance(rgb)
    base = 10 + lum * 90.0
    jitter = np.random.normal(0, 5)
    return max(1, min(100, base + jitter))

def pick_colors(k: int) -> List[Tuple[str, str]]:
    """Pick k distinct CSS4 colors, pretty-named."""
    all_items = list(mcolors.CSS4_COLORS.items())
    random.shuffle(all_items)
    picks = []
    for name, hexv in all_items:
        pretty = prettify_color_name(name)
        picks.append((pretty, hexv))
        if len(picks) >= k:
            break
    return picks[:k]

# ========================== DRAWERS =========================
def style_axes_for_bars(ax, axis_color="#222222"):
    ax.grid(True, axis="y", color="#888888", alpha=0.35, linewidth=0.8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    for side in ['left','bottom']:
        ax.spines[side].set_color(axis_color)
    ax.tick_params(colors=axis_color, labelsize=9)

def draw_vertical_bars(out_path: str, names: List[str], hexes: List[str], values: List[float]):
    fig, ax = plt.subplots(figsize=SIZE_VBAR, dpi=DPI)
    x = np.arange(len(names))
    ax.bar(x, values, color=hexes)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=90)
    ax.set_xlabel("xaxis_label", style="italic")
    ax.set_ylabel("yaxis_label")
    ax.set_title("title", loc='left', fontsize=13, fontweight='bold')
    style_axes_for_bars(ax)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)

def draw_horizontal_bars(out_path: str, names: List[str], hexes: List[str], values: List[float]):
    fig, ax = plt.subplots(figsize=SIZE_HBAR, dpi=DPI)
    y = np.arange(len(names))
    ax.barh(y, values, color=hexes)
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlabel("xaxis_label", style="italic")
    ax.set_ylabel("yaxis_label")
    ax.set_title("title", loc='left', fontsize=13, fontweight='bold')
    style_axes_for_bars(ax)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)

def draw_pie(out_path: str, names: List[str], hexes: List[str], values: List[float]):
    vals = np.array(values, dtype=float)
    vals = np.clip(vals, 1e-3, None)
    fig, ax = plt.subplots(figsize=SIZE_PIE, dpi=DPI)
    wedges, _ = ax.pie(vals, colors=hexes, startangle=90, counterclock=False)
    ax.set_title("title", loc='left', fontsize=13, fontweight='bold')
    ax.legend(wedges, names, loc="center left", bbox_to_anchor=(-0.25, 0.5),
              frameon=True, fontsize=9)
    ax.axis('equal')
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)

# ========================== MAIN GEN ========================
def generate_one(idx: int) -> Dict:
    k = random.randint(MIN_CATS, MAX_CATS)
    pairs = pick_colors(k)
    names = [p[0] for p in pairs]
    hexes = [p[1] for p in pairs]
    values = [value_from_color(h) for h in hexes]

    ctype = random.choice(CHART_TYPES)
    fname = f"figqa_{idx:05}_{ctype}.png"
    path = os.path.join(OUTPUT_DIR, fname)

    if ctype == "vbar":
        draw_vertical_bars(path, names, hexes, values)
    elif ctype == "hbar":
        order = np.argsort(values)[::-1]
        names = [names[i] for i in order]
        hexes = [hexes[i] for i in order]
        values = [values[i] for i in order]
        draw_horizontal_bars(path, names, hexes, values)
    else:
        if k > 6:
            order = np.argsort(values)[::-1][:6]
            names = [names[i] for i in order]
            hexes = [hexes[i] for i in order]
            values = [values[i] for i in order]
        draw_pie(path, names, hexes, values)

    return {
        "file": path.replace("\\", "/"),
        "type": ctype,
        "colors": [{"name": n, "hex": h, "value": round(v, 2)} for n, h, v in zip(names, hexes, values)]
    }

def main():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)
        np.random.seed(RANDOM_SEED)

    ensure_dir(OUTPUT_DIR)
    manifest = []
    for i in range(N_IMAGES):
        item = generate_one(i)
        manifest.append(item)

    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Done! Wrote {len(manifest)} images to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
