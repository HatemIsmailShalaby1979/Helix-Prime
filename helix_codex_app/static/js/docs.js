/* Block editor autosave: debounced PUTs with a small saved indicator.
 *
 * Each contenteditable block carries data-block-url. Typing schedules a
 * save 1.5 seconds after the last keystroke; blurring saves immediately, so
 * leaving a block never leaves an unsaved edit behind. The page still reads
 * fine without this file — the blocks are already rendered — and only the
 * save needs the request this script fires.
 */
(function () {
  var SAVE_DELAY_MS = 1500;
  var SETTLE_MS = 2000;

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function saveBlock(block) {
    var url = block.getAttribute("data-block-url");
    if (!url) return;
    var saved = block.parentElement.querySelector("[data-block-saved]");
    htmx
      .ajax("PUT", url, {
        source: block,
        values: { content: block.innerText },
        headers: { "X-CSRF-Token": csrfToken() },
      })
      .then(function () {
        if (!saved) return;
        saved.hidden = false;
        clearTimeout(saved._hide);
        saved._hide = setTimeout(function () {
          saved.hidden = true;
        }, SETTLE_MS);
      })
      .catch(function () {
        if (saved) {
          saved.textContent = "Not saved";
          saved.hidden = false;
          clearTimeout(saved._hide);
          saved._hide = setTimeout(function () {
            saved.textContent = "Saved";
            saved.hidden = true;
          }, SETTLE_MS);
        }
      });
  }

  function wire(block) {
    var timer = null;
    block.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        saveBlock(block);
      }, SAVE_DELAY_MS);
    });
    block.addEventListener("blur", function () {
      clearTimeout(timer);
      saveBlock(block);
    });
  }

  function init() {
    var blocks = document.querySelectorAll("[data-block-url]");
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i]._helixDocsWired) continue;
      blocks[i]._helixDocsWired = true;
      wire(blocks[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  document.addEventListener("htmx:afterSwap", init);
})();