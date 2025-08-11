#!/usr/bin/env python3
"""
Scrape all visible OWID Grapher charts from ourworldindata.org pages/subpages.

Features:
- Pulls all URLs from sitemap.xml and filters to site pages (excludes /grapher/* direct).
- Parses each page for <iframe src="https://ourworldindata.org/grapher/...">.
- Exports each chart to PNG or SVG using Grapher's image endpoints.
- Deduplicates charts by (slug + normalized query), supports resume via metadata log.
- Polite crawling: robots.txt check, concurrency limits, and small delays.

Usage:
    python owid_scraper.py --out charts --fmt png --concurrency 8

Requirements:
    pip install httpx==0.27.0 beautifulsoup4==4.12.2 lxml==5.2.2
"""

import asyncio
import csv
import hashlib
import os
import re
import sys
import time
import urllib.parse as up
from dataclasses import dataclass
from typing import Optional, Set, Tuple, Dict, List

import httpx
from bs4 import BeautifulSoup
from lxml import etree

BASE = "https://ourworldindata.org"
SITEMAP = f"{BASE}/sitemap.xml"
ROBOTS = f"{BASE}/robots.txt"
USER_AGENT = "OWID-Chart-Scraper/1.0 (+https://github.com/)"

# ---------------------------- Utilities ----------------------------

def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-")
    return s or "chart"

def parse_slug_and_query(iframe_src: str) -> Tuple[str, str, Dict[str, List[str]]]:
    """
    Returns (slug, raw_query_string, parsed_query) for a grapher iframe src.
    Example: https://ourworldindata.org/grapher/co2?tab=chart -> ("co2", "tab=chart", {"tab": ["chart"]})
    """
    parsed = up.urlparse(iframe_src)
    # Path like /grapher/<slug>
    parts = [p for p in parsed.path.split("/") if p]
    slug = parts[-1] if parts else "chart"
    qs = parsed.query or ""
    qd = up.parse_qs(qs, keep_blank_values=True)
    return slug, qs, qd

def normalize_query(qd: Dict[str, List[str]]) -> str:
    """
    Build a normalized, stable querystring (sorted keys & values) for deduplication & filenames.
    """
    items = []
    for k in sorted(qd.keys()):
        vals = sorted(v for v in qd[k])
        for v in vals:
            items.append(f"{k}={v}")
    return "&".join(items)

def export_url_from_iframe(iframe_src: str, fmt: str) -> str:
    """
    Turn a grapher iframe URL into a static image export URL.
    OWID Grapher supports .png/.svg export. We preserve chart options via existing query params.
    """
    fmt = fmt.lower()
    if fmt not in {"png", "svg"}:
        raise ValueError("fmt must be png or svg")

    parsed = up.urlparse(iframe_src)
    # Swap path /grapher/slug -> /grapher/slug.png or .svg
    base_no_ext = re.sub(r"(\.png|\.svg)$", "", parsed.path)
    path_with_ext = base_no_ext + f".{fmt}"

    query = parsed.query or ""
    # Some instances benefit from download-format; harmless if redundant
    qparams = up.parse_qs(query, keep_blank_values=True)
    qparams.setdefault("download-format", [fmt])

    # Re-encode querystring in stable order
    flat = []
    for k in sorted(qparams.keys()):
        for v in qparams[k]:
            flat.append((k, v))
    norm_query = up.urlencode(flat, doseq=True)

    new = parsed._replace(path=path_with_ext, query=norm_query)
    return up.urlunparse(new)

def looks_like_grapher_iframe(src: str) -> bool:
    return src.startswith(f"{BASE}/grapher/") or src.startswith("/grapher/")

def absolutize(url: str) -> str:
    return up.urljoin(BASE + "/", url)

# ---------------------------- Data Models ----------------------------

@dataclass(frozen=True)
class ChartRef:
    page_url: str
    iframe_src: str
    slug: str
    norm_query: str
    export_url: str
    filename: str

# ---------------------------- Robots ----------------------------

async def allowed_by_robots(client: httpx.AsyncClient, path: str) -> bool:
    # Light robots check: deny if Disallow matches. Full parser would be heavier.
    try:
        r = await client.get(ROBOTS, timeout=20)
        r.raise_for_status()
        disallows = []
        ua_section = None
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("user-agent:"):
                ua = line.split(":", 1)[1].strip()
                ua_section = (ua == "*")
            elif ua_section and line.lower().startswith("disallow:"):
                rule = line.split(":", 1)[1].strip()
                disallows.append(rule)
        path_only = up.urlparse(path).path
        for rule in disallows:
            if not rule:
                continue
            if path_only.startswith(rule):
                return False
        return True
    except Exception:
        # If robots fails, err on side of caution and allow (common practice is to allow site fetch if robots unreachable)
        return True

# ---------------------------- Sitemap ----------------------------

async def fetch_sitemap_urls(client: httpx.AsyncClient) -> List[str]:
    resp = await client.get(SITEMAP, timeout=60)
    resp.raise_for_status()
    root = etree.fromstring(resp.content)
    ns = {"sm": root.nsmap.get(None) or "http://www.sitemaps.org/schemas/sitemap/0.9"}

    locs = []
    # Handle both sitemap index and urlset
    if root.tag.endswith("sitemapindex"):
        for site in root.findall("sm:sitemap", namespaces=ns):
            loc = site.findtext("sm:loc", namespaces=ns)
            if loc:
                try:
                    r = await client.get(loc, timeout=60)
                    r.raise_for_status()
                    rs = etree.fromstring(r.content)
                    for u in rs.findall("sm:url", namespaces=ns):
                        url = u.findtext("sm:loc", namespaces=ns)
                        if url:
                            locs.append(url)
                except Exception:
                    continue
    else:
        for u in root.findall("sm:url", namespaces=ns):
            url = u.findtext("sm:loc", namespaces=ns)
            if url:
                locs.append(url)

    # Filter to ourworldindata.org pages, not direct /grapher/* or assets
    cleaned = []
    for u in locs:
        if not u.startswith(BASE):
            continue
        path = up.urlparse(u).path
        if path.startswith("/grapher/") or path.startswith("/owid-static/"):
            continue
        cleaned.append(u)
    return list(dict.fromkeys(cleaned))  # preserve order, dedupe

# ---------------------------- Page Parsing ----------------------------

def extract_grapher_iframes(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    srcs = []
    for iframe in soup.find_all("iframe"):
        src = (iframe.get("src") or "").strip()
        if not src:
            continue
        if looks_like_grapher_iframe(absolutize(src)):
            srcs.append(absolutize(src))
    # Also handle rare <a href=".../grapher/..."> fallback
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if looks_like_grapher_iframe(absolutize(href)):
            srcs.append(absolutize(href))
    # Dedupe while preserving order
    seen = set()
    out = []
    for s in srcs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

# ---------------------------- Scraper Core ----------------------------

class OwidScraper:
    def __init__(
        self,
        out_dir: str,
        fmt: str = "png",
        concurrency: int = 8,
        per_request_delay: float = 0.25,
        timeout: float = 45.0,
        max_pages: Optional[int] = None,
        resume: bool = True,
    ):
        self.out_dir = out_dir
        self.img_dir = os.path.join(out_dir, "images")
        self.meta_path = os.path.join(out_dir, "charts_metadata.csv")
        self.fmt = fmt.lower()
        self.sem = asyncio.Semaphore(concurrency)
        self.delay = per_request_delay
        self.timeout = timeout
        self.max_pages = max_pages
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
        """Use slug plus a short hash of query to avoid collisions across different chart states."""
        h = hashlib.sha1(norm_query.encode("utf-8")).hexdigest()[:8] if norm_query else "base"
        base = f"{slug}-{h}.{self.fmt}"
        return slugify(base)

    async def run(self):
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=self.timeout,
            limits=limits,
        ) as client:
            if not await allowed_by_robots(client, "/"):
                print("Blocked by robots.txt", file=sys.stderr)
                return

            print("Fetching sitemap...")
            urls = await fetch_sitemap_urls(client)
            if self.max_pages:
                urls = urls[: self.max_pages]
            print(f"Found {len(urls)} pages to scan.")

            page_count = 0
            tasks = []
            for url in urls:
                tasks.append(asyncio.create_task(self.process_page(client, url)))
            # Process with backpressure
            for t in asyncio.as_completed(tasks):
                await t
                page_count += 1
                if page_count % 50 == 0:
                    print(f"Scanned {page_count}/{len(urls)} pages...")

    async def process_page(self, client: httpx.AsyncClient, page_url: str):
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

        # Download charts serially per page to reduce server burst
        for iframe_src in iframe_srcs:
            await self.process_iframe(client, page_url, iframe_src)

    async def process_iframe(self, client: httpx.AsyncClient, page_url: str, iframe_src: str):
        # Only handle grapher charts
        if not looks_like_grapher_iframe(iframe_src):
            return

        slug, qs, qd = parse_slug_and_query(iframe_src)
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
        ))
        self.already.add(export_url)
        print(f"Saved {filename}  ←  {page_url}")

    def _append_meta(self, ref: ChartRef):
        with open(self.meta_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([ref.page_url, ref.iframe_src, ref.export_url, ref.filename, ref.slug, ref.norm_query])


# ---------------------------- CLI ----------------------------

def parse_args(argv: List[str]):
    import argparse
    ap = argparse.ArgumentParser(description="Scrape OWID Grapher charts from all site pages.")
    ap.add_argument("--out", default="owid_charts", help="Output directory (default: owid_charts)")
    ap.add_argument("--fmt", default="png", choices=["png", "svg"], help="Image format to download")
    ap.add_argument("--concurrency", type=int, default=8, help="Max concurrent requests (default: 8)")
    ap.add_argument("--delay", type=float, default=0.25, help="Delay between requests in seconds (default: 0.25)")
    ap.add_argument("--timeout", type=float, default=45.0, help="HTTP timeout seconds (default: 45)")
    ap.add_argument("--max-pages", type=int, default=None, help="Limit pages processed (for testing)")
    ap.add_argument("--no-resume", action="store_true", help="Do not resume; ignore existing metadata file")
    return ap.parse_args(argv)

async def main_async():
    args = parse_args(sys.argv[1:])
    scraper = OwidScraper(
        out_dir=args.out,
        fmt=args.fmt,
        concurrency=args.concurrency,
        per_request_delay=args.delay,
        timeout=args.timeout,
        max_pages=args.max_pages,
        resume=not args.no_resume,
    )
    await scraper.run()

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)

if __name__ == "__main__":
    main()
