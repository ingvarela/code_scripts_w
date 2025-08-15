#!/usr/bin/env python3
"""
Scrape Pew Research Center pages for chart CSV downloads.

Examples:
  # Single fact sheet or article
  python pew_chart_csv_scraper.py --urls https://www.pewresearch.org/internet/fact-sheet/internet-broadband/ --out pew_charts

  # Multiple pages
  python pew_chart_csv_scraper.py --urls https://www.pewresearch.org/internet/fact-sheet/social-media/ https://www.pewresearch.org/short-reads/2024/02/05/8-charts-on-technology-use-around-the-world/

  # Also follow any internal /chart/... pages linked within starting pages
  python pew_chart_csv_scraper.py --urls https://www.pewresearch.org/internet/fact-sheet/internet-broadband/ --follow-chart-pages --sleep 1.0

Notes:
- Focuses on the *per-chart* "Download data as .csv" links that Pew includes on many pages.
- Keeps a registry.jsonl in the output folder with one record per attempt.
"""

import argparse
import json
import os
import re
import time
import urllib.parse as up
from typing import List, Set, Tuple

import requests
from bs4 import BeautifulSoup

PEW_HOST = "www.pewresearch.org"
UA = "pew-chart-scraper/1.0 (+https://www.pewresearch.org/)"

CSV_TEXT_PAT = re.compile(r"\bdownload\s+data\s+as\s+\.?csv\b", re.I)
CSV_EXT_PAT = re.compile(r"\.csv(\?.*)?$", re.I)
CHART_PATH_PAT = re.compile(r"^/chart/[^?#]+", re.I)

def is_pew_url(url: str) -> bool:
    try:
        p = up.urlparse(url)
        return (p.netloc.lower().endswith("pewresearch.org"))
    except Exception:
        return False

def norm_url(base: str, href: str) -> str:
    return up.urljoin(base, href)

def fetch(session: requests.Session, url: str, retries=3, backoff=2.0, timeout=60):
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, headers={"User-Agent": UA}, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(backoff * attempt)
                continue
            r.raise_for_status()
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(backoff * attempt)
                continue
            raise
    if last:
        raise last

def find_csv_links(html: str, base_url: str) -> List[Tuple[str, str]]:
    """
    Return list of tuples (csv_url, label) found in the page.
    We detect:
      - anchors whose text looks like "Download data as .csv"
      - anchors with href ending in .csv
    """
    out = []
    soup = BeautifulSoup(html, "lxml")

    # 1) Text-based detection: "Download data as .csv"
    for a in soup.find_all("a"):
        text = (a.get_text() or "").strip()
        href = a.get("href")
        if not href:
            continue
        if CSV_TEXT_PAT.search(text):
            url = norm_url(base_url, href)
            out.append((url, text))

    # 2) Extension-based detection: direct .csv links
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        if CSV_EXT_PAT.search(href):
            url = norm_url(base_url, href)
            text = (a.get_text() or "CSV").strip()
            out.append((url, text))

    # De-dupe while preserving order
    seen = set()
    deduped = []
    for url, label in out:
        if url not in seen:
            seen.add(url)
            deduped.append((url, label))
    return deduped

def find_internal_chart_pages(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    found = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        url = norm_url(base_url, href)
        if not is_pew_url(url):
            continue
        p = up.urlparse(url)
        if CHART_PATH_PAT.search(p.path or ""):
            found.append(url)
    # de-dupe
    seen = set()
    out = []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")

def save_csv(text: str, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

def main():
    ap = argparse.ArgumentParser(description="Scrape Pew pages for chart CSV downloads.")
    ap.add_argument("--urls", nargs="*", default=[], help="Starting Pew page URLs (articles, fact sheets, etc.).")
    ap.add_argument("--out", default="pew_charts", help="Output folder for CSV + registry.jsonl")
    ap.add_argument("--follow-chart-pages", action="store_true",
                    help="Also follow /chart/... pages discovered on the starting pages to collect their CSVs.")
    ap.add_argument("--sleep", type=float, default=0.8, help="Delay between HTTP requests (seconds).")
    ap.add_argument("--retries", type=int, default=3, help="Retries for transient errors.")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    registry_path = os.path.join(args.out, "registry.jsonl")

    visited_pages: Set[str] = set()
    collected_csvs: Set[str] = set()

    with requests.Session() as sess, open(registry_path, "a", encoding="utf-8") as reg:
        # Crawl each starting URL
        to_visit = list(dict.fromkeys(args.urls))  # preserve order, de-dupe

        while to_visit:
            page_url = to_visit.pop(0)
            if page_url in visited_pages:
                continue
            visited_pages.add(page_url)

            if not is_pew_url(page_url):
                print(f"[SKIP] Non-Pew URL: {page_url}")
                continue

            try:
                r = fetch(sess, page_url, retries=args.retries)
                html = r.text
            except Exception as e:
                print(f"[WARN] Failed to fetch page: {page_url} -> {e}")
                reg.write(json.dumps({"page_url": page_url, "status": "error", "error": str(e)}) + "\n")
                time.sleep(args.sleep)
                continue

            # 1) Collect CSVs on this page
            csvs = find_csv_links(html, page_url)
            for csv_url, label in csvs:
                if csv_url in collected_csvs:
                    reg.write(json.dumps({"page_url": page_url, "csv_url": csv_url, "status": "exists"}) + "\n")
                    continue

                # Build filename: base on page slug + hash-like short
                p = up.urlparse(csv_url)
                # Try to infer a nice name
                base_slug = slugify( (up.urlparse(page_url).path or "/").strip("/").replace("/", "__") or "root" )
                leaf = os.path.basename(p.path) or "data.csv"
                out_name = f"{base_slug}__{leaf}"
                out_path = os.path.join(args.out, out_name)

                if os.path.exists(out_path):
                    collected_csvs.add(csv_url)
                    reg.write(json.dumps({"page_url": page_url, "csv_url": csv_url, "csv": out_path, "status": "exists"}) + "\n")
                    continue

                try:
                    rcsv = fetch(sess, csv_url, retries=args.retries)
                    if "text/csv" in rcsv.headers.get("Content-Type", "").lower() or rcsv.text.startswith(("Year,", "YEAR,", "time,")):
                        save_csv(rcsv.text, out_path)
                    else:
                        # Save anyway; some endpoints serve CSV with generic content-type
                        save_csv(rcsv.text, out_path)
                    collected_csvs.add(csv_url)
                    print(f"[OK] CSV -> {out_path}")
                    reg.write(json.dumps({"page_url": page_url, "csv_url": csv_url, "csv": out_path, "status": "ok"}) + "\n")
                except Exception as e:
                    print(f"[ERR] CSV {csv_url} -> {e}")
                    reg.write(json.dumps({"page_url": page_url, "csv_url": csv_url, "status": "error", "error": str(e)}) + "\n")

                time.sleep(args.sleep)

            # 2) Optionally discover internal /chart/... pages and queue them
            if args.follow_chart_pages:
                chart_pages = find_internal_chart_pages(html, page_url)
                for u in chart_pages:
                    if u not in visited_pages and u not in to_visit:
                        to_visit.append(u)

            time.sleep(args.sleep)

if __name__ == "__main__":
    main()
