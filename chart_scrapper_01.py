#!/usr/bin/env python3
"""
Scrape OWID Grapher charts from pages listed in a specific Data catalog (with pagination).

Example catalog:
  https://ourworldindata.org/data?topics=Poverty+and+Economic+Development~Migration
Paginated pages:
  https://ourworldindata.org/data?topics=...&page=2

What it does:
- Paginates through the catalog
- Extracts content links from <main> (ignores header/footer)
- Fetches each page and downloads all embedded Grapher charts as PNG/SVG
- Writes images and a metadata CSV; deduplicates & can resume

Run in Spyder/IPython or CLI.

Install:
  pip install httpx==0.27.0 beautifulsoup4==4.12.2 lxml==5.2.2 nest_asyncio
"""

import asyncio
import csv
import hashlib
import os
import re
import sys
import urllib.parse as up
from dataclasses import dataclass
from typing import Optional, Set, Tuple, Dict, List

import httpx
from bs4 import BeautifulSoup

# ---------------------------- Config ----------------------------

BASE = "https://ourworldindata.org"
USER_AGENT = "OWID-Chart-Scraper/1.1 (+https://github.com/)"

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

def extract_catalog_links(html: str, base_catalog_url: str) -> List[str]:
    """
    From a catalog page, return the list of item page URLs we should scan for charts.
    Strategy: only take links within <main>, on-domain, not /grapher, not /owid-static,
    not the catalog page itself. This avoids header/footer noise.
    """
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup  # fallback to whole doc
    
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
        if path.startswith("/grapher/") or path.startswith("/owid-static/"):
            continue
        # Skip links that just navigate catalog pages/sorts
        if path == "/data":
            continue
        # Avoid anchors, mailto, etc.
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.fragment:
            continue
        # Heuristic: most content pages are single-segment or multi-segment slugs (no file ext)
        if re.search(r"\.[a-zA-Z0-9]{2,4}$", path):
            continue
        urls.append(up.urlunparse(parsed._replace(query="", fragment="")))

    # Dedupe, preserve order
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
        out_dir: str = "owid_catalog_charts",
        fmt: str = "png",
        concurrency: int = 8,
        per_request_delay: float = 0.25,
        timeout: float = 45.0,
        max_catalog_pages: Optional[int] = None,
        resume: bool = True,
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
            # page=1 usually same as no page param
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
            catalog_pages = []
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
                        # Stop on hard 404/410
                        if r.status_code in (404, 410):
                            break
                        r.raise_for_status()
                except Exception as e:
                    print(f"[CATALOG FAIL] {url} -> {e}", file=sys.stderr)
                    break

                links = extract_catalog_links(r.text, self.catalog_url)
                print(f"Catalog page {page}: found {len(links)} candidate pages")
                catalog_pages.append((url, links))

                if len(links) == 0:
                    empty_streak += 1
                else:
                    empty_streak = 0
                # Heuristic stop: two consecutive empty pages -> no more results
                if empty_streak >= 2:
                    break

                # Look for rel="next" to be polite if present
                soup = BeautifulSoup(r.text, "lxml")
                rel_next = soup.find("a", rel=lambda v: v and "next" in [x.lower() for x in (v if isinstance(v, list) else [v])])
                if not rel_next and len(links) == 0:
                    break

                page += 1

            # Collect unique target pages
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
    import argparse
    ap = argparse.ArgumentParser(description="Scrape OWID Grapher charts from a specific Data catalog (with pagination).")
    ap.add_argument("--catalog", required=True, help="Catalog URL with filters, e.g. https://ourworldindata.org/data?topics=Foo~Bar")
    ap.add_argument("--out", default="owid_catalog_charts", help="Output directory (default: owid_catalog_charts)")
    ap.add_argument("--fmt", default="png", choices=["png", "svg"], help="Image format to download")
    ap.add_argument("--concurrency", type=int, default=8, help="Max concurrent requests (default: 8)")
    ap.add_argument("--delay", type=float, default=0.25, help="Delay between requests in seconds (default: 0.25)")
    ap.add_argument("--timeout", type=float, default=45.0, help="HTTP timeout seconds (default: 45)")
    ap.add_argument("--max-catalog-pages", type=int, default=None, help="Max number of paginated catalog pages to scan (optional)")
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

def main():
    """
    Spyder/IPython-safe entry: tries asyncio.run(), falls back to reusing the running loop.
    """
    try:
        asyncio.run(main_async())
    except RuntimeError as e:
        msg = str(e)
        if "asyncio.run() cannot be called" in msg or "already running" in msg:
            try:
                import nest_asyncio
                nest_asyncio.apply()
            except Exception:
                pass
            loop = asyncio.get_event_loop()
            if loop.is_running():
                fut = asyncio.ensure_future(main_async())
                try:
                    loop.run_until_complete(fut)
                except RuntimeError:
                    print("Active IPython loop detected. In console you can run: `await main_async()`", file=sys.stderr)
            else:
                loop.run_until_complete(main_async())
        else:
            raise

if __name__ == "__main__":
    main()
