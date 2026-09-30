#!/usr/bin/env python3
"""
Monthly silo link rotation for company-marketcap.github.io.

Single silo structure:
  - Pillar: index.html links to exactly one page — whichever is first in the monthly shuffled order.
  - Each silo page links back to the pillar (slot_a, rotating anchor variant)
    and to its neighbours in the monthly chain (slot_b = prev, slot_c = next).

HTML files are patched in-place using comment markers:
  <!-- SILO_START:slot_a -->sentence with link<!-- SILO_END:slot_a -->

Run via GitHub Actions on the 1st of each month, or manually:
  python3 utilities/silo_linking/generate_silo_rotation.py
  python3 utilities/silo_linking/generate_silo_rotation.py --dry-run
"""

import datetime
import hashlib
import html as html_lib
import os
import random
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Silo structure
# ---------------------------------------------------------------------------

SILO_PAGES = [
    {"file": "position-sizing.html",             "anchor": "position sizing calculator",              "url": "position-sizing.html"},
    {"file": "tax-harvesting.html",               "anchor": "tax-loss harvesting calculator",          "url": "tax-harvesting.html"},
    {"file": "sector-balance.html",               "anchor": "sector balance optimizer",                "url": "sector-balance.html"},
    {"file": "stock-split-impact.html",           "anchor": "stock split calculator",                  "url": "stock-split-impact.html"},
    {"file": "dividend-reinvestment.html",         "anchor": "dividend reinvestment calculator",        "url": "dividend-reinvestment.html"},
    {"file": "stock-valuation-confidence.html",   "anchor": "stock valuation calculator",              "url": "stock-valuation-confidence.html"},
    {"file": "inflation-adjusted-calculator.html","anchor": "inflation-adjusted return calculator",     "url": "inflation-adjusted-calculator.html"},
]

# Rotating anchor variants used by silo pages when linking UP to the pillar.
PILLAR_UP_ANCHORS = [
    "market cap growth calculator",
    "free market cap calculator",
    "market cap calculator",
    "stock market cap calculator",
    "company market cap calculator",
    "market cap investment calculator",
]

# ---------------------------------------------------------------------------
# Injection targets: physical HTML location for each slot (first run only).
# (heading_tag, heading_text_fragment) — None = first <p> after <h1>.
# ---------------------------------------------------------------------------

INJECTION_TARGETS = {
    "index.html": {
        "slot_a": ("h1", None),
    },
    "position-sizing.html": {
        "slot_a": ("h1", None),
        "slot_b": ("h3", "Common Position Sizing Methods"),
        "slot_c": ("h3", "Fixed Risk Percentage Method"),
    },
    "tax-harvesting.html": {
        "slot_a": ("h1", None),
        "slot_b": ("h3", "What Is Tax-Loss Harvesting?"),
        "slot_c": ("h3", "When To Consider Tax-Loss Harvesting"),
    },
    "sector-balance.html": {
        "slot_a": ("h1", None),
        "slot_b": ("h3", "Common Allocation Approaches"),
        "slot_c": ("h3", "Sector Rotation Through Economic Cycles"),
    },
    "stock-split-impact.html": {
        "slot_a": ("h1", None),
        "slot_b": ("h3", "What Is a Stock Split?"),
        "slot_c": ("h3", "Why Do Companies Split Their Stock?"),
    },
    "dividend-reinvestment.html": {
        "slot_a": ("h1", None),
        "slot_b": ("h3", "Dividend Reinvestment Scenarios"),
        "slot_c": ("h3", "Optimal DRIP Characteristics"),
    },
    "stock-valuation-confidence.html": {
        "slot_a": ("h1", None),
        "slot_b": ("h3", "Why Point Estimates Are Misleading"),
        "slot_c": ("h3", "Benefits of Confidence Interval Approach"),
    },
    "inflation-adjusted-calculator.html": {
        "slot_a": ("h1", None),
        "slot_b": ("h3", "The Hidden Tax on Your Investments"),
        "slot_c": ("h3", "Strategies to Combat Inflation"),
    },
}

# ---------------------------------------------------------------------------
# Sentence templates — 6 per anchor keyword, {link} replaced at render time.
# ---------------------------------------------------------------------------

SENTENCES = {
    "market cap growth calculator": [
        "Use this {link} to project how a company's valuation could change over your investment horizon.",
        "The {link} shows your projected investment value alongside market capitalization growth, year by year.",
        "A {link} lets you model different growth rates and see how SIP contributions compound over time.",
        "For a quick sanity-check on your long-term investment thesis, the {link} runs the numbers in seconds.",
        "The free {link} factors in revenue multiples and P/E ratios for more accurate projections.",
        "Before committing capital, a {link} shows the full growth trajectory based on your inputs.",
    ],
    "free market cap calculator": [
        "The {link} projects market capitalization growth and investment returns without any signup or fees.",
        "Use the {link} to model different annual growth rates and see your portfolio's potential value.",
        "A {link} gives you year-by-year projections of both company growth and your investment returns.",
        "The {link} runs entirely in your browser, so your financial data stays on your device.",
        "Try the {link} to compare how different growth assumptions affect your projected returns.",
        "For investors researching growth stocks, the {link} provides structured projection analysis.",
    ],
    "market cap calculator": [
        "The {link} on this site takes initial market cap, growth rate, and investment amount as inputs.",
        "Use the {link} to explore how changes in a company's valuation might affect your portfolio.",
        "A {link} helps quantify growth assumptions before you commit to a long-term position.",
        "The free {link} includes SIP modeling so you can see how regular contributions compound alongside market cap growth.",
        "The {link} is suitable for comparing different companies and their potential valuation trajectories.",
        "Before building a position, a {link} gives you a structured framework to evaluate upside scenarios.",
    ],
    "stock market cap calculator": [
        "The {link} lets you project how a company's total value might grow based on historical and expected rates.",
        "Use this {link} to evaluate whether a company's valuation supports your return expectations.",
        "A {link} incorporates both market cap growth and your investment contributions for a complete projection.",
        "The {link} accounts for dividend reinvestment options to give you a more complete return picture.",
        "For growth stock analysis, the {link} provides a structured way to stress-test your assumptions.",
        "The free {link} runs in your browser — no downloads, no account, no limits on calculations.",
    ],
    "company market cap calculator": [
        "The {link} takes just a few inputs and produces a year-by-year projection of both company and portfolio growth.",
        "Use a {link} to quantify your investment thesis before adding a new position.",
        "A {link} helps you model the compound effect of market cap growth alongside ongoing contributions.",
        "The free {link} includes revenue multiple and P/E ratio inputs for sector-specific projections.",
        "Try the {link} to compare optimistic, base, and conservative growth scenarios side by side.",
        "The {link} calculates projected ROI at each year so you can set realistic return expectations.",
    ],
    "market cap investment calculator": [
        "The {link} models how your investment grows in parallel with a company's market capitalization.",
        "Use this {link} to factor dividend reinvestment and monthly contributions into your growth projections.",
        "A {link} shows the compounded effect of market cap growth on your initial and ongoing investments.",
        "The {link} runs each projection locally in your browser, keeping your financial data private.",
        "For portfolio planning, the {link} provides structured outputs including total contributions and ROI.",
        "Before sizing a new position, a {link} lets you see the growth trajectory based on your exact inputs.",
    ],
    "position sizing calculator": [
        "The {link} tells you the exact share count, position value, and risk amount before you place any trade.",
        "Use the {link} to apply the fixed-risk-percentage method and keep any single loss within your tolerance.",
        "A {link} factors in commission and fees to give you a net position size adjusted for transaction costs.",
        "The free {link} runs in your browser and requires just four inputs: account value, risk %, entry, and stop.",
        "For disciplined trading, the {link} removes guesswork from position sizing and enforces consistent risk.",
        "Try the {link} to see how different stop-loss placements change your optimal share count.",
    ],
    "tax-loss harvesting calculator": [
        "The {link} shows your federal, state, and total tax savings before you decide whether to sell.",
        "Use the {link} to see how realized losses offset short-term gains, long-term gains, and ordinary income.",
        "A {link} runs the full wash-sale and benefit analysis so you know the net effect of harvesting.",
        "The free {link} takes purchase price, current value, purchase date, and income as inputs and outputs a full savings breakdown.",
        "For year-end portfolio reviews, the {link} quantifies the after-tax benefit of locking in unrealized losses.",
        "Before harvesting a position, the {link} confirms whether the tax saving justifies the transaction.",
    ],
    "sector balance optimizer": [
        "The {link} analyzes your portfolio's current sector weights and shows exactly which positions to adjust.",
        "Use the {link} to compare your actual sector allocation against your target weights.",
        "A {link} generates prioritized rebalancing recommendations showing what to buy and what to reduce.",
        "The free {link} works with any number of holdings and any set of target sector percentages.",
        "For quarterly portfolio reviews, the {link} identifies allocation drift before it becomes significant.",
        "Try the {link} to see how adding or removing a single position shifts your overall sector exposure.",
    ],
    "stock split calculator": [
        "The {link} shows your post-split share count, adjusted price, and total position value instantly.",
        "Use the {link} to verify how a forward or reverse split changes your options contract adjustments.",
        "A {link} puts pre-split and post-split figures side by side so you can confirm the math quickly.",
        "The free {link} handles any split ratio and also calculates strike price and contract adjustments for options holders.",
        "Before a split takes effect, the {link} confirms your exact post-split position and value.",
        "For portfolio modeling, the {link} lets you run any hypothetical forward or reverse split scenario.",
    ],
    "dividend reinvestment calculator": [
        "The {link} shows how many years your DRIP strategy needs to recover from a price drop.",
        "Use the {link} to see the year-by-year recovery timeline including shares owned and total portfolio value.",
        "A {link} factors in dividend yield, growth rate, and payment frequency to project your exact breakeven point.",
        "The free {link} runs the full DRIP analysis in your browser — no signup and no limits.",
        "For income investors, the {link} quantifies how reinvested dividends accelerate recovery after a drawdown.",
        "Try the {link} to compare different dividend growth rates and see how they shift your breakeven timeline.",
    ],
    "stock valuation calculator": [
        "The {link} puts a statistical range around your price target instead of leaving you with a single estimate.",
        "Use the {link} to see bearish, base, and bullish price scenarios along with the probability of each.",
        "A {link} incorporates historical volatility and your estimation error to produce a confidence interval for the stock price.",
        "The free {link} also shows the probability of loss and the probability of a 25%-plus gain.",
        "For analysts and investors, the {link} replaces point estimates with a full statistical distribution.",
        "Try the {link} to stress-test any valuation model by adjusting the confidence level slider.",
    ],
    "inflation-adjusted return calculator": [
        "The {link} separates your nominal return from what inflation actually took away.",
        "Use the {link} to compare your real purchasing power retention against nominal portfolio growth.",
        "A {link} shows the year-by-year breakdown of nominal versus inflation-adjusted returns.",
        "The free {link} supports annual contributions and adjustable compounding frequency for a complete picture.",
        "For long-term planning, the {link} quantifies how different inflation rates erode the same nominal return.",
        "Try the {link} to see whether your investment strategy is keeping pace with inflation over your target horizon.",
    ],
}

# ---------------------------------------------------------------------------
# Rotation helpers
# ---------------------------------------------------------------------------

def monthly_shuffle(items: list, seed_key: str, today: datetime.date) -> list:
    seed = int(hashlib.md5(f"{today.year}-{today.month}-{seed_key}".encode()).hexdigest(), 16)
    items = list(items)
    random.Random(seed).shuffle(items)
    return items


def pick_pillar_up_anchor(page_file: str, today: datetime.date) -> str:
    key = f"{today.year}-{today.month}-{page_file}-slot_a"
    idx = int(hashlib.md5(key.encode()).hexdigest(), 16) % len(PILLAR_UP_ANCHORS)
    return PILLAR_UP_ANCHORS[idx]


def pick_sentence(source_file: str, anchor: str, today: datetime.date) -> str:
    key = f"{today.year}-{today.month}-{source_file}-{anchor}"
    idx = int(hashlib.md5(key.encode()).hexdigest(), 16) % 6
    return SENTENCES[anchor][idx]


def generate_silo_links(today: datetime.date) -> dict:
    """Return SILO_LINKS dict for the given month via deterministic shuffle."""

    shuffled = monthly_shuffle(SILO_PAGES, "silo", today)

    links: dict = {}

    # Pillar: 1 outgoing link to the first page in the monthly shuffle
    links["index.html"] = [
        {"slot": "slot_a", "anchor": shuffled[0]["anchor"], "url": shuffled[0]["url"]},
    ]

    # Silo pages: slot_a = up to pillar, slot_b = prev, slot_c = next
    n = len(shuffled)
    for i, page in enumerate(shuffled):
        is_first = (i == 0)
        is_last  = (i == n - 1)

        pillar_anchor = pick_pillar_up_anchor(page["file"], today)
        slot_a_def = {"slot": "slot_a", "anchor": pillar_anchor, "url": "index.html"}

        if is_first:
            slot_b_def = {"slot": "slot_b", "anchor": None, "url": None}
        else:
            prev_page  = shuffled[i - 1]
            slot_b_def = {"slot": "slot_b", "anchor": prev_page["anchor"], "url": prev_page["url"]}

        if is_last:
            slot_c_def = {"slot": "slot_c", "anchor": None, "url": None}
        else:
            next_page  = shuffled[i + 1]
            slot_c_def = {"slot": "slot_c", "anchor": next_page["anchor"], "url": next_page["url"]}

        links[page["file"]] = [slot_a_def, slot_b_def, slot_c_def]

    return links

# ---------------------------------------------------------------------------
# Core HTML helpers
# ---------------------------------------------------------------------------

def _strip_tags(s: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def make_sentence_html(template: str, url: str, anchor: str) -> str:
    link = f'<a href="{url}">{anchor}</a>'
    return template.replace("{link}", link)


def update_markers(html: str, slot: str, sentence_html: str) -> str:
    start   = f"<!-- SILO_START:{slot} -->"
    end     = f"<!-- SILO_END:{slot} -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    return pattern.sub(start + sentence_html + end, html)


def find_paragraph_end(html: str, heading_tag: str, heading_text: str | None) -> int | None:
    """Return position just before </p> to inject into, based on the given heading."""
    if heading_text is None:
        m = re.search(r"</h1>", html)
        if not m:
            return None
        search_from = m.end()
    else:
        for m in re.finditer(
            r"<" + heading_tag + r"[^>]*>(.*?)</" + heading_tag + r">",
            html, re.S
        ):
            if heading_text in _strip_tags(m.group(1)):
                search_from = m.end()
                break
        else:
            return None

    p_end = re.search(r"</p>", html[search_from:])
    if not p_end:
        return None
    return search_from + p_end.start()


def insert_markers(html: str, slot: str, sentence_html: str,
                   heading_tag: str, heading_text: str | None) -> str:
    pos = find_paragraph_end(html, heading_tag, heading_text)
    if pos is None:
        return html
    start     = f"<!-- SILO_START:{slot} -->"
    end       = f"<!-- SILO_END:{slot} -->"
    injection = f" {start}{sentence_html}{end}"
    return html[:pos] + injection + html[pos:]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(today: datetime.date, dry_run: bool = False) -> None:
    silo_links = generate_silo_links(today)
    errors: list[str] = []

    for page_file, link_defs in silo_links.items():
        filepath = os.path.join(REPO_ROOT, page_file)
        if not os.path.exists(filepath):
            errors.append(f"MISSING FILE: {page_file}")
            continue

        html     = open(filepath, encoding="utf-8").read()
        original = html

        for link_def in link_defs:
            slot   = link_def["slot"]
            anchor = link_def["anchor"]
            url    = link_def["url"]

            marker_start = f"<!-- SILO_START:{slot} -->"

            if anchor is None:
                if marker_start in html:
                    html = update_markers(html, slot, "")
                else:
                    tag, text = INJECTION_TARGETS[page_file][slot]
                    html = insert_markers(html, slot, "", tag, text)
            else:
                sentence_html = make_sentence_html(
                    pick_sentence(page_file, anchor, today), url, anchor
                )
                if marker_start in html:
                    html = update_markers(html, slot, sentence_html)
                else:
                    tag, text = INJECTION_TARGETS[page_file][slot]
                    new_html  = insert_markers(html, slot, sentence_html, tag, text)
                    if new_html == html:
                        errors.append(f"INJECT FAILED: {page_file}/{slot} — heading not found")
                    html = new_html

        if html != original:
            if dry_run:
                print(f"[dry-run] would update: {page_file}")
            else:
                open(filepath, "w", encoding="utf-8").write(html)
                print(f"Updated: {page_file}")
        else:
            print(f"No change: {page_file}")

    if errors:
        print("\nErrors:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    today = datetime.date.today()
    for arg in sys.argv[1:]:
        if arg.startswith("--date=") or (arg == "--date" and sys.argv.index(arg) + 1 < len(sys.argv)):
            raw = arg.split("=", 1)[1] if "=" in arg else sys.argv[sys.argv.index(arg) + 1]
            try:
                year, month = map(int, raw.split("-"))
                today = datetime.date(year, month, 1)
            except ValueError:
                print(f"Invalid --date value {raw!r}. Expected YYYY-MM.", file=sys.stderr)
                sys.exit(1)

    print(f"Silo rotation — {today.year}-{today.month:02d}"
          + (" [DRY RUN]" if dry_run else ""))
    run(today, dry_run=dry_run)
    print("Done.")
