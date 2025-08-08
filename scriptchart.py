# chartgen.py
import os
import io
import gc
import re
import json
import uuid
import hashlib
import random
import argparse
import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
import seaborn as sns

# ------------- Defaults (same as your originals) -------------
DEFAULT_ROOT = "C://Users//svs26//Desktop//MS COCO 2017//UREADER//owid-datasets-master//owid-datasets-master//datasets"
DEFAULT_OUT  = "ChartQA"
DEFAULT_N    = 20
DEFAULT_MAX_ROWS = 300

# Paleta OWID / Pew-like
owid_palette = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    "#bcbd22", "#17becf"
]

PLOT_STRATEGIES = [
    "single_vs_index",
    "horizontal_bar",
    "pie_chart",
    # Re-enable more here as you convert them to _txn style:
    # "transpose_multiline",
    # "scatter_pairs",
    # "correlation_heatmap",
    # "distributions",
    # "stacked_area",
]

# ============================================================
#                      Utilities & IO
# ============================================================

def crop_text_to_20_words(text: str) -> str:
    words = text.split()
    if len(words) <= 20:
        return text
    first_20 = ' '.join(words[:20])
    tail = ' '.join(words[20:28])
    dot = tail.find('.')
    return first_20 + ' ' + (tail if dot == -1 else tail[:dot + 1])

def get_metadata_for_csv(csv_path: str):
    folder = os.path.dirname(csv_path)
    dp = os.path.join(folder, "datapackage.json")
    if not os.path.exists(dp):
        return "Chart", "No description available"
    try:
        with open(dp, "r", encoding="utf-8") as f:
            data = json.load(f)
        title = crop_text_to_20_words(data.get("title", "Chart"))
        desc  = crop_text_to_20_words(data.get("description", ""))
        return title, desc
    except Exception:
        return "Chart", "No description available"

def get_distinct_colors(n):
    return sns.color_palette("PuBu", n)

def get_shuffled_colors(n):
    colors = get_distinct_colors(n)
    random.shuffle(colors)
    return colors

def get_random_fontsize():
    return random.choice([5, 6, 7, 8])

# ============================================================
#                        Tick Manager
# ============================================================

@dataclass
class TickSpec:
    kind: str                           # "numeric" | "datetime" | "categorical"
    axis: str                           # "x" | "y"
    locator: Optional[mticker.Locator] = None
    formatter: Optional[mticker.Formatter] = None
    positions: Optional[List[float]] = None
    labels: Optional[List[str]] = None

class TickManager:
    def __init__(self, max_ticks:int=6, thousands:bool=True, integer_only:bool=False):
        self.max_ticks = max_ticks
        self.thousands = thousands
        self.integer_only = integer_only

    def for_series(self, s: pd.Series, axis:str="x", prefer:str="auto", log:bool=False) -> TickSpec:
        if prefer == "categorical" or (prefer=="auto" and (s.dtype == "object" or s.dtype.name == "category")):
            cats = pd.Index(s.dropna().astype(str).unique())
            positions = np.arange(len(cats)).astype(float).tolist()
            labels = cats.tolist()
            return TickSpec(kind="categorical", axis=axis, positions=positions, labels=labels)

        if prefer == "datetime" or (prefer=="auto" and np.issubdtype(s.dropna().infer_objects().dtype, np.datetime64)):
            locator = mdates.AutoDateLocator(minticks=3, maxticks=self.max_ticks)
            formatter = mdates.ConciseDateFormatter(locator)
            return TickSpec(kind="datetime", axis=axis, locator=locator, formatter=formatter)

        # numeric
        if self.integer_only:
            locator = mticker.MaxNLocator(nbins=self.max_ticks, integer=True, prune=None)
        else:
            locator = mticker.MaxNLocator(nbins=self.max_ticks, prune=None)

        if self.thousands:
            def _fmt(x, pos):
                if float(x).is_integer():
                    return f"{int(x):,}"
                return f"{x:,.2f}"
            formatter = mticker.FuncFormatter(_fmt)
        else:
            formatter = mticker.ScalarFormatter(useOffset=False)
            formatter.set_powerlimits((-3, 4))

        return TickSpec(kind="numeric", axis=axis, locator=locator, formatter=formatter)

    def apply(self, ax, spec: TickSpec):
        axis = ax.xaxis if spec.axis == "x" else ax.yaxis
        if spec.kind in ("numeric", "datetime"):
            if spec.locator is not None:
                axis.set_major_locator(spec.locator)
            if spec.formatter is not None:
                axis.set_major_formatter(spec.formatter)
        elif spec.kind == "categorical":
            idx = 0 if spec.axis == "x" else 1
            if spec.positions is None or spec.labels is None:
                return
            if idx == 0:
                ax.set_xticks(spec.positions)
                ax.set_xticklabels(spec.labels)
            else:
                ax.set_yticks(spec.positions)
                ax.set_yticklabels(spec.labels)

# ============================================================
#                     Style & No-overlap Layout
# ============================================================

def apply_custom_style(ax, title=None, subtitle=None):
    ax.set_facecolor("white")
    ax.grid(True, axis='y', linestyle='--', alpha=0.4)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#999999')
    ax.spines['bottom'].set_color('#999999')
    ax.spines['left'].set_linewidth(0.8)
    ax.spines['bottom'].set_linewidth(0.8)

    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontname("DejaVu Sans")
        label.set_fontweight("bold")
        label.set_color("#333333")

    if title:
        ax.set_title(title, fontsize=10, pad=40, loc='center',
                     fontweight='bold', color="#222222", fontname="DejaVu Sans")

    if subtitle:
        import textwrap
        wrapped = textwrap.fill(subtitle, width=83)
        ax.text(0.5, 1.02, wrapped,
                transform=ax.transAxes,
                ha='center', va='bottom',
                fontsize=7, color='#555555', fontname="DejaVu Sans")

    # footer (source/license)
    ax.text(0, -0.40, "Our World In Data",
            fontsize=6, transform=ax.transAxes, ha='left', color='#444444', fontname="DejaVu Sans")
    ax.text(1, -0.40, "CC BY",
            fontsize=6, transform=ax.transAxes, ha='right', color='#888888', fontname="DejaVu Sans")

def _bbox(fig, artist):
    if artist is None:
        return None
    try:
        return artist.get_window_extent(renderer=fig.canvas.get_renderer())
    except Exception:
        return None

def _union_height(bboxes):
    bboxes = [b for b in bboxes if b is not None]
    if not bboxes: return 0
    y0 = min(b.y0 for b in bboxes); y1 = max(b.y1 for b in bboxes)
    return y1 - y0

def _union_width(bboxes):
    bboxes = [b for b in bboxes if b is not None]
    if not bboxes: return 0
    x0 = min(b.x0 for b in bboxes); x1 = max(b.x1 for b in bboxes)
    return x1 - x0

def wrap_ticklabels(ax, axis="x", width=12):
    import textwrap
    labs = ax.get_xticklabels() if axis == "x" else ax.get_yticklabels()
    for t in labs:
        s = t.get_text()
        if len(s) > width and " " in s:
            t.set_text("\n".join(textwrap.wrap(s, width=width)))
    if axis == "x":
        ax.set_xticklabels(labs)
    else:
        ax.set_yticklabels(labs)

def ensure_no_overlap(fig, ax, *, legend_outside=True, rotate_xticks_if_needed=True,
                      wrap_categorical_ticks=True, max_xticks=6, max_yticks=6,
                      min_fontsize=6, passes=3):
    # trim tick counts
    try:
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=max_xticks))
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=max_yticks))
    except Exception:
        pass

    # legend to the right
    if legend_outside and ax.get_legend():
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0.)

    if wrap_categorical_ticks:
        wrap_ticklabels(ax, "x", width=14)
        wrap_ticklabels(ax, "y", width=20)

    for _ in range(passes):
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        W, H = fig.get_size_inches() * fig.dpi

        # top: title + any subtitle above axes
        top_bboxes = []
        if ax.get_title(): top_bboxes.append(_bbox(fig, ax.title))
        top_texts = [t for t in ax.texts if t.get_position()[1] > 1.0 and t.get_transform() is ax.transAxes]
        top_bboxes += [_bbox(fig, t) for t in top_texts]

        # right: legend width (outside)
        leg = ax.get_legend()
        legend_w = 0
        if leg:
            lb = _bbox(fig, leg)
            if lb: legend_w = max(0, lb.width)

        # bottom: footer + xlabel
        bottom_texts = [t for t in ax.texts if t.get_position()[1] < 0 and t.get_transform() is ax.transAxes]
        bottom_bboxes = [_bbox(fig, t) for t in bottom_texts]
        xlabel_bbox = _bbox(fig, ax.xaxis.label)

        # left/right tick labels and y/x labels
        ytick_bboxes = [_bbox(fig, t) for t in ax.get_yticklabels() if t.get_visible()]
        ylabel_bbox = _bbox(fig, ax.yaxis.label)
        xtick_bboxes = [_bbox(fig, t) for t in ax.get_xticklabels() if t.get_visible()]

        # rotate x ticks if too wide
        if rotate_xticks_if_needed and xtick_bboxes:
            xt_total = sum(b.width for b in xtick_bboxes if b)
            axbb = ax.get_window_extent(renderer=r)
            if xt_total > 0.95 * axbb.width:
                for lbl in ax.get_xticklabels():
                    lbl.set_rotation(30)
                    lbl.set_ha("right")
                fig.canvas.draw()
                xtick_bboxes = [_bbox(fig, t) for t in ax.get_xticklabels() if t.get_visible()]

        top_px    = _union_height(top_bboxes)
        bottom_px = _union_height(bottom_bboxes) + (xlabel_bbox.height if xlabel_bbox else 0)
        left_px   = _union_width(ytick_bboxes + ([ylabel_bbox] if ylabel_bbox else []))
        right_px  = legend_w

        pad = 8
        top    = min(0.95, 1 - (top_px + pad) / H)
        bottom = max(0.06, (bottom_px + pad) / H)
        left   = max(0.08, (left_px + pad) / W)
        right  = min(0.92, 1 - (right_px + pad) / W)

        # degrade gracefully if squeezed
        if right <= left + 0.02:
            ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=max(max_xticks//2, 3)))
            right = min(0.92, left + 0.06)
        if top <= bottom + 0.02:
            ttl = ax.title
            if ttl and ttl.get_fontsize() > min_fontsize:
                ttl.set_fontsize(max(min_fontsize, ttl.get_fontsize() - 1))
            for t in top_texts:
                fs = t.get_fontsize()
                if fs > min_fontsize: t.set_fontsize(max(min_fontsize, fs - 1))
            top = min(0.95, max(top, bottom + 0.06))

        plt.subplots_adjust(left=left, right=right, top=top, bottom=bottom)

    fig.canvas.draw()

# ============================================================
#                      Exact-as-rendered OCR
# ============================================================

def collect_ocr_text(fig, ax, title=None, subtitle=None) -> str:
    fig.canvas.draw()
    parts = []
    seen = set()

    t = (ax.get_title() or "").strip()
    if t and t not in seen:
        parts.append(t); seen.add(t)

    if subtitle:
        s = subtitle.strip()
        if s and s not in seen:
            parts.append(s); seen.add(s)

    for lbl in ax.get_yticklabels():
        if lbl.get_visible():
            txt = lbl.get_text().strip()
            if txt and txt not in seen:
                parts.append(txt); seen.add(txt)

    yl = (ax.get_ylabel() or "").strip()
    if yl and yl not in seen:
        parts.append(yl); seen.add(yl)

    for lbl in ax.get_xticklabels():
        if lbl.get_visible():
            txt = lbl.get_text().strip()
            if txt and txt not in seen:
                parts.append(txt); seen.add(txt)

    xl = (ax.get_xlabel() or "").strip()
    if xl and xl not in seen:
        parts.append(xl); seen.add(xl)

    leg = ax.get_legend()
    if leg:
        for text in leg.get_texts():
            txt = text.get_text().strip()
            if txt and txt not in seen:
                parts.append(txt); seen.add(txt)

    footer = "Our World In Data CC BY"
    if footer not in seen:
        parts.append(footer)

    # Keep line breaks; if you prefer single line, join with " ".
    return "\n".join(parts) if parts else "[NO TEXT DETECTED]"

def validate_ticks_and_labels(fig, ax):
    fig.canvas.draw()
    xt = [t.get_text().strip() for t in ax.get_xticklabels() if t.get_visible()]
    yt = [t.get_text().strip() for t in ax.get_yticklabels() if t.get_visible()]
    # pies have no axes; if axis has data and both lists are empty, we reject
    has_axes = ax.has_data()
    if has_axes and not (any(xt) or any(yt)):
        raise RuntimeError("No visible tick labels.")

# ============================================================
#                   Atomic sample transactions
# ============================================================

@dataclass
class Paths:
    out_dir: Path
    tmp_dir: Path
    manifest: Path

def make_paths(output_folder: str) -> Paths:
    out = Path(output_folder)
    tmp = out / "_tmp"
    out.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    return Paths(out, tmp, out / "metadata.jsonl")

def atomic_write_bytes(tmp_path: Path, final_path: Path, data: bytes):
    tmp_path.write_bytes(data)
    os.replace(tmp_path, final_path)  # atomic on same volume

def atomic_write_jsonl(manifest: Path, rec: dict):
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(manifest, "a", encoding="utf-8") as mf:
        mf.write(line)
        mf.flush()
        os.fsync(mf.fileno())

def deterministic_seed(*parts) -> int:
    h = hashlib.sha256("||".join(map(str, parts)).encode("utf-8")).hexdigest()
    return int(h[:16], 16) % (2**32 - 1)

class SampleTxn:
    def __init__(self, paths: Paths, base_filename: str):
        self.paths = paths
        self.base = base_filename
        self.id = uuid.uuid4().hex
        self.image_tmp = paths.tmp_dir / f"{self.base}.{self.id}.png.tmp"
        self.image_final = paths.out_dir / f"{self.base}.png"
        self.ocr_text = None
        self.ok = False
        self.info = {}

    def commit_image(self, png_bytes: bytes):
        atomic_write_bytes(self.image_tmp, self.image_final, png_bytes)

    def set_info(self, **kvs):
        self.info.update(kvs)

    def set_ocr(self, text: str):
        self.ocr_text = (text or "").strip()

    def validate(self):
        if not self.image_final.exists() or self.image_final.stat().st_size == 0:
            raise RuntimeError("Image not written or zero size.")
        if not self.ocr_text:
            raise RuntimeError("Empty OCR text.")
        self.ok = True

    def record_manifest(self, manifest_path: Path):
        rec = {
            "id": self.id,
            "image": str(self.image_final.as_posix()),
            "ocr": self.ocr_text,
            **self.info
        }
        atomic_write_jsonl(manifest_path, rec)

    def abort_cleanup(self):
        try:
            if self.image_tmp.exists():
                self.image_tmp.unlink()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.ok:
            self.abort_cleanup()
        gc.collect()
        return False

def save_plot_safely_txn(fig, ax, txn: SampleTxn, ocr_text: str):
    fig.canvas.draw()  # finalize
    ensure_no_overlap(fig, ax, legend_outside=True, rotate_xticks_if_needed=True)
    fig.canvas.draw()
    buf = io.BytesIO()
    fig.savefig(buf, dpi=150, format="png", bbox_inches="tight")
    png_bytes = buf.getvalue()
    plt.close(fig)
    txn.set_ocr(ocr_text)
    txn.commit_image(png_bytes)

def load_done_set(manifest_path: Path):
    done = set()
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    done.add(Path(rec["image"]).stem)
                except Exception:
                    continue
    return done

# ============================================================
#                       Plot functions (_txn)
# ============================================================

TM_NUMERIC = TickManager(max_ticks=6, thousands=True, integer_only=False)

def plot_single_vs_index_txn(df, cols, title, subtitle):
    fig, ax = plt.subplots(figsize=(6, 3))
    fontsize = get_random_fontsize()

    col = cols[0]
    data = df[col].reset_index(drop=True)
    if len(data) == 0:
        raise RuntimeError("Empty series")

    segment_len = max(1, len(data) // 10)
    colors = get_shuffled_colors(10)
    for i in range(0, len(data), segment_len):
        end = min(i + segment_len, len(data))
        ax.plot(range(i, end), data[i:end], color=colors[(i // segment_len) % 10])

    ax.set_xlabel("Row Index", fontsize=fontsize)
    ax.set_ylabel(col, fontsize=fontsize)
    ax.tick_params(axis='x', labelsize=fontsize)
    ax.tick_params(axis='y', labelsize=fontsize)

    # centralized ticks
    x_series = pd.Series(np.arange(len(data)))
    TM_NUMERIC.apply(ax, TM_NUMERIC.for_series(x_series, axis="x", prefer="numeric"))
    TM_NUMERIC.apply(ax, TM_NUMERIC.for_series(df[col], axis="y", prefer="numeric"))

    apply_custom_style(ax, title=title, subtitle=subtitle)
    ensure_no_overlap(fig, ax, legend_outside=True, rotate_xticks_if_needed=True)

    fig.canvas.draw()
    ocr_text = collect_ocr_text(fig, ax, title=title, subtitle=subtitle)
    validate_ticks_and_labels(fig, ax)
    return fig, ax, ocr_text

def plot_horizontal_bar_chart_txn(df, cols, title, subtitle):
    col = cols[0]
    # categorical distribution
    counts = df[col].value_counts().sort_values(ascending=True)
    if counts.empty:
        raise RuntimeError("No data to plot for horizontal_bar")

    fig, ax = plt.subplots(figsize=(6, 4))
    fontsize = get_random_fontsize()
    colors = owid_palette[:len(counts)]

    ax.barh(counts.index.astype(str), counts.values, color=colors)
    ax.set_title(f"{col} distribution", fontsize=fontsize, loc='left')
    ax.set_xlabel("Count", fontsize=fontsize)
    ax.tick_params(axis='x', labelsize=fontsize)
    ax.tick_params(axis='y', labelsize=fontsize)

    # ticks: categories on Y, numeric on X
    TM_NUMERIC.apply(ax, TM_NUMERIC.for_series(pd.Series(counts.index.astype(str)), axis="y", prefer="categorical"))
    TM_NUMERIC.apply(ax, TM_NUMERIC.for_series(pd.Series(counts.values), axis="x", prefer="numeric"))

    apply_custom_style(ax, title=title, subtitle=subtitle)

    maxv = counts.values.max()
    for i, v in enumerate(counts.values):
        ax.text(v + maxv * 0.01, i, str(v), va='center', fontsize=max(fontsize-1, 5))

    ensure_no_overlap(fig, ax, legend_outside=False, rotate_xticks_if_needed=False)

    fig.canvas.draw()
    ocr_text = collect_ocr_text(fig, ax, title=title, subtitle=subtitle)
    validate_ticks_and_labels(fig, ax)
    return fig, ax, ocr_text

def plot_pie_chart_txn(df, cols, title, subtitle):
    col = cols[0]
    counts = df[col].value_counts()
    if len(counts) == 0:
        raise RuntimeError("No data to plot for pie")

    if len(counts) > 10:
        counts = counts[:10]

    fig, ax = plt.subplots(figsize=(5, 5))
    fontsize = get_random_fontsize()
    colors = owid_palette[:len(counts)]

    wedges, label_texts, autotexts = ax.pie(
        counts.values,
        labels=counts.index.astype(str),
        autopct='%1.1f%%',
        startangle=90,
        colors=colors,
        textprops={'fontsize': fontsize},
        labeldistance=1.15
    )

    ax.set_title(f"{col} distribution", fontsize=fontsize)
    apply_custom_style(ax, title=title, subtitle=subtitle)

    ensure_no_overlap(fig, ax, legend_outside=False, rotate_xticks_if_needed=False)

    # OCR for pie: use rendered texts (labels and percentages) + title/subtitle + footer
    fig.canvas.draw()
    pie_texts = []
    for t in ax.texts:
        txt = (t.get_text() or "").strip()
        if txt:
            pie_texts.append(txt)
    parts = []
    if ax.get_title():
        parts.append(ax.get_title())
    if subtitle:
        parts.append(subtitle)
    parts.extend(pie_texts)
    parts.append("Our World In Data CC BY")
    ocr_text = "\n".join(parts)  # keep line breaks

    return fig, ax, ocr_text

# ============================================================
#                 Strategy runner & main generator
# ============================================================

FALLBACK_STRATEGIES = PLOT_STRATEGIES[:]  # order shuffled per-sample

def try_plot_once(strategy, df, selected_cols, title, subtitle):
    if strategy == "single_vs_index":
        return plot_single_vs_index_txn(df, selected_cols, title, subtitle)
    elif strategy == "horizontal_bar":
        # for bar we need categorical; if none, coerce to string of binned numeric
        col = selected_cols[0]
        if pd.api.types.is_numeric_dtype(df[col]):
            # bin numeric into categories so we can draw a bar distribution
            bins = min(10, max(4, int(np.sqrt(len(df)))))
            b = pd.cut(df[col], bins=bins).astype(str)
            df = df.copy()
            df[col] = b
        return plot_horizontal_bar_chart_txn(df, [col], title, subtitle)
    elif strategy == "pie_chart":
        col = selected_cols[0]
        if pd.api.types.is_numeric_dtype(df[col]):
            bins = min(8, max(3, int(np.sqrt(len(df)))))
            b = pd.cut(df[col], bins=bins).astype(str)
            df = df.copy()
            df[col] = b
        return plot_pie_chart_txn(df, [col], title, subtitle)
    else:
        raise RuntimeError(f"Unknown strategy {strategy}")

def generate_images_from_csvs_robust(root_folder, output_folder, n=20, max_rows=300, retries=2):
    paths = make_paths(output_folder)
    done = load_done_set(paths.manifest)

    # discover CSVs
    csv_files = []
    for root, _, files in os.walk(root_folder):
        for file in files:
            if file.endswith(".csv"):
                csv_files.append(os.path.join(root, file))
    if not csv_files:
        print("⚠️ No CSV files found."); return

    total = 0
    i = 0
    while total < n:
        csv_path = csv_files[i % len(csv_files)]; i += 1
        title, subtitle = get_metadata_for_csv(csv_path)

        try:
            df = pd.read_csv(csv_path).dropna()
            if len(df) > max_rows:
                df = df.sample(n=max_rows, random_state=random.randint(0, 10**6)).sort_index()

            # pick numeric cols for line; for pie/bar we can coerce later if needed
            numeric_cols = df.select_dtypes(include='number').columns.tolist()
            candidate_cols = numeric_cols or df.columns.tolist()
            if len(candidate_cols) < 1:
                continue

            seed = deterministic_seed(csv_path, total, len(df))
            rng = random.Random(seed)
            # pick up to 2 cols
            pick_count = 2 if len(candidate_cols) >= 2 else 1
            selected_cols = rng.sample(candidate_cols, pick_count)
            strategies = FALLBACK_STRATEGIES[:]
            rng.shuffle(strategies)

            base_name = f"{Path(csv_path).stem}_{total:05d}"
            if base_name in done:
                continue

            with SampleTxn(paths, base_name) as txn:
                txn.set_info(source_csv=str(csv_path), title=title, subtitle=subtitle, cols=selected_cols)

                last_err = None
                for attempt in range(retries + 1):
                    for strategy in strategies:
                        try:
                            sub_seed = deterministic_seed(csv_path, total, strategy, attempt)
                            random.seed(sub_seed)
                            np.random.seed(sub_seed % (2**32 - 1))

                            fig, ax, ocr_text = try_plot_once(strategy, df, selected_cols, title, subtitle)
                            # validate axis text (pies skip via OCR content)
                            if strategy != "pie_chart":
                                validate_ticks_and_labels(fig, ax)

                            save_plot_safely_txn(fig, ax, txn, ocr_text)
                            txn.validate()
                            txn.record_manifest(paths.manifest)
                            total += 1
                            last_err = None
                            break  # committed
                        except Exception as e:
                            last_err = e
                            plt.close("all")
                            gc.collect()
                            continue
                    if last_err is None:
                        break
                if last_err is not None:
                    raise last_err

        except Exception as e:
            print(f"⚠️ Skipped {os.path.basename(csv_path)}: {e}")
            gc.collect()
            continue

    # Also write a legacy metadata.json (array) for compatibility
    try:
        arr = []
        with open(paths.manifest, "r", encoding="utf-8") as f:
            for line in f:
                arr.append(json.loads(line))
        with open(Path(output_folder) / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(arr, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

    print(f"\n✅ Done! {total} images generated.")
    print(f"📁 Manifest: {paths.manifest.as_posix()}")
    print(f"📁 metadata.json also written for compatibility.")

# ============================================================
#                            CLI
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="Robust chart generator with exact OCR and no-overlap layout.")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="Root folder with CSV datasets.")
    ap.add_argument("--out",  default=DEFAULT_OUT,  help="Output folder for images and metadata.")
    ap.add_argument("--n",    type=int, default=DEFAULT_N, help="Number of images to generate.")
    ap.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS, help="Max rows per CSV sample.")
    ap.add_argument("--retries", type=int, default=2, help="Retries per sample before moving on.")
    args = ap.parse_args()

    generate_images_from_csvs_robust(
        root_folder=args.root,
        output_folder=args.out,
        n=args.n,
        max_rows=args.max_rows,
        retries=args.retries
    )

if __name__ == "__main__":
    main()
