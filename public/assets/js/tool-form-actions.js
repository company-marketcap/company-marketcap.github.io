/*
 * File: assets/js/tool-form-actions.js
 * Calculate and Reset buttons for single-form calculator pages. Each tool's own script still does the
 * maths and live updating; this only adds the buttons, brings the results into view and flashes them.
 * Reset restores a snapshot of the values taken once the tool's own script has set its defaults (some fill
 * today's date in with JavaScript, so form.reset() would blank them). It is skipped for forms that contain
 * other buttons (add/remove rows), which a value snapshot can't undo.
 */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function fire(control, type) {
    control.dispatchEvent(new Event(type, { bubbles: true }));
  }

  function revealResults(results) {
    var top = results.getBoundingClientRect().top;
    if (top < 88 || top > window.innerHeight - 160) {
      window.scrollTo({ top: window.scrollY + top - 96, behavior: reduceMotion.matches ? "auto" : "smooth" });
    }
    results.classList.remove("result-flash");
    void results.offsetWidth;
    results.classList.add("result-flash");
  }

  function init() {
    var pageSlug = document.body.dataset.pageSlug;
    var card = document.getElementById(pageSlug + "-tool");
    if (!card) return;
    var forms = card.querySelectorAll("form");
    if (forms.length !== 1) return;
    var form = forms[0];
    var results = card.querySelector('[aria-live="polite"]');
    if (!results || form.querySelector('[type="submit"], [type="reset"]')) return;

    var hasOtherButtons = !!form.querySelector("button");
    var bar = document.createElement("div");
    bar.id = pageSlug + "-form-actions";
    bar.className = "flex flex-wrap gap-3";

    var calculate = document.createElement("button");
    calculate.type = "submit";
    calculate.id = pageSlug + "-calculate-button";
    calculate.className = "button-primary";
    calculate.textContent = "Calculate";
    bar.appendChild(calculate);

    if (!hasOtherButtons) {
      var reset = document.createElement("button");
      reset.type = "button";
      reset.id = pageSlug + "-reset-button";
      reset.className = "button-danger";
      reset.textContent = "Reset";
      var controls = Array.prototype.slice.call(form.querySelectorAll("input, select, textarea"));
      var defaults = controls.map(function (control) {
        return { value: control.value, checked: control.checked };
      });
      reset.addEventListener("click", function () {
        controls.forEach(function (control, index) {
          control.value = defaults[index].value;
          control.checked = defaults[index].checked;
          fire(control, "input");
          if (control.tagName === "SELECT" || control.type === "checkbox" || control.type === "radio") fire(control, "change");
        });
        var first = form.querySelector("input:not([type=hidden]), select, textarea");
        if (first) first.focus({ preventScroll: true });
        revealResults(results);
      });
      bar.appendChild(reset);
    }

    var error = form.querySelector('[role="alert"]');
    form.insertBefore(bar, error);

    form.addEventListener("submit", function (event) {
      if (!event.defaultPrevented) event.preventDefault();
      window.setTimeout(function () { revealResults(results); }, 0);
    });
    results.addEventListener("animationend", function () { results.classList.remove("result-flash"); });
  }

  // Deferred scripts run before DOMContentLoaded, so wait for it: the tool's own script registered first and
  // has set its defaults by the time this runs.
  if (document.readyState === "complete") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
