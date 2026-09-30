#!/usr/bin/env python3
"""
Validate the JSON sources and assemble the build data.

Sources of truth (edit these, never the output):
    src/config/site.json           site-wide settings
    src/config/categories.json     the category page + nav groups -> subcategories (its sections)
    src/content/tools/<slug>.json  one file per calculator: its ENTIRE page
    src/content/pages/<slug>.json  home page copy/FAQ + info pages (about, contact, privacy-policy, terms)

Output (build artifacts, gitignored — regenerated on every build):
    src/data/site.json    site settings + resolved nav tree
    src/data/tools.json   every tool, validated, in nav order
    src/data/pages.json   home, category page and info pages

Usage:
    python3 src/build_data.py                    # validate + write src/data/
    python3 src/build_data.py --include-planned  # treat planned tools as live (template preview)
"""
import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
CONFIG_DIR = SRC / "config"
TOOLS_DIR = SRC / "content" / "tools"
PAGES_DIR = SRC / "content" / "pages"
DATA_DIR = SRC / "data"

STATUSES = ["planned", "in_progress", "built", "verified", "done"]
# Statuses that produce a public page. planned/in_progress tools exist only as data.
LIVE_STATUSES = {"built", "verified", "done"}
CARD_LAYOUTS = {"raw"}
REQUIRED_WHEN_LIVE = ["meta_title", "meta_description", "h1", "subtitle", "content_html"]
TITLE_MAX, DESCRIPTION_MAX = 60, 160
# Marker for details still to be filled in (e.g. the contact email). A live page can't contain it.
PLACEHOLDER = "PLACEHOLDER"
# Page slugs generate.py produces itself; a tool can't use them.
RESERVED_SLUGS = {"index", "home", "404", "sitemap"}


class Problems:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


def load_json(path, problems):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        problems.error(path.relative_to(SRC), f"invalid JSON: {e}")
        return None


def check_meta(where, item, problems):
    if len(item.get("meta_title", "")) > TITLE_MAX:
        problems.warn(where, f"meta_title is {len(item['meta_title'])} chars (> {TITLE_MAX})")
    if len(item.get("meta_description", "")) > DESCRIPTION_MAX:
        problems.warn(where, f"meta_description is {len(item['meta_description'])} chars (> {DESCRIPTION_MAX})")


def load_categories(problems):
    cats = load_json(CONFIG_DIR / "categories.json", problems)
    subcats = {}
    for group in cats["nav_groups"]:
        for sub in group["subcategories"]:
            if sub["slug"] in subcats:
                problems.error("categories.json", f"duplicate subcategory slug {sub['slug']!r}")
            subcats[sub["slug"]] = dict(sub, group_id=group["id"], group_name=group["name"])
    return cats, subcats


def load_tools(subcats, include_planned, problems):
    tools = []
    for path in sorted(TOOLS_DIR.glob("*.json")):
        tool = load_json(path, problems)
        if tool is None:
            continue
        where = f"tools/{path.name}"
        if tool.get("slug") != path.stem:
            problems.error(where, f"slug {tool.get('slug')!r} doesn't match file name")
        if tool.get("status") not in STATUSES:
            problems.error(where, f"status must be one of {STATUSES}")
        if tool.get("subcategory") not in subcats:
            problems.error(where, f"unknown subcategory {tool.get('subcategory')!r}")
        if tool.get("card", {}).get("layout") not in CARD_LAYOUTS:
            problems.error(where, f"card.layout must be one of {sorted(CARD_LAYOUTS)}")
        for i, qa in enumerate(tool.get("faq", [])):
            if not qa.get("question") or not qa.get("answer"):
                problems.error(where, f"faq[{i}] needs non-empty question and answer")

        live = tool.get("status") in LIVE_STATUSES
        if live:
            for field in REQUIRED_WHEN_LIVE:
                if not str(tool.get(field, "")).strip():
                    problems.error(where, f"status {tool['status']!r} but {field} is empty")
            if not tool.get("card", {}).get("fields_html", "").strip():
                problems.error(where, f"status {tool['status']!r} but card.fields_html is empty")
            if not tool.get("script", "").strip():
                problems.error(where, f"status {tool['status']!r} but script is empty")
            check_meta(where, tool, problems)
            if PLACEHOLDER in json.dumps(tool):
                problems.error(where, f"status {tool['status']!r} but it still contains a {PLACEHOLDER} marker")
        tool["live"] = live or include_planned
        tool["preview"] = include_planned and not live
        tools.append(tool)

    slugs = {t["slug"] for t in tools}
    for tool in tools:
        for rel in tool.get("related", []):
            if rel not in slugs:
                problems.error(f"tools/{tool['slug']}.json", f"related slug {rel!r} does not exist")
        if tool["slug"] in RESERVED_SLUGS:
            problems.error(f"tools/{tool['slug']}.json", "slug collides with a reserved page")
    # Nav order: subcategory order from categories.json, then each tool's own order, then name.
    sub_order = {slug: i for i, slug in enumerate(subcats)}
    tools.sort(key=lambda t: (sub_order.get(t.get("subcategory"), 999), t.get("order", 999),
                              t.get("name", "").lower()))
    return tools


def load_info_pages(site, include_planned, problems):
    pages = []
    for slug in site["info_pages"]:
        if slug == "sitemap":
            continue  # generated by generate.py from the nav tree
        path = PAGES_DIR / f"{slug}.json"
        if not path.exists():
            problems.error(f"pages/{slug}.json", "listed in site.json info_pages but missing")
            continue
        page = load_json(path, problems)
        if page is None:
            continue
        live = page.get("status") in LIVE_STATUSES
        if live:
            for field in ("meta_title", "meta_description", "h1", "content_html"):
                if not page.get(field, "").strip():
                    problems.error(f"pages/{slug}.json", f"status {page['status']!r} but {field} is empty")
            check_meta(f"pages/{slug}.json", page, problems)
            if PLACEHOLDER in json.dumps(page):
                problems.error(f"pages/{slug}.json", f"status {page['status']!r} but it still contains a {PLACEHOLDER} marker")
        page["live"] = live or include_planned
        page["preview"] = include_planned and not live
        pages.append(page)
    return pages


def build(include_planned=False, write=True):
    problems = Problems()
    site = load_json(CONFIG_DIR / "site.json", problems)
    cats, subcats = load_categories(problems)
    tools = load_tools(subcats, include_planned, problems)
    info_pages = load_info_pages(site, include_planned, problems)
    home = load_json(PAGES_DIR / "home.json", problems)
    category = cats["category"]
    reserved = RESERVED_SLUGS | {category["slug"]} | set(site["info_pages"])
    for tool in tools:
        if tool["slug"] in reserved:
            problems.error(f"tools/{tool['slug']}.json", "slug collides with the category page or an info page")

    # Nav tree: groups -> subcategories -> every tool (live ones are linked, planned ones listed
    # as "coming soon" by generate.py). Subcategories/groups with no tools at all are hidden.
    nav = []
    for group in cats["nav_groups"]:
        subs = []
        for sub in group["subcategories"]:
            sub_tools = [t["slug"] for t in tools if t["subcategory"] == sub["slug"]]
            if sub_tools:
                subs.append(dict(sub, tools=sub_tools))
        if subs:
            nav.append({k: group[k] for k in ("id", "name", "color", "symbol", "description")} | {"subcategories": subs})

    site_out = dict(site, nav=nav)
    pages_out = {"home": home, "category": category, "info_pages": info_pages}

    for w in problems.warnings:
        print(f"warning: {w}")
    if problems.errors:
        for e in problems.errors:
            print(f"error: {e}", file=sys.stderr)
        raise SystemExit(f"{len(problems.errors)} error(s) — nothing written")

    if write:
        DATA_DIR.mkdir(exist_ok=True)
        for name, data in (("site", site_out), ("tools", tools), ("pages", pages_out)):
            (DATA_DIR / f"{name}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    counts = {s: sum(1 for t in tools if t["status"] == s) for s in STATUSES}
    print(f"{len(tools)} tools — " + ", ".join(f"{s}: {n}" for s, n in counts.items() if n) +
          f" · {sum(1 for t in tools if t['live'])} live tool pages"
          + (" (planned included for preview)" if include_planned else ""))
    return site_out, tools, pages_out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--include-planned", action="store_true",
                    help="treat planned/in-progress tools and pages as live (noindex preview)")
    build(ap.parse_args().include_planned)


if __name__ == "__main__":
    main()
