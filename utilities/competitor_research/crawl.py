#!/usr/bin/env python3
"""
Mirror a competitor site for private offline viewing.

Each site is configured in SITES below and saved to its own folder:
    competitor_research/<site>/mirror/        the offline copy (open mirror/index.html)
    competitor_research/<site>/crawl.log      progress log
    competitor_research/<site>/crawl_state.json  totals, failed URLs, pages not in sitemap

- Traverses the whole site: starts at the homepage (plus sitemap.xml as extra seeds)
  and follows every same-site <a> link on every page it downloads (BFS).
- Skips query-string URLs (calculator result permutations are effectively infinite).
- Downloads every page asset (CSS, JS, images, fonts, icons, manifest), including
  ones on the site's CDN and ones referenced from inside CSS via url()/@import.
- Rewrites links in HTML and CSS to relative local paths so the mirror opens from disk.
- Polite: single-threaded, delay between requests, honours robots.txt.
- Resumable: files already on disk are reused instead of re-downloaded.

Usage (from utilities/competitor_research/):
    .venv/bin/python crawl.py calculator.net                 # full crawl
    .venv/bin/python crawl.py dinkytown.net --max-pages 20   # quick test
    .venv/bin/python crawl.py dinkytown.net --delay 2        # slower / gentler
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote

import requests
from bs4 import BeautifulSoup

# start: where the crawl begins. hosts: hosts whose pages are crawled.
# cdn_hosts: extra hosts whose files are downloaded as page assets (never crawled as pages).
# page_query (optional): regex a page URL's whole query string must match to be crawled;
#   without it, query-string URLs are skipped (form results are effectively infinite).
SITES = {
    "calculator.net": {
        "start": "https://www.calculator.net/",
        "hosts": {"www.calculator.net", "calculator.net"},
        "cdn_hosts": {"d26tpo4cm8sb6k.cloudfront.net"},
    },
    "dinkytown.net": {
        "start": "https://www.dinkytown.net/",
        "hosts": {"www.dinkytown.net", "dinkytown.net"},
        "cdn_hosts": set(),
    },
    "fncalculator.com": {
        "start": "https://www.fncalculator.com/",
        "hosts": {"www.fncalculator.com", "fncalculator.com"},
        "cdn_hosts": set(),
        # Every calculator is financialcalculator?type=<name>; allow only that query shape.
        "page_query": r"type=[A-Za-z0-9_]+",
    },
}

# Set from the chosen site in main().
START_URL = ""
SITE_HOSTS = set()
ASSET_HOSTS = set()
PAGE_QUERY_RE = None
# Ads / analytics / tracking — never downloaded; references are left pointing online.
SKIP_HOST_PATTERNS = re.compile(
    r"(googlesyndication|googletagmanager|google-analytics|doubleclick|adservice|"
    r"googleadservices|facebook|twitter|amazon-adsystem|adnxs|quantserve|scorecardresearch)"
)
# Dynamic / account areas that are not useful offline.
SKIP_PATH_PATTERNS = re.compile(r"^/(my-account|cgi-bin)/|\.php$")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
HERE = Path(__file__).resolve().parent
OUT_DIR = Path()
STATE_FILE = Path()

CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.I)
CSS_IMPORT_RE = re.compile(r"""@import\s+(['"])([^'"]+)\1""", re.I)

# Attributes that can carry a URL, per tag.
URL_ATTRS = {
    "a": ["href"],
    "link": ["href"],
    "script": ["src"],
    "img": ["src", "data-src"],
    "source": ["src"],
    "video": ["src", "poster"],
    "audio": ["src"],
    "iframe": ["src"],
    "embed": ["src"],
    "object": ["data"],
    "input": ["src"],
    "form": ["action"],
    "use": ["href", "xlink:href"],
    "image": ["href", "xlink:href"],
}
SRCSET_TAGS = {"img", "source"}


def log(msg):
    print(msg, flush=True)


def normalize(url):
    """Absolute http(s) URL without fragment, scheme forced to https."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    host = parts.netloc.lower()
    path = parts.path or "/"
    return urlunsplit(("https", host, path, parts.query, ""))


def is_page_url(url):
    p = urlsplit(url)
    if p.netloc not in SITE_HOSTS:
        return False
    if p.query and not (PAGE_QUERY_RE and PAGE_QUERY_RE.fullmatch(p.query)):
        return False
    if SKIP_PATH_PATTERNS.search(p.path):
        return False
    ext = os.path.splitext(p.path)[1].lower()
    return ext in ("", ".html", ".htm")


def is_asset_url(url):
    p = urlsplit(url)
    if SKIP_HOST_PATTERNS.search(p.netloc):
        return False
    if p.netloc in SITE_HOSTS and SKIP_PATH_PATTERNS.search(p.path):
        return False
    return p.netloc in ASSET_HOSTS


def local_path(url, is_html=False):
    """Map a URL to a file path inside OUT_DIR."""
    p = urlsplit(url)
    host = p.netloc
    path = unquote(p.path)
    if path.endswith("/"):
        path += "index.html"
    if is_html and not os.path.splitext(path)[1]:
        path += ".html"
    if p.query:
        stem, ext = os.path.splitext(path)
        if is_html and PAGE_QUERY_RE and PAGE_QUERY_RE.fullmatch(p.query):
            # Readable name for allowed query pages, e.g. financialcalculator__type-bondCalculator.html
            suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", p.query)
        else:
            suffix = hashlib.md5(p.query.encode()).hexdigest()[:8]
        path = f"{stem}__{suffix}{ext}"
    path = path.lstrip("/")
    # The main site lives at the mirror root; every other host gets its own folder.
    if host in SITE_HOSTS:
        return OUT_DIR / path
    return OUT_DIR / "_hosts" / host / path


def rel_link(from_file, to_file, fragment=""):
    rel = os.path.relpath(to_file, start=from_file.parent)
    return rel.replace(os.sep, "/") + (f"#{fragment}" if fragment else "")


class Crawler:
    def __init__(self, delay, max_pages):
        self.delay = delay
        self.max_pages = max_pages
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.robots = robotparser.RobotFileParser()
        self.robots.set_url(urljoin(START_URL, "/robots.txt"))
        self.robots.read()

        self.page_queue = deque()
        self.seen_pages = set()
        self.done_assets = {}  # url -> local Path, or None if failed
        self.pages_saved = 0
        self.sitemap_urls = set()
        self.last_request = 0.0
        self._load_state()

    # --- state -------------------------------------------------------------
    def _load_state(self):
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            self.failed = set(state.get("failed", []))
        else:
            self.failed = set()

    def _save_state(self):
        STATE_FILE.write_text(json.dumps({
            "pages_seen": len(self.seen_pages),
            "pages_saved": self.pages_saved,
            "pages_not_in_sitemap": sorted(self.seen_pages - self.sitemap_urls),
            "assets": len(self.done_assets),
            "failed": sorted(self.failed),
        }, indent=2))

    # --- http --------------------------------------------------------------
    def fetch(self, url):
        wait = self.delay - (time.time() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            try:
                self.last_request = time.time()
                r = self.session.get(url, timeout=30)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(10 * (attempt + 1))
                    continue
                return r
            except requests.RequestException as e:
                log(f"  ! {url}: {e}")
                time.sleep(5 * (attempt + 1))
        return None

    # --- assets ------------------------------------------------------------
    def get_asset(self, url):
        """Download an asset (once) and return its local Path, or None."""
        if url in self.done_assets:
            return self.done_assets[url]
        dest = local_path(url)
        if dest.exists() and dest.stat().st_size > 0:
            self.done_assets[url] = dest
            if dest.suffix.lower() == ".css":
                self._process_css_file(url, dest)
            return dest
        self.done_assets[url] = None  # guard against recursion via CSS imports
        r = self.fetch(url)
        if r is None or r.status_code != 200:
            self.failed.add(url)
            log(f"  x asset {url} ({r.status_code if r is not None else 'error'})")
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        self.done_assets[url] = dest
        ctype = r.headers.get("content-type", "")
        if dest.suffix.lower() == ".css" or "text/css" in ctype:
            self._process_css_file(url, dest)
        log(f"  + asset {url}")
        return dest

    def _process_css_file(self, css_url, css_path):
        text = css_path.read_text(encoding="utf-8", errors="replace")
        new = self.rewrite_css(text, css_url, css_path)
        if new != text:
            css_path.write_text(new, encoding="utf-8")

    def rewrite_css(self, text, base_url, from_file):
        def repl(match, quote_group, url_group, template):
            raw = match.group(url_group).strip()
            if raw.startswith(("data:", "#")):
                return match.group(0)
            absu = normalize(urljoin(base_url, raw))
            if not absu or not is_asset_url(absu):
                return match.group(0)
            frag = urlsplit(urljoin(base_url, raw)).fragment
            dest = self.get_asset(absu)
            if dest is None:
                return match.group(0)
            return template.format(rel_link(from_file, dest, frag))

        text = CSS_IMPORT_RE.sub(lambda m: repl(m, 1, 2, '@import "{}"'), text)
        text = CSS_URL_RE.sub(lambda m: repl(m, 1, 2, 'url("{}")'), text)
        return text

    # --- pages -------------------------------------------------------------
    def enqueue(self, url):
        if url and url not in self.seen_pages and is_page_url(url):
            if self.robots.can_fetch(USER_AGENT, url):
                self.seen_pages.add(url)
                self.page_queue.append(url)

    def seed_from_sitemap(self):
        r = self.fetch(urljoin(START_URL, "/sitemap.xml"))
        if r is None or r.status_code != 200:
            return
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text):
            self.sitemap_urls.add(normalize(loc))
            self.enqueue(normalize(loc))

    def process_page(self, url):
        r = self.fetch(url)
        if r is None or r.status_code != 200:
            self.failed.add(url)
            log(f"x page {url} ({r.status_code if r is not None else 'error'})")
            return
        if "text/html" not in r.headers.get("content-type", ""):
            # Linked non-HTML file (e.g. a PDF) — keep it as an asset.
            dest = local_path(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return
        final_url = normalize(r.url) or url
        page_file = local_path(final_url, is_html=True)
        soup = BeautifulSoup(r.content, "html.parser")

        for tag_name, attrs in URL_ATTRS.items():
            for tag in soup.find_all(tag_name):
                for attr in attrs:
                    if tag.has_attr(attr):
                        tag[attr] = self.rewrite_url(tag[attr], final_url, page_file, tag_name)
                if tag_name in SRCSET_TAGS and tag.has_attr("srcset"):
                    tag["srcset"] = self.rewrite_srcset(tag["srcset"], final_url, page_file)

        for style in soup.find_all("style"):
            if style.string:
                style.string = self.rewrite_css(style.string, final_url, page_file)
        for tag in soup.find_all(style=True):
            tag["style"] = self.rewrite_css(tag["style"], final_url, page_file)

        page_file.parent.mkdir(parents=True, exist_ok=True)
        page_file.write_text(str(soup), encoding="utf-8")
        self.pages_saved += 1
        log(f"[{self.pages_saved} saved / {len(self.page_queue)} queued] {final_url}")

    def rewrite_url(self, value, base_url, page_file, tag_name):
        raw = value.strip()
        if not raw or raw.startswith(("#", "data:", "mailto:", "tel:", "javascript:")):
            return value
        joined = urljoin(base_url, raw)
        absu = normalize(joined)
        if not absu:
            return value
        frag = urlsplit(joined).fragment

        # Links to other pages: queue them and point to the local copy.
        if tag_name in ("a", "iframe", "form", "link") and is_page_url(absu):
            self.enqueue(absu)
            if tag_name == "form":
                return value  # forms submit to the live site; leave as-is
            return rel_link(page_file, local_path(absu, is_html=True), frag)

        # Everything else on the site / CDN is an asset.
        if tag_name != "a" and is_asset_url(absu):
            dest = self.get_asset(absu)
            if dest is not None:
                return rel_link(page_file, dest, frag)
        # Non-HTML files linked from <a> (PDFs, images) on the site.
        if tag_name == "a" and is_asset_url(absu) and os.path.splitext(urlsplit(absu).path)[1]:
            dest = self.get_asset(absu)
            if dest is not None:
                return rel_link(page_file, dest, frag)

        # Anything external: make protocol-relative URLs explicit so they work from file://.
        return joined if raw.startswith("//") else value

    def rewrite_srcset(self, value, base_url, page_file):
        out = []
        for part in value.split(","):
            bits = part.strip().split()
            if not bits:
                continue
            bits[0] = self.rewrite_url(bits[0], base_url, page_file, "img")
            out.append(" ".join(bits))
        return ", ".join(out)

    # --- main loop ---------------------------------------------------------
    def run(self):
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        self.enqueue(normalize(START_URL))
        self.seed_from_sitemap()
        log(f"Seeded {len(self.page_queue)} pages. Output: {OUT_DIR}")
        try:
            while self.page_queue:
                if self.max_pages and self.pages_saved >= self.max_pages:
                    log(f"Reached --max-pages {self.max_pages}")
                    break
                self.process_page(self.page_queue.popleft())
                if self.pages_saved % 10 == 0:
                    self._save_state()
        finally:
            self._save_state()
        extra = len(self.seen_pages - self.sitemap_urls)
        log(f"Pages discovered by following links (not in sitemap): {extra}")
        log(f"Done. Pages: {self.pages_saved}, assets: {sum(1 for v in self.done_assets.values() if v)}, "
            f"failed: {len(self.failed)}. Open {OUT_DIR / 'index.html'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", choices=sorted(SITES), help="which configured site to mirror")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    ap.add_argument("--max-pages", type=int, default=0, help="stop after N pages (0 = no limit)")
    args = ap.parse_args()

    global START_URL, SITE_HOSTS, ASSET_HOSTS, PAGE_QUERY_RE, OUT_DIR, STATE_FILE
    site = SITES[args.site]
    START_URL = site["start"]
    SITE_HOSTS = site["hosts"]
    ASSET_HOSTS = SITE_HOSTS | site["cdn_hosts"]
    PAGE_QUERY_RE = re.compile(site["page_query"]) if site.get("page_query") else None
    OUT_DIR = HERE / args.site / "mirror"
    STATE_FILE = HERE / args.site / "crawl_state.json"
    Crawler(args.delay, args.max_pages).run()


if __name__ == "__main__":
    sys.exit(main())
