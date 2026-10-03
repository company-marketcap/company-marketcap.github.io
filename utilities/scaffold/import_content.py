#!/usr/bin/env python3
"""Import generated article content into the tool JSON files.

Reads the on-page SEO pipeline's per-slug output folders and, for every folder that has a
config.json and content.html, writes into src/content/tools/<slug>.json:

  content_html   <- content.html (image paths rewritten to /assets/images/tools/<slug>/...)
  faq            <- config.json "faqs_json"
  subtitle       <- the article's opening <p> as plain text (hero intro under the H1); the paragraph
                    is removed from content_html so it appears once
  meta_title, meta_description, h1  <- meta.json (skip with --keep-meta)

The calculator itself (card, script) is never touched. Infographic SVGs are copied to
src/static/assets/images/tools/<slug>/. With --demote-rest, every tool that was not imported
and is still `built` without content is set to `planned` (shown as "Coming soon").

    python3 utilities/scaffold/import_content.py SOURCE_DIR            # dry run
    python3 utilities/scaffold/import_content.py SOURCE_DIR --apply [--demote-rest] [--keep-meta]

The home page article is imported separately from one output folder:

    python3 utilities/scaffold/import_content.py --home HOME_OUTPUT_DIR [--apply]

The category page article is imported the same way with `--category CATEGORY_OUTPUT_DIR`
(src/config/categories.json, "category" object).

The home import sets subtitle in src/content/pages/home.json from the article's opening paragraph (plain text, shown under
the H1), content_html from the rest, and copies the infographic SVGs to src/static/assets/images/home/. Nothing else on the home page changes.
"""
import argparse
import html as htmllib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "src" / "content" / "tools"
HOME_PAGE = ROOT / "src" / "content" / "pages" / "home.json"
HOME_IMAGES = ROOT / "src" / "static" / "assets" / "images" / "home"
CATEGORIES = ROOT / "src" / "config" / "categories.json"
CATEGORY_IMAGES = ROOT / "src" / "static" / "assets" / "images" / "category"
IMAGES = ROOT / "src" / "static" / "assets" / "images" / "tools"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def import_article(folder, apply, label, images_dir, images_url, get_target, save_target):
    """Shared by --home and --category: opening paragraph -> subtitle, the rest -> content_html, SVGs copied."""
    html = (folder / "content.html").read_text(encoding="utf-8").strip()
    html = re.sub(r'(<img\b[^>]*?\bsrc=")images/([^"]+)"', lambda m: f'{m.group(1)}{images_url}/{m.group(2)}"', html)
    images = sorted((folder / "images").glob("*.svg")) if (folder / "images").is_dir() else []
    problems = [f"{name} referenced but not in images/" for name in re.findall(re.escape(images_url) + r'/([^"]+)"', html)
                if not (folder / "images" / name).exists()]
    opening = re.match(r"\s*<p>(.*?)</p>\s*", html, re.S)
    if not opening:
        print("PROBLEM the article does not open with a <p>")
        return 1
    subtitle = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", "", opening.group(1))).split())
    html = html[opening.end():].strip()
    if apply:
        target = get_target()
        target["subtitle"] = subtitle
        target["content_html"] = html
        save_target(target)
        if images:
            images_dir.mkdir(parents=True, exist_ok=True)
            for img in images:
                shutil.copy2(img, images_dir / img.name)
    print(f"{'APPLIED' if apply else 'DRY RUN'}: {label} article {len(html)} characters, {len(images)} infographic(s)")
    for problem in problems:
        print(f"  PROBLEM {problem}")
    return 1 if problems else 0


def import_home(folder, apply):
    return import_article(folder, apply, "home", HOME_IMAGES, "/assets/images/home",
                          lambda: load(HOME_PAGE), lambda page: save(HOME_PAGE, page))


def import_category(folder, apply):
    def save_category(category):
        data = load(CATEGORIES)
        data["category"] = category
        save(CATEGORIES, data)
    return import_article(folder, apply, "category", CATEGORY_IMAGES, "/assets/images/category",
                          lambda: load(CATEGORIES)["category"], save_category)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, nargs="?")
    ap.add_argument("--home", type=Path, help="import the home page article from this output folder instead")
    ap.add_argument("--category", type=Path, help="import the category page article from this output folder instead")
    ap.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    ap.add_argument("--keep-meta", action="store_true", help="leave title, description and h1 unchanged")
    ap.add_argument("--demote-rest", action="store_true", help="set non-imported content-less tools to planned")
    ap.add_argument("--allow-no-faq", action="store_true", help="import folders with no config.json / empty FAQ (faq left empty)")
    args = ap.parse_args()
    if args.home:
        return import_home(args.home, args.apply)
    if args.category:
        return import_category(args.category, args.apply)
    if not args.source:
        ap.error("give a SOURCE_DIR, or --home HOME_OUTPUT_DIR")

    imported, skipped, problems = [], [], []
    for folder in sorted(p for p in args.source.iterdir() if p.is_dir() and not p.name.startswith("_")):
        slug = folder.name
        tool_file = TOOLS / f"{slug}.json"
        if not tool_file.exists():
            skipped.append((slug, "no matching tool JSON")); continue
        if not (folder / "content.html").exists() or not ((folder / "config.json").exists() or args.allow_no_faq):
            skipped.append((slug, "no config.json/content.html (generation incomplete)")); continue
        config = load(folder / "config.json") if (folder / "config.json").exists() else {}
        faqs = [{"question": f["question"].strip(), "answer": f["answer"].strip()}
                for f in config.get("faqs_json") or [] if f.get("question") and f.get("answer")]
        html = (folder / "content.html").read_text(encoding="utf-8").strip()
        if not html or not (faqs or args.allow_no_faq):
            skipped.append((slug, "empty content or FAQ")); continue

        html = re.sub(r'(<img\b[^>]*?\bsrc=")images/([^"]+)"',
                      lambda m: f'{m.group(1)}/assets/images/tools/{slug}/{m.group(2)}"', html)
        if re.search(r'src="(?!/assets/|https?://|data:)', html):
            problems.append(f"{slug}: unrewritten image path")
        images = sorted((folder / "images").glob("*.svg")) if (folder / "images").is_dir() else []
        for img in re.findall(r'/assets/images/tools/[^/]+/([^"]+)"', html):
            if not (folder / "images" / img).exists():
                problems.append(f"{slug}: {img} referenced but not in images/")

        opening = re.match(r"\s*<p>(.*?)</p>\s*", html, re.S)
        if not opening:
            skipped.append((slug, "article does not open with a <p>")); continue
        subtitle = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", "", opening.group(1))).split())
        if re.search(r"\\\(|\$\$", subtitle):
            problems.append(f"{slug}: opening paragraph contains a formula (hero does not render math)")
        html = html[opening.end():].strip()

        tool = load(tool_file)
        tool["subtitle"] = subtitle
        tool["content_html"] = html
        tool["faq"] = faqs
        meta_file = folder / "meta.json"
        if not args.keep_meta and meta_file.exists():
            meta = load(meta_file)
            for src, dst in (("title", "meta_title"), ("meta_description", "meta_description"), ("h1", "h1")):
                if meta.get(src):
                    tool[dst] = meta[src].strip()
        imported.append(slug)
        if args.apply:
            save(tool_file, tool)
            if images:
                dest = IMAGES / slug
                dest.mkdir(parents=True, exist_ok=True)
                for img in images:
                    shutil.copy2(img, dest / img.name)

    demoted = []
    if args.demote_rest:
        for f in sorted(TOOLS.glob("*.json")):
            tool = load(f)
            if f.stem not in imported and tool["status"] == "built" and not tool["content_html"].strip():
                demoted.append(f.stem)
                if args.apply:
                    tool["status"] = "planned"
                    save(f, tool)

    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"{mode}: imported {len(imported)}, skipped {len(skipped)}, demoted to planned {len(demoted)}")
    for slug, why in skipped:
        print(f"  skipped {slug}: {why}")
    for p in problems:
        print(f"  PROBLEM {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
