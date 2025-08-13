#!/usr/bin/env python3
"""
Scrape OWID Grapher charts from pages listed in a specific Data catalog (with pagination).

- Paginates the catalog (?page=2,3,...) until no results (or a max page cap).
- Extracts each catalog item's page link.
- On each page, finds Grapher iframes and downloads PNG/SVG via export endpoints.
- Deduplicates and logs metadata (CSV). Resumable.

Designed to run cleanly in Spyder/IPython and in normal Python.
"""

import asyncio
import csv
import hashlib
import os
import re
import sys
import threading
import urllib.parse as up
from dataclasses import dataclass
from typing import Optional, Set, Tuple, Dict, List

import httpx
from bs4 import BeautifulSoup

# ===================== USER DEFAULTS (edit these if you want) =====================
# If you just click "Run" in Spyder, these defaults are used unless you pass CLI args.
DEFAULT_CATALOG = "https://ourworldindata.org/data?topics=Poverty+and+Economic+Development~Migration"
DEFAULT_OUT_DIR = "charts_poverty_migration"
DEFAULT_FMT = "png"           # "png" or "svg"
DEFAULT_CONCURRENCY = 8
DEFAULT_DELAY = 0.25          # seconds between requests (politeness)
DEFAULT_TIMEOUT = 45.0        # HTTP timeout
DEFAULT_MAX_CATALOG_PAGES = None  # e.g. 10 to cap; None to auto-stop when empty
DEFAULT_RESUME = True
# ================================================================================

BASE = "https://ourworldindata.org"
USER_AGENT = "OWID-Chart-Scraper/1.2 (+https://github.com/)"

# ---------------------------- Helpers ----------------------------

def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-")
    return s or "chart"

def looks_like_grapher_iframe(src: str) -> bool:
    return src.startswith(f"{BASE}/grapher/") or src.startswith("/grapher/")

def absolutize(url: str) -> str:
    return up.urljoin(BASE + "/", url)

def parse_slug_and_query(iframe_src: str) -> Tuple[str, str, Dict[str, List[str]]]:
    parsed = up.urlparse(iframe_src)
    parts = [p for p in parsed.path.split("/") if p]
    slug = parts[-1] if parts else "chart"
    qs = parsed.query or ""
    qd = up.parse_qs(qs, keep_blank_values=True)
    return slug, qs, qd

def normalize_query(qd: Dict[str, List[str]]) -> str:
    items = []
    for k in sorted(qd.keys()):
        vals = sorted(v for v in qd[k])
        for v in vals:
            items.append(f"{k}={v}")
    return "&".join(items)

def export_url_from_iframe(iframe_src: str, fmt: str) -> str:
    fmt = fmt.lower()
    if fmt not in {"png", "svg"}:
        raise ValueError("fmt must be png or svg")

    parsed = up.urlparse(iframe_src)
    base_no_ext = re.sub(r"(\.png|\.svg)$", "", parsed.path)
    path_with_ext = base_no_ext + f".{fmt}"

    qparams = up.parse_qs(parsed.query or "", keep_blank_values=True)
    qparams.setdefault("download-format", [fmt])

    flat = []
    for k in sorted(qparams.keys()):
        for v in qparams[k]:
            flat.append((k, v))
    norm_query = up.urlencode(flat, doseq=True)

    new = parsed._replace(path=path_with_ext, query=norm_query)
    return up.urlunparse(new)

# ---------------------------- Data Models ----------------------------

@dataclass(frozen=True)
class ChartRef:
    page_url: str
    iframe_src: str
    slug: str
    norm_query: str
    export_url: str
    filename: str

# ---------------------------- Parsers ----------------------------

def extract_catalog_links(html: str) -> List[str]:
    """
    From a catalog page, return the list of item page URLs to scan for charts.
    Only take links within <main>, ignore /grapher, static assets, and /data.
    """
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup

    urls: List[str] = []
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue
        absu = absolutize(href)
        if not absu.startswith(BASE):
            continue
        parsed = up.urlparse(absu)
        path = parsed.path or "/"

        # Filter out non-content
        if path.startswith("/grapher/") or path.startswith("/owid-static/"):
            continue
        if path == "/data":
            continue
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.fragment:
            continue
        # Skip file-like links
        if re.search(r"\.[a-zA-Z0-9]{2,4}$", path):
            continue

        # Normalize: strip query/fragment for target content pages
        cleaned = up.urlunparse(parsed._replace(query="", fragment=""))
        urls.append(cleaned)

    # Dedupe preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_grapher_iframes(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    srcs = []
    for iframe in soup.find_all("iframe"):
        src = (iframe.get("src") or "").strip()
        if not src:
            continue
        absu = absolutize(src)
        if looks_like_grapher_iframe(absu):
            srcs.append(absu)
    # Dedupe preserve order
    seen = set()
    out = []
    for s in srcs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

# ---------------------------- Scraper ----------------------------

class CatalogGrapherScraper:
    def __init__(
        self,
        catalog_url: str,
        out_dir: str = DEFAULT_OUT_DIR,
        fmt: str = DEFAULT_FMT,
        concurrency: int = DEFAULT_CONCURRENCY,
        per_request_delay: float = DEFAULT_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        max_catalog_pages: Optional[int] = DEFAULT_MAX_CATALOG_PAGES,
        resume: bool = DEFAULT_RESUME,
    ):
        self.catalog_url = catalog_url
        self.out_dir = out_dir
        self.img_dir = os.path.join(out_dir, "images")
        self.meta_path = os.path.join(out_dir, "charts_metadata.csv")
        self.fmt = fmt.lower()
        self.sem = asyncio.Semaphore(concurrency)
        self.delay = per_request_delay
        self.timeout = timeout
        self.max_catalog_pages = max_catalog_pages
        self.resume = resume

        os.makedirs(self.img_dir, exist_ok=True)
        if not os.path.exists(self.meta_path):
            with open(self.meta_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "page_url",
                    "iframe_src",
                    "export_url",
                    "filename",
                    "slug",
                    "query_normalized",
                    "catalog_source",
                ])

        self.already: Set[str] = self._load_already()

    def _load_already(self) -> Set[str]:
        seen = set()
        if self.resume and os.path.exists(self.meta_path):
            with open(self.meta_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    seen.add(row["export_url"])
        return seen

    def _filename_for(self, slug: str, norm_query: str) -> str:
        h = hashlib.sha1(norm_query.encode("utf-8")).hexdigest()[:8] if norm_query else "base"
        base = f"{slug}-{h}.{self.fmt}"
        return slugify(base)

    def _page_url_for(self, base_url: str, page_num: int) -> str:
        """Add or replace the 'page' query parameter."""
        p = up.urlparse(base_url)
        q = up.parse_qs(p.query, keep_blank_values=True)
        if page_num <= 1:
            q.pop("page", None)
        else:
            q["page"] = [str(page_num)]
        new_query = up.urlencode([(k, v) for k, vals in q.items() for v in vals])
        return up.urlunparse(p._replace(query=new_query))

    async def run(self):
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=self.timeout,
            limits=limits,
        ) as client:
            # Crawl catalog pages (pagination)
            catalog_pages: List[Tuple[str, List[str]]] = []
            page = 1
            empty_streak = 0
            while True:
                if self.max_catalog_pages and page > self.max_catalog_pages:
                    break
                url = self._page_url_for(self.catalog_url, page)
                try:
                    async with self.sem:
                        await asyncio.sleep(self.delay)
                        r = await client.get(url)
                        if r.status_code in (404, 410):
                            break
                        r.raise_for_status()
                except Exception as e:
                    print(f"[CATALOG FAIL] {url} -> {e}", file=sys.stderr)
                    break

                links = extract_catalog_links(r.text)
                print(f"Catalog page {page}: found {len(links)} candidate pages")
                catalog_pages.append((url, links))

                if len(links) == 0:
                    empty_streak += 1
                else:
                    empty_streak = 0
                # Heuristic stop: two consecutive empty pages -> no more results
                if empty_streak >= 2:
                    break

                # If there's a rel="next" we could also rely on it; this heuristic is enough.
                page += 1

            # Collect & dedupe targets
            targets: List[str] = []
            seen_links: Set[str] = set()
            for _, links in catalog_pages:
                for u in links:
                    if u not in seen_links:
                        seen_links.add(u)
                        targets.append(u)

            print(f"Total unique target pages to scan: {len(targets)}")

            # Visit each target and download charts
            tasks = [asyncio.create_task(self.process_target_page(client, src_catalog, url))
                     for (src_catalog, links) in catalog_pages
                     for url in links]

            processed = 0
            for t in asyncio.as_completed(tasks):
                await t
                processed += 1
                if processed % 20 == 0:
                    print(f"Processed {processed}/{len(tasks)} target pages...")

    async def process_target_page(self, client: httpx.AsyncClient, source_catalog: str, page_url: str):
        try:
            async with self.sem:
                await asyncio.sleep(self.delay)
                r = await client.get(page_url)
                r.raise_for_status()
                html = r.text
        except Exception as e:
            print(f"[PAGE FAIL] {page_url} -> {e}", file=sys.stderr)
            return

        iframe_srcs = extract_grapher_iframes(html)
        if not iframe_srcs:
            return

        for iframe_src in iframe_srcs:
            await self.download_chart(client, source_catalog, page_url, iframe_src)

    async def download_chart(self, client: httpx.AsyncClient, source_catalog: str, page_url: str, iframe_src: str):
        if not looks_like_grapher_iframe(iframe_src):
            return

        slug, _qs, qd = parse_slug_and_query(iframe_src)
        norm_query = normalize_query(qd)
        export_url = export_url_from_iframe(iframe_src, self.fmt)

        if export_url in self.already:
            return

        filename = self._filename_for(slug, norm_query)
        dest = os.path.join(self.img_dir, filename)

        try:
            async with self.sem:
                await asyncio.sleep(self.delay)
                resp = await client.get(export_url)
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    f.write(resp.content)
        except Exception as e:
            print(f"[DL FAIL] {export_url} -> {e}", file=sys.stderr)
            return

        self._append_meta(ChartRef(
            page_url=page_url,
            iframe_src=iframe_src,
            slug=slug,
            norm_query=norm_query,
            export_url=export_url,
            filename=filename,
        ), source_catalog)
        self.already.add(export_url)
        print(f"Saved {filename}  ←  {page_url}")

    def _append_meta(self, ref: ChartRef, source_catalog: str):
        os.makedirs(self.out_dir, exist_ok=True)
        with open(self.meta_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([ref.page_url, ref.iframe_src, ref.export_url, ref.filename, ref.slug, ref.norm_query, source_catalog])

# ---------------------------- CLI & Spyder Entry ----------------------------

def parse_args(argv: List[str]):
    """
    CLI parser that also supports sensible defaults so you can just click Run in Spyder.
    """
    import argparse
    ap = argparse.ArgumentParser(description="Scrape OWID Grapher charts from a specific Data catalog (with pagination).")
    ap.add_argument("--catalog", default=DEFAULT_CATALOG, help="Catalog URL with filters")
    ap.add_argument("--out", default=DEFAULT_OUT_DIR, help="Output directory")
    ap.add_argument("--fmt", default=DEFAULT_FMT, choices=["png", "svg"], help="Image format")
    ap.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Max concurrent requests")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between requests in seconds")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout seconds")
    ap.add_argument("--max-catalog-pages", type=int, default=DEFAULT_MAX_CATALOG_PAGES, help="Max paginated catalog pages to scan (optional)")
    ap.add_argument("--no-resume", action="store_true", help="Do not resume; ignore existing metadata file")
    return ap.parse_args(argv)

async def main_async():
    args = parse_args(sys.argv[1:])
    scraper = CatalogGrapherScraper(
        catalog_url=args.catalog,
        out_dir=args.out,
        fmt=args.fmt,
        concurrency=args.concurrency,
        per_request_delay=args.delay,
        timeout=args.timeout,
        max_catalog_pages=args.max_catalog_pages,
        resume=not args.no_resume,
    )
    await scraper.run()

def _run_in_new_thread():
    """Run a fresh asyncio loop in a separate thread (Spyder-safe fallback)."""
    def target():
        asyncio.run(main_async())
    t = threading.Thread(target=target, daemon=False)
    t.start()
    t.join()

def main():
    """
    Works in:
      - Normal Python (uses asyncio.run)
      - Spyder/Jupyter/IPython (falls back to running a fresh loop in a separate thread)
    """
    try:
        asyncio.run(main_async())
    except RuntimeError as e:
        msg = str(e)
        if "asyncio.run() cannot be called" in msg or "already running" in msg:
            # Spyder/IPython: start a fresh loop in a dedicated thread
            try:
                import nest_asyncio  # not strictly required with thread fallback, but harmless
                nest_asyncio.apply()
            except Exception:
                pass
            _run_in_new_thread()
        else:
            raise

if __name__ == "__main__":
    main()
