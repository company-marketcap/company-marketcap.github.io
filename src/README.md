# src/ — JSON-driven site build

Every page on the site is generated from JSON. **Edit the JSON, never `public/`** — `generate.py`
deletes and rewrites `public/` on every build, and GitHub Actions rebuilds it on every push to `main`.

```
src/
  config/site.json          site name, base URL, home copy, AdSense client, footer links
  config/categories.json    nav groups -> subcategories (hub pages), in nav order
  content/tools/<slug>.json one file per calculator = that calculator's entire page
  content/pages/<slug>.json info pages: about, contact, privacy-policy, terms
  templates/                tool.html, hub.html, home.html, page.html ({{TOKEN}} templates)
  static/                   copied verbatim to the site root (styles.css, icons, ads.txt, ...)
  build_data.py             validates all JSON, writes src/data/ (gitignored)
  generate.py               runs build_data, renders public/ (gitignored)
```

## Build

```bash
python3 src/generate.py                    # validate + render public/ (only live tools)
python3 src/generate.py --include-planned  # also render all planned tools, noindex (template work)
cd public && python3 -m http.server 8811   # preview: http://localhost:8811/compound-interest-calculator.html
```

Python 3 standard library only — no pip installs needed for the site build. Locally, use the
`.html` URL; GitHub Pages serves `/compound-interest-calculator` from the `.html` file.

## Tool file contract — `content/tools/<slug>.json`

| Field | Notes |
|---|---|
| `slug` | Must equal the file name. Becomes the URL: `/<slug>`. Don't change once live. |
| `status` | `planned` → `in_progress` → `built` → `verified` → `done`. Only `built`/`verified`/`done` get a public page, nav entry and sitemap entry. |
| `name` | Full display name (hub cards, breadcrumb, related links). |
| `nav_name` | Short label for the nav menu. |
| `subcategory` | A subcategory `slug` from `config/categories.json` (the hub it appears on). |
| `priority` | 1–3; seeded from how many competitor sites have the tool. Use it to choose build order. |
| `order` | Sort order within its hub and nav (lower first). |
| `meta_title`, `meta_description` | Required when live. Build warns above 60 / 160 characters. |
| `h1`, `subtitle` | Required when live. |
| `card.layout` | `raw` — `card.fields_html` is inserted verbatim as the calculator UI. |
| `card.fields_html` | The calculator's form and results markup. Required when live. |
| `card.extra_scripts` | CDN script URLs this tool alone needs (e.g. a chart library). Loaded only on this page. |
| `script` | The tool's complete JavaScript: self-contained IIFE, `'use strict'`, its own `DOMContentLoaded` wiring. No shared runtime file — duplicate small helpers rather than sharing them. Required when live. |
| `content_html` | Original explanatory content. Plain semantic HTML (h2/h3/p/ul/ol/table/code, no classes). Split at each `<h2>` into `.content-card` sections; an intro before the first `<h2>` is kept at the top of the first section. Required when live. |
| `faq` | `[{"question", "answer"}]` (plain text). Renders the visible FAQ **and** the FAQPage JSON-LD from the same array, so they can't drift apart. Never put an FAQ inside `content_html`. |
| `related` | Optional slugs to show first under "Related calculators"; the rest fill from the same hub. |
| `legacy` | Old-site calculators only: `source` (file in `/archive` to port) and the old `url`. |
| `research` | Competitor URLs and name variants from the inventory, for reference while building. Not rendered. |

`compound-interest-calculator.json` is the worked reference: copy its structure when building a new tool.

### Rules for tool content
- Write everything in our own words. The competitor mirrors in `utilities/competitor_research/`
  are for checking what inputs and outputs a tool needs — never copy their text, code or layout.
- Check every formula against known reference values before marking a tool `built`, and note
  the check in a comment at the top of `script` (see the compound interest script).
- Browser-test each tool (every input, invalid input, console clean) before marking it `verified`.

## Template contract — `templates/*.html`

Templates are plain HTML with `{{TOKENS}}`. The build fails on an unknown token, so typos surface
immediately. Available tokens:

- **All templates:** `SITE_NAME`, `META_TITLE`, `META_DESCRIPTION`, `CANONICAL_URL`, `ROBOTS`, `JSON_LD`,
  `ADSENSE_CLIENT`, `NAV`, `BREADCRUMB`, `H1`, `SUBTITLE`, `FOOTER`, `YEAR`
- **tool.html:** `TOOL_CARD`, `CONTENT_SECTIONS`, `FAQ`, `RELATED_TOOLS`, `DISCLAIMER`,
  `TOOL_EXTRA_SCRIPTS`, `TOOL_SCRIPT`
- **hub.html:** `TOOL_GRID`
- **home.html:** `CATEGORY_GRID`
- **page.html:** `CONTENT_HTML` (info pages, sitemap page, 404)

### Markup contract (classes generate.py emits, for styling)
`site-nav`, `nav-groups`, `nav-group`, `nav-group-toggle` (`aria-expanded`), `nav-subs`, `nav-sub`,
`nav-sub-link`, `nav-tools` · `breadcrumb` · `tool-card` (`data-tool="<slug>"`) · `content-card` ·
`faq`, `faq-item` (`<details>`), `faq-answer` · `related-tools`, `tool-grid`, `tool-link`,
`tool-link-name`, `tool-link-desc` · `category-group`, `category-grid`, `category-card`,
`category-name`, `category-desc`, `category-count` · `footer-links`, `footer-tagline`, `footer-copy` ·
`tool-preview-note` (planned-tool placeholder in preview builds).

Inside `fields_html`, the reference tool uses `calc-form`, `calc-field`, `calc-error`, `calc-results`,
`calc-stat`, `calc-stat-main`, `calc-stat-label`, `calc-stat-value`, `calc-schedule`, `table-scroll`.
Reuse these in new tools so one stylesheet covers every calculator.

## Adding things

- **A calculator:** create `content/tools/<slug>.json` (or fill in its existing stub), set `status`
  to `built`, run the build. Nav, hub, sitemap, related links and JSON-LD all update automatically.
- **A subcategory:** add it to `config/categories.json`; point tools at its slug.
- **New calculators from the competitor inventory:** `utilities/scaffold/seed_tool_stubs.py`
  creates stubs only for tools that don't have a file yet — it never overwrites.
