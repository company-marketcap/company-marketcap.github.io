# CLAUDE.md — competitor research

Research workspace for the MarketCapInsights overhaul (branch `overhaul`). The old site lives in
`/archive`; this folder holds offline copies of competitor finance-calculator sites and the analysis
built from them, which drives the plan for the new site below.

## Ground rules

- **Mirrors are reference only.** Use them to learn what calculators exist, how inputs/outputs are
  structured, and how sites are organised. Never copy their page text, explanations, code, images or
  design into the new site — write our own content and build our own calculators.
- **Mirrors never go into git.** `mirror/`, `crawl.log`, `crawl_state.json` and `.venv/` are ignored
  (`.gitignore` here). This repo is a public GitHub Pages site; committing a mirror would republish a
  competitor's site under our domain.
- Crawl politely: keep the default 1 s delay, one site at a time per process, robots.txt honoured.

## Layout

```
competitor_research/
  crawl.py                      offline-mirror crawler; sites configured in SITES
  build_calculator_inventory.py builds calculator_inventory.xlsx from the mirrors
  calculator_inventory.xlsx     consolidated calculator list (output)
  requirements.txt              requests, beautifulsoup4, openpyxl
  .venv/                        shared virtualenv (not committed)
  calculator.net/   dinkytown.net/   fncalculator.com/
      mirror/                   offline copy — open mirror/index.html
      crawl.log, crawl_state.json
```

## Commands (run from this folder)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # first time only
.venv/bin/python crawl.py <site>                  # mirror a site (resumable; re-run to continue)
.venv/bin/python crawl.py <site> --max-pages 5    # quick test
.venv/bin/python build_calculator_inventory.py    # rebuild the spreadsheet
```

Adding a competitor: add an entry to `SITES` in `crawl.py` (`start`, `hosts`, `cdn_hosts`, and
`page_query` if its pages are query-string URLs like fncalculator's `?type=`), crawl it, then add an
`extract_<site>()` function to `build_calculator_inventory.py` that reads its index/category pages.

## How the inventory is built

- Each site's own index/category pages are the source of truth for which pages are calculators and
  which category the site files them under (kept in the "All source rows" sheet).
- dinkytown's French (`FR.html`) and Spanish (`SP.html`) pages are translations and are excluded;
  its Canadian versions are merged with the US equivalent and flagged in the Regions column.
- The same calculator across sites is merged by a normalised name key (`norm_key`) plus the `ALIASES`
  map. Yearly editions ("Tax Year 2023", "Prior Tax Year") merge into one.
- Subcategory = first matching rule in `OVERRIDES`, then `FINANCE_SUBCATEGORIES` (ordered, specific
  before broad). Anything unmatched lands in "Uncategorized (review)" — fix by adding a rule or alias,
  not by editing the spreadsheet by hand.
- calculator.net's fitness/health, math and "other" calculators are listed on a separate reference
  sheet and are out of scope for the finance subcategories.

## Plan for the new site

The new MarketCapInsights is a broad **finance calculators** site organised into ~20–25 subcategories,
replacing the current handful of investing calculators.

### Step 1 — Consolidated calculator inventory ✅
`calculator_inventory.xlsx`: every unique finance calculator across calculator.net, dinkytown.net and
fncalculator.com, merged across sites and assigned to one of 23 subcategories, with per-site coverage
and links. Review the "Calculators" sheet and adjust rules/aliases where a grouping looks wrong.

### Step 2 — Prioritise
- Add columns for priority: coverage (on 2–3 sites = proven demand), estimated search volume and
  keyword difficulty, build effort (S/M/L), and US-only vs global relevance.
- Decide scope for Canada-specific tools (RRSP, TFSA, RESP, CPP) — separate section or skip.
- Cut near-duplicates and niche variants (e.g. many RMD/beneficiary permutations) into one flexible
  calculator with options where it serves users better.
- Output: a ranked launch list (MVP ≈ 40–60 calculators) plus a backlog.

### Step 3 — Information architecture
- One hub page per subcategory (title, short intro, grid of its calculators), linked from a top-level
  "Finance calculators" page and the main nav.
- Clean, stable URLs: `/<subcategory-slug>/<calculator-slug>` or flat `/<calculator-slug>`; decide once
  and record it here. Carry over and redirect the existing archive URLs that have traffic.
- Related-calculator links within and across subcategories (replaces the old silo-rotation script).

### Step 4 — Calculator template & design system
- One reusable page template: inputs panel, results summary, chart/table (amortisation, growth),
  explanation, formula, worked example, FAQ, related calculators.
- Shared JS modules for money/percent formatting, input validation, amortisation, compounding, TVM,
  charting — each calculator only defines its inputs and formula.
- Mobile-first, fast (no heavy frameworks), accessible, shareable results via URL parameters.

### Step 5 — Build in waves
- Wave 1: the MVP list, highest-priority subcategories first (mortgage, loans, retirement, investing,
  savings, credit card/debt, tax, salary).
- Each calculator ships with original explanatory content, unit-tested formulas checked against known
  results, schema markup (FAQPage / SoftwareApplication), and a sitemap entry.
- Later waves work through the backlog.

### Step 6 — Launch & migrate
- Redirect old URLs, submit the new sitemap, keep `ads.txt` and the Search Console verification file at
  the site root, re-check AdSense placement on the new templates.
- Fix or retire `.github/workflows/silo-rotation.yml`, which points at the archived script.
