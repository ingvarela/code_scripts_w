#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pew_pies.py — Robust Pew-style pie/donut chart generator from CSV files.

Usage examples:
  # Minimal: pick columns by name
  python pew_pies.py data.csv --labels "Category" --values "Count"

  # Donut, aggregate small slices under 3%, and save SVG too
  python pew_pies.py data.csv --labels Category --values Count \
      --donut --other-threshold 0.03 --fmt png svg

  # Many files using a glob, consistent colors across charts
  python pew_pies.py "surveys/*.csv" --labels Answer --values Responses --out charts/

  # If your values are already percentages (0-100 or 0-1), tell the script
  python pew_pies.py poll.csv --labels Option --values Share --values-are-percent

  # Choose top N and bucket the rest as Other
  python pew_pies.py poll.csv --labels Option --values Share --topn 8

  # Tweak labeling and figure size
  python pew_pies.py poll.csv --labels Option --values Share \
      --min-label-pct 0.02 --w 1400 --h 950 --title "How people feel about X"

"""

import argparse
import csv
import math
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from textwrap import wrap

# ---------- Aesthetic defaults (Pew-ish) ----------
matplotlib.rcParams.update({
    "figure.dpi": 140,
    "savefig.dpi": 300,
    "font.size": 12,
    "font.family": "DejaVu Sans",
    "axes.axisbelow": True,
    "axes.titleweight": "semibold",
    "text.color": "#222222",
})

# Colorblind-friendly palette (muted, Pew-ish vibe)
PEW_PALETTE = [
    "#4C78A8", "#F58518", "#54A24B", "#EECA3B", "#B279A2",
    "#FF9DA6", "#9D755D", "#BAB0AC", "#72B7B2", "#E45756",
    "#F2CF5B", "#60ACFC", "#5C8EAA", "#B3DE69", "#C2C2F0",
]

def stable_color_map(labels: List[str]) -> Dict[str, str]:
    """
    Deterministically map labels to colors so charts stay consistent across runs/files.
    """
    cmap = {}
    for i, lab in enumerate(sorted(set(labels), key=lambda s: s.lower())):
        cmap[lab] = PEW_PALETTE[i % len(PEW_PALETTE)]
    return cmap

def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        # Fallbacks that often help with messy CSVs
        return pd.read_csv(path, encoding="latin-1")
    except Exception as e:
        raise RuntimeError(f"Failed to read {path}: {e}")

def coerce_numeric(series: pd.Series) -> pd.Series:
    # Convert strings like "1,234" or "12.5%" to numbers
    s = series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False)
    return pd.to_numeric(s, errors="coerce")

def prepare_data(df: pd.DataFrame,
                 label_col: str,
                 value_col: str,
                 values_are_percent: bool,
                 topn: int,
                 other_threshold: float,
                 dropna_labels: bool) -> Tuple[pd.DataFrame, float]:
    # Select & sanitize
    if label_col not in df.columns:
        # allow integer index choice
        try:
            label_col = df.columns[int(label_col)]
        except Exception:
            raise ValueError(f"Label column '{label_col}' not found.")
    if value_col not in df.columns:
        try:
            value_col = df.columns[int(value_col)]
        except Exception:
            raise ValueError(f"Value column '{value_col}' not found.")

    out = df[[label_col, value_col]].copy()
    if dropna_labels:
        out = out[out[label_col].notna()]
    out[label_col] = out[label_col].astype(str).str.strip()

    vals = coerce_numeric(out[value_col])
    if values_are_percent:
        # Accept 0-100 or 0-1
        vals = vals.where(vals <= 1.0000001, vals / 100.0)
    else:
        # Counts -> normalize later
        pass

    out[value_col] = vals
    out = out.dropna(subset=[value_col])

    # Aggregate duplicates
    out = out.groupby(label_col, as_index=False, sort=False)[value_col].sum()

    # Normalize to percentages
    if values_are_percent:
        # In case they don't sum to 1.0, renormalize for display
        total = out[value_col].sum()
        if total <= 0:
            raise ValueError("Sum of percentages is non-positive.")
        out[value_col] = out[value_col] / total
    else:
        total = out[value_col].sum()
        if total <= 0:
            raise ValueError("Sum of values is non-positive.")
        out[value_col] = out[value_col] / total

    # Apply topn if requested
    if topn and topn > 0 and len(out) > topn:
        out = out.sort_values(value_col, ascending=False)
        head = out.iloc[:topn].copy()
        tail = out.iloc[topn:]
        other_share = tail[value_col].sum()
        if other_share > 0:
            head = pd.concat([head, pd.DataFrame({label_col: ["Other"], value_col: [other_share]})],
                             ignore_index=True)
        out = head

    # Apply threshold into "Other"
    if other_threshold and other_threshold > 0:
        major = out[out[value_col] >= other_threshold].copy()
        minor = out[out[value_col] < other_threshold]
        other_share = minor[value_col].sum()
        if other_share > 0:
            major = pd.concat([major, pd.DataFrame({label_col: ["Other"], value_col: [other_share]})],
                              ignore_index=True)
        out = major

    # Re-sort by share descending for better visuals
    out = out.sort_values(value_col, ascending=False).reset_index(drop=True)
    return out, float(out[value_col].sum())  # should be ~1.0

def wrap_labels(labels: List[str], width: int = 20) -> List[str]:
    return ["\n".join(wrap(str(lab), width=width)) if lab else "" for lab in labels]

def autopct_factory(min_label_pct: float):
    def fmt(pct):
        return f"{pct:.0f}%" if pct >= min_label_pct * 100 else ""
    return fmt

def draw_pie(labels: List[str],
             shares: List[float],
             title: str,
             outfile_base: Path,
             donut: bool,
             cmap: Dict[str, str],
             w_px: int,
             h_px: int,
             formats: List[str],
             min_label_pct: float,
             show_values_outside: bool,
             title_sub: str = "") -> None:

    # Figure size in inches (pixels / 100 for a nice balance with dpi=100-ish in savefig)
    fig_w = w_px / 100.0
    fig_h = h_px / 100.0
    fig = plt.figure(figsize=(fig_w, fig_h))
    ax = fig.add_subplot(111)

    colors = [cmap.get(l, PEW_PALETTE[i % len(PEW_PALETTE)]) for i, l in enumerate(labels)]

    # Pew vibe: thin white borders, muted colors, tidy labels
    wedgeprops = dict(linewidth=1, edgecolor="white")
    textprops = dict(color="#222222")

    # Label layout
    labeldistance = 1.08 if show_values_outside else 1.0
    pctdistance = 0.75 if not show_values_outside else 0.85

    # Donut ring width
    radius = 1.0
    width = 0.45 if donut else None

    patches, texts, autotexts = ax.pie(
        shares,
        labels=wrap_labels(labels, width=24) if show_values_outside else None,
        autopct=autopct_factory(min_label_pct),
        startangle=90,
        colors=colors,
        pctdistance=pctdistance,
        labeldistance=labeldistance,
        counterclock=False,
        wedgeprops=wedgeprops,
        textprops=textprops,
        radius=radius,
        normalize=True
    )

    if donut:
        centre_circle = plt.Circle((0, 0), radius - (width or 0.45), fc="white")
        ax.add_artist(centre_circle)

    # If labels outside, draw leader lines (Matplotlib handles basics)
    if show_values_outside:
        for t in texts:
            t.set_horizontalalignment("center")

    # Title styling
    if title:
        ax.set_title(title, fontsize=18, pad=18, weight="semibold")
        if title_sub:
            ax.text(0.5, 1.02, title_sub, transform=ax.transAxes,
                    ha="center", va="bottom", fontsize=11, color="#555")

    # Equal aspect so pie is circular
    ax.axis("equal")

    # Tighter layout
    plt.tight_layout()

    # Save
    for fmt in formats:
        path = outfile_base.with_suffix(f".{fmt.lower()}")
        fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)

def infer_title(path: Path, override: str = "") -> str:
    if override:
        return override
    # Use file stem in Title Case
    stem = re.sub(r"[_\-]+", " ", path.stem).strip()
    return stem.title() if stem else "Pie Chart"

def main():
    p = argparse.ArgumentParser(description="Generate Pew-style pie/donut charts from CSVs.")
    p.add_argument("inputs", nargs="+", help="CSV file(s) or quoted glob pattern.")
    p.add_argument("--labels", required=True, help="Label column name or 0-based index.")
    p.add_argument("--values", required=True, help="Value column name or 0-based index.")
    p.add_argument("--values-are-percent", action="store_true",
                   help="If values are already percentages (0-100 or 0-1).")
    p.add_argument("--topn", type=int, default=0,
                   help="Keep only the top N categories; bucket the rest as 'Other'.")
    p.add_argument("--other-threshold", type=float, default=0.0,
                   help="Bucket slices under this share into 'Other' (e.g., 0.03 for 3%).")
    p.add_argument("--min-label-pct", type=float, default=0.02,
                   help="Hide percentage labels smaller than this share (e.g., 0.02 for 2%).")
    p.add_argument("--donut", action="store_true", help="Render as donut chart.")
    p.add_argument("--outside-labels", action="store_true",
                   help="Place labels outside with leader lines (Pew-like).")
    p.add_argument("--title", default="", help="Override chart title.")
    p.add_argument("--subtitle", default="", help="Optional subtitle under the title.")
    p.add_argument("--fmt", nargs="+", default=["png"], choices=["png", "svg"],
                   help="Export format(s). Default: png")
    p.add_argument("--w", type=int, default=1200, help="Figure width in pixels.")
    p.add_argument("--h", type=int, default=850, help="Figure height in pixels.")
    p.add_argument("--out", default="", help="Output folder. Defaults next to each CSV.")
    p.add_argument("--suffix", default="", help="Suffix to append to output filename.")
    p.add_argument("--dropna-labels", action="store_true",
                   help="Drop rows where label is missing/NaN.")

    args = p.parse_args()

    # Expand globs manually for cross-platform behavior
    paths: List[Path] = []
    for inp in args.inputs:
        expanded = list(map(Path, sorted(Path().glob(inp) if any(ch in inp for ch in "*?[]") else [inp])))
        if not expanded:
            print(f"Warning: no files matched '{inp}'", file=sys.stderr)
        paths.extend(expanded)

    if not paths:
        print("No input files found. Exiting.", file=sys.stderr)
        sys.exit(2)

    # For consistent colors across all charts in the same run, collect all labels first
    all_labels: List[str] = []
    prepared: List[Tuple[Path, pd.DataFrame]] = []

    for path in paths:
        if not path.exists():
            print(f"Warning: missing file {path}", file=sys.stderr)
            continue
        try:
            df = read_csv(path)
            data, _ = prepare_data(
                df=df,
                label_col=args.labels,
                value_col=args.values,
                values_are_percent=args.values_are_percent,
                topn=args.topn,
                other_threshold=args.other_threshold,
                dropna_labels=args.dropna_labels
            )
            prepared.append((path, data))
            all_labels.extend(list(data.iloc[:, 0].astype(str)))
        except Exception as e:
            print(f"[SKIP] {path}: {e}", file=sys.stderr)

    if not prepared:
        print("No valid datasets to plot.", file=sys.stderr)
        sys.exit(3)

    cmap = stable_color_map(all_labels)

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for path, data in prepared:
        labels = data.iloc[:, 0].astype(str).tolist()
        shares = data.iloc[:, 1].astype(float).tolist()

        # Determine output filename
        base = path.with_suffix("")  # drop .csv
        if args.suffix:
            base = Path(str(base) + f"_{args.suffix}")
        if out_dir:
            base = out_dir / base.name

        title = infer_title(path, args.title)
        try:
            draw_pie(
                labels=labels,
                shares=shares,
                title=title,
                outfile_base=base,
                donut=args.donut,
                cmap=cmap,
                w_px=args.w,
                h_px=args.h,
                formats=[fmt.lower() for fmt in args.fmt],
                min_label_pct=max(0.0, float(args.min_label_pct)),
                show_values_outside=args.outside_labels,
                title_sub=args.subtitle
            )
            print(f"[OK] {base}")
        except Exception as e:
            print(f"[FAIL] {path}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
