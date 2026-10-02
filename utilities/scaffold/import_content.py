#!/usr/bin/env python3
"""Import generated article content into the tool JSON files.

Reads the on-page SEO pipeline's per-slug output folders and, for every folder that has a
config.json and content.html, writes into src/content/tools/<slug>.json:

  content_html   <- content.html (image paths rewritten to /assets/images/tools/<slug>/...)
  faq            <- config.json "faqs_json"
  meta_title, meta_description, h1  <- meta.json (skip with --keep-meta)

The calculator itself (card, script) is never touched. Infographic SVGs are copied to
src/static/assets/images/tools/<slug>/. With --demote-rest, every tool that was not imported
and is still `built` without content is set to `planned` (shown as "Coming soon").

    python3 utilities/scaffold/import_content.py SOURCE_DIR            # dry run
    python3 utilities/scaffold/import_content.py SOURCE_DIR --apply [--demote-rest] [--keep-meta]
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "src" / "content" / "tools"
IMAGES = ROOT / "src" / "static" / "assets" / "images" / "tools"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    ap.add_argument("--keep-meta", action="store_true", help="leave title, description and h1 unchanged")
    ap.add_argument("--demote-rest", action="store_true", help="set non-imported content-less tools to planned")
    args = ap.parse_args()

    imported, skipped, problems = [], [], []
    for folder in sorted(p for p in args.source.iterdir() if p.is_dir() and not p.name.startswith("_")):
        slug = folder.name
        tool_file = TOOLS / f"{slug}.json"
        if not tool_file.exists():
            skipped.append((slug, "no matching tool JSON")); continue
        if not (folder / "config.json").exists() or not (folder / "content.html").exists():
            skipped.append((slug, "no config.json/content.html (generation incomplete)")); continue
        config = load(folder / "config.json")
        faqs = [{"question": f["question"].strip(), "answer": f["answer"].strip()}
                for f in config.get("faqs_json") or [] if f.get("question") and f.get("answer")]
        html = (folder / "content.html").read_text(encoding="utf-8").strip()
        if not html or not faqs:
            skipped.append((slug, "empty content or FAQ")); continue

        html = re.sub(r'(<img\b[^>]*?\bsrc=")images/([^"]+)"',
                      lambda m: f'{m.group(1)}/assets/images/tools/{slug}/{m.group(2)}"', html)
        if re.search(r'src="(?!/assets/|https?://|data:)', html):
            problems.append(f"{slug}: unrewritten image path")
        images = sorted((folder / "images").glob("*.svg")) if (folder / "images").is_dir() else []
        for img in re.findall(r'/assets/images/tools/[^/]+/([^"]+)"', html):
            if not (folder / "images" / img).exists():
                problems.append(f"{slug}: {img} referenced but not in images/")

        tool = load(tool_file)
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
