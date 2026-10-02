#!/usr/bin/env python3
"""Compile src/styles/site-theme-and-components.css with the Tailwind v4 CLI into public/assets/css/site.css.

Scans every rendered page and script in public/ for utility classes, so run it after the pages are rendered.
Needs Node/npm; the Tailwind CLI is installed from package.json on first run.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "styles" / "site-theme-and-components.css"
OUT = ROOT / "public"
TARGET = OUT / "assets" / "css" / "site.css"


def build():
    if not shutil.which("npm"):
        sys.exit("error: Node.js (npm) is required to compile the Tailwind stylesheet")
    if not (ROOT / "node_modules" / "@tailwindcss" / "cli").exists():
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=ROOT, check=True)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:  # inside the project so 'tailwindcss' resolves from node_modules
        entry = Path(tmp) / "entry.css"
        entry.write_text(f'@import "tailwindcss";\n@source "{OUT}";\n{SOURCE.read_text(encoding="utf-8")}', encoding="utf-8")
        result = subprocess.run([str(ROOT / "node_modules" / ".bin" / "tailwindcss"), "-i", str(entry), "-o", str(TARGET), "--minify"],
                                capture_output=True, text=True)
    if result.returncode:
        sys.exit(f"error: Tailwind build failed\n{result.stderr}")
    print(f"Wrote {TARGET.relative_to(ROOT)} ({TARGET.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
