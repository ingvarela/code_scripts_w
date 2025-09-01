"""
vistext.py — text-forward charts with bold typography, single accent color,
adaptive background contrast, automatic title wrapping, and variability controls.

- Scans ROOT_FOLDER for CSVs, writes PNGs to OUTPUT_DIR.
- Chart types: vertical bar, horizontal bar, line, area (filled line).
- Single accent color per chart (from CSS4); background randomized (light/dark).
- Axis labels are omitted (ticks only), like your samples.
- Titles are automatically wrapped to avoid wasted horizontal space.
- Data pickers add downsampling/robust-scaling/variability so plots aren't flat.
"""

import os, json, gc, random, unicodedata, warnings, textwrap
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors

# =================== CONFIG ===================
ROOT_FOLDER = "C://Users//svs26//Desktop//MS COCO 2017//UREADER//owid-datasets-master//owid-datasets-master//datasets"
OUTPUT_DIR  = "VISTEXT_05"
N_IMAGES    = 500
MAX_ROWS    = 800

CHART_TYPES = ["vbar", "hbar", "line", "area"]  # cycle evenly

# Figure sizes (inches)
SIZE_BAR   = (7.2, 7.2)     # square-ish bars
SIZE_LINE  = (8.5, 7.0)     # a bit wide for lines
DPI        = 140

# Data requirements
MIN_BARS   = 3
MAX_BARS   = 14
MIN_POINTS = 6

# Random seed (set to an int for reproducibility)
RANDOM_SEED = None

# Bold font globally
plt.rcParams.update({
    "font.weight": "bold",
    "axes.titleweight": "bold",
    "axes.labelweight": "bold",
})

warnings.filterwarnings("ignore", category=UserWarning)

# =================== UTILS ===================
def ensure_dir(d: str):
    os.makedirs(d, exist_ok=True)

def ascii_only(s) -> str:
    if s is None: return ""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii","ignore").decode("ascii").strip()

def find_csvs(root: str) -> List[str]:
    out = []
    for r, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".csv"):
                out.append(os.path.join(r, f))
    return out

def safe_read_csv(path: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path, low_memory=False)
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty: return None
        if len(df) > MAX_ROWS:
            df = df.sample(n=MAX_ROWS, random_state=42).sort_index()
        return df
    except Exception:
        return None

def datapackage_title(csv_path: str) -> str:
    dp = os.path.join(os.path.dirname(csv_path), "datapackage.json")
    if os.path.exists(dp):
        try:
            meta = json.load(open(dp, "r", encoding="utf-8"))
            t = meta.get("title") or meta.get("name") or ""
            return ascii_only(t) if t else "title"
        except Exception:
            pass
    return "title"

# =================== COLOR HELPERS ===================
def rel_luminance(rgb: Tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126*r + 0.7152*g + 0.0722*b

def pick_css4_accent() -> str:
    """Pick an accent from CSS4 colors, excluding near-white and near-black."""
    candidates = []
    for _, hexv in mcolors.CSS4_COLORS.items():
        rgb = mcolors.to_rgb(hexv)
        L = rel_luminance(rgb)
        if 0.08 < L < 0.92:
            candidates.append(hexv)
    return random.choice(candidates)

def pick_background() -> str:
    """Light & dark backgrounds (text color adapts automatically)."""
    palette = [
        "#f7f7f7", "#efefef", "#e6e6e6", "#dedede", "#e9f0f7", "#f9efe6",  # light
        "#58595b", "#4a4a4a", "#555555",                                   # dark greys
    ]
    return random.choice(palette)

def contrast_text_color(bg_hex: str) -> str:
    L = rel_luminance(mcolors.to_rgb(bg_hex))
    return "#000000" if L > 0.6 else "#ffffff"

# =================== VARIABILITY HELPERS ===================
def _robust_clip_scale(arr: np.ndarray) -> np.ndarray:
    """Clip 1..99 percentiles and scale to ~[0,100]; if flat, rank+jitter."""
    a = np.asarray(arr, dtype=float)
    if a.size == 0:
        return np.array([])
    q1, q99 = np.percentile(a, [1, 99])
    if np.isfinite(q1) and np.isfinite(q99) and q99 > q1:
        a = np.clip(a, q1, q99)
    mn, mx = np.nanmin(a), np.nanmax(a)
    if not np.isfinite(mn) or not np.isfinite(mx):
        return np.array([])
    if mx - mn < 1e-9:
        ranks = np.arange(len(a)) + 1
        jitter = np.random.uniform(0.9, 1.1, size=len(a))
        a = ranks * jitter
        a = (a - a.min()) / (a.max() - a.min() + 1e-12)
    else:
        a = (a - mn) / (mx - mn)
    return a * np.random.uniform(60, 100)

def _maybe_variabilize(y: np.ndarray) -> np.ndarray:
    """If y is very flat, add a gentle trend + noise."""
    y = np.asarray(y, dtype=float)
    if y.size < 3:
        return y
    rel = (np.nanstd(y) / (abs(np.nanmean(y)) + 1e-9))
    if rel < 0.03:
        slope = np.random.uniform(-0.25, 0.25) * (np.nanstd(y) + 1.0)
        trend = slope * np.linspace(0, 1, len(y))
        noise = np.random.normal(scale=0.05 * (np.nanstd(y) + 1.0), size=len(y))
        y = y + trend + noise
    return y

def _downsample_series(x: np.ndarray, y: np.ndarray,
                       lo: int = 12, hi: int = 30) -> Tuple[np.ndarray, np.ndarray]:
    """Evenly pick between lo..hi points (not exceeding available)."""
    n = len(y)
    if n <= lo:
        return x, y
    target = np.random.randint(lo, min(hi, n) + 1)
    idx = np.linspace(0, n - 1, target).round().astype(int)
    return x[idx], y[idx]

# =================== DATA PICKERS ===================
def pick_bar_series(df: pd.DataFrame) -> Optional[Tuple[List[str], List[float]]]:
    cat_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if cat_cols and num_cols:
        s = df.groupby(df[cat_cols[0]].astype(str))[num_cols[0]].sum()
    elif cat_cols:
        s = df[cat_cols[0]].astype(str).value_counts()
    elif df.shape[1] >= 2:
        x = df.iloc[:, 0].astype(str)
        y = pd.to_numeric(df.iloc[:, 1], errors="coerce")
        s = y.groupby(x).sum()
    else:
        return None

    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    s = s[s > 0]
    if s.empty:
        return None

    s = s.sort_values(ascending=False)
    if len(s) < MIN_BARS:
        return None

    max_take = min(MAX_BARS, len(s))
    take = np.random.randint(MIN_BARS, max_take + 1)

    if np.random.rand() < 0.6:
        s = s.iloc[:take]       # top-k
    else:
        s = s.sample(n=take)    # random subset

    vals = _robust_clip_scale(s.values)
    if vals.size == 0:
        return None
    if np.allclose(vals.max() - vals.min(), 0, atol=1e-6):
        vals = vals + np.random.uniform(-0.5, 0.5, size=len(vals))

    cats = [ascii_only(c) for c in s.index.tolist()]
    return cats, vals.tolist()

def pick_timeseries(df: pd.DataFrame) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    nums = df.select_dtypes(include=[np.number]).columns.tolist()
    if not nums:
        if df.shape[1] >= 2:
            y = pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy()
            x = df.iloc[:, 0].to_numpy()
        else:
            return None
    else:
        y = pd.to_numeric(df[nums[0]], errors="coerce").to_numpy()
        cand = None
        for c in df.columns:
            if c == nums[0]:
                continue
            if np.issubdtype(df[c].dtype, np.number):
                cand = df[c].to_numpy(); break
            try:
                dt = pd.to_datetime(df[c], errors="coerce")
                if dt.notna().sum() >= MIN_POINTS:
                    cand = dt.to_numpy(); break
            except Exception:
                pass
        if cand is None:
            cand = np.arange(len(y))
        x = np.asarray(cand)

    m = np.isfinite(y)
    y = y[m]; x = x[m]
    if len(y) < MIN_POINTS:
        return None

    try:
        order = np.argsort(x)
        x = np.array(x)[order]; y = np.array(y)[order]
    except Exception:
        x = np.arange(len(y))

    y = _maybe_variabilize(y)
    x, y = _downsample_series(np.asarray(x), np.asarray(y), lo=12, hi=30)
    y = _robust_clip_scale(y)
    return x, y

# =================== STYLING & TITLES ===================
def apply_theme(fig, ax, bg: str, txt: str):
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    grid_color = "#cfcfcf" if txt == "#000000" else "#b0b0b0"
    ax.grid(True, color=grid_color, alpha=0.7, linewidth=1.0)
    for spine in ("top","right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left","bottom"):
        ax.spines[spine].set_color(txt)
        ax.spines[spine].set_linewidth(1.6)
    ax.tick_params(colors=txt, labelsize=12, width=1.2)

def set_wrapped_title(ax, title: str, txt: str, max_chars: int = 60):
    """Center, wrap long titles to fit figure width (avoid wasted space)."""
    title = ascii_only(title or "title")
    wrapped = "\n".join(textwrap.wrap(title, max_chars)) if len(title) > max_chars else title
    ax.set_title(wrapped, loc="center", fontsize=24, fontweight="bold", color=txt, pad=12)

# =================== RENDERERS ===================
def render_vbar(cats: List[str], vals: List[float], title: str, out_path: str,
                accent: str, bg: str, txt: str):
    fig, ax = plt.subplots(figsize=SIZE_BAR, dpi=DPI)
    apply_theme(fig, ax, bg, txt)
    x = np.arange(len(cats))
    ax.bar(x, vals, color=accent, edgecolor=txt, linewidth=0.0)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=45, ha="right", color=txt, fontsize=12)
    ax.set_xlabel(""); ax.set_ylabel("")  # ticks only
    set_wrapped_title(ax, title, txt)
    fig.tight_layout(); ensure_dir(os.path.dirname(out_path))
    fig.savefig(out_path, facecolor=fig.get_facecolor(), bbox_inches="tight"); plt.close(fig)

def render_hbar(cats: List[str], vals: List[float], title: str, out_path: str,
                accent: str, bg: str, txt: str):
    fig, ax = plt.subplots(figsize=SIZE_BAR, dpi=DPI)
    apply_theme(fig, ax, bg, txt)
    y = np.arange(len(cats))
    ax.barh(y, vals, color=accent, edgecolor=txt, linewidth=0.0)
    ax.set_yticks(y)
    ax.set_yticklabels(cats, color=txt, fontsize=12)
    ax.set_xlabel(""); ax.set_ylabel("")
    set_wrapped_title(ax, title, txt)
    fig.tight_layout(); ensure_dir(os.path.dirname(out_path))
    fig.savefig(out_path, facecolor=fig.get_facecolor(), bbox_inches="tight"); plt.close(fig)

def render_line(x: np.ndarray, y: np.ndarray, title: str, out_path: str,
                accent: str, bg: str, txt: str, fill: bool=False):
    fig, ax = plt.subplots(figsize=SIZE_LINE, dpi=DPI)
    apply_theme(fig, ax, bg, txt)
    if fill:
        ax.fill_between(x, y, color=accent, alpha=0.9, step=None, zorder=2)
        ax.plot(x, y, color=accent, linewidth=3.2, zorder=3)
    else:
        ls = random.choice(["-", "--"])
        ax.plot(x, y, linestyle=ls, color=accent, linewidth=3.2)
    ax.set_xlabel(""); ax.set_ylabel("")
    set_wrapped_title(ax, title, txt)
    fig.tight_layout(); ensure_dir(os.path.dirname(out_path))
    fig.savefig(out_path, facecolor=fig.get_facecolor(), bbox_inches="tight"); plt.close(fig)

# =================== PIPELINE ===================
def render_one(csv_path: str, idx: int, ctype: str) -> Optional[str]:
    df = safe_read_csv(csv_path)
    if df is None or df.empty: return None

    title = datapackage_title(csv_path)
    accent = pick_css4_accent()
    bg = pick_background()
    txt = contrast_text_color(bg)

    base = os.path.splitext(os.path.basename(csv_path))[0]
    out_path = os.path.join(OUTPUT_DIR, f"{base}_{idx:05}_{ctype}.png")

    if ctype in ("vbar","hbar"):
        picked = pick_bar_series(df)
        if not picked: return None
        cats, vals = picked
        if len(cats) < MIN_BARS: return None
        if ctype == "vbar":
            render_vbar(cats, vals, title, out_path, accent, bg, txt)
        else:
            render_hbar(cats, vals, title, out_path, accent, bg, txt)
        return out_path

    ts = pick_timeseries(df)
    if not ts: return None
    x, y = ts
    if len(y) < MIN_POINTS: return None
    render_line(x, y, title, out_path, accent, bg, txt, fill=(ctype=="area"))
    return out_path

def generate_images(n: int = N_IMAGES):
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED); np.random.seed(RANDOM_SEED)

    ensure_dir(OUTPUT_DIR)
    csvs = find_csvs(ROOT_FOLDER)
    print(f"Found {len(csvs)} CSVs.")
    if not csvs:
        print("No CSVs found. Update ROOT_FOLDER.")
        return

    results = []
    i = 0
    scan_cap = n * 200
    while len(results) < n and i < scan_cap:
        csv_path = csvs[i % len(csvs)]
        ctype = CHART_TYPES[len(results) % len(CHART_TYPES)]  # cycle evenly
        try:
            out = render_one(csv_path, len(results), ctype)
            if out:
                results.append(out)
                print(f"  ✓ {ctype:4s} -> {out}")
        except Exception as e:
            print(f"  - skip {os.path.basename(csv_path)}: {e}")
            gc.collect()
        i += 1

    print(f"\nDone. Generated {len(results)} charts → {OUTPUT_DIR}")

# =================== MAIN ===================
if __name__ == "__main__":
    generate_images()
