# src/ — JSON-driven site build

Every page on the site is generated from JSON. **Edit the JSON, never `public/`** — `generate.py`
deletes and rewrites `public/` on every build, and GitHub Actions rebuilds it on every push to `main`.

```
src/
  config/site.json          site name, base URL, home copy, AdSense client, footer links
  config/categories.json    the category page + nav groups -> subcategories (its sections)
  content/tools/<slug>.json one file per calculator = that calculator's entire page
  content/pages/<slug>.json home copy + FAQ (home.json); about, contact, privacy-policy, terms
  templates/                home, category, tool, page + shared _partials ({{TOKEN}} templates)
  static/                   copied verbatim to the site root (assets/, icons, ads.txt, ...)
  build_data.py             validates all JSON, writes src/data/ (gitignored)
  generate.py               runs build_data, renders public/ (gitignored)
```

## Build

```bash
python3 src/generate.py                    # validate + render public/ (only live tools)
python3 src/generate.py --include-planned  # also render all planned tools, noindex (template work)
cd public && python3 -m http.server 8811   # preview: http://localhost:8811/
```

Python 3 standard library only — no pip installs needed for the site build.

## Tool file contract — `content/tools/<slug>.json`

| Field | Notes |
|---|---|
| `slug` | Must equal the file name. Becomes the URL: `/<slug>.html`. Don't change once live. |
| `status` | `planned` → `in_progress` → `built` → `verified` → `done`. Only `built`/`verified`/`done` get a public page, nav entry and sitemap entry. |
| `name` | Full display name (category page, breadcrumb, related links, search). |
| `nav_name` | Short label for the nav menu. |
| `subcategory` | A subcategory `slug` from `config/categories.json` (its section on the category page). |
| `priority` | 1–3; seeded from how many competitor sites have the tool. Use it to choose build order. |
| `order` | Sort order within its subcategory (lower first). |
| `meta_title`, `meta_description` | Required when live. Build warns above 60 / 160 characters. |
| `h1`, `subtitle` | Required when live. |
| `card.layout` | `raw` — `card.fields_html` is inserted verbatim as the calculator UI. |
| `card.fields_html` | The calculator's form and results markup. Required when live. |
| `card.extra_scripts` | CDN script URLs this tool alone needs (e.g. a chart library). Loaded only on this page. |
| `script` | The tool's complete JavaScript: self-contained IIFE, `'use strict'`, its own `DOMContentLoaded` wiring. No shared runtime file — duplicate small helpers rather than sharing them. Required when live. |
| `content_html` | Original explanatory content. Plain semantic HTML (h2/h3/p/ul/ol/table/code, no classes), rendered inside `.article-content`. Optional: a tool can go live with just its calculator and get its article later (the tracker's Content column shows which). |
| `faq` | `[{"question", "answer"}]` (plain text). Renders the visible FAQ **and** the FAQPage JSON-LD from the same array, so they can't drift apart. Never put an FAQ inside `content_html`. Optional; empty means no FAQ section or FAQ JSON-LD. |
| `related` | Optional slugs to show first under "Related calculators"; the rest fill from the same subcategory. |
| `legacy` | Old-site calculators only: `source` (file in `/archive` to port) and the old `url`. |
| `research` | Competitor URLs and name variants from the inventory, for reference while building. Not rendered. |

`compound-interest-calculator.json` is the worked reference: copy its structure when building a new tool.

### Rules for tool content
- Write everything in our own words. The competitor mirrors in `utilities/competitor_research/`
  are for checking what inputs and outputs a tool needs — never copy their text, code or layout.
- Check every formula against known reference values before marking a tool `built`, and note
  the check in a comment at the top of `script` (see the compound interest script).
- Browser-test each tool (every input, invalid input, console clean) before marking it `verified`.

## Pages and URLs

Every page is a flat `.html` file and every internal link ends in `.html` (no category folders):

| Page | File | Template |
|---|---|---|
| Home — scientific calculator + finance topic directory | `/` (`index.html`) | `home.html` |
| The one category page — a section per subcategory | `/financial-calculators.html` | `category.html` |
| A calculator | `/<slug>.html` | `tool.html` |
| About, contact, privacy, terms, sitemap, 404 | `/<slug>.html` | `page.html` |

Subcategories are **sections** of the category page, not pages: link to them as
`/financial-calculators.html#<subcategory-slug>`; nav groups are `#<group-id>`. Planned tools are
listed there unlinked with a "Coming soon" badge; built tools are linked. Counts on tiles and in the
sidebar are live calculators only (copy never claims a total).

## Template contract — `templates/`

The design comes from the Company Marketcap template (Tailwind v4 compiled in the browser from
`static/assets/css/site-theme-and-components.css`; theme, sidebar and search from
`static/assets/js/site-theme-navigation-and-search.js`).

- `_head.html`, `_header.html`, `_sidebar.html`, `_footer.html` are shared partials, pulled in with
  `{{INCLUDE:_name.html}}`. Edit the header, sidebar or footer once there.
- Every element id is prefixed with the page id (`{{PAGE_ID}}-…`), and `<body data-page-slug>` holds
  it — the template's scripts find elements that way. The page id is the tool slug, the category slug,
  the info page slug, or `home`.
- The build fails on an unknown token. Tokens every template gets: `PAGE_ID`, `PAGE_TYPE`, `SITE_NAME`,
  `META_TITLE`, `META_DESCRIPTION`, `CANONICAL_URL`, `ROBOTS`, `HEAD_EXTRA`, `JSON_LD`,
  `SIDEBAR_CATEGORIES`, `FOOTER_CATEGORIES`, `FOOTER_DESCRIPTION`, `YEAR`, `AD_TOP`, `AD_BOTTOM`,
  `AD_RIGHT_RAIL_TOP` (300 × 250, scrolls with the page), `AD_RIGHT_RAIL` (300 × 600, sticky), `H1`, `SUBTITLE`, `SIDEBAR_DESKTOP_CLASSES`, `HEADER_NAV_CLASSES` (home drops the
  desktop sidebar and uses the full width; the sidebar is still its mobile drawer). Page-specific ones are listed in `TEMPLATE_TOKENS` in `generate.py`.
- Ad slots are generated with the template's `ad-slot` markup; paste AdSense unit code per slot type
  (`ad-top-leaderboard`, `ad-bottom-leaderboard`, `ad-in-feed`, `ad-hero-rectangle`,
  `ad-right-rail-skyscraper`) in `render_ad()` when ads go live.
- The search index (`/assets/data/calculator-search-index.json`) is generated: the category page,
  each subcategory section and every live tool.

### Building a tool's UI (`card.fields_html`)
Insert one or more `<section class="panel p-4 sm:p-6">` blocks using the stylesheet's components:
`panel-heading`, `form-label`, `input-group` + `input-affix`, `form-select`, `form-row form-row-2`,
`form-hint`, `form-error`, `stat-grid` + `stat-card` (`stat-card-highlight`) + `stat-label`/`stat-value`,
`table-scroll` + `data-table`, `result-row`/`result-term`/`result-value`, `callout`, `badge`.
`compound-interest-calculator.json` shows the pattern.

### Tool content (`content_html`)
Plain semantic HTML with no classes — it is wrapped in `<article class="article-content">`, which
styles h2/h3/p/lists/tables/code. FAQ stays in the separate `faq` field (optional `faq_heading`).

## Adding things

- **A calculator:** create `content/tools/<slug>.json` (or fill in its existing stub), set `status`
  to `built`, run the build. The category page link, sidebar count, search index, sitemap, related
  links and JSON-LD all update automatically.
- **A subcategory:** add it to `config/categories.json`; point tools at its slug.
- **New calculators from the competitor inventory:** `utilities/scaffold/seed_tool_stubs.py`
  creates stubs only for tools that don't have a file yet — it never overwrites.
