/* WedSync — small progressive enhancements. Every page works without this file. */
(function () {
  "use strict";

  var STORAGE_KEY = "wedsync-theme";
  var root = document.documentElement;

  function storeTheme(theme) {
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) { /* storage blocked: theme lasts for this page only */ }
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#0e0716" : "#141217");
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      var dark = theme === "dark";
      button.setAttribute("aria-pressed", dark ? "true" : "false");
      button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
      button.setAttribute("title", dark ? "Switch to light mode" : "Switch to dark mode");
    });
  }

  // Theme toggle (the initial theme is set inline in <head> to avoid a flash).
  applyTheme(root.getAttribute("data-theme") || "light");
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-theme-toggle]");
    if (!button) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    storeTheme(next);
  });

  // Pending state on submit: keep the label, add a spinner, ignore repeat clicks.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || form.hasAttribute("data-no-pending")) return;
    var button = event.submitter || form.querySelector('button[type="submit"]');
    if (!button || button.getAttribute("aria-disabled") === "true") {
      if (button) event.preventDefault();
      return;
    }
    var pendingLabel = button.getAttribute("data-pending-label");
    button.setAttribute("data-original-html", button.innerHTML);
    button.setAttribute("aria-disabled", "true");
    if (pendingLabel) {
      var spinner = document.createElement("span");
      spinner.className = "ws-spinner";
      spinner.setAttribute("aria-hidden", "true");
      button.textContent = pendingLabel;
      button.prepend(spinner);
    }
  });

  // Alerts: every message has a close button; success and info messages also close
  // themselves after a few seconds. The timer pauses while the pointer or focus is on them.
  // Errors and warnings stay until closed so nobody misses why something failed.
  var AUTO_DISMISS_MS = 5000;

  function dismissAlert(alert, moveFocus) {
    if (!alert || alert.classList.contains("is-leaving")) return;
    alert.classList.add("is-leaving");
    window.setTimeout(function () {
      var list = alert.parentElement;
      alert.remove();
      if (list && list.hasAttribute("data-alerts") && !list.children.length) {
        var slot = list.parentElement;
        list.remove();
        if (slot && slot.hasAttribute("data-alerts-slot") && !slot.children.length) slot.remove();
      }
      if (moveFocus) {
        var main = document.getElementById("main");
        if (main) main.focus({ preventScroll: true });
      }
    }, 220);
  }

  document.addEventListener("click", function (event) {
    var close = event.target.closest("[data-alert-close]");
    if (close) dismissAlert(close.closest(".ws-alert"), true);
  });

  document.querySelectorAll("[data-autodismiss]").forEach(function (alert) {
    var remaining = AUTO_DISMISS_MS;
    var startedAt = 0;
    var timer = null;
    var holds = 0; // pointer and focus can both hold the alert open

    function start() {
      if (timer || holds > 0) return;
      startedAt = Date.now();
      timer = window.setTimeout(function () { dismissAlert(alert, false); }, remaining);
    }
    function hold() {
      holds += 1;
      if (timer) {
        window.clearTimeout(timer);
        timer = null;
        remaining = Math.max(1500, remaining - (Date.now() - startedAt));
      }
    }
    function release() {
      holds = Math.max(0, holds - 1);
      start();
    }

    alert.addEventListener("mouseenter", hold);
    alert.addEventListener("mouseleave", release);
    alert.addEventListener("focusin", hold);
    alert.addEventListener("focusout", release);
    start();
  });

  // Copy buttons (event codes): data-copy points at the element whose text is copied.
  // They are hidden in the HTML and only shown where the browser can copy.
  if (navigator.clipboard && window.isSecureContext) {
    document.querySelectorAll("[data-copy]").forEach(function (button) { button.hidden = false; });
  }
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy]");
    if (!button) return;
    var source = document.querySelector(button.getAttribute("data-copy"));
    if (!source) return;
    var label = button.textContent;
    navigator.clipboard.writeText(source.textContent.trim()).then(function () {
      button.textContent = button.getAttribute("data-copied-label") || "Copied";
      window.setTimeout(function () { button.textContent = label; }, 2000);
    });
  });

  // Coming back with the browser's Back button restores the page as it was: undo the pending state.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll("[data-original-html]").forEach(function (button) {
      button.innerHTML = button.getAttribute("data-original-html");
      button.removeAttribute("data-original-html");
      button.removeAttribute("aria-disabled");
    });
  });

  // After a failed submit, move focus to the first field with an error.
  var firstInvalid = document.querySelector('[aria-invalid="true"]');
  if (firstInvalid && typeof firstInvalid.focus === "function") {
    firstInvalid.focus({ preventScroll: false });
  }
})();
