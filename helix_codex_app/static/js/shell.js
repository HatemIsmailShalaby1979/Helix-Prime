/* The application shell: command palette, mobile section sheet, the guided
 * checklist, and one place that turns a failed request into a visible toast.
 *
 * Everything here is progressive: with JavaScript off the palette and sheet
 * markup still renders as ordinary lists of links, and the guide stays on
 * screen until it is dismissed. Nothing in this file decides access — the
 * server already filtered every link by role before it was rendered.
 */
(function () {
  "use strict";

  var VISITS_KEY = "helix-codex:visited";
  var GUIDE_KEY = "helix-codex:guide-dismissed";

  /* ------------------------------------------------------------------ */
  /* Toasts                                                              */
  /* ------------------------------------------------------------------ */

  function toast(message, kind) {
    var host = document.getElementById("toast-host");
    if (!host) return;
    var node = document.createElement("div");
    node.className = "toast" + (kind === "error" ? " toast--error" : "");
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = message;
    host.appendChild(node);
    window.setTimeout(function () {
      node.remove();
    }, kind === "error" ? 7000 : 4000);
  }

  window.HelixToast = { show: toast };

  /* ------------------------------------------------------------------ */
  /* Command palette                                                     */
  /* ------------------------------------------------------------------ */

  function setupPalette() {
    var dialog = document.getElementById("command-palette");
    var input = document.getElementById("palette-input");
    var list = document.getElementById("palette-list");
    var empty = document.getElementById("palette-empty");
    if (!dialog || !input || !list) return;

    var items = Array.prototype.slice.call(list.querySelectorAll("[data-palette-item]"));
    var cursor = -1;

    function visible() {
      return items.filter(function (item) {
        return !item.parentElement.hidden;
      });
    }

    function highlight(next) {
      var shown = visible();
      if (!shown.length) return;
      cursor = (next + shown.length) % shown.length;
      shown.forEach(function (item, index) {
        item.setAttribute("data-active", index === cursor ? "true" : "false");
      });
      shown[cursor].scrollIntoView({ block: "nearest" });
    }

    function filter(query) {
      var needle = query.trim().toLowerCase();
      items.forEach(function (item) {
        var haystack = item.getAttribute("data-search") || "";
        var match = !needle || haystack.indexOf(needle) !== -1;
        item.parentElement.hidden = !match;
      });
      var any = visible().length > 0;
      if (empty) empty.hidden = any;
      cursor = -1;
      if (any) highlight(0);
    }

    function open() {
      if (dialog.open) return;
      dialog.showModal();
      input.value = "";
      filter("");
      input.focus();
    }

    function close() {
      if (dialog.open) dialog.close();
    }

    window.HelixPalette = { open: open, close: close };

    document.querySelectorAll("[data-command-open]").forEach(function (trigger) {
      trigger.addEventListener("click", open);
    });

    input.addEventListener("input", function () {
      filter(input.value);
    });

    dialog.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        highlight(cursor + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        highlight(cursor - 1);
      } else if (event.key === "Enter") {
        var shown = visible();
        if (cursor >= 0 && shown[cursor]) {
          event.preventDefault();
          shown[cursor].click();
        }
      }
    });

    // Clicking the backdrop closes the dialog.
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) close();
    });

    document.addEventListener("keydown", function (event) {
      var meta = event.metaKey || event.ctrlKey;
      if (meta && event.key.toLowerCase() === "k") {
        event.preventDefault();
        dialog.open ? close() : open();
        return;
      }
      var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName) ||
        event.target.isContentEditable;
      if (!typing && event.key === "/" && !meta) {
        event.preventDefault();
        open();
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* Mobile "More" sheet                                                 */
  /* ------------------------------------------------------------------ */

  function setupSheet() {
    var sheet = document.getElementById("more-sheet");
    if (!sheet) return;

    document.querySelectorAll("[data-more-open]").forEach(function (trigger) {
      trigger.addEventListener("click", function () {
        if (!sheet.open) sheet.showModal();
      });
    });

    document.querySelectorAll("[data-sheet-close]").forEach(function (button) {
      button.addEventListener("click", function () {
        sheet.close();
      });
    });

    sheet.addEventListener("click", function (event) {
      if (event.target === sheet) sheet.close();
    });
  }

  /* ------------------------------------------------------------------ */
  /* Guided checklist                                                    */
  /* ------------------------------------------------------------------ */

  function readVisits() {
    try {
      return JSON.parse(window.localStorage.getItem(VISITS_KEY) || "[]");
    } catch (err) {
      return [];
    }
  }

  function setupGuide() {
    var guide = document.querySelector("[data-guide]");
    if (!guide) return;

    var here = guide.getAttribute("data-guide-here") || "";
    var visits = readVisits();
    if (here && visits.indexOf(here) === -1) {
      visits.push(here);
      try {
        window.localStorage.setItem(VISITS_KEY, JSON.stringify(visits));
      } catch (err) {
        /* storage unavailable — the checklist simply never ticks */
      }
    }

    var steps = guide.querySelectorAll("[data-guide-step]");
    var done = 0;
    steps.forEach(function (step) {
      var key = step.getAttribute("data-guide-step");
      if (visits.indexOf(key) !== -1) {
        step.classList.add("guide__step--done");
        step.setAttribute("data-done", "true");
        done += 1;
      }
    });

    var progress = guide.querySelector("[data-guide-progress]");
    if (progress) {
      progress.textContent = done + " of " + steps.length + " explored";
    }

    guide.querySelectorAll("[data-guide-dismiss]").forEach(function (button) {
      button.addEventListener("click", function () {
        guide.hidden = true;
        try {
          window.localStorage.setItem(GUIDE_KEY, "1");
        } catch (err) {
          /* nothing to do */
        }
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* Failed requests become visible                                      */
  /* ------------------------------------------------------------------ */

  function setupRequestFeedback() {
    document.body.addEventListener("htmx:responseError", function (event) {
      var status = event.detail.xhr ? event.detail.xhr.status : 0;
      if (status === 403) {
        toast("That action is outside your permissions.", "error");
      } else if (status === 401) {
        toast("Your session ended. Sign in again.", "error");
      } else {
        toast("That did not go through. Nothing was changed.", "error");
      }
    });
    document.body.addEventListener("htmx:sendError", function () {
      toast("No connection to the app. Nothing was changed.", "error");
    });
  }

  function boot() {
    setupPalette();
    setupSheet();
    setupGuide();
    setupRequestFeedback();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
