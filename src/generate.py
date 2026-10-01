#!/usr/bin/env python3
"""
Render the site from the JSON sources into public/ (the deploy artifact, gitignored).

Runs build_data.build() first, so one command validates and renders:
    python3 src/generate.py                    # production build
    python3 src/generate.py --include-planned  # also render planned tools (noindex) for template work
    cd public && python3 -m http.server 8811   # preview at http://localhost:8811/

Pages and URLs (flat, every internal link ends in .html):
    /                               home (index.html): scientific calculator + topic directory
    /financial-calculators.html     the one category page: a section per subcategory
    /<tool-slug>.html               one page per live tool
    /about.html etc.                info pages, /sitemap.html, /404.html

Templates live in src/templates/. {{INCLUDE:_partial.html}} pulls in a shared partial, then
{{TOKENS}} are filled. Rendering fails on an unknown token (TEMPLATE_TOKENS lists what each
page type gets), so a typo can't ship as literal "{{...}}" text.
"""
import argparse
import html
import json
import re
import shutil
from datetime import date
from pathlib import Path

import build_data

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
TEMPLATES = SRC / "templates"
STATIC = SRC / "static"
OUT = ROOT / "public"

COMMON_TOKENS = {"PAGE_ID", "PAGE_TYPE", "SITE_NAME", "META_TITLE", "META_DESCRIPTION", "CANONICAL_URL",
                 "ROBOTS", "HEAD_EXTRA", "JSON_LD", "SIDEBAR_CATEGORIES", "FOOTER_CATEGORIES",
                 "FOOTER_DESCRIPTION", "YEAR", "AD_TOP", "AD_BOTTOM", "AD_RIGHT_RAIL", "H1", "SUBTITLE",
                 "SIDEBAR_DESKTOP_CLASSES", "HEADER_NAV_CLASSES"}
TEMPLATE_TOKENS = {
    "home.html": COMMON_TOKENS | {"AD_HERO", "AD_IN_FEED", "SIDE_CATEGORIES", "DIRECTORY", "DIRECTORY_COUNT",
                                  "DIRECTORY_HEADING", "DIRECTORY_INTRO", "FAQ"},
    "category.html": COMMON_TOKENS | {"BREADCRUMB", "HERO_TILE", "JUMP_LINKS", "FINDER_INTRO", "AD_HERO",
                                      "DIRECTORY_COUNT", "DIRECTORY", "FAQ"},
    "tool.html": COMMON_TOKENS | {"BREADCRUMB", "SUBCATEGORY_SLUG", "TOOL_CARD", "DISCLAIMER", "AD_IN_FEED",
                                  "CONTENT_SECTIONS", "FAQ", "RELATED_TOOLS", "TOOL_EXTRA_SCRIPTS", "TOOL_SCRIPT"},
    "page.html": COMMON_TOKENS | {"BREADCRUMB", "CONTENT_HTML"},
    "404.html": COMMON_TOKENS | {"POPULAR_TOOLS", "CATEGORY_URL", "SITEMAP_URL"},
}
TOKEN_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
INCLUDE_RE = re.compile(r"\{\{INCLUDE:([\w.-]+)\}\}")
RELATED_COUNT = 6
# Bullet dot before each calculator in the category page cards.
LIST_BULLET = '<span class="mt-[0.6em] size-1.5 shrink-0 rounded-full bg-current opacity-60" aria-hidden="true"></span>'
# Desktop (lg+) sidebar: a sticky column on every page except home, which uses the full width.
# Below lg the sidebar is always the hamburger drawer. Home shows the header links from lg instead.
SIDEBAR_DESKTOP = ("lg:sticky lg:top-16 lg:bottom-auto lg:z-auto lg:h-[calc(100dvh-4rem)] lg:w-60 lg:max-w-none "
                   "lg:shrink-0 lg:translate-x-0 lg:border-r-0 lg:bg-transparent")
SIDEBAR_DESKTOP_HOME = "lg:hidden"
HOME_ID = "home"
SEARCH_INDEX = "assets/data/calculator-search-index.json"

esc = html.escape

# Ad slot geometry, copied from the template's ad-slot markup.
LEADERBOARD = ("728 × 90 or 320 × 100", "h-[100px] w-full max-w-[320px] md:h-[90px] md:max-w-[728px]")
AD_SLOTS = {
    "top": ("ad-top-leaderboard", "Advertisement, top of page", *LEADERBOARD),
    "bottom": ("ad-bottom-leaderboard", "Advertisement, bottom of page", *LEADERBOARD),
    "in_feed": ("ad-in-feed", "Advertisement", *LEADERBOARD),
    "hero": ("ad-hero-rectangle", "Advertisement, beside the introduction", "300 × 250", "h-[250px] w-[300px] max-w-full"),
    "right_rail": ("ad-right-rail-skyscraper", "Advertisement, right column", "300 × 600", "h-[600px] w-[300px]"),
}
SEPARATOR_SVG = ('<svg class="breadcrumb-separator" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
                 'stroke-width="2" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="m6 3 5 5-5 5"/></svg>')


# --- URLs --------------------------------------------------------------------------------
def href(slug, anchor=""):
    """Site-relative link. Every page is a flat .html file; the home page is /."""
    path = "/" if slug in ("", HOME_ID) else f"/{slug}.html"
    return path + (f"#{anchor}" if anchor else "")


def url(site, slug):
    return site["base_url"] + href(slug)


def fill(text, site):
    """Placeholders allowed in copy fields."""
    return text.replace("{site}", site["site_name"])


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# --- template engine ---------------------------------------------------------------------
def load_template(name):
    tpl = (TEMPLATES / name).read_text(encoding="utf-8")
    return INCLUDE_RE.sub(lambda m: (TEMPLATES / m.group(1)).read_text(encoding="utf-8").rstrip("\n"), tpl)


def render(template_name, values):
    tpl = load_template(template_name)
    allowed = TEMPLATE_TOKENS[template_name]
    used = set(TOKEN_RE.findall(tpl))
    unknown = used - allowed
    if unknown:
        raise SystemExit(f"{template_name}: unknown token(s) {sorted(unknown)}; allowed: {sorted(allowed)}")
    missing = used - values.keys()
    if missing:
        raise SystemExit(f"{template_name}: no value for {sorted(missing)}")
    return TOKEN_RE.sub(lambda m: values[m.group(1)], tpl)


def json_ld(*objects):
    return "\n  ".join(f'<script type="application/ld+json">{json.dumps(o, ensure_ascii=False)}</script>'
                       for o in objects if o)


# --- shared components -------------------------------------------------------------------
def render_ad(page_id, slot, suffix=""):
    key, label, size, frame = AD_SLOTS[slot]
    name = f"{page_id}-{key}{suffix}"
    return (f'<aside id="{name}" class="ad-slot" aria-label="{label}" data-ad-slot-name="{name}" data-ad-size="{size}">\n'
            f'          <p id="{name}-label" class="ad-slot-label">Advertisement</p>\n'
            f'          <div id="{name}-frame" class="ad-slot-frame {frame}" data-ad-container="{name}">\n'
            f'            <!-- Paste the ad unit code for "{key}" here -->\n'
            f'            <span aria-hidden="true">{size}</span>\n'
            f'          </div>\n        </aside>')


def render_breadcrumb(site, page_id, trail):
    """trail: [(name, href_or_None)], last item is the current page."""
    items = []
    for i, (name, link) in enumerate(trail, 1):
        sep = SEPARATOR_SVG if i > 1 else ""
        attrs = (f'id="{page_id}-breadcrumb-item-{i}" class="flex items-center gap-1.5" itemprop="itemListElement" '
                 f'itemscope itemtype="https://schema.org/ListItem"')
        if i < len(trail):
            body = (f'<a class="breadcrumb-link" href="{link}" itemprop="item"><span itemprop="name">{esc(name)}</span></a>')
        else:
            body = (f'<span itemprop="name" aria-current="page" class="font-semibold text-ink">{esc(name)}</span>'
                    f'<meta itemprop="item" content="{site["base_url"]}{link}">')
        items.append(f'<li {attrs}>{sep}{body}<meta itemprop="position" content="{i}"></li>')
    return (f'<nav id="{page_id}-breadcrumb" aria-label="Breadcrumb" data-section="breadcrumb">\n'
            f'          <ol id="{page_id}-breadcrumb-list" class="flex flex-wrap items-center gap-1.5 text-sm" '
            f'itemprop="breadcrumb" itemscope itemtype="https://schema.org/BreadcrumbList">\n            '
            + "\n            ".join(items) + "\n          </ol>\n        </nav>")


def breadcrumb_ld(site, trail):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": site["base_url"] + link}
        for i, (name, link) in enumerate(trail, 1)]}


def faq_ld(faq):
    if not faq:
        return None
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": qa["question"],
         "acceptedAnswer": {"@type": "Answer", "text": qa["answer"]}} for qa in faq]}


def render_faq(page_id, heading, faq):
    if not faq:
        return ""
    items = []
    for i, qa in enumerate(faq, 1):
        fid = f"{page_id}-faq-{i}"
        items.append(
            f'<details id="{fid}" class="faq-item">'
            f'<summary id="{fid}-summary" class="faq-summary"><h3 id="{fid}-question" class="faq-question">'
            f'{esc(qa["question"])}</h3><span class="faq-marker" aria-hidden="true"></span></summary>'
            f'<div id="{fid}-answer" class="faq-answer"><p>{esc(qa["answer"])}</p></div></details>')
    return (f'<section id="{page_id}-faq-section" class="border-t border-line pt-8" aria-labelledby="{page_id}-faq-heading" data-section="faq">\n'
            f'        <h2 id="{page_id}-faq-heading" class="font-display text-2xl font-bold tracking-tight">{esc(heading)}</h2>\n'
            f'        <div id="{page_id}-faq-list" class="mt-4 border-t border-line">\n          '
            + "\n          ".join(items) + "\n        </div>\n      </section>")


class Site:
    """Shared, per-build view of the data that every page renderer needs."""

    def __init__(self, site, tools, pages):
        self.site, self.tools, self.pages = site, tools, pages
        self.category = pages["category"]
        self.by_slug = {t["slug"]: t for t in tools}
        self.subcats = {s["slug"]: dict(s, group=g) for g in site["nav"] for s in g["subcategories"]}
        self.live_count = sum(1 for t in tools if t["live"])

    def live_in(self, slugs):
        return [s for s in slugs if self.by_slug[s]["live"]]

    def group_tools(self, group):
        return [t for s in group["subcategories"] for t in s["tools"]]

    def count_line(self, slugs, topics=None):
        live = len(self.live_in(slugs))
        planned = len(slugs) - live
        text = plural(live, "calculator") + (f" in {plural(topics, 'topic')}" if topics else "")
        return text + (f" · {planned} coming soon" if planned else "")

    # --- chrome shared by every page ---
    def sidebar(self, page_id, current_sub=None, on_category=False):
        cat = self.category
        groups = []
        for g in self.site["nav"]:
            links = "".join(
                f'<li><a id="{page_id}-sidebar-sub-link-{s["slug"]}" class="sidebar-sub-link" '
                f'href="{href(cat["slug"], s["slug"])}" data-sub-category-slug="{s["slug"]}"'
                + (' aria-current="true"' if s["slug"] == current_sub else "") + f'>{esc(s["nav_name"])}</a></li>'
                for s in g["subcategories"])
            groups.append(f'<li><p class="sidebar-group-heading">{esc(g["name"])}</p>'
                          f'<ul class="space-y-0.5" role="list">{links}</ul></li>')
        current = ' aria-current="page"' if on_category else (' aria-current="true"' if current_sub else "")
        return (f'                <li><a id="{page_id}-sidebar-link-{cat["slug"]}" href="{href(cat["slug"])}" class="sidebar-link" '
                f'data-main-category-slug="{cat["slug"]}" itemprop="url"{current}>'
                f'<span class="sidebar-link-swatch bg-{cat["color"]} dark:bg-{cat["color"]}-ink" aria-hidden="true"></span>'
                f'<span itemprop="name">{esc(cat["name"])}</span><span class="sidebar-link-count"><span class="sr-only">, </span>'
                f'{self.live_count}<span class="sr-only"> calculators</span></span></a>\n'
                f'                  <ul id="{page_id}-sidebar-sub-links-{cat["slug"]}" class="mb-2 mt-0.5 space-y-0.5" role="list" '
                f'aria-label="{esc(cat["name"])} topics">{"".join(groups)}</ul></li>')

    def footer_categories(self, page_id):
        cat = self.category
        items = [f'<li><a id="{page_id}-footer-link-{cat["slug"]}" class="footer-link" href="{href(cat["slug"])}">{esc(cat["name"])}</a></li>']
        items += [f'<li><a id="{page_id}-footer-link-{g["id"]}" class="footer-link" href="{href(cat["slug"], g["id"])}">'
                  f'{esc(g["name"])} calculators</a></li>' for g in self.site["nav"]]
        return "          " + "\n          ".join(items)

    def base(self, page_id, page_type, slug, meta_title, meta_description, h1, subtitle, preview=False, head_extra=""):
        return {
            "PAGE_ID": page_id, "PAGE_TYPE": page_type,
            "SITE_NAME": esc(self.site["site_name"]),
            "META_TITLE": esc(fill(meta_title or h1, self.site)),
            "META_DESCRIPTION": esc(fill(meta_description, self.site)),
            "CANONICAL_URL": url(self.site, slug),
            "ROBOTS": "noindex, follow" if preview else "index, follow, max-image-preview:large",
            "HEAD_EXTRA": head_extra,
            "SIDEBAR_CATEGORIES": self.sidebar(page_id),
            "FOOTER_CATEGORIES": self.footer_categories(page_id),
            "FOOTER_DESCRIPTION": esc(self.site["footer_description"]),
            "YEAR": str(date.today().year),
            "AD_TOP": render_ad(page_id, "top"), "AD_BOTTOM": render_ad(page_id, "bottom"),
            "AD_RIGHT_RAIL": render_ad(page_id, "right_rail"),
            "H1": esc(fill(h1, self.site)), "SUBTITLE": esc(fill(subtitle, self.site)),
            "SIDEBAR_DESKTOP_CLASSES": SIDEBAR_DESKTOP_HOME if page_type == "home" else SIDEBAR_DESKTOP,
            "HEADER_NAV_CLASSES": "hidden lg:block" if page_type == "home" else "hidden xl:block",
        }

    # --- listing components ---
    def tool_list_item(self, page_id, sub, slug):
        t = self.by_slug[slug]
        if t["live"]:
            return (f'<li><a id="{page_id}-sub-category-{sub["slug"]}-link-{slug}" class="category-calculator-link flex items-start gap-2.5" '
                    f'href="{href(slug)}" data-calculator-name="{esc(t["name"])}" data-calculator-slug="{slug}" '
                    f'data-sub-category-slug="{sub["slug"]}" data-category-name="{esc(sub["name"])}">{LIST_BULLET}'
                    f'<span>{esc(t["name"])}</span></a></li>')
        return (f'<li><span class="category-calculator-link flex items-start gap-2.5 cursor-default opacity-70" aria-disabled="true">'
                f'{LIST_BULLET}<span>{esc(t["name"])} <span class="badge badge-outline">Coming soon</span></span></span></li>')

    def subcategory_card(self, page_id, position, group, sub):
        c, sid = group["color"], sub["slug"]
        ordered = self.live_in(sub["tools"]) + [s for s in sub["tools"] if not self.by_slug[s]["live"]]
        items = "\n              ".join(self.tool_list_item(page_id, sub, s) for s in ordered)
        p = f"{page_id}-sub-category-{sid}"
        return (f'<section id="{sid}" class="category-card scroll-mt-24" aria-labelledby="{p}-heading" itemprop="itemListElement" '
                f'itemscope itemtype="https://schema.org/ListItem" data-sub-category-slug="{sid}">\n'
                f'            <meta itemprop="position" content="{position}">\n'
                f'            <div id="{p}-header" class="category-card-header bg-{c} text-{c}-ink">\n'
                f'              <span id="{p}-tile" class="category-element-tile" aria-hidden="true"><span class="category-element-count">'
                f'{len(self.live_in(sub["tools"]))}</span><span class="category-element-symbol">{esc(sub["symbol"])}</span></span>\n'
                f'              <div class="min-w-0">\n'
                f'                <h2 id="{p}-heading" class="font-display text-lg font-bold leading-tight"><span itemprop="name">{esc(sub["name"])} Calculators</span></h2>\n'
                f'                <p id="{p}-count" class="text-sm opacity-80">{esc(self.count_line(sub["tools"]))}</p>\n'
                f'              </div>\n            </div>\n'
                f'            <p id="{p}-description" class="px-4 pt-3 text-sm text-ink-muted" itemprop="description">{esc(sub["description"])}</p>\n'
                f'            <ul id="{p}-list" class="category-calculator-list" role="list">\n              {items}\n            </ul>\n'
                f'          </section>')


# --- page renderers ------------------------------------------------------------------------
def render_home(S):
    site, home, cat = S.site, S.pages["home"], S.category
    page_id = HOME_ID
    values = S.base(page_id, "home", "", home["meta_title"], home["meta_description"], home["h1"], home["subtitle"],
                    head_extra='<script src="/assets/js/home-scientific-calculator-widget.js" defer></script>')
    side = [f'              <li><a id="{page_id}-side-category-list-link-{g["id"]}" class="side-category-link" '
            f'href="{href(cat["slug"], g["id"])}" data-main-category-slug="{g["id"]}"><span class="sidebar-link-swatch '
            f'bg-{g["color"]} dark:bg-{g["color"]}-ink" aria-hidden="true"></span><span>{esc(g["name"])}</span></a></li>'
            for g in site["nav"]]
    cards = []
    for i, g in enumerate(site["nav"], 1):
        p, c = f'{page_id}-main-category-{g["id"]}', g["color"]
        slugs = S.group_tools(g)
        covers = ", ".join(s["nav_name"].lower() for s in g["subcategories"])
        cards.append(
            f'<section id="{p}" class="main-category-card" aria-labelledby="{p}-heading" itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">\n'
            f'            <meta itemprop="position" content="{i}">\n'
            f'            <div id="{p}-header" class="category-card-header bg-{c} text-{c}-ink">\n'
            f'              <span id="{p}-tile" class="category-element-tile" aria-hidden="true"><span class="category-element-count">{len(S.live_in(slugs))}</span>'
            f'<span class="category-element-symbol">{esc(g["symbol"])}</span></span>\n'
            f'              <div class="min-w-0">\n'
            f'                <h3 id="{p}-heading" class="font-display text-lg font-bold leading-tight"><a href="{href(cat["slug"], g["id"])}" '
            f'class="category-heading-link" itemprop="url"><span itemprop="name">{esc(g["name"])} calculators</span></a></h3>\n'
            f'                <p id="{p}-count" class="text-sm opacity-80">{esc(S.count_line(slugs, len(g["subcategories"])))}</p>\n'
            f'              </div>\n            </div>\n'
            f'            <div id="{p}-body" class="main-category-body">\n'
            f'              <p id="{p}-intro" class="text-ink">{esc(g["description"])}</p>\n'
            f'              <p id="{p}-covers" class="text-sm text-ink-muted">Covers {esc(covers)}.</p>\n'
            f'              <a id="{p}-cta" class="main-category-cta" href="{href(cat["slug"], g["id"])}" aria-describedby="{p}-heading">'
            f'Browse {esc(g["name"].lower())} calculators</a>\n'
            f'            </div>\n          </section>')
    values.update({
        "JSON_LD": json_ld({"@context": "https://schema.org", "@type": "WebSite", "name": site["site_name"],
                            "url": url(site, ""), "potentialAction": {
                                "@type": "SearchAction", "target": f'{site["base_url"]}/?q={{search_term_string}}',
                                "query-input": "required name=search_term_string"}},
                           faq_ld(home["faq"])),
        "AD_HERO": render_ad(page_id, "hero"), "AD_IN_FEED": render_ad(page_id, "in_feed"),
        "SIDE_CATEGORIES": "\n".join(side),
        "DIRECTORY": "          " + "\n          ".join(cards),
        "DIRECTORY_COUNT": str(len(site["nav"])),
        "DIRECTORY_HEADING": esc(home["directory_heading"]),
        "DIRECTORY_INTRO": esc(home["directory_intro"]),
        "FAQ": render_faq(page_id, home["faq_heading"], home["faq"]),
    })
    return render("home.html", values)


def render_category(S):
    site, cat = S.site, S.category
    page_id = cat["slug"]
    trail = [("Home", "/"), (cat["name"], href(cat["slug"]))]
    values = S.base(page_id, "main-category", cat["slug"], cat["meta_title"], cat["meta_description"],
                    cat["h1"], cat["subtitle"])
    values["SIDEBAR_CATEGORIES"] = S.sidebar(page_id, on_category=True)
    groups, position = [], 0
    for gi, g in enumerate(site["nav"], 1):
        cards = []
        for sub in g["subcategories"]:
            position += 1
            cards.append(S.subcategory_card(page_id, position, g, sub))
        groups.append(
            f'<div id="{g["id"]}" class="scroll-mt-24 space-y-4" data-group="{g["id"]}">\n'
            f'          <h2 id="{page_id}-group-{g["id"]}-heading" class="font-display text-xl font-bold tracking-tight sm:text-2xl">{esc(g["name"])} Calculators</h2>\n'
            f'          <p id="{page_id}-group-{g["id"]}-intro" class="max-w-2xl text-ink-muted">{esc(g["description"])}</p>\n'
            f'          <div id="{page_id}-sub-category-grid-{gi}" class="grid gap-5 @2xl:grid-cols-2 @6xl:grid-cols-3">\n          '
            + "\n          ".join(cards) + "\n          </div>\n        </div>")
        if gi % 2 == 0 and gi < len(site["nav"]):  # an in-feed ad after every second group
            groups.append(render_ad(page_id, "in_feed", f"-after-group-{gi}"))
    jump = [f'                  <li><a id="{page_id}-jump-link-{s["slug"]}" class="jump-link" href="#{s["slug"]}" '
            f'data-sub-category-slug="{s["slug"]}">{esc(s["nav_name"])}<span class="text-xs text-ink-muted">'
            f'{len(S.live_in(s["tools"]))}</span></a></li>' for g in site["nav"] for s in g["subcategories"]]
    live = [t for t in S.tools if t["live"]]
    values.update({
        "JSON_LD": json_ld(
            {"@context": "https://schema.org", "@type": "CollectionPage", "name": cat["name"],
             "url": url(site, cat["slug"]), "description": fill(cat["meta_description"], site),
             "hasPart": [{"@type": "WebApplication", "name": t["name"], "url": url(site, t["slug"])} for t in live]},
            breadcrumb_ld(site, trail), faq_ld(cat["faq"])),
        "BREADCRUMB": render_breadcrumb(site, page_id, trail),
        "HERO_TILE": (f'<span id="{page_id}-hero-tile" class="category-element-tile hidden size-16 sm:flex bg-{cat["color"]} '
                      f'text-{cat["color"]}-ink" aria-hidden="true"><span class="category-element-count">{S.live_count}</span>'
                      f'<span class="category-element-symbol text-2xl">{esc(cat["symbol"])}</span></span>'),
        "JUMP_LINKS": "\n".join(jump),
        "FINDER_INTRO": esc(cat["finder_intro"]),
        "AD_HERO": render_ad(page_id, "hero"),
        "DIRECTORY_COUNT": str(len(S.subcats)),
        "DIRECTORY": "        " + "\n        ".join(groups),
        "FAQ": render_faq(page_id, cat["faq_heading"], cat["faq"]),
    })
    return render("category.html", values)


def render_related(S, tool):
    live = {t["slug"]: t for t in S.tools if t["live"] and t["slug"] != tool["slug"]}
    picked = [s for s in tool.get("related", []) if s in live]
    for t in S.tools:  # fill from the same subcategory, in nav order
        if len(picked) >= RELATED_COUNT:
            break
        if t["subcategory"] == tool["subcategory"] and t["slug"] in live and t["slug"] not in picked:
            picked.append(t["slug"])
    if not picked:
        return ""
    page_id = tool["slug"]
    items = "\n          ".join(
        f'<li><a id="{page_id}-related-link-{s}" class="related-link" href="{href(s)}" data-calculator-name="{esc(live[s]["name"])}" '
        f'data-category-name="{esc(S.subcats[live[s]["subcategory"]]["name"])}">{esc(live[s]["name"])}'
        f'<span aria-hidden="true" class="text-ink-muted">›</span></a></li>' for s in picked[:RELATED_COUNT])
    return (f'<nav id="{page_id}-related-section" class="border-t border-line pt-8" aria-labelledby="{page_id}-related-heading" data-section="related-calculators">\n'
            f'        <h2 id="{page_id}-related-heading" class="guide-heading">Related calculators</h2>\n'
            f'        <ul id="{page_id}-related-list" class="mt-5 grid gap-3 @2xl:grid-cols-2 @5xl:grid-cols-3" role="list">\n          {items}\n        </ul>\n      </nav>')


def render_tool(S, tool):
    site, cat = S.site, S.category
    sub = S.subcats[tool["subcategory"]]
    page_id = tool["slug"]
    trail = [("Home", "/"), (cat["name"], href(cat["slug"])), (sub["name"], href(cat["slug"], sub["slug"])),
             (tool["name"], href(tool["slug"]))]
    values = S.base(page_id, "calculator", tool["slug"], tool["meta_title"], tool["meta_description"],
                    tool["h1"], tool["subtitle"], preview=tool["preview"])
    values["SIDEBAR_CATEGORIES"] = S.sidebar(page_id, current_sub=sub["slug"])
    card = tool["card"]
    fields = card.get("fields_html") or ('<section class="panel p-4 sm:p-6"><p class="text-ink-muted">This calculator '
                                         'is planned and not built yet.</p></section>')
    app = {"@context": "https://schema.org", "@type": "WebApplication", "name": tool["name"],
           "url": url(site, tool["slug"]), "applicationCategory": "FinanceApplication", "operatingSystem": "Any",
           "browserRequirements": "Requires JavaScript",
           "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}}
    if tool["meta_description"]:
        app["description"] = tool["meta_description"]
    content = tool["content_html"].strip()
    values.update({
        "JSON_LD": json_ld(app, breadcrumb_ld(site, trail), faq_ld(tool["faq"])),
        "BREADCRUMB": render_breadcrumb(site, page_id, trail),
        "SUBCATEGORY_SLUG": sub["slug"],
        "TOOL_CARD": fields,
        "DISCLAIMER": esc(site["disclaimer"]),
        "AD_IN_FEED": render_ad(page_id, "in_feed"),
        "CONTENT_SECTIONS": (f'<article id="{page_id}-guide" class="article-content border-t border-line pt-10" data-section="guide">\n'
                             f'{content}\n      </article>') if content else "",
        "FAQ": render_faq(page_id, tool.get("faq_heading") or f'{tool["name"]} questions', tool["faq"]),
        "RELATED_TOOLS": render_related(S, tool),
        "TOOL_EXTRA_SCRIPTS": "\n".join(f'<script src="{esc(s)}" defer></script>' for s in card.get("extra_scripts", [])),
        "TOOL_SCRIPT": f"<script>{tool['script']}</script>" if tool["script"].strip() else "",
    })
    return render("tool.html", values)


def render_page(S, slug, meta_title, meta_description, h1, subtitle, content_html, preview=False):
    trail = [("Home", "/"), (h1, href(slug))]
    values = S.base(slug, "page", slug, meta_title, meta_description, h1, subtitle, preview=preview)
    values.update({
        "JSON_LD": json_ld(breadcrumb_ld(S.site, trail)),
        "BREADCRUMB": render_breadcrumb(S.site, slug, trail),
        "CONTENT_HTML": content_html,
    })
    return render("page.html", values)


POPULAR_404 = ["mortgage-calculator", "compound-interest-calculator", "401k-calculator", "retirement-calculator",
               "income-tax-calculator", "auto-loan-calculator", "loan-calculator", "savings-calculator",
               "house-affordability-calculator"]


def render_404(S):
    """Custom 404: cartoon + caption + calculator search, pre-filled from the mistyped URL (see templates/404.html)."""
    site, page_id = S.site, "404"
    values = S.base(page_id, "page", "404", f"Page not found (404) | {site['site_name']}", "", "This page doesn\u2019t add up",
                    "The page you asked for doesn\u2019t exist or has moved. The calculators are all still here, so "
                    "search for the one you wanted below.", preview=True)
    items = "\n".join(
        f'          <li><a id="{page_id}-popular-link-{t}" class="category-calculator-link flex items-start gap-2.5" '
        f'href="{href(t)}">{LIST_BULLET}<span>{esc(S.by_slug[t]["name"])}</span></a></li>'
        for t in POPULAR_404 if t in S.by_slug and S.by_slug[t]["live"])
    values.update({
        "JSON_LD": json_ld(breadcrumb_ld(site, [("Home", "/"), ("Page not found", href("404"))])),
        "POPULAR_TOOLS": items,
        "CATEGORY_URL": href(S.category["slug"]), "SITEMAP_URL": href("sitemap"),
        # AdSense policy: no ads on error / non-content pages, so every ad slot is blanked here.
        "AD_TOP": "", "AD_BOTTOM": "", "AD_RIGHT_RAIL": "",
    })
    return render("404.html", values)


def sitemap_page_html(S):
    cat, parts = S.category, []
    parts.append(f'<p><a href="{href(cat["slug"])}">{esc(cat["name"])}</a></p>')
    for g in S.site["nav"]:
        parts.append(f"<h2>{esc(g['name'])}</h2>")
        for s in g["subcategories"]:
            items = "".join(
                f'<li><a href="{href(t)}">{esc(S.by_slug[t]["name"])}</a></li>' if S.by_slug[t]["live"]
                else f'<li>{esc(S.by_slug[t]["name"])} <small>(coming soon)</small></li>' for t in s["tools"])
            parts.append(f'<h3><a href="{href(cat["slug"], s["slug"])}">{esc(s["name"])}</a></h3><ul>{items}</ul>')
    return "\n".join(parts)


def search_index(S):
    cat = S.category
    entries = [{"name": cat["name"], "category": "Category", "url": href(cat["slug"]), "type": "main-category"}]
    entries += [{"name": s["name"], "category": cat["name"], "url": href(cat["slug"], s["slug"]), "type": "sub-category"}
                for s in S.subcats.values()]
    entries += [{"name": t["name"], "category": S.subcats[t["subcategory"]]["name"], "url": href(t["slug"]), "type": "calculator"}
                for t in S.tools if t["live"]]
    return entries


def unlink_unpublished(content, dead_hrefs):
    """While an info page isn't published, drop menu items that point at it and turn any other
    link to it into plain text, so production never links to a missing page."""
    for h in dead_hrefs:
        content = re.sub(rf'\s*<li><a [^>]*href="{re.escape(h)}"[^>]*>[^<]*</a></li>', "", content)
        content = re.sub(rf'<a [^>]*href="{re.escape(h)}"[^>]*>(.*?)</a>', r"\1", content, flags=re.S)
    return content


def sitemap_xml(site, slugs):
    today = date.today().isoformat()
    urls = "".join(f"<url><loc>{esc(url(site, s))}</loc><lastmod>{today}</lastmod></url>" for s in slugs)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')


# --- main ----------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--include-planned", action="store_true",
                    help="also render planned tools/pages as noindex previews (for template work)")
    args = ap.parse_args()

    site, tools, pages = build_data.build(include_planned=args.include_planned)
    S = Site(site, tools, pages)

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(STATIC, OUT)

    dead = [href(p["slug"]) for p in pages["info_pages"] if not p["live"]]

    def write(name, content):
        (OUT / f"{name}.html").write_text(unlink_unpublished(content, dead), encoding="utf-8")

    indexable = [""]
    write("index", render_home(S))
    write(S.category["slug"], render_category(S))
    indexable.append(S.category["slug"])
    for tool in tools:
        if tool["live"]:
            write(tool["slug"], render_tool(S, tool))
            if not tool["preview"]:
                indexable.append(tool["slug"])
    for page in pages["info_pages"]:
        if page["live"]:
            write(page["slug"], render_page(S, page["slug"], page["meta_title"], page["meta_description"], page["h1"],
                                            page.get("subtitle", ""), page["content_html"] or
                                            "<p>This page is being written.</p>", preview=page["preview"]))
            if not page["preview"]:
                indexable.append(page["slug"])
    write("sitemap", render_page(S, "sitemap", f"Sitemap | {site['site_name']}",
                                 f"Every calculator on {site['site_name']}, grouped by topic.", "Sitemap",
                                 "Every financial calculator on the site, grouped by topic.", sitemap_page_html(S)))
    indexable.append("sitemap")
    write("404", render_404(S))

    (OUT / SEARCH_INDEX).parent.mkdir(parents=True, exist_ok=True)
    (OUT / SEARCH_INDEX).write_text(json.dumps(search_index(S), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "sitemap.xml").write_text(sitemap_xml(site, indexable), encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {site['base_url']}/sitemap.xml\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")  # serve files as-is on GitHub Pages
    print(f"Wrote {OUT.relative_to(ROOT)}/ — {len(indexable)} indexable URLs in sitemap.xml")


if __name__ == "__main__":
    main()
