#!/usr/bin/env python3
"""
Builds the silo structure for all 320 tools from the Google Ads volume spreadsheet.

    python3 utilities/silo_linking/build_silo_plan.py [XLSX]      # default: newest file in
                                                                   # utilities/google_ads_keyword_research/output/
Writes (next to this script):
    silo_plan.json   machine-readable plan, read by generate_silo_rotation.py (stdlib only at run time)
    SILO_PLAN.md     the same plan as a readable report

Structure (decided from the global search volumes):
  Pillar     one per nav group in src/config/categories.json — the highest-volume tool in the group.
  Sub-silo   one per subcategory (the highest-volume tool left after the pillar is taken), plus the
             subcategories larger than CHAIN_CAP tools, which are split by keyword stem (SPLITS below).
  Supporting every other tool, ordered by descending volume inside its sub-silo's chain.

Volume is each tool's `best_volume` (best of its primary keyword and the research name variants);
`best_keyword` is the phrase used as link anchor text. Needs openpyxl (only this script, not the rotation).
"""
import collections
import datetime
import glob
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
CATEGORIES = ROOT / "src" / "config" / "categories.json"
VOLUMES_GLOB = ROOT / "utilities" / "google_ads_keyword_research" / "output" / "companymarketcap_search_volumes_*.xlsx"
CHAIN_CAP = 20

# Subcategories bigger than CHAIN_CAP are split by keyword stem. First matching rule wins; the last
# entry (pattern None) takes everything else.
SPLITS = {
    "mortgage-calculators": [
        ("Home buying & qualifying", r"fha|va-mortgage|down-payment|house-afford|closing-cost|qualifier|maximum-mortgage|required-income|home-buyer|purchase-price|seller"),
        ("Mortgage payments, payoff & rate types", None),
    ],
    "retirement-account-calculators": [
        ("RMDs & pensions", r"rmd|required-minimum|beneficiary|pension|stretch"),
        ("IRA & Roth", r"ira|roth|72t"),
        ("401(k), 403(b) & 457 plans", None),
    ],
    "investment-calculators": [
        ("Portfolio, allocation & fees", r"asset-allocation|sector|questionnaire|fees|inflation|distributions|income|goal|investment-loan|savings-and"),
        ("Investment returns & growth", None),
    ],
}


def load_tools(xlsx):
    import openpyxl
    ws = openpyxl.load_workbook(xlsx, read_only=True)["Tools"]
    rows = list(ws.iter_rows(values_only=True))
    tools = [dict(zip(rows[0], r)) for r in rows[1:]]
    for t in tools:
        t["best_volume"] = t["best_volume"] or 0
    return tools


def node(t):
    return {"slug": t["slug"], "name": t["name"], "anchor": t["best_keyword"],
            "volume": t["best_volume"], "status": t["status"]}


def ranked(tools):
    return sorted(tools, key=lambda t: (-t["best_volume"], t["name"]))


def split_subcategory(slug, tools):
    """-> [(label, [tools])] — one entry unless the subcategory is split."""
    rules = SPLITS.get(slug)
    if not rules:
        return [(None, tools)]
    buckets = collections.OrderedDict((label, []) for label, _ in rules)
    for t in tools:
        for label, pattern in rules:
            if pattern is None or re.search(pattern, t["slug"]):
                buckets[label].append(t)
                break
    return list(buckets.items())


def build(xlsx):
    groups = json.loads(CATEGORIES.read_text(encoding="utf-8"))["nav_groups"]
    tools = load_tools(xlsx)
    by_sub = collections.defaultdict(list)
    for t in tools:
        by_sub[t["subcategory"]].append(t)

    clusters = []
    for g in groups:
        members = [t for s in g["subcategories"] for t in by_sub[s["slug"]]]
        pillar = ranked(members)[0]
        subsilos = []
        for s in g["subcategories"]:
            remaining = [t for t in by_sub[s["slug"]] if t is not pillar]
            for label, bucket in split_subcategory(s["slug"], remaining):
                if not bucket:
                    continue
                chain = ranked(bucket)
                subsilos.append({"label": label or s["name"], "subcategory": s["slug"],
                                 "chain": [node(t) for t in chain]})
        subsilos.sort(key=lambda ss: (-ss["chain"][0]["volume"], ss["label"]))
        clusters.append({"id": g["id"], "group": g["name"], "pillar": node(pillar), "subsilos": subsilos})

    total = sum(1 + sum(len(ss["chain"]) for ss in c["subsilos"]) for c in clusters)
    assert total == len(tools) == len({n["slug"] for c in clusters for n in [c["pillar"]] + [x for ss in c["subsilos"] for x in ss["chain"]]}), "every tool must appear exactly once"
    return {"generated": datetime.date.today().isoformat(), "volumes_file": Path(xlsx).name, "clusters": clusters}


def report(plan):
    cl = plan["clusters"]
    n_sub = sum(len(c["subsilos"]) for c in cl)
    n_total = sum(1 + sum(len(ss["chain"]) for ss in c["subsilos"]) for c in cl)
    lines = ["# Silo plan", "",
             f"Generated {plan['generated']} from `{plan['volumes_file']}` by `build_silo_plan.py`. Don't edit by hand.", "",
             f"**{len(cl)} pillars · {n_sub} sub-silos · {n_total - len(cl) - n_sub} supporting pages = {n_total} tools.**",
             "Volumes are global average monthly searches for each tool's best keyword (the anchor text).", ""]
    for c in cl:
        size = 1 + sum(len(ss["chain"]) for ss in c["subsilos"])
        lines += [f"## {c['group']} — {size} tools", "",
                  f"**Pillar:** {c['pillar']['name']} (`{c['pillar']['slug']}`) — {c['pillar']['volume']:,}", ""]
        for ss in c["subsilos"]:
            head, rest = ss["chain"][0], ss["chain"][1:]
            lines += [f"### Sub-silo: {head['name']} — {head['volume']:,}  \n*{ss['label']}, {len(rest)} supporting*", ""]
            lines += [f"- {x['name']} — {x['volume']:,}" + ("" if x["status"] in ("built", "verified", "done") else " *(planned)*") for x in rest]
            lines.append("")
    return "\n".join(lines) + "\n"


def main():
    xlsx = sys.argv[1] if len(sys.argv) > 1 else None
    if not xlsx:
        files = sorted(glob.glob(str(VOLUMES_GLOB)))
        files = [f for f in files if not Path(f).name.startswith("~$")]
        if not files:
            sys.exit(f"No volume spreadsheet found at {VOLUMES_GLOB}")
        xlsx = files[-1]
    plan = build(xlsx)
    (HERE / "silo_plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (HERE / "SILO_PLAN.md").write_text(report(plan), encoding="utf-8")
    cl = plan["clusters"]
    print(f"{len(cl)} pillars, {sum(len(c['subsilos']) for c in cl)} sub-silos -> silo_plan.json, SILO_PLAN.md")


if __name__ == "__main__":
    main()
