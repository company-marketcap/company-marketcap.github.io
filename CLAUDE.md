# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**MarketCapInsights** — a static frontend site of free investment calculators (market cap growth, position sizing, tax harvesting, sector balance, stock split impact, dividend reinvestment, inflation-adjusted returns). Monetized via Google AdSense (`ca-pub-5426315045205785`). Deployed to GitHub Pages at `company-marketcap.github.io`.

No backend. All calculation logic runs in the browser (vanilla JS).

## Commands

```bash
npm install          # install dependencies
npm start            # webpack-dev-server with hot reload (serves from project root)
npm run build        # production build → ./dist/
```

## Architecture

### Shared Components via Dynamic Inclusion
`js/include.js` fetches `header.html`, `footer.html`, and `calculator-nav.html` at runtime and injects them into placeholder elements. There is no server-side templating. When changing the nav or footer, edit those standalone HTML files — every page picks up the change.

### Webpack Setup
- `webpack.config.common.js` — shared base config; entry point is `js/app.js`
- `webpack.config.dev.js` — dev server with live reload
- `webpack.config.prod.js` — production build: cleans `dist/`, bundles, copies static assets (`img/`, `css/`, `js/vendor/`, icons, `robots.txt`, `site.webmanifest`, `404.html`)

Assets NOT bundled through webpack (CSS, images, vendor JS) are copied as-is via `copy-webpack-plugin`. Only `js/app.js` is a true webpack entry.

### Calculator Pages
Each calculator is a self-contained HTML file with its own JS file in `js/` (e.g., `position-sizing.html` + `js/position-sizing.js`). They share `css/styles.css` and page-specific CSS where needed. Adding a new calculator means: new HTML page, new JS file, update `calculator-nav.html` and `sitemap.xml`.

### Hosting
GitHub Pages serves straight from the `main` branch (not from `dist/`). Production builds are committed to the repo root, not a separate branch.
