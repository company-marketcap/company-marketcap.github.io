#!/usr/bin/env python3
"""
Monthly silo link rotation for Company Marketcap — all 320 tools (live pages get links, planned tools wait).

Reads silo_plan.json (built by build_silo_plan.py from the Google Ads volumes) and patches one rotating
sentence-with-link into each live tool page in public/. Stdlib only.

  Pillar     (7)    slot_a  one link down to a sub-silo, rotated monthly
  Sub-silo   (27)   slot_a  up to its pillar
                    slot_b/c  horizontal neighbour sub-silos in the same pillar (order shuffled monthly)
                    slot_d  down to the first supporting page of its own chain
  Supporting (286)  slot_a  up to its sub-silo
                    slot_b/c  previous/next page in its chain — chains bridge into each other linearly
                              inside one pillar (the last chain does not wrap to the first)

Every tool with a page is linked (a tool whose status isn't built/verified/done is skipped, and if a sub-silo is
skipped the first live page of its chain acts as the sub-silo). Pages without an article yet get only the intro
link (slot_a); generate.py shows Related calculators on those pages and drops it once the article exists.

Anchor text rotates among four variants of the tool's best keyword; the sentence rotates among six templates;
both are chosen deterministically per (source page, slot, month).

Pages are patched in place with comment markers (<!-- SILO_START:slot_a -->…<!-- SILO_END:slot_a -->):
slot_a lands at the end of the hero intro (the page renders it twice — the desktop copy and the mobile copy — so
the same link goes into both, as slot_a and slot_a_m); slot_b..d land after the first paragraph of the 1st..3rd
article section (the "guide" headings). Nothing is ever injected inside the calculator card. Run AFTER src/generate.py — the build wipes public/ and knows nothing about the markers.

    python3 utilities/silo_linking/generate_silo_rotation.py [--dry-run] [--date=YYYY-MM]
"""
import datetime
import hashlib
import html as html_lib
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
PAGES_DIR = ROOT / "public"
PLAN = json.loads((HERE / "silo_plan.json").read_text(encoding="utf-8"))
LIVE_STATUSES = {"built", "verified", "done"}
TOOLS_DIR = ROOT / "src" / "content" / "tools"


def tool_is_live(slug):
    """Read the status from the tool JSON at run time, so the plan never goes stale when tools are built."""
    path = TOOLS_DIR / f"{slug}.json"
    return path.exists() and json.loads(path.read_text(encoding="utf-8")).get("status") in LIVE_STATUSES

SENTENCES = [
    "Try the {link} to run your own numbers — everything is calculated in your browser and nothing you enter is stored or sent anywhere.",
    "The {link} is free to use with no sign-up, and works on desktop and mobile.",
    "If you want to see how the figures change, the {link} gives you an instant result you can adjust as you go.",
    "Pair this with the {link} for a fuller picture before you make a decision.",
    "The {link} uses the same plain-English approach, so you can compare results side by side.",
    "Next, open the {link} and enter your own details to see an estimate in seconds.",
]


# --- anchors & rotation helpers ----------------------------------------------------------------------
OVERRIDES = {k: v for k, v in json.loads((HERE / "anchor_overrides.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
QUESTION_START = re.compile(r"^(should|how|what|when|why|is|can|do|does|will)\b")
MAX_WORDS = 6  # longer phrases read badly as anchor text


def plain(text):
    """A tool name as a lower-case phrase: '401(k) Calculator' -> '401k calculator'."""
    t = re.sub(r"\((\w)\)", r"\1", text.lower())
    t = re.sub(r"[^a-z0-9' ]+", " ", t.replace("&", " and "))
    return re.sub(r"\s+", " ", t).strip()


def anchor_variants(target):
    """Four anchors at most: the keyword, the tool's own name, 'free …' and '… online'. The last two only suit
    short noun phrases (so the result stays within MAX_WORDS); questions and long phrases keep just their plain forms."""
    kw = OVERRIDES.get(target["slug"], target["anchor"]).strip()
    variants = [kw]
    name = plain(target["name"])
    if len(name.split()) <= MAX_WORDS and not QUESTION_START.match(name):
        variants.append(name)
    if len(kw.split()) < MAX_WORDS and not QUESTION_START.match(kw):  # room for the extra word
        if not kw.startswith("free "):
            variants.append(f"free {kw}")
        if not kw.endswith(" online"):
            variants.append(f"{kw} online")
    return list(dict.fromkeys(variants))


def month_key(today):
    return f"{today.year}-M{today.month:02d}"


def pick(items, seed_key, today):
    idx = int(hashlib.md5(f"{month_key(today)}-{seed_key}".encode()).hexdigest(), 16) % len(items)
    return items[idx]


def shuffle(items, seed_key, today):
    seed = int(hashlib.md5(f"{month_key(today)}-{seed_key}".encode()).hexdigest(), 16)
    items = list(items)
    random.Random(seed).shuffle(items)
    return items


def link(src_slug, slot, target, today):
    anchor = pick(anchor_variants(target), f"{src_slug}_{slot}_anchor", today)
    sentence = pick(SENTENCES, f"{src_slug}_{slot}_sentence", today)
    return {"slot": slot, "anchor": anchor, "url": f"/{target['slug']}.html", "sentence": sentence}


def empty(slot):
    return {"slot": slot, "anchor": None}


# --- live structure ------------------------------------------------------------------------------------
def live_structure(cluster):
    """Pillar + chains reduced to live pages. A planned sub-silo is replaced by the chain's first live page."""
    live = lambda n: tool_is_live(n["slug"])  # noqa: E731
    chains = []
    for ss in cluster["subsilos"]:
        pages = [n for n in ss["chain"] if live(n)]
        if pages:
            chains.append({"head": pages[0], "support": pages[1:]})
    return cluster["pillar"] if live(cluster["pillar"]) else None, chains


def generate_links(today):
    links = {}
    for cluster in PLAN["clusters"]:
        pillar, chains = live_structure(cluster)
        if not pillar or not chains:
            continue
        cid = cluster["id"]
        heads = [c["head"] for c in chains]

        links[pillar["slug"]] = [link(pillar["slug"], "slot_a", pick(heads, f"{cid}_pillar_down", today), today)]

        shuffled_support = [shuffle(c["support"], f"{cid}_chain{i}", today) for i, c in enumerate(chains)]
        order = shuffle(list(range(len(chains))), f"{cid}_subsilo_order", today)
        for pos, i in enumerate(order):
            head = chains[i]["head"]
            left = chains[order[pos - 1]]["head"] if pos > 0 else None
            right = chains[order[pos + 1]]["head"] if pos < len(order) - 1 else None
            down = shuffled_support[i][0] if shuffled_support[i] else None
            src = head["slug"]
            links[src] = [
                link(src, "slot_a", pillar, today),
                link(src, "slot_b", left, today) if left else empty("slot_b"),
                link(src, "slot_c", right, today) if right else empty("slot_c"),
                link(src, "slot_d", down, today) if down else empty("slot_d"),
            ]

        # Supporting chains bridge linearly: chain 0 -> chain 1 -> ... (no wraparound).
        nonempty = [i for i, s in enumerate(shuffled_support) if s]
        for k, i in enumerate(nonempty):
            pages = shuffled_support[i]
            prev_bridge = shuffled_support[nonempty[k - 1]][-1] if k > 0 else None
            next_bridge = shuffled_support[nonempty[k + 1]][0] if k < len(nonempty) - 1 else None
            for pos, page in enumerate(pages):
                left = pages[pos - 1] if pos > 0 else prev_bridge
                right = pages[pos + 1] if pos < len(pages) - 1 else next_bridge
                src = page["slug"]
                links[src] = [
                    link(src, "slot_a", chains[i]["head"], today),
                    link(src, "slot_b", left, today) if left else empty("slot_b"),
                    link(src, "slot_c", right, today) if right else empty("slot_c"),
                ]
    return links


# --- HTML patching -------------------------------------------------------------------------------------
SLOT_SECTION = {"slot_b": 1, "slot_c": 2, "slot_d": 3}  # article section (guide heading) index
INTRO_IDS = {"slot_a": "hero-intro", "slot_a_m": "hero-intro-mobile"}  # slot_a is injected into both intro copies


def article_paragraph_ends(html, slug):
    """{section number: [offsets of each </p> in that article section]} — bounded to before the footer."""
    footer = html.find("<footer")
    body = html if footer == -1 else html[:footer]
    heads = [(int(m.group(1)), m.end()) for m in re.finditer(rf'<h2\b[^>]*id="{re.escape(slug)}-guide-heading-(\d+)"[^>]*>.*?</h2>', body, re.S)]
    out = {}
    for k, (num, end) in enumerate(heads):
        stop = body.find("<h2", end)
        stop = len(body) if stop == -1 else stop
        out[num] = [end + m.start() for m in re.finditer(r"</p>", body[end:stop])]
    return out


def slot_positions(html, slug, slots):
    """Insertion offset per slot. Sections that don't exist fall back to the last section's later paragraphs."""
    ends = article_paragraph_ends(html, slug)
    if not ends:
        return {}
    last = max(ends)
    used = set()
    result = {}
    for slot in slots:
        num = SLOT_SECTION[slot]
        candidates = [(num, 0)] if num in ends else []
        candidates += [(last, p) for p in range(len(ends[last]))]
        for sec, p in candidates:
            if sec in ends and p < len(ends[sec]) and (sec, p) not in used:
                used.add((sec, p))
                result[slot] = ends[sec][p]
                break
    return result


def intro_position(html, slug, intro_id):
    m = re.search(rf'<p\b[^>]*id="{re.escape(slug)}-{intro_id}"[^>]*>', html)
    end = html.find("</p>", m.end()) if m else -1
    return end if end != -1 else None


def sentence_html(sentence, url, anchor):
    return sentence.replace("{link}", f'<a class="silo-link" href="{url}">{html_lib.escape(anchor)}</a>')


def patch(html, slug, link_defs):
    # Remove earlier markers first so positions are computed on a clean page, then reinsert all slots.
    html = re.sub(r" ?<!-- SILO_START:(slot_[a-d](?:_m)?) -->.*?<!-- SILO_END:\1 -->", "", html, flags=re.S)
    link_defs = [d for d in link_defs if d["anchor"]]
    wanted = []
    for d in link_defs:  # slot_a goes into both intro copies
        wanted += [dict(d, slot=s) for s in INTRO_IDS] if d["slot"] == "slot_a" else [d]
    if not article_paragraph_ends(html, slug):  # no article yet: only the intro link; Related calculators cover the rest
        wanted = [d for d in wanted if d["slot"] in INTRO_IDS]
    positions = slot_positions(html, slug, [d["slot"] for d in wanted if d["slot"] in SLOT_SECTION])
    for slot, intro_id in INTRO_IDS.items():
        pos = intro_position(html, slug, intro_id)
        if pos is not None:
            positions[slot] = pos
    errors = [f"INJECT FAILED: {slug}/{d['slot']} — no target paragraph" for d in wanted if d["slot"] not in positions]
    for d in sorted(wanted, key=lambda d: -positions.get(d["slot"], -1)):
        pos = positions.get(d["slot"])
        if pos is None:
            continue
        s, e = f"<!-- SILO_START:{d['slot']} -->", f"<!-- SILO_END:{d['slot']} -->"
        html = html[:pos] + f" {s}{sentence_html(d['sentence'], d['url'], d['anchor'])}{e}" + html[pos:]
    return html, errors


def run(today, dry_run=False):
    links = generate_links(today)
    errors, changed = [], 0
    for slug, defs in links.items():
        path = PAGES_DIR / f"{slug}.html"
        if not path.exists():
            errors.append(f"MISSING FILE: {slug}.html")
            continue
        original = path.read_text(encoding="utf-8")
        html, errs = patch(original, slug, defs)
        errors += errs
        if html != original:
            changed += 1
            if not dry_run:
                path.write_text(html, encoding="utf-8")
    total = sum(1 + sum(len(ss["chain"]) for ss in c["subsilos"]) for c in PLAN["clusters"])
    print(f"{len(links)} live pages linked of {total} tools in the plan; {changed} files {'would change' if dry_run else 'updated'}.")
    return errors


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    today = datetime.date.today()
    for arg in sys.argv[1:]:
        if arg.startswith("--date="):
            try:
                year, month = map(int, arg.split("=", 1)[1].split("-"))
                today = datetime.date(year, month, 1)
            except ValueError:
                sys.exit(f"Invalid {arg!r}. Expected --date=YYYY-MM.")
    print(f"Silo rotation — Company Marketcap — {month_key(today)}" + (" [DRY RUN]" if dry_run else ""))
    errs = run(today, dry_run)
    warnings = [e for e in errs if e.startswith("INJECT FAILED")]
    fatal = [e for e in errs if not e.startswith("INJECT FAILED")]
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    if fatal:
        for e in fatal:
            print(f"  error: {e}", file=sys.stderr)
        sys.exit(1)
    print("Done.")
