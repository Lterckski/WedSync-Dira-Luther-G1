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
