#!/usr/bin/env python3
"""
Scrape only base OWID Grapher charts from ourworldindata.org pages.

Features:
- Filters to charts with no query params (base view only).
- Exports only .png images ending in 'base.png'.
- Logs downloaded URLs, supports resume, deduplication.
- Gentle crawling: increased delay to prevent server rate-limiting.

Usage:
    python owid_scraper_baseonly.py --out charts --fmt png
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

    query = parsed.query or ""
    qparams = up.parse_qs(query, keep_blank_values=True)
    qparams.setdefault("download-format", [fmt])

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
        return True

# ---------------------------- Sitemap ----------------------------

async def fetch_sitemap_urls(client: httpx.AsyncClient) -> List[str]:
    resp = await client.get(SITEMAP, timeout=60)
    resp.raise_for_status()
    root = etree.fromstring(resp.content)
    ns = {"sm": root.nsmap.get(None) or "http://www.sitemaps.org/schemas/sitemap/0.9"}

    locs = []
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

    cleaned = []
    for u in locs:
        if not u.startswith(BASE):
            continue
        path = up.urlparse(u).path
        if path.startswith("/grapher/") or path.startswith("/owid-static/"):
            continue
        cleaned.append(u)
    return list(dict.fromkeys(cleaned))

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
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if looks_like_grapher_iframe(absolutize(href)):
            srcs.append(absolutize(href))
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
        concurrency: int = 4,
        per_request_delay: float = 1.0,
        timeout: float = 60.0,
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
                    if row["filename"].endswith(f"base.{self.fmt}"):
                        seen.add(row["export_url"])
        return seen

    def _filename_for(self, slug: str, norm_query: str) -> str:
        h = "base" if not norm_query else hashlib.sha1(norm_query.encode("utf-8")).hexdigest()[:8]
        base = f"{slug}-{h}.{self.fmt}"
        return slugify(base)

    async def run(self):
        limits = httpx.Limits(max_connections=30, max_keepalive_connections=15)
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
            tasks = [self.process_page(client, url) for url in urls]
            for coro in asyncio.as_completed(tasks):
                await coro
                page_count += 1
                if page_count % 25 == 0:
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
        for iframe_src in iframe_srcs:
            await self.process_iframe(client, page_url, iframe_src)

    async def process_iframe(self, client: httpx.AsyncClient, page_url: str, iframe_src: str):
        if not looks_like_grapher_iframe(iframe_src):
            return

        slug, qs, qd = parse_slug_and_query(iframe_src)
        norm_query = normalize_query(qd)
        if norm_query != "":
            return  # Only base charts (no query)

        export_url = export_url_from_iframe(iframe_src, self.fmt)
        if export_url in self.already:
            return

        filename = self._filename_for(slug, norm_query)
        if not filename.endswith(f"base.{self.fmt}"):
            return

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
        print(f"Saved {filename} ← {page_url}")

    def _append_meta(self, ref: ChartRef):
        with open(self.meta_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                ref.page_url,
                ref.iframe_src,
                ref.export_url,
                ref.filename,
                ref.slug,
                ref.norm_query
            ])

# ---------------------------- CLI ----------------------------

def parse_args(argv: List[str]):
    import argparse
    ap = argparse.ArgumentParser(description="Scrape only base OWID Grapher charts.")
    ap.add_argument("--out", default="owid_charts", help="Output directory")
    ap.add_argument("--fmt", default="png", choices=["png", "svg"], help="Image format")
    ap.add_argument("--concurrency", type=int, default=4, help="Max concurrent requests")
    ap.add_argument("--delay", type=float, default=1.0, help="Delay between requests")
    ap.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout seconds")
    ap.add_argument("--max-pages", type=int, default=None, help="Limit pages processed")
    ap.add_argument("--no-resume", action="store_true", help="Do not resume previous run")
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
