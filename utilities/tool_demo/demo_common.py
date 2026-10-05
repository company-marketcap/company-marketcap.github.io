"""Shared Playwright helpers for the tool demo recorder: a synthetic cursor, click ripple, caption banner and
result pulse injected into the page (headless Chrome draws none of this), plus smooth mouse and scroll motion.

No zoom or pan effects: the page is recorded at 1x and its own layout carries the shot.
"""

# Desktop-width frame. The sidebar shows (lg breakpoint) and the right rail does not (2xl), so the calculator
# gets most of the frame. Recorded at the final size, so nothing is scaled afterwards.
VIEWPORT = {"width": 1280, "height": 800}

CALC_SECTION = 'section[data-section="calculator"]'
# The headline result: the highlighted stat card, then any stat card or result row. Searched across the whole page
# main (some tools put their results in a separate section from the form).
PRIMARY_RESULT_SELS = ["main .stat-card-highlight .stat-value", "main .stat-value", "main .result-value"]

# Last resort for tools with a different results layout (plain table cells, etc.): the first leaf element with an id
# and a number in it, in the results area, outside any form.
FALLBACK_RESULT_JS = """
() => {
  const main = document.querySelector('main');
  if (!main) return null;
  const scope = main.querySelector('[id$="Results"], section[data-section="results"]') || main;
  const skip = ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'H1', 'H2', 'H3', 'LABEL', 'OPTION'];
  for (const el of scope.querySelectorAll('[id]')) {
    if (el.children.length || skip.includes(el.tagName) || el.closest('form')) continue;
    const t = el.textContent.trim();
    const r = el.getBoundingClientRect();
    if (/\\d/.test(t) && t.length < 40 && r.width > 0 && r.height > 0) return { id: el.id };
  }
  return null;
}
"""

# The label for a result element: its card's label, its result row's term, its table row's header, or its previous sibling.
RESULT_LABEL_JS = """
(el) => {
  const c = el.closest('.stat-card, .result-row');
  let l = c && c.querySelector('.stat-label, .result-term');
  if (!l) { const tr = el.closest('tr'); l = tr && tr.querySelector('th'); }
  if (!l) l = el.previousElementSibling;
  const t = l ? l.textContent.trim() : '';
  return t || 'Result';
}
"""

# Third-party requests are blocked while recording (no analytics hits, no ads); Google Fonts stay allowed so the
# page looks as it does for visitors.
ALLOWED_EXTERNAL = ("fonts.googleapis.com", "fonts.gstatic.com", "api.frankfurter.dev")  # + the currency calculator's rates

INIT_SCRIPT = """
(() => {
  let cursor, ripple, caption;
  function setup() {
    const style = document.createElement('style');
    style.textContent = `
      .ad-slot, ins.adsbygoogle { display: none !important; }
      #__demo_overlay__ { position: fixed; inset: 0; pointer-events: none; z-index: 2147483647; }
      #__demo_cursor__ { position: fixed; top:0; left:0; width:24px; height:24px; display:none; }
      #__demo_ripple__ { position: fixed; top:0; left:0; width:28px; height:28px;
        margin:-14px 0 0 -14px; border-radius:50%; background: rgba(47,82,51,0.55); opacity:0; }
      #__demo_caption__ { position: fixed; left:50%; bottom:36px; transform:translateX(-50%);
        max-width: 880px; padding: 12px 24px; border-radius: 999px;
        background: rgba(18,23,20,0.92); color:#fff; font: 600 19px/1.4 -apple-system,
        BlinkMacSystemFont, 'Segoe UI', sans-serif; text-align:center;
        box-shadow: 0 8px 30px rgba(0,0,0,0.25); opacity:0; transition: opacity 200ms ease; }
      #__demo_caption__.visible { opacity:1; }
      @keyframes __demo_ripple_anim__ { 0% { transform: scale(0.3); opacity:0.55; } 100% { transform: scale(1.8); opacity:0; } }
      .__demo_result_pulse__ { animation: __demo_result_pulse_anim__ 900ms ease-out 3; border-radius: 12px; }
      @keyframes __demo_result_pulse_anim__ {
        0%   { box-shadow: 0 0 0 0 rgba(47,82,51,0.9), 0 0 0 0 rgba(47,82,51,0.35); }
        45%  { box-shadow: 0 0 0 3px rgba(47,82,51,0.9), 0 0 0 20px rgba(47,82,51,0); }
        100% { box-shadow: 0 0 0 0 rgba(47,82,51,0), 0 0 0 20px rgba(47,82,51,0); }
      }
    `;
    document.documentElement.appendChild(style);
    const overlay = document.createElement('div');
    overlay.id = '__demo_overlay__';
    document.documentElement.appendChild(overlay);
    cursor = document.createElement('div');
    cursor.id = '__demo_cursor__';
    cursor.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24"><path d="M3 2 L3 19 L7.5 15.6 L10.5 22 L13.3 20.7 L10.3 14.3 L16 14.3 Z" fill="#161616" stroke="#ffffff" stroke-width="1.3" stroke-linejoin="round"/></svg>`;
    overlay.appendChild(cursor);
    ripple = document.createElement('div');
    ripple.id = '__demo_ripple__';
    overlay.appendChild(ripple);
    caption = document.createElement('div');
    caption.id = '__demo_caption__';
    overlay.appendChild(caption);
    window.__setCaption__ = (t) => { if (!t) { caption.classList.remove('visible'); return; } caption.textContent = t; caption.classList.add('visible'); };
    window.__pulse__ = (el) => { if (!el) return; el.classList.remove('__demo_result_pulse__'); void el.offsetWidth; el.classList.add('__demo_result_pulse__'); };
  }
  if (document.documentElement) setup(); else document.addEventListener('DOMContentLoaded', setup, { once: true });
  document.addEventListener('mousemove', (e) => {
    if (!cursor) return;
    cursor.style.display = 'block';
    cursor.style.transform = `translate(${e.clientX - 3}px, ${e.clientY - 2}px)`;
  }, true);
  document.addEventListener('mousedown', (e) => {
    if (!ripple) return;
    ripple.style.left = e.clientX + 'px'; ripple.style.top = e.clientY + 'px';
    ripple.style.animation = 'none'; void ripple.offsetWidth;
    ripple.style.animation = '__demo_ripple_anim__ 380ms ease-out';
  }, true);
})();
"""

# Controls inside the calculator section, in page order, with their label and constraints.
DISCOVER_JS = """
(sel) => {
  const root = document.querySelector(sel);
  if (!root) return [];
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const labelOf = (el) => {
    let l = el.id ? root.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
    if (!l) l = el.closest('label');
    let t = l ? l.textContent : (el.getAttribute('aria-label') || '');
    return t.replace(/\\s+/g, ' ').trim();
  };
  return [...root.querySelectorAll('input, select')].filter((el) => el.id && visible(el)).map((el) => ({
    id: el.id, tag: el.tagName.toLowerCase(), type: el.type, label: labelOf(el), value: el.value,
    checked: el.checked, name: el.name,
    min: el.min, max: el.max, step: el.step, readonly: el.readOnly || el.disabled,
    options: el.tagName === 'SELECT' ? [...el.options].map((o) => ({value: o.value, text: o.textContent.trim()})) : [],
  }));
}
"""

ERROR_JS = """
(sel) => [...document.querySelectorAll(sel + ' .form-error, ' + sel + ' [role=alert], ' + sel + ' .field-error')]
  .filter((e) => !e.hidden && getComputedStyle(e).display !== 'none' && e.textContent.trim()).map((e) => e.textContent.trim())
"""


def animate_move(page, start, end, duration_ms=700, steps=36):
    for i in range(1, steps + 1):
        t = i / steps
        eased = t * t * (3 - 2 * t)
        page.mouse.move(start[0] + (end[0] - start[0]) * eased, start[1] + (end[1] - start[1]) * eased)
        page.wait_for_timeout(duration_ms / steps)
    return end


def center_of(locator):
    box = locator.bounding_box()
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def smooth_scroll_to(page, y, duration_ms=450, steps=24):
    """Eased scroll to an absolute scrollY (own animation, so it doesn't depend on the page's CSS)."""
    start = page.evaluate("window.scrollY")
    y = max(0, y)
    for i in range(1, steps + 1):
        t = i / steps
        eased = t * t * (3 - 2 * t)
        page.evaluate("(v) => window.scrollTo(0, v)", start + (y - start) * eased)
        page.wait_for_timeout(duration_ms / steps)


def ensure_in_view(page, locator, margin=140):
    """Scroll just enough that locator sits inside the frame with some margin (no-op when it already does)."""
    box = locator.bounding_box()
    vh = page.viewport_size["height"]
    if box is None:
        return
    if box["y"] < margin or box["y"] + box["height"] > vh - margin:
        smooth_scroll_to(page, page.evaluate("window.scrollY") + box["y"] - vh / 2 + box["height"] / 2)


def set_caption(page, text):
    page.evaluate("(t) => window.__setCaption__(t || null)", text)


def pulse(locator):
    locator.evaluate("(el) => window.__pulse__(el)")
