#!/usr/bin/env python3
"""One-time cleanup: remove calculator-nav, CTAs, and fix / links across all calculator pages."""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGES = [
    "index.html",
    "position-sizing.html",
    "tax-harvesting.html",
    "sector-balance.html",
    "stock-split-impact.html",
    "dividend-reinvestment.html",
    "stock-valuation-confidence.html",
    "inflation-adjusted-calculator.html",
]


def clean(content: str) -> str:
    # 1. Nav brand: / → index.html
    content = content.replace(
        'href="/">MCInsights</a>',
        'href="index.html">MCInsights</a>',
    )

    # 2. Footer home link: / → index.html
    content = content.replace(
        'href="/"><i class="bi bi-chevron-right small me-1"></i>Home</a>',
        'href="index.html"><i class="bi bi-chevron-right small me-1"></i>Home</a>',
    )

    # 3. Remove entire calculator-nav div (including any ad unit nested inside)
    content = re.sub(
        r'\n<div class="calculator-nav bg-light py-3 border-bottom">.*?</div>\n</div>\n',
        "\n",
        content,
        flags=re.S,
    )

    # 4. Remove features-section CTA (btn-primary → #calculator "Try the...")
    content = re.sub(
        r'\n\n    <div class="text-center mt-5">\n      <a class="btn btn-primary[^>]*" href="#calculator">[^\n]+\n      <p class="text-muted mt-2">[^\n]+\n    </div>',
        "",
        content,
    )

    # 5. Remove insights-section CTA (btn-outline-primary → #calculator)
    content = re.sub(
        r'\n    <div class="text-center mt-5">\n      <a class="btn btn-outline-primary" href="#calculator">[^\n]+\n    </div>',
        "",
        content,
    )

    # 6. Remove FAQ-section CTA ("Still have questions…" + "Contact Our Team")
    content = re.sub(
        r'\n\n        <div class="text-center mt-5">\n          <p class="lead mb-3">Still have questions[^<]*</p>\n          <a [^\n]+Contact Our Team[^\n]+\n        </div>',
        "",
        content,
    )

    return content


for page in PAGES:
    path = os.path.join(ROOT, page)
    original = open(path, encoding="utf-8").read()
    updated  = clean(original)
    if updated != original:
        open(path, "w", encoding="utf-8").write(updated)
        print(f"Updated: {page}")
    else:
        print(f"No change: {page}")
