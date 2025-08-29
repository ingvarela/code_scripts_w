#!/usr/bin/env python3
"""
figureQA — synthetic charts where *color is the data*.

Adds line & dotline plots (in your sample style) to the existing vertical/horizontal bars and pie.
- No CSVs. Categories = color names; values = luminance-derived numbers (± jitter).
- Chart types: "vbar", "hbar", "pie", "line", "dotline".
- Titles/axis labels: title left & bold; x label italic; y label normal.
- Legends are color-coded.

Edit CONFIG below to control counts, sizes, and which chart types to include.
"""

import os, json, random, re
from typing import List, Dict, Tuple
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors

# ========================== CONFIG ==========================
OUTPUT_DIR = "FigureQA_out"
N_IMAGES   = 30

# Include the new types here:
CHART_TYPES = ["vbar", "hbar", "pie", "line", "dotline"]

# Categories per chart
MIN_CATS, MAX_CATS = 3, 9

# Figure sizes (inches) similar to your examples
SIZE_VBAR   = (10.0, 4.0)
SIZE_HBAR   = (7.5, 4.0)
SIZE_PIE    = (6.0, 4.0)
SIZE_LINE   = (12.0, 4.0)  # wide
DPI = 100

RANDOM_SEED = None  # set an int for reproducibility, e.g., 42

# ========================== UTILITIES =======================
def ensure_dir(d: str):
    os.makedirs(d, exist_ok=True)

def prettify_color_name(name: str) -> str:
    """Turn 'royalblue' -> 'Royal Blue' and similar."""
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)  # camel-case split (if any)
    s = s.replace("_", " ")
    return s.title()

def luminance(rgb: Tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126*r + 0.7152*g + 0.0722*b

def value_from_color(hexcolor: str) -> float:
    """Map color → value ~[10..100] from luminance with small jitter."""
    rgb = mcolors.to_rgb(hexcolor)
    base = 10 + luminance(rgb) * 90.0
    jitter = np.random.normal(0, 5)
    return float(np.clip(base + jitter, 1, 100))

def pick_colors(k: int) -> List[Tuple[str, str]]:
    """Pick k distinct CSS4 colors, prettified names, use full palette."""
    items = list(mcolors.CSS4_COLORS.items())
    random.shuffle(items)
    picks = []
    for name, hexv in items:
        picks.append((prettify_color_name(name), hexv))
        if len(picks) >= k:
            break
    return picks[:k]

def style_axes_basic(ax, axis_color="#222"):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    for side in ('left','bottom'):
        ax.spines[side].set_color(axis_color)
    ax.tick_params(colors=axis_color, labelsize=9)

def style_axes_grid_y(ax):
    ax.grid(True, axis="y", color="#888", alpha=0.35, linewidth=0.8)

def style_axes_grid_both(ax):
    ax.grid(True, axis="both", color="#aaa", alpha=0.35, linewidth=0.7)

# ========================== BAR & PIE =======================
def draw_vertical_bars(out_path: str, names: List[str], hexes: List[str], values: List[float]):
    fig, ax = plt.subplots(figsize=SIZE_VBAR, dpi=DPI)
    x = np.arange(len(names))
    ax.bar(x, values, color=hexes)
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=90)
    ax.set_xlabel("xaxis_label", style="italic")
    ax.set_ylabel("yaxis_label")
    ax.set_title("title", loc='left', fontsize=13, fontweight='bold')
    style_axes_basic(ax); style_axes_grid_y(ax)
    fig.tight_layout(); fig.savefig(out_path, bbox_inches="tight"); plt.close(fig)

def draw_horizontal_bars(out_path: str, names: List[str], hexes: List[str], values: List[float]):
    fig, ax = plt.subplots(figsize=SIZE_HBAR, dpi=DPI)
    y = np.arange(len(names))
    ax.barh(y, values, color=hexes)
    ax.set_yticks(y); ax.set_yticklabels(names)
    ax.set_xlabel("xaxis_label", style="italic")
    ax.set_ylabel("yaxis_label")
    ax.set_title("title", loc='left', fontsize=13, fontweight='bold')
    style_axes_basic(ax); style_axes_grid_y(ax)
    fig.tight_layout(); fig.savefig(out_path, bbox_inches="tight"); plt.close(fig)

def draw_pie(out_path: str, names: List[str], hexes: List[str], values: List[float]):
    vals = np.clip(np.array(values, dtype=float), 1e-3, None)
    fig, ax = plt.subplots(figsize=SIZE_PIE, dpi=DPI)
    wedges, _ = ax.pie(vals, colors=hexes, startangle=90, counterclock=False)
    ax.set_title("title", loc='left', fontsize=13, fontweight='bold')
    ax.legend(wedges, names, loc="center left", bbox_to_anchor=(-0.25, 0.5),
              frameon=True, fontsize=9)
    ax.axis('equal')
    fig.tight_layout(); fig.savefig(out_path, bbox_inches="tight"); plt.close(fig)

# ========================== LINE & DOTLINE ===================
def synth_series(x: np.ndarray, base: float) -> np.ndarray:
    """
    Make a smooth-ish series using a blend of linear + gentle curve + noise.
    'base' around 10..100 seeds the vertical placement from color luminance.
    """
    # start near base with mild slope and curvature
    slope = np.random.uniform(-0.08, 0.12) * (x.max() - x.min())
    curve = np.random.uniform(-0.0005, 0.0005) * (x - x.mean())**2
    noise = np.random.normal(0, 0.6, size=x.shape)
    y = base + (slope * (x / x.max())) + curve + noise
    return y

def draw_line_plot(out_path: str, names: List[str], hexes: List[str]):
    # x domain like samples (0..100 with ~20 points)
    n_pts = random.randint(16, 26)
    x = np.linspace(0, 100, n_pts)

    fig, ax = plt.subplots(figsize=SIZE_LINE, dpi=DPI)
    for name, hexv in zip(names, hexes):
        base = value_from_color(hexv)
        y = synth_series(x, base)
        # choose style: solid or dashed/dotted like examples
        ls = random.choice(["-", "--", "-.", ":"])
        ax.plot(x, y, linestyle=ls, color=hexv, linewidth=2.0, label=name)

    ax.set_xlabel("xaxis_label", style="italic")
    ax.set_ylabel("yaxis_label")
    ax.set_title("title", loc='left', fontsize=13, fontweight='bold')
    style_axes_basic(ax); style_axes_grid_both(ax)

    # Legend to the right (as in examples)
    leg = ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=True, fontsize=9)
    for text in leg.get_texts(): text.set_color("#222")

    fig.tight_layout(); fig.savefig(out_path, bbox_inches="tight"); plt.close(fig)

def draw_dotline_plot(out_path: str, names: List[str], hexes: List[str]):
    # x domain like samples; sometimes constant or strongly linear series
    n_pts = random.randint(16, 26)
    x = np.linspace(0, 100, n_pts)

    fig, ax = plt.subplots(figsize=SIZE_LINE, dpi=DPI)
    for name, hexv in zip(names, hexes):
        base = value_from_color(hexv)
        mode = random.choice(["linear", "constant", "curved"])
        if mode == "linear":
            slope = np.random.uniform(-0.3, 0.3)
            y = base + slope * (x - x.min())
        elif mode == "constant":
            y = np.full_like(x, base) + np.random.normal(0, 0.15, size=x.shape)
        else:
            # gentle arc
            y = base + 8*np.sin((x/100.0)*np.pi) + np.random.normal(0, 0.4, size=x.shape)

        # dotted/dashed line with round markers like your examples
        ls = random.choice(["--", ":", "-."])
        ax.plot(x, y, linestyle=ls, color=hexv, linewidth=2.0, marker='o',
                markersize=4.5, markeredgecolor=hexv, markerfacecolor=hexv, label=name)

    ax.set_xlabel("xaxis_label", style="italic")
    ax.set_ylabel("yaxis_label")
    ax.set_title("title", loc='left', fontsize=13, fontweight='bold')
    style_axes_basic(ax); style_axes_grid_both(ax)

    leg = ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=True, fontsize=9)
    for text in leg.get_texts(): text.set_color("#222")

    fig.tight_layout(); fig.savefig(out_path, bbox_inches="tight"); plt.close(fig)

# ========================== MAIN GEN ========================
def generate_one(idx: int) -> Dict:
    k = random.randint(MIN_CATS, MAX_CATS)
    pairs = pick_colors(k)
    names = [p[0] for p in pairs]
    hexes = [p[1] for p in pairs]

    # values for bar/pie
    values = [value_from_color(h) for h in hexes]

    ctype = random.choice(CHART_TYPES)
    fname = f"figqa_{idx:05}_{ctype}.png"
    path = os.path.join(OUTPUT_DIR, fname)

    if ctype == "vbar":
        draw_vertical_bars(path, names, hexes, values)
    elif ctype == "hbar":
        order = np.argsort(values)[::-1]
        draw_horizontal_bars(path,
                             [names[i] for i in order],
                             [hexes[i] for i in order],
                             [values[i] for i in order])
    elif ctype == "pie":
        # keep pies tidy: cap slices at 6
        if k > 6:
            order = np.argsort(values)[::-1][:6]
            names = [names[i] for i in order]
            hexes = [hexes[i] for i in order]
            values = [values[i] for i in order]
        draw_pie(path, names, hexes, values)
    elif ctype == "line":
        # choose 2–8 series for readability
        n_series = random.randint(2, min(8, k))
        draw_line_plot(path, names[:n_series], hexes[:n_series])
    else:  # dotline
        n_series = random.randint(2, min(8, k))
        draw_dotline_plot(path, names[:n_series], hexes[:n_series])

    return {
        "file": path.replace("\\", "/"),
        "type": ctype,
        "colors": [{"name": n, "hex": h, "value": float(v)} for n, h, v in zip(names, hexes, values)]
    }

def main():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED); np.random.seed(RANDOM_SEED)
    ensure_dir(OUTPUT_DIR)
    manifest = [generate_one(i) for i in range(N_IMAGES)]
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Done! Wrote {len(manifest)} images to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
