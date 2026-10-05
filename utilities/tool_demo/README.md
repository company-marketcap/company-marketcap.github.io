# Tool demos (animated AVIF)

`record_demo.py` records a short, silent, looping demo of each live calculator and encodes it as an animated AVIF
with embedded XMP/EXIF metadata. No zoom or pan: the page is recorded at 1x, 1280x800.

What a demo shows: the tool name, then each input in page order (up to 6 number, select or date fields) - a cursor
moves to the field and types a NEW value (the default moved 20-40%, or a different select option), a caption names
the field - ending on the highlighted result with a pulse and a caption such as "Future value: $95,035.01".
`basic-calculator` has no form, so it clicks a key sequence (`KEYPAD_FLOWS`). If the varied values give a validation
error or no result, it retries with other values and finally with the real defaults.

```bash
python3 src/generate.py                                    # build public/ first
.venv/bin/python record_demo.py compound-interest-calculator   # one tool
.venv/bin/python record_demo.py --all --skip-existing --jobs 3  # every live tool, 3 recorders in parallel
```

Setup (once): `python3 -m venv utilities/tool_demo/.venv && utilities/tool_demo/.venv/bin/pip install playwright piexif Pillow &&
utilities/tool_demo/.venv/bin/playwright install chromium`. Also needs `ffmpeg` and `avifenc` (libavif) on PATH.

Output (both committed):
- `src/static/assets/images/demos/<slug>-demo.avif`
- `src/config/demos.json`: slug -> alt text, width, height, duration, bytes, date. `generate.py` reads it to render the
  demo card under each calculator (`render_demo`) and the `ImageObject` in the page's JSON-LD (`schema.py`,
  `WebApplication.screenshot`). A tool with no entry simply has no demo card.

Notes:
- The recorder serves `public/` itself (stopped afterwards). Pass `--site-dir` with a copy of `public/` to rebuild the
  site while a long batch runs.
- Third-party requests (analytics, ads) are blocked and ad slots are hidden while recording; Google Fonts load.
- Each AVIF is ~300-500 KB. Re-recording a tool replaces its file, which adds that much to git history again, so only
  re-record tools whose calculator or layout changed.
- Failures are listed in `_work/failures-*.txt` (gitignored scratch folder).
