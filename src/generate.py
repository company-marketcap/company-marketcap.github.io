#!/usr/bin/env python3
"""
Render the site from the JSON sources into public/ (the deploy artifact, gitignored).

Runs build_data.build() first, so one command validates and renders:
    python3 src/generate.py                    # production build
    python3 src/generate.py --include-planned  # also render planned tools (noindex) for template work
    cd public && python3 -m http.server 8811   # preview at http://localhost:8811/

Templates live in src/templates/. Each uses {{TOKENS}}; the full token list per template is
TEMPLATE_TOKENS below. Rendering fails if a template uses an unknown token, so a typo in a
template can't silently ship as literal "{{...}}" text.
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

COMMON_TOKENS = {"SITE_NAME", "META_TITLE", "META_DESCRIPTION", "CANONICAL_URL", "ROBOTS", "JSON_LD",
                 "ADSENSE_CLIENT", "NAV", "BREADCRUMB", "H1", "SUBTITLE", "FOOTER", "YEAR"}
TEMPLATE_TOKENS = {
    "tool.html": COMMON_TOKENS | {"TOOL_CARD", "CONTENT_SECTIONS", "FAQ", "RELATED_TOOLS",
                                  "DISCLAIMER", "TOOL_EXTRA_SCRIPTS", "TOOL_SCRIPT"},
    "hub.html": COMMON_TOKENS | {"TOOL_GRID"},
    "home.html": COMMON_TOKENS | {"CATEGORY_GRID"},
    "page.html": COMMON_TOKENS | {"CONTENT_HTML"},
}
TOKEN_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
RELATED_COUNT = 6

esc = html.escape


# --- helpers ---------------------------------------------------------------------------
def url(site, slug=""):
    """Absolute, extensionless URL (GitHub Pages serves /slug from slug.html)."""
    return f"{site['base_url']}/{slug}" if slug else f"{site['base_url']}/"


def render(template_name, values):
    tpl = (TEMPLATES / template_name).read_text(encoding="utf-8")
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
    return "\n".join(f'<script type="application/ld+json">{json.dumps(o, ensure_ascii=False)}</script>'
                     for o in objects if o)


def breadcrumb_ld(site, trail):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": url(site, slug)}
        for i, (name, slug) in enumerate(trail, 1)]}


def faq_ld(faq):
    if not faq:
        return None
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": qa["question"],
         "acceptedAnswer": {"@type": "Answer", "text": qa["answer"]}} for qa in faq]}


def render_breadcrumb(trail):
    items = []
    for i, (name, slug) in enumerate(trail):
        if i == len(trail) - 1:
            items.append(f'<li aria-current="page">{esc(name)}</li>')
        else:
            items.append(f'<li><a href="/{slug}">{esc(name)}</a></li>')
    return f'<nav class="breadcrumb" aria-label="Breadcrumb"><ol>{"".join(items)}</ol></nav>'


def render_nav(site, tools_by_slug):
    groups = []
    for group in site["nav"]:
        subs = []
        for sub in group["subcategories"]:
            links = "".join(f'<li><a href="/{s}">{esc(tools_by_slug[s]["nav_name"])}</a></li>'
                            for s in sub["tools"])
            subs.append(f'<li class="nav-sub"><a class="nav-sub-link" href="/{sub["slug"]}">'
                        f'{esc(sub["nav_name"])}</a><ul class="nav-tools">{links}</ul></li>')
        groups.append(f'<li class="nav-group"><button type="button" class="nav-group-toggle" '
                      f'aria-expanded="false">{esc(group["name"])}</button>'
                      f'<ul class="nav-subs">{"".join(subs)}</ul></li>')
    return f'<nav class="site-nav" aria-label="Calculators"><ul class="nav-groups">{"".join(groups)}</ul></nav>'


def render_footer(site):
    links = "".join(f'<li><a href="/{l["slug"]}">{esc(l["label"])}</a></li>' for l in site["footer_links"])
    return (f'<ul class="footer-links">{links}</ul>'
            f'<p class="footer-tagline">{esc(site["tagline"])}</p>'
            f'<p class="footer-copy">&copy; {date.today().year} {esc(site["site_name"])}</p>')


def split_content_by_h2(content_html):
    """Split at each <h2> into <section class="content-card">. Any intro before the first <h2>
    is kept and placed at the top of the first section rather than dropped."""
    if not content_html.strip():
        return ""
    parts = re.split(r"(?=<h2[\s>])", content_html.strip())
    lead = parts[0] if not parts[0].lstrip().startswith("<h2") else ""
    sections = [p for p in parts if p.lstrip().startswith("<h2")]
    if not sections:
        return f'<section class="content-card">{lead}</section>'
    sections[0] = lead + sections[0]
    return "".join(f'<section class="content-card">{s}</section>' for s in sections)


def render_faq(faq):
    if not faq:
        return ""
    items = "".join(f'<details class="faq-item"><summary>{esc(qa["question"])}</summary>'
                    f'<div class="faq-answer"><p>{esc(qa["answer"])}</p></div></details>' for qa in faq)
    return f'<section class="faq" id="faq"><h2>Frequently asked questions</h2>{items}</section>'


def tool_card_link(tool):
    desc = tool.get("subtitle") or ""
    return (f'<li class="tool-link"><a href="/{tool["slug"]}"><span class="tool-link-name">'
            f'{esc(tool["name"])}</span>' + (f'<span class="tool-link-desc">{esc(desc)}</span>' if desc else "")
            + "</a></li>")


def related_tools(tool, tools):
    live = {t["slug"]: t for t in tools if t["live"] and t["slug"] != tool["slug"]}
    picked = [s for s in tool.get("related", []) if s in live]
    for t in tools:  # fill from the same subcategory, in nav order
        if len(picked) >= RELATED_COUNT:
            break
        if t["subcategory"] == tool["subcategory"] and t["slug"] in live and t["slug"] not in picked:
            picked.append(t["slug"])
    if not picked:
        return ""
    items = "".join(tool_card_link(live[s]) for s in picked[:RELATED_COUNT])
    return f'<section class="related-tools"><h2>Related calculators</h2><ul class="tool-grid">{items}</ul></section>'


def base_values(site, nav_html, footer_html, meta_title, meta_description, slug, preview, h1, subtitle, trail):
    return {
        "SITE_NAME": esc(site["site_name"]),
        "META_TITLE": esc(meta_title or h1),
        "META_DESCRIPTION": esc(meta_description),
        "CANONICAL_URL": url(site, slug),
        "ROBOTS": "noindex, nofollow" if preview else "index, follow",
        "ADSENSE_CLIENT": site["adsense_client"],
        "NAV": nav_html,
        "BREADCRUMB": render_breadcrumb(trail) if trail else "",
        "H1": esc(h1),
        "SUBTITLE": esc(subtitle),
        "FOOTER": footer_html,
        "YEAR": str(date.today().year),
    }


# --- page renderers -------------------------------------------------------------------
def render_tool(site, tool, tools, hubs, nav_html, footer_html):
    hub = hubs[tool["subcategory"]]
    trail = [("Home", ""), (hub["name"], hub["slug"]), (tool["name"], tool["slug"])]
    card = tool["card"]
    fields = card.get("fields_html") or (
        '<p class="tool-preview-note">This calculator is planned and not built yet.</p>')
    values = base_values(site, nav_html, footer_html, tool["meta_title"], tool["meta_description"],
                         tool["slug"], tool["preview"], tool["h1"], tool["subtitle"], trail)
    app = {"@context": "https://schema.org", "@type": "WebApplication", "name": tool["name"],
           "url": url(site, tool["slug"]), "applicationCategory": "FinanceApplication",
           "operatingSystem": "Any", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}}
    if tool["meta_description"]:
        app["description"] = tool["meta_description"]
    values.update({
        "JSON_LD": json_ld(app, breadcrumb_ld(site, trail), faq_ld(tool["faq"])),
        "TOOL_CARD": f'<div class="tool-card" data-tool="{esc(tool["slug"])}">{fields}</div>',
        "CONTENT_SECTIONS": split_content_by_h2(tool["content_html"]),
        "FAQ": render_faq(tool["faq"]),
        "RELATED_TOOLS": related_tools(tool, tools),
        "DISCLAIMER": esc(site["disclaimer"]),
        "TOOL_EXTRA_SCRIPTS": "".join(f'<script src="{esc(s)}" defer></script>'
                                      for s in card.get("extra_scripts", [])),
        "TOOL_SCRIPT": f"<script>{tool['script']}</script>" if tool["script"].strip() else "",
    })
    return render("tool.html", values)


def render_hub(site, hub, tools_by_slug, nav_html, footer_html, preview):
    trail = [("Home", ""), (hub["name"], hub["slug"])]
    title = f"{hub['name']} Calculators"
    values = base_values(site, nav_html, footer_html, f"{title} | {site['site_name']}", hub["description"],
                         hub["slug"], preview, title, hub["description"], trail)
    items = [tools_by_slug[s] for s in hub["tools"]]
    values["JSON_LD"] = json_ld(
        {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
         "url": url(site, hub["slug"]), "description": hub["description"],
         "hasPart": [{"@type": "WebApplication", "name": t["name"], "url": url(site, t["slug"])} for t in items]},
        breadcrumb_ld(site, trail))
    values["TOOL_GRID"] = f'<ul class="tool-grid">{"".join(tool_card_link(t) for t in items)}</ul>'
    return render("hub.html", values)


def render_home(site, nav_html, footer_html, preview):
    groups = []
    for group in site["nav"]:
        cards = "".join(
            f'<li class="category-card"><a href="/{s["slug"]}"><span class="category-name">{esc(s["name"])}</span>'
            f'<span class="category-desc">{esc(s["description"])}</span>'
            f'<span class="category-count">{len(s["tools"])} calculators</span></a></li>'
            for s in group["subcategories"])
        groups.append(f'<section class="category-group"><h2>{esc(group["name"])}</h2>'
                      f'<ul class="category-grid">{cards}</ul></section>')
    values = base_values(site, nav_html, footer_html, site["home_meta_title"], site["home_meta_description"],
                         "", preview, site["home_title"], site["home_subtitle"], None)
    values["JSON_LD"] = json_ld({"@context": "https://schema.org", "@type": "WebSite",
                                 "name": site["site_name"], "url": url(site)})
    values["CATEGORY_GRID"] = "".join(groups)
    return render("home.html", values)


def render_info_page(site, page, nav_html, footer_html):
    trail = [("Home", ""), (page["h1"], page["slug"])]
    values = base_values(site, nav_html, footer_html, page["meta_title"], page["meta_description"],
                         page["slug"], page["preview"], page["h1"], page.get("subtitle", ""), trail)
    values["JSON_LD"] = json_ld(breadcrumb_ld(site, trail))
    values["CONTENT_HTML"] = page["content_html"] or '<p class="tool-preview-note">This page is planned.</p>'
    return render("page.html", values)


def render_sitemap_page(site, tools_by_slug, nav_html, footer_html, preview):
    trail = [("Home", ""), ("Sitemap", "sitemap")]
    blocks = []
    for group in site["nav"]:
        subs = "".join(
            f'<h3><a href="/{s["slug"]}">{esc(s["name"])}</a></h3><ul>'
            + "".join(f'<li><a href="/{t}">{esc(tools_by_slug[t]["name"])}</a></li>' for t in s["tools"])
            + "</ul>" for s in group["subcategories"])
        blocks.append(f"<h2>{esc(group['name'])}</h2>{subs}")
    values = base_values(site, nav_html, footer_html, f"Sitemap | {site['site_name']}",
                         f"Every calculator on {site['site_name']}, grouped by topic.", "sitemap", preview,
                         "Sitemap", "", trail)
    values["JSON_LD"] = json_ld(breadcrumb_ld(site, trail))
    values["CONTENT_HTML"] = "".join(blocks)
    return render("page.html", values)


def render_404(site, nav_html, footer_html):
    values = base_values(site, nav_html, footer_html, f"Page not found | {site['site_name']}",
                         "", "404", True, "Page not found", "", None)
    values["JSON_LD"] = ""
    values["CONTENT_HTML"] = '<p>That page doesn\'t exist. Try the <a href="/">home page</a> or the <a href="/sitemap">sitemap</a>.</p>'
    return render("page.html", values)


def sitemap_xml(site, slugs):
    today = date.today().isoformat()
    urls = "".join(f"<url><loc>{esc(url(site, s))}</loc><lastmod>{today}</lastmod></url>" for s in slugs)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')


# --- main ------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--include-planned", action="store_true",
                    help="also render planned tools/pages as noindex previews (for template work)")
    args = ap.parse_args()

    site, tools, pages = build_data.build(include_planned=args.include_planned)
    tools_by_slug = {t["slug"]: t for t in tools}
    hubs = {h["slug"]: h for h in pages["hubs"]}
    nav_html, footer_html = render_nav(site, tools_by_slug), render_footer(site)

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(STATIC, OUT)

    def write(slug, content):
        (OUT / f"{slug}.html").write_text(content, encoding="utf-8")

    indexable = [""]  # home
    write("index", render_home(site, nav_html, footer_html, preview=False))
    for tool in tools:
        if tool["live"]:
            write(tool["slug"], render_tool(site, tool, tools, hubs, nav_html, footer_html))
            if not tool["preview"]:
                indexable.append(tool["slug"])
    for hub in pages["hubs"]:
        hub_preview = all(tools_by_slug[s]["preview"] for s in hub["tools"])
        write(hub["slug"], render_hub(site, hub, tools_by_slug, nav_html, footer_html, hub_preview))
        if not hub_preview:
            indexable.append(hub["slug"])
    for page in pages["info_pages"]:
        if page["live"]:
            write(page["slug"], render_info_page(site, page, nav_html, footer_html))
            if not page["preview"]:
                indexable.append(page["slug"])
    write("sitemap", render_sitemap_page(site, tools_by_slug, nav_html, footer_html, preview=False))
    indexable.append("sitemap")
    write("404", render_404(site, nav_html, footer_html))

    (OUT / "sitemap.xml").write_text(sitemap_xml(site, indexable), encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {url(site, 'sitemap.xml')}\n",
                                    encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")  # serve files as-is on GitHub Pages
    print(f"Wrote {OUT.relative_to(ROOT)}/ — {len(indexable)} indexable URLs in sitemap.xml")


if __name__ == "__main__":
    main()
