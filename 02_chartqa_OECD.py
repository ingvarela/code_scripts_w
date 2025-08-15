#!/usr/bin/env python3
"""
Scrape OECD pages for embedded Data Explorer charts and download their data via the OECD SDMX API.

Usage examples:
  # Single OECD page (e.g., an Insights article with embedded charts)
  python oecd_chart_scraper.py --urls https://www.oecd.org/en/insights/some-article.html --out data_oecd

  # Multiple pages
  python oecd_chart_scraper.py --urls https://www.oecd.org/en/insights/a.html https://www.oecd.org/en/insights/b.html

  # Directly pass a Data Explorer "vis" link (skips scraping the page)
  python oecd_chart_scraper.py --vis https://data-explorer.oecd.org/vis?df%5Bag%5D=OECD.SDD.NAD&df%5Bid%5D=DSD_NAAG%40DF_NAAG_I

  # Limit period and auto-plot quick checks
  python oecd_chart_scraper.py --urls https://www.oecd.org/en/insights/a.html --start 2015 --end 2024 --plot

Notes:
- Uses the official Data Explorer SDMX REST endpoint documented by OECD (Apr 30, 2025).
- Fetches CSV with labels. You can switch to JSON/XML by changing the 'format' parameter if desired.
"""

import argparse
import json
import os
import re
import time
import urllib.parse as up
from io import StringIO

import requests
from bs4 import BeautifulSoup

try:
    import pandas as pd
    import matplotlib.pyplot as plt
except Exception:
    pd = None
    plt = None

API_HOST = "https://sdmx.oecd.org/public/rest/data"  # Official host
CSV_FORMAT = "csvfilewithlabels"  # nice for downstream use
HEADERS = {"User-Agent": "oecd-chart-scraper/1.0 (https://oecd.org/)"}

FIND_VIS_RE = re.compile(r"https://data-explorer\.oecd\.org/vis\?[^\"'<> ]+", re.I)

def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")

def parse_vis_params(vis_url: str):
    """
    Parse a Data Explorer 'vis' URL and extract df[ag], df[id], and optional df[ds].
    Example vis:
      https://data-explorer.oecd.org/vis?df[ag]=OECD.SDD.NAD&df[id]=DSD_NAAG@DF_NAAG_I
    Returns dict or None.
    """
    q = up.urlparse(vis_url).query
    qs = up.parse_qs(q)
    # params like df[ag], df[id], df[ds]
    ag = qs.get("df[ag]", [None])[0]
    did = qs.get("df[id]", [None])[0]
    ds = qs.get("df[ds]", [None])[0]  # dataset version identifier (optional)
    if ag and did:
        return {"ag": ag, "id": did, "ds": ds}
    return None

def build_data_api_url(ag: str, dataset_id: str, start=None, end=None, dimension_at_obs="AllDimensions"):
    """
    Follows OECD doc syntax:
      {Host}/{Agency identifier},{Dataset identifier},{Dataset version}/<selection>
    We request 'all' selection by default, then attach CSV/labels and period filters.

    Ref: OECD data via API page (Apr 30, 2025) and examples. 
    """
    # Use 'all' selection to fetch unfiltered content unless caller wants to add filters later.
    base = f"{API_HOST}/{ag},{dataset_id}/all"
    params = {
        "format": CSV_FORMAT,
        "dimensionAtObservation": dimension_at_obs
    }
    if start:
        params["startPeriod"] = str(start)
    if end:
        params["endPeriod"] = str(end)
    return base + "?" + up.urlencode(params)

def fetch(url: str, session: requests.Session, retries=3, backoff=2.0, timeout=60):
    for attempt in range(1, retries + 1):
        r = session.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r
        if attempt < retries and r.status_code in (429, 500, 502, 503, 504):
            time.sleep(backoff * attempt)
            continue
        r.raise_for_status()
    raise RuntimeError("Unreachable")

def find_vis_links_in_page(page_url: str, session: requests.Session):
    r = fetch(page_url, session)
    html = r.text
    # catch both raw and HTML-escaped forms
    links = set(FIND_VIS_RE.findall(html))
    # also unescape in case we find percent-encoded versions inside attributes
    unescaped = set()
    for m in re.findall(r"https?://[^\s\"'>]+", html):
        if "data-explorer.oecd.org/vis" in m:
            try:
                unescaped.add(up.unquote(m))
            except Exception:
                pass
    return sorted(links.union(unescaped))

def save_csv(text: str, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

def maybe_plot_quick_png(csv_text: str, png_path: str, max_series=5):
    if pd is None or plt is None:
        return
    try:
        df = pd.read_csv(StringIO(csv_text))
        # Heuristic: look for time series columns typical of SDMX CSV
        time_col = None
        for cand in ["TIME_PERIOD", "time_period", "TIME", "Period"]:
            if cand in df.columns:
                time_col = cand
                break
        val_col = None
        for cand in ["OBS_VALUE", "obs_value", "Value", "value"]:
            if cand in df.columns:
                val_col = cand
                break
        if time_col and val_col:
            # Choose a grouping column to split series (LOCATION / REF_AREA / GEO / etc.)
            group_col = None
            for cand in ["LOCATION", "REF_AREA", "GEO", "Country", "Reference area"]:
                if cand in df.columns:
                    group_col = cand
                    break
            if group_col:
                # pick up to N series
                keep = df[group_col].dropna().unique().tolist()[:max_series]
                sub = df[df[group_col].isin(keep)].copy()
                # cast time to string for plotting on x-axis
                sub[time_col] = sub[time_col].astype(str)
                # simple multi-line plot
                for key, g in sub.groupby(group_col):
                    g = g.sort_values(time_col)
                    plt.figure()
                    plt.plot(g[time_col], g[val_col])
                    plt.title(f"{group_col}={key}")
                    plt.xticks(rotation=45, ha="right")
                    plt.tight_layout()
                    base_dir = os.path.dirname(png_path)
                    os.makedirs(base_dir, exist_ok=True)
                    out = png_path.replace(".png", f"_{slugify(str(key))}.png")
                    plt.savefig(out, dpi=140)
                    plt.close()
        # else: silently skip plotting if columns not found
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser(description="Scrape OECD pages for Data Explorer charts and download underlying CSV via official SDMX API.")
    ap.add_argument("--urls", nargs="*", default=[], help="OECD page URLs to scan for embedded charts (Data Explorer 'vis' links).")
    ap.add_argument("--vis", nargs="*", default=[], help="Optional: pass Data Explorer 'vis' URLs directly (skips page scraping).")
    ap.add_argument("--out", default="oecd_downloads", help="Output folder.")
    ap.add_argument("--start", help="startPeriod (e.g., 2015, 2015-Q1, 2015-M01).")
    ap.add_argument("--end", help="endPeriod (e.g., 2024, 2024-Q4).")
    ap.add_argument("--sleep", type=float, default=1.0, help="Delay between API calls (seconds) to be polite.")
    ap.add_argument("--retries", type=int, default=3, help="HTTP retries for transient errors.")
    ap.add_argument("--plot", action="store_true", help="Create quick sanity-check PNG charts from the downloaded CSV.")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    registry_path = os.path.join(args.out, "registry.jsonl")
    seen = set()

    with requests.Session() as sess, open(registry_path, "a", encoding="utf-8") as reg:
        # 1) Collect VIS links
        vis_links = []
        for url in args.urls:
            try:
                found = find_vis_links_in_page(url, sess)
                vis_links.extend(found)
                time.sleep(args.sleep)
            except Exception as e:
                print(f"[WARN] Failed to scan page: {url} -> {e}")

        vis_links.extend(args.vis)
        # dedupe
        vis_links = sorted(set(vis_links))

        # 2) For each vis link, extract df[ag], df[id], build API URL, download CSV
        for vis in vis_links:
            if vis in seen:
                continue
            seen.add(vis)

            meta = parse_vis_params(vis)
            if not meta:
                print(f"[SKIP] Could not parse identifiers from vis URL: {vis}")
                continue

            ag = meta["ag"]
            dataset_id = meta["id"]  # like DSD_NAAG@DF_NAAG_I
            ds_version = meta.get("ds")  # optional; if desired, you can add ',{ds_version}' to the path

            # Build API URL (unfiltered 'all')
            api_url = build_data_api_url(ag, dataset_id, start=args.start, end=args.end)

            # Prepare filenames
            base_name = slugify(f"{ag}__{dataset_id}")
            csv_path = os.path.join(args.out, f"{base_name}.csv")
            plot_path = os.path.join(args.out, f"{base_name}.png")

            # Skip if already downloaded
            if os.path.exists(csv_path):
                print(f"[SKIP] Exists: {csv_path}")
                # Still record to registry for traceability
                rec = {"vis_url": vis, "api_url": api_url, "csv": csv_path, "status": "exists"}
                reg.write(json.dumps(rec, ensure_ascii=False) + "\n")
                continue

            try:
                r = fetch(api_url, sess, retries=args.retries)
                save_csv(r.text, csv_path)
                print(f"[OK] CSV -> {csv_path}")

                if args.plot:
                    maybe_plot_quick_png(r.text, plot_path)

                rec = {"vis_url": vis, "api_url": api_url, "csv": csv_path, "status": "ok"}
                reg.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[ERR] {vis} -> {e}")
                rec = {"vis_url": vis, "api_url": api_url, "error": str(e), "status": "error"}
                reg.write(json.dumps(rec, ensure_ascii=False) + "\n")

            time.sleep(args.sleep)

if __name__ == "__main__":
    main()
