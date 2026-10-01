#!/usr/bin/env python3
"""Write a field brief for a calculator from the offline competitor mirrors.

For each competitor URL in a tool's `research.competitors` (src/content/tools/<slug>.json) this
finds the mirrored page and lists what the calculator asks for: input names, labels, default
values, select/radio options, and the page's section headings (hints at the outputs). dinkytown's
calculators are JavaScript apps, so their fields are read from the KJE scripts the page loads.

The brief is research material for deciding a tool's inputs and outputs — never copy competitor
text or code into the site. Briefs are written to field_briefs/ (gitignored).

    .venv/bin/python extract_fields.py mortgage-calculator auto-loan-calculator
    .venv/bin/python extract_fields.py --priority 3          # every planned tool at priority 3
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1] / "src" / "content" / "tools"
OUT = HERE / "field_briefs"

KJE_FIELD = re.compile(r'KJE\.(\w+)\("([A-Z][A-Z_0-9]*)","([^"]*)"')
KJE_PARAM = re.compile(r'KJE\.parameters\.set\("([A-Z][A-Z_0-9]*)",\s*([^)]*)\)')


def mirror_file(site, url):
    """Map a competitor URL to its file in <site>/mirror (same rules as crawl.local_path)."""
    p = urlsplit(url)
    path = unquote(p.path)
    if path.endswith("/"):
        path += "index.html"
    if not Path(path).suffix:
        path += ".html"
    if p.query:
        stem, ext = path.rsplit(".", 1)
        path = f"{stem}__{re.sub(r'[^A-Za-z0-9_-]+', '-', p.query)}.{ext}"
    return HERE / site / "mirror" / path.lstrip("/")


def text(el):
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def label_for(soup, el):
    if el.get("id"):
        lab = soup.find("label", attrs={"for": el["id"]})
        if lab and text(lab):
            return text(lab)
    lab = el.find_parent("label")
    if lab and text(lab):
        return text(lab)
    # calculator.net / fncalculator put the label in the previous table cell.
    td = el.find_parent("td")
    if td:
        prev = td.find_previous_sibling("td")
        if prev and text(prev):
            return text(prev)
    prev = el.find_previous(string=lambda s: s and s.strip())
    return " ".join(prev.split())[:60] if prev else ""


def html_fields(soup):
    lines, radios = [], {}
    for el in soup.find_all(["input", "select", "textarea"]):
        kind = el.get("type", el.name).lower()
        name = el.get("name") or el.get("id") or ""
        if kind in ("hidden", "submit", "button", "reset", "image", "search") or name in ("q",) or "search" in name.lower():
            continue
        if kind == "radio":
            radios.setdefault(name, []).append(
                (label_for(soup, el) or el.get("value", ""), el.has_attr("checked")))
            continue
        line = f"- `{name}` ({kind}) — {label_for(soup, el)}"
        if el.name == "select":
            opts = [("*" if o.has_attr("selected") else "") + text(o) for o in el.find_all("option")]
            line += f" — options: {', '.join(opts[:15])}{' …' if len(opts) > 15 else ''}"
        elif kind == "checkbox":
            line += " — checked" if el.has_attr("checked") else " — unchecked"
        elif el.get("value") not in (None, ""):
            line += f" — default `{el['value']}`"
        lines.append(line)
    for name, opts in radios.items():
        lines.append(f"- `{name}` (radio) — " + ", ".join(("*" if c else "") + lab for lab, c in opts))
    return lines


def kje_fields(page, soup):
    lines = []
    for s in soup.find_all("script", src=True):
        src = s["src"]
        if src.startswith("http") or "KJE" in src or src.startswith("../"):
            continue
        js = page.parent / src
        if not js.exists():
            continue
        body = js.read_text(errors="ignore")
        kind = "defaults" if js.stem.endswith("Params") else "inputs"
        found = (KJE_PARAM.findall(body) if kind == "defaults"
                 else [(n, f"{lab} ({widget})") for widget, n, lab in KJE_FIELD.findall(body)])
        seen = set()
        for name, val in found:
            if name.startswith("MSG_") or name in seen:
                continue
            seen.add(name)
            lines.append(f"- [{js.name} {kind}] `{name}` — {val.strip()}")
    return lines


def brief(slug):
    tool = json.loads((TOOLS / f"{slug}.json").read_text())
    out = [f"# {tool['name']} (`{slug}`)", "",
           f"Subcategory: {tool['subcategory']} · priority {tool.get('priority')} · status {tool['status']}"]
    research = tool.get("research") or {}
    if research.get("name_variants"):
        out.append("Name variants: " + "; ".join(research["name_variants"]))
    if tool.get("legacy"):
        out.append(f"Legacy source to port: {tool['legacy']['source']}")
    for comp in research.get("competitors", []):
        page = mirror_file(comp["site"], comp["url"])
        out += ["", f"## {comp['site']} — {comp['url']}"]
        if not page.exists():
            out.append(f"(not in mirror: {page.relative_to(HERE)})")
            continue
        out.append(f"Mirror: {page.relative_to(HERE)}")
        soup = BeautifulSoup(page.read_text(errors="ignore"), "html.parser")
        fields = kje_fields(page, soup) if comp["site"] == "dinkytown.net" else []
        fields += html_fields(soup)
        out += ["", "Inputs:"] + (fields or ["(none found)"])
        heads = [text(h) for h in soup.find_all(["h2", "h3"]) if 2 < len(text(h)) < 90]
        if heads:
            out += ["", "Headings: " + " | ".join(heads[:25])]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--priority", type=int, help="all planned tools at this priority")
    ap.add_argument("--quiet", action="store_true", help="write files only, don't print")
    args = ap.parse_args()
    slugs = list(args.slugs)
    if args.priority:
        for f in sorted(TOOLS.glob("*.json")):
            t = json.loads(f.read_text())
            if t.get("priority") == args.priority and t["status"] == "planned":
                slugs.append(t["slug"])
    if not slugs:
        ap.error("give tool slugs or --priority")
    OUT.mkdir(exist_ok=True)
    for slug in slugs:
        if not (TOOLS / f"{slug}.json").exists():
            sys.exit(f"no tool file for {slug!r}")
        b = brief(slug)
        (OUT / f"{slug}.md").write_text(b)
        if not args.quiet:
            print(b)
    print(f"Wrote {len(slugs)} brief(s) to {OUT.relative_to(HERE)}/", file=sys.stderr)


if __name__ == "__main__":
    main()
