"""
Record a short, silent, looping demo (animated AVIF) of each live calculator page.

For each tool the recorder opens the built page (public/, served locally), walks through the calculator's real
inputs in order - moving a visible cursor to each field, typing a NEW value over the default (the default moved by
20-40%, or a different option for a select) - and ends on the highlighted result with a pulse and a caption. The
page is recorded at 1x with no zoom or pan. Frames are cut from the recording and encoded by avifenc with
embedded XMP/EXIF metadata (tag_metadata.py).

Output: src/static/assets/images/demos/<slug>-demo.avif  (committed; copied to the site by generate.py)
        src/config/demos.json                             (slug -> alt text, size, duration, date; read by generate.py)

    utilities/tool_demo/.venv/bin/python utilities/tool_demo/record_demo.py compound-interest-calculator
    utilities/tool_demo/.venv/bin/python utilities/tool_demo/record_demo.py --all --jobs 4 --skip-existing

Build the site first (python3 src/generate.py); the recorder serves public/ itself on --port.
"""
import argparse
import json
import random
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from demo_common import (ALLOWED_EXTERNAL, CALC_SECTION, DISCOVER_JS, ERROR_JS, FALLBACK_RESULT_JS, INIT_SCRIPT,
                         PRIMARY_RESULT_SELS, RESULT_LABEL_JS, VIEWPORT, animate_move, center_of, ensure_in_view, pulse, set_caption)
import tag_metadata as tm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOLS_DIR = ROOT / "src/content/tools"
PUBLIC = ROOT / "public"
OUT_DIR = ROOT / "src/static/assets/images/demos"
MANIFEST = ROOT / "src/config/demos.json"
WORK = HERE / "_work"
RESULTS = WORK / "results"

MAX_FIELDS = 8            # controls touched per demo (numbers, selects, dates and switches)
MAX_SWITCHES = 2          # checkboxes / radio buttons flipped per demo
MAX_BYTES = 900_000       # re-encode at lower quality above this (the whole set has a repo-size budget)
VARY_MIN, VARY_MAX = 0.20, 0.40
MAX_VARY_ATTEMPTS = 3
LEAD_IN_MS, FIELD_MOVE_MS, TYPE_DELAY_MS = 1200, 900, 110
PRE_TYPE_MS, POST_FIELD_MS, PULSE_MS, TAIL_MS, CAPTION_PRE_MS = 350, 700, 2600, 1800, 400
SECOND_PASS_FIELDS = 2    # numbers changed again after the first result, to show it respond
PLACEHOLDER_RESULTS = {"", "–", "—", "-", "--"}


class InvalidScenario(Exception):
    """The varied inputs produced a validation error or no usable result (worth retrying with other values)."""


# Tools with no form: a keypad. Each is a sequence of key ids to click, and the element that shows the answer.
KEYPAD_FLOWS = {
    "basic-calculator": {"keys": ["bcKey1", "bcKey2", "bcKeyDot", "bcKey5", "bcKeyMultiply", "bcKey8", "bcKeyAdd",
                                  "bcKey3", "bcKey0", "bcKeyEquals"],
                         "caption": "Press 12.5 × 8 + 30 =", "screen": "#bcScreen", "label": "Result"},
}


def decimals(text):
    return len(text.split(".")[1].rstrip("0")) if "." in text else 0


def vary_number(f, rng):
    """The field's current value moved by 20-40% in a random direction, kept to its precision, clamped to min/max."""
    try:
        d = float(f["value"])
    except ValueError:
        return None
    if d == 0:
        return None
    places = max(decimals(f["value"]), decimals(f["step"]) if f["step"] not in ("", "any") else 0)
    v = d * (1 + rng.choice((-1, 1)) * rng.uniform(VARY_MIN, VARY_MAX))
    v = round(v, places) if places else float(round(v))
    if d >= 1 and v < 1:
        v = 1.0
    if f["min"] not in ("", None):
        v = max(v, float(f["min"]))
    if f["max"] not in ("", None):
        v = min(v, float(f["max"]))
    if v == d:  # clamping landed back on the default; nudge by one unit inside the limits
        v = d + (10 ** -places if places else 1)
        if f["max"] not in ("", None) and v > float(f["max"]):
            v = d - (10 ** -places if places else 1)
    return f"{v:.{places}f}" if places else str(int(v))


def vary_date(f, rng, previous):
    """A new date: an empty field gets a date after the previous empty one; a filled field moves by 1-12 months."""
    lo = date.fromisoformat(f["min"]) if len(f["min"]) == 10 else date.min
    hi = date.fromisoformat(f["max"]) if len(f["max"]) == 10 else date.max
    if f["type"] == "month":
        base = date.fromisoformat(f["value"] + "-01") if f["value"] else date(2025, 1, 1)
        d = base + timedelta(days=30 * rng.choice((-1, 1)) * rng.randint(1, 6))
        return d.strftime("%Y-%m")
    if f["value"]:
        d = date.fromisoformat(f["value"]) + timedelta(days=rng.choice((-1, 1)) * rng.randint(30, 365))
    elif previous:
        d = previous + timedelta(days=rng.randint(30, 300))
    else:
        d = date(2025, 1, 1) + timedelta(days=rng.randint(0, 364))
    return min(max(d, lo), hi).isoformat()


def vary_select(f, rng):
    others = [o["value"] for o in f["options"] if o["value"] != f["value"] and o["value"] != ""]
    return rng.choice(others) if others else None


def plan_fields(fields, rng, vary):
    """[(field, new_value)] for the controls the demo touches: numbers and selects only (dates, text, radios and
    checkboxes keep the page's own values)."""
    plan, previous_date, dates, switches, seen_radio = [], None, [], 0, set()
    for f in fields:
        if f["readonly"]:
            continue
        if f["type"] in ("checkbox", "radio"):
            # Flip a checkbox, or pick another radio option (one per group). Only on varied runs: a switch can hide
            # fields or make a combination invalid, so the final default-values attempt leaves them alone.
            if vary and switches < MAX_SWITCHES and not (f["type"] == "radio" and (f["checked"] or f["name"] in seen_radio)):
                plan.append((f, "switch"))
                switches += 1
                if f["type"] == "radio":
                    seen_radio.add(f["name"])
            continue
        if f["tag"] == "select":
            value = vary_select(f, rng) if vary else None
        elif f["type"] == "number":
            value = vary_number(f, rng) if vary else f["value"]
        elif f["type"] in ("date", "month"):
            # Empty dates must be filled to get any result. Filled ones are only moved when the form has nothing
            # else to vary: shifting one date on its own usually breaks an ordering rule (first payment after funding).
            value = vary_date(f, rng, previous_date) if not f["value"] else f["value"]
            if f["value"]:
                dates.append(f)
            else:
                previous_date = date.fromisoformat(value) if f["type"] == "date" else previous_date
        else:
            continue
        if value is not None and not (f["type"] in ("date", "month") and f["value"]):
            plan.append((f, value))
    if vary and not plan:  # a form made only of pre-filled dates: move them
        plan = [(f, vary_date(f, rng, None)) for f in dates]
    return plan[:MAX_FIELDS]


def route_handler(route):
    host = urlparse(route.request.url).hostname or ""
    if host in ("localhost", "127.0.0.1") or host in ALLOWED_EXTERNAL:
        return route.continue_()
    return route.abort()


def find_result(page):
    """The headline result element, or None when the page has none we recognise yet."""
    for sel in PRIMARY_RESULT_SELS:
        loc = page.locator(sel)
        if loc.count():
            return loc.first
    found = page.evaluate(FALLBACK_RESULT_JS)
    return page.locator(f"#{found['id']}") if found else None


def result_ok(text, errors):
    return not errors and text.strip() not in PLACEHOLDER_RESULTS and not re.search(r"NaN|Infinity", text)


def record(tool, base_url, video_dir, attempt):
    slug = tool["slug"]
    rng = random.Random(f"{slug}:{attempt}")
    vary = attempt < MAX_VARY_ATTEMPTS  # last attempt keeps the real defaults
    with sync_playwright() as p:
        browser = p.chromium.launch()
        t0 = time.perf_counter()  # the recording starts at context creation
        context = browser.new_context(viewport=VIEWPORT, record_video_dir=str(video_dir), record_video_size=VIEWPORT)
        page = context.new_page()
        page.route("**/*", route_handler)
        page.add_init_script(INIT_SCRIPT)
        try:
            page.goto(f"{base_url}/{slug}.html", wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(300)
            t_ready = time.perf_counter() - t0

            if slug in KEYPAD_FLOWS:
                return record_keypad(page, tool, KEYPAD_FLOWS[slug], video_dir, browser, context, t0, t_ready)
            fields = page.evaluate(DISCOVER_JS, CALC_SECTION)
            plan = plan_fields(fields, rng, vary)
            if not plan:
                raise RuntimeError("no number, select or date inputs to demo")
            result = find_result(page)
            initial = result.inner_text() if result else None  # a result found only after typing has no baseline

            cursor = (40, 120)
            page.mouse.move(*cursor)
            set_caption(page, tool["name"])
            page.wait_for_timeout(LEAD_IN_MS)
            t_start = time.perf_counter() - t0

            touched = []
            for f, value in plan:
                loc = page.locator(f"#{f['id']}")
                if not loc.is_visible():  # a field hidden by an earlier choice
                    continue
                ensure_in_view(page, loc)
                label = f["label"] or f["id"]
                verb = "Choose" if f["tag"] == "select" or f["type"] == "radio" else "Switch" if f["type"] == "checkbox" else "Set"
                set_caption(page, f"{verb} {label}")
                page.wait_for_timeout(CAPTION_PRE_MS)
                target = center_of(loc)
                cursor = animate_move(page, cursor, target, FIELD_MOVE_MS)
                page.wait_for_timeout(PRE_TYPE_MS)
                if f["type"] in ("checkbox", "radio"):
                    page.mouse.click(*target)
                elif f["tag"] == "select":
                    loc.select_option(value)
                elif f["type"] in ("date", "month"):
                    page.mouse.click(*target)
                    loc.fill(value)  # a native date input can't be typed into reliably
                    page.keyboard.press("Tab")
                else:
                    page.mouse.click(*target, click_count=3)
                    page.keyboard.type(value, delay=TYPE_DELAY_MS)
                    page.keyboard.press("Tab")  # fire 'change' for pages that calculate on blur
                page.wait_for_timeout(POST_FIELD_MS)
                touched.append(label)

            if result is None:
                result = find_result(page)
                if result is None:
                    raise RuntimeError("no result element (.stat-value / .result-value / numeric leaf) on the page")
            primary_label = page.evaluate(RESULT_LABEL_JS, result.element_handle())
            ensure_in_view(page, result)
            text = result.inner_text()
            errors = page.evaluate(ERROR_JS, CALC_SECTION)
            if vary and initial is not None and text == initial and touched:  # a page that only calculates on submit
                page.keyboard.press("Enter")
                page.wait_for_timeout(400)
                text = result.inner_text()
                errors = page.evaluate(ERROR_JS, CALC_SECTION)
            if vary and (not result_ok(text, errors) or (initial is not None and text == initial)):
                raise InvalidScenario(f"attempt {attempt}: result {text!r} (was {initial!r}), errors {errors}")
            if not result_ok(text, errors):
                raise RuntimeError(f"result {text!r}, errors {errors} even with defaults")

            cursor = animate_move(page, cursor, center_of(result), 700)
            card = result.locator("xpath=ancestor::*[contains(@class,'stat-card') or contains(@class,'result-row')][1]")
            pulse(card if card.count() else result)
            page.wait_for_timeout(PULSE_MS)
            set_caption(page, f"{primary_label}: {text}")
            page.wait_for_timeout(TAIL_MS)

            if vary:  # second scenario: change the first numbers again and let the result respond
                second = [(f, vary_number(dict(f, value=v), rng)) for f, v in plan if f["type"] == "number"][:SECOND_PASS_FIELDS]
                second = [(f, v) for f, v in second if v is not None and page.locator(f"#{f['id']}").is_visible()]
                if second:
                    set_caption(page, "Now try different numbers")
                    page.wait_for_timeout(900)
                    for f, v in second:
                        loc = page.locator(f"#{f['id']}")
                        ensure_in_view(page, loc)
                        set_caption(page, f"Set {f['label'] or f['id']}")
                        page.wait_for_timeout(CAPTION_PRE_MS)
                        target = center_of(loc)
                        cursor = animate_move(page, cursor, target, FIELD_MOVE_MS)
                        page.mouse.click(*target, click_count=3)
                        page.keyboard.type(v, delay=TYPE_DELAY_MS)
                        page.keyboard.press("Tab")
                        page.wait_for_timeout(POST_FIELD_MS)
                    text2 = result.inner_text()
                    if result_ok(text2, page.evaluate(ERROR_JS, CALC_SECTION)) and text2 != text:
                        ensure_in_view(page, result)
                        cursor = animate_move(page, cursor, center_of(result), 700)
                        pulse(card if card.count() else result)
                        page.wait_for_timeout(PULSE_MS)
                        text = text2
                        set_caption(page, f"{primary_label}: {text}")
                        page.wait_for_timeout(TAIL_MS)
                    else:  # the second scenario broke validation: put the first numbers back and end on the first result
                        for f, _ in second:
                            old = next(v for ff, v in plan if ff["id"] == f["id"])
                            loc = page.locator(f"#{f['id']}")
                            loc.fill(old)
                            page.keyboard.press("Tab")
                        page.wait_for_timeout(300)
                        text = result.inner_text()
                        set_caption(page, f"{primary_label}: {text}")
                        page.wait_for_timeout(TAIL_MS)
            t_end = time.perf_counter() - t0
        finally:
            context.close()  # flushes the .webm
            browser.close()
    webm = sorted(video_dir.glob("*.webm"), key=lambda f: f.stat().st_mtime)[-1]
    return webm, (t_ready, t_end), {"labels": touched, "primary_label": primary_label, "result": text}


def record_keypad(page, tool, flow, video_dir, browser, context, t0, t_ready):
    """Click a key sequence on a keypad calculator, ending on the answer. Closes the recording itself."""
    screen = page.locator(flow["screen"])
    cursor = (40, 120)
    page.mouse.move(*cursor)
    set_caption(page, tool["name"])
    page.wait_for_timeout(LEAD_IN_MS)
    set_caption(page, flow["caption"])
    ensure_in_view(page, screen)
    for key in flow["keys"]:
        loc = page.locator(f"#{key}")
        ensure_in_view(page, loc, margin=40)  # a click outside the frame would miss
        target = center_of(loc)
        cursor = animate_move(page, cursor, target, 450)
        page.mouse.click(*target)
        page.wait_for_timeout(250)
    text = screen.inner_text()
    if text.strip() in PLACEHOLDER_RESULTS | {"0"}:
        raise RuntimeError(f"keypad result {text!r}")
    pulse(screen)
    page.wait_for_timeout(PULSE_MS)
    set_caption(page, f"{flow['label']}: {text}")
    page.wait_for_timeout(TAIL_MS)
    t_end = time.perf_counter() - t0
    context.close()
    browser.close()
    webm = sorted(video_dir.glob("*.webm"), key=lambda f: f.stat().st_mtime)[-1]
    return webm, (t_ready, t_end), {"labels": [], "primary_label": flow["label"], "result": text, "keypad": flow["caption"]}


def make_one(slug, base_url, keep_temp):
    tool = json.loads((TOOLS_DIR / f"{slug}.json").read_text(encoding="utf-8"))
    work = WORK / slug
    shutil.rmtree(work, ignore_errors=True)
    video_dir = work / "raw"
    video_dir.mkdir(parents=True)
    try:
        for attempt in range(MAX_VARY_ATTEMPTS + 1):
            try:
                webm, (t_ready, t_end), info = record(tool, base_url, video_dir, attempt)
                break
            except InvalidScenario as exc:
                print(f"  {exc}; retrying", flush=True)
                for f in video_dir.glob("*.webm"):
                    f.unlink()
        else:
            raise RuntimeError("no valid scenario")
        frames = work / "frames"
        frames.mkdir()
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t_ready:.3f}", "-to", f"{t_end:.3f}", "-i", str(webm),
                        "-vf", f"fps={tm.FPS}", str(frames / "frame_%04d.png")], check=True)
        n = len(list(frames.glob("frame_*.png")))
        out = OUT_DIR / f"{slug}-demo.avif"
        alt = (f"Animated walkthrough of the {tool['name']}: {info['keypad'][0].lower() + info['keypad'][1:]} "
               f"and reading the answer." if info.get("keypad")
               else tm.build_alt_text(tool["name"], info["labels"], info["primary_label"].lower()))
        q = tm.QCOLOR
        tm.encode_tagged_avif(tool, alt, frames, out, VIEWPORT["width"], VIEWPORT["height"], n, qcolor=q)
        while out.stat().st_size > MAX_BYTES and q > 29:  # keep the whole set inside its repo-size budget
            q -= 8
            print(f"  {out.stat().st_size / 1024:.0f} KB is over budget; re-encoding at q={q}", flush=True)
            tm.encode_tagged_avif(tool, alt, frames, out, VIEWPORT["width"], VIEWPORT["height"], n, qcolor=q)
        entry = {"alt": alt, "width": VIEWPORT["width"], "height": VIEWPORT["height"],
                 "duration_s": round(n / tm.FPS, 2), "bytes": out.stat().st_size, "generated": date.today().isoformat()}
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f"{slug}.json").write_text(json.dumps(entry), encoding="utf-8")
        print(f"  wrote {out.name}: {entry['bytes'] / 1024:.0f} KB, {entry['duration_s']}s, {n} frames; "
              f"{info['primary_label']} = {info['result']}", flush=True)
    finally:
        if not keep_temp:
            shutil.rmtree(work, ignore_errors=True)


def merge_manifest():
    """Fold the per-tool result files into src/config/demos.json (sorted, so diffs stay small)."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    for f in RESULTS.glob("*.json") if RESULTS.exists() else []:
        data[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    MANIFEST.write_text(json.dumps(dict(sorted(data.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{MANIFEST.relative_to(ROOT)}: {len(data)} demos")


def live_slugs():
    return sorted(p.stem for p in TOOLS_DIR.glob("*.json")
                  if json.loads(p.read_text(encoding="utf-8")).get("status") in ("built", "verified", "done"))


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--all", action="store_true", help="every live tool")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--jobs", type=int, default=1, help="parallel recorder processes")
    ap.add_argument("--shard", help="i/N: handle every N-th slug starting at i (used by --jobs)")
    ap.add_argument("--port", type=int, default=8821)
    ap.add_argument("--site-dir", default=str(PUBLIC), help="built site to record (a copy of public/ lets you rebuild meanwhile)")
    ap.add_argument("--keep-temp", action="store_true")
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()
    if args.merge_only:
        return merge_manifest()

    slugs = live_slugs() if args.all else args.slugs
    if args.skip_existing:
        done = set(json.loads(MANIFEST.read_text(encoding="utf-8"))) if MANIFEST.exists() else set()
        done |= {f.stem for f in RESULTS.glob("*.json")}  # recorded in this run but not merged yet
        slugs = [s for s in slugs if s not in done or not (OUT_DIR / f"{s}-demo.avif").exists()]
    if args.shard:
        i, n = map(int, args.shard.split("/"))
        slugs = slugs[i::n]
    if not slugs:
        return print("nothing to do")

    server = None
    if not port_open(args.port):  # serve public/ for the recording (stopped again below)
        server = subprocess.Popen([sys.executable, "-m", "http.server", str(args.port), "--directory", args.site_dir],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if port_open(args.port):
                break
            time.sleep(0.1)
    base_url = f"http://localhost:{args.port}"
    try:
        if args.jobs > 1 and not args.shard:
            procs = [subprocess.Popen([sys.executable, __file__, *sys.argv[1:], "--jobs", "1", "--shard", f"{i}/{args.jobs}"])
                     for i in range(args.jobs)]
            for pr in procs:
                pr.wait()
        else:
            failures = []
            for n, slug in enumerate(slugs, 1):
                print(f"[{n}/{len(slugs)}] {slug}", flush=True)
                try:
                    make_one(slug, base_url, args.keep_temp)
                except Exception as exc:  # one broken tool must not stop the batch
                    msg = (str(exc).splitlines() or [repr(exc)])[0]
                    print(f"  FAILED: {msg}", flush=True)
                    failures.append(f"{slug}\t{msg}\n")
            if failures:
                WORK.mkdir(exist_ok=True)
                tag = args.shard.replace("/", "of") if args.shard else "all"
                (WORK / f"failures-{tag}.txt").write_text("".join(failures), encoding="utf-8")
                print(f"{len(failures)} failed")
    finally:
        if server:
            server.terminate()
    if not args.shard:
        merge_manifest()


if __name__ == "__main__":
    main()
