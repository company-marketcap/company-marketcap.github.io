"""
google_ads_fetch_volumes_companymarketcap.py
--------------------------------------------
Fetches Google Ads keyword historical metrics (average monthly searches) for every calculator in
src/content/tools/*.json — all 320, whatever their status.

Keywords per tool (read from the tool JSON, nothing hardcoded):
  * primary   — the tool name, normalised the way people search it ("401(k) Calculator" -> "401k calculator",
                "Rent vs. Buy Calculator" -> "rent vs buy calculator")
  * variants  — research.name_variants from the competitor research (same normalisation), when present

Output (utilities/google_ads_keyword_research/output/*.xlsx):
  * "Tools"     — one row per tool, sorted by best_volume (descending): primary keyword + volume, the
                  best-volume keyword across primary + variants, subcategory, status, priority
  * "Keywords"  — one row per unique keyword with the full metrics and which tools use it

Usage (from the repo root):
    python3 utilities/google_ads_keyword_research/google_ads_fetch_volumes_companymarketcap.py --dry-run
    python3 utilities/google_ads_keyword_research/google_ads_fetch_volumes_companymarketcap.py \
        --customer-id 8450761335 --geo 2840

Needs `pip install google-ads openpyxl` and a google-ads.yaml next to this script (gitignored).
US market only, so --geo 2840 (United States) is the default.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parents[1]
TOOLS_DIR = ROOT / "src" / "content" / "tools"
YAML_PATH = SCRIPT_DIR / "google-ads.yaml"
OUTPUT_DIR = SCRIPT_DIR / "output"

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

RETRY_LIMIT = 3
RETRY_DELAY = 5
BATCH_SIZE = 700  # the API accepts up to 1000 keywords per request
LANGUAGE_EN = "languageConstants/1000"
DEFAULT_GEO = "2840"
GEO_TARGETS = {"2840": "United States", "2356": "India", "2036": "Australia", "2826": "United Kingdom", "2124": "Canada"}


def normalise(text):
    """Tool name -> the phrase people actually type."""
    t = text.lower().replace("&", " and ")
    t = re.sub(r"\((\w+)\)", r" \1 ", t)          # 401(k) -> 401 k ... fixed below
    t = re.sub(r"\b(\d+)\s+([a-z])\b", r"\1\2", t)  # "401 k" -> "401k", "72 t" -> "72t"
    t = re.sub(r"\bvs\.", "vs", t)
    t = re.sub(r"[:\-–—/,]", " ", t)
    t = re.sub(r"[^a-z0-9' ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def load_tools():
    tools = []
    for path in sorted(TOOLS_DIR.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        primary = normalise(d["name"])
        variants = []
        for v in (d.get("research") or {}).get("name_variants", []):
            n = normalise(v)
            if n and n != primary and n not in variants:
                variants.append(n)
        tools.append({"slug": d["slug"], "name": d["name"], "subcategory": d.get("subcategory", ""),
                      "status": d.get("status", ""), "priority": d.get("priority", ""),
                      "keyword": primary, "variants": variants})
    return tools


def competition_label(value):
    mapping = {0: "UNSPECIFIED", 1: "UNKNOWN", 2: "LOW", 3: "MEDIUM", 4: "HIGH"}
    try:
        return mapping.get(int(value), str(value))
    except Exception:
        return str(value)


def fetch_batch(client, customer_id, keywords, geo_target_id):
    service = client.get_service("KeywordPlanIdeaService")
    request = client.get_type("GenerateKeywordHistoricalMetricsRequest")
    request.customer_id = customer_id
    request.language = LANGUAGE_EN
    if geo_target_id:
        request.geo_target_constants.append(
            client.get_service("GeoTargetConstantService").geo_target_constant_path(geo_target_id))
    request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    request.keywords.extend(keywords)
    response = service.generate_keyword_historical_metrics(request=request)

    out = {}
    for result in response.results:
        m = result.keyword_metrics
        metrics = {
            "avg_monthly_searches": m.avg_monthly_searches,
            "competition": competition_label(m.competition),
            "competition_index": m.competition_index,
            "low_bid": round(m.low_top_of_page_bid_micros / 1_000_000, 2) if m.low_top_of_page_bid_micros else None,
            "high_bid": round(m.high_top_of_page_bid_micros / 1_000_000, 2) if m.high_top_of_page_bid_micros else None,
        }
        out[result.text.lower()] = metrics
        # Google folds close variants into one result; map those back to the keywords we sent.
        for close in result.close_variants:
            out.setdefault(close.lower(), metrics)
    return out


def fetch_all(client, customer_id, keywords, geo_target_id):
    metrics = {}
    for i in range(0, len(keywords), BATCH_SIZE):
        chunk = keywords[i:i + BATCH_SIZE]
        log.info(f"Fetching keywords {i + 1}-{i + len(chunk)} of {len(keywords)}…")
        for attempt in range(1, RETRY_LIMIT + 1):
            try:
                metrics.update(fetch_batch(client, customer_id, chunk, geo_target_id))
                break
            except Exception as e:
                if attempt < RETRY_LIMIT:
                    log.warning(f"  Attempt {attempt} failed: {e} — retrying in {RETRY_DELAY}s…")
                    time.sleep(RETRY_DELAY)
                else:
                    log.error(f"  Batch failed after {RETRY_LIMIT} attempts: {e}")
    return metrics


def build_rows(tools, metrics):
    def vol(kw):
        v = metrics.get(kw, {}).get("avg_monthly_searches")
        return v or 0

    tool_rows = []
    for t in tools:
        candidates = [t["keyword"]] + t["variants"]
        best = max(candidates, key=vol)
        tool_rows.append({
            "name": t["name"], "slug": t["slug"], "subcategory": t["subcategory"], "status": t["status"],
            "priority": t["priority"], "keyword": t["keyword"], "volume": vol(t["keyword"]),
            "competition": metrics.get(t["keyword"], {}).get("competition"),
            "best_keyword": best, "best_volume": vol(best),
        })
    tool_rows.sort(key=lambda r: (-r["best_volume"], r["name"]))

    users = {}
    for t in tools:
        for kw in [t["keyword"]] + t["variants"]:
            users.setdefault(kw, []).append(t["slug"])
    kw_rows = []
    for kw, slugs in users.items():
        m = metrics.get(kw, {})
        kw_rows.append({"keyword": kw, "avg_monthly_searches": m.get("avg_monthly_searches"),
                        "competition": m.get("competition"), "competition_index": m.get("competition_index"),
                        "low_bid": m.get("low_bid"), "high_bid": m.get("high_bid"), "tools": ", ".join(slugs)})
    kw_rows.sort(key=lambda r: (-(r["avg_monthly_searches"] or 0), r["keyword"]))
    return tool_rows, kw_rows


TOOL_FIELDS = ["name", "slug", "subcategory", "status", "priority", "keyword", "volume", "competition",
               "best_keyword", "best_volume"]
KW_FIELDS = ["keyword", "avg_monthly_searches", "competition", "competition_index", "low_bid", "high_bid", "tools"]


def save_xlsx(tool_rows, kw_rows, path):
    import openpyxl
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tools"
    ws.append(TOOL_FIELDS)
    for r in tool_rows:
        ws.append([r.get(f) for f in TOOL_FIELDS])
    ws2 = wb.create_sheet("Keywords")
    ws2.append(KW_FIELDS)
    for r in kw_rows:
        ws2.append([r.get(f) for f in KW_FIELDS])
    wb.save(path)
    log.info(f"Saved {len(tool_rows)} tools / {len(kw_rows)} keywords → {path}")


def print_summary(tool_rows):
    print("\n" + "=" * 92)
    print(f"  {'Tool':<44} {'Keyword':<32} {'Volume':>9}")
    print("-" * 92)
    for r in tool_rows[:40]:
        print(f"  {r['name'][:44]:<44} {r['keyword'][:32]:<32} {r['volume']:>9,}")
    zero = sum(1 for r in tool_rows if not r["best_volume"])
    print("=" * 92)
    print(f"  top 40 of {len(tool_rows)} tools shown; {zero} have no volume data (<10 searches/month)\n")


def parse_args():
    p = argparse.ArgumentParser(description="Fetch Google Ads search volumes for every Company Marketcap tool")
    p.add_argument("--customer-id", default=None, help="Google Ads customer ID (digits) or GOOGLE_ADS_CUSTOMER_ID env var")
    p.add_argument("--geo", default=DEFAULT_GEO, help="Geo target ID (default 2840 = United States; 'global' for none)")
    p.add_argument("--dry-run", action="store_true", help="Print the keyword list only, skip the API call")
    p.add_argument("--yaml", default=str(YAML_PATH), help="Path to google-ads.yaml credentials file")
    return p.parse_args()


def main():
    args = parse_args()
    tools = load_tools()
    keywords = list(dict.fromkeys(kw for t in tools for kw in [t["keyword"]] + t["variants"]))
    log.info(f"{len(tools)} tools → {len(keywords)} unique keywords")

    if args.dry_run:
        for t in tools:
            print(f"  [{t['name'][:48]:<48}]  {t['keyword']}" + (f"   (+{len(t['variants'])} variants)" if t["variants"] else ""))
        return

    customer_id = (args.customer_id or os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")).replace("-", "").strip()
    if not customer_id:
        sys.exit("No customer ID. Pass --customer-id XXXXXXXXXX or set GOOGLE_ADS_CUSTOMER_ID.")
    try:
        from google.ads.googleads.client import GoogleAdsClient
        import openpyxl  # noqa: F401
    except ImportError:
        sys.exit("Missing packages. Run: pip install google-ads openpyxl")
    if not Path(args.yaml).exists():
        sys.exit(f"Credentials file not found: {args.yaml}")

    geo = None if args.geo == "global" else args.geo
    log.info(f"Connecting to Google Ads API (customer {customer_id}, geo {GEO_TARGETS.get(geo, geo) if geo else 'global'})…")
    client = GoogleAdsClient.load_from_storage(args.yaml)

    start = time.time()
    metrics = fetch_all(client, customer_id, keywords, geo)
    log.info(f"Completed in {time.time() - start:.1f}s")

    tool_rows, kw_rows = build_rows(tools, metrics)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = GEO_TARGETS.get(geo, geo).lower().replace(" ", "_") if geo else "global"
    save_xlsx(tool_rows, kw_rows, OUTPUT_DIR / f"companymarketcap_search_volumes_{label}_{stamp}.xlsx")
    print_summary(tool_rows)


if __name__ == "__main__":
    main()
