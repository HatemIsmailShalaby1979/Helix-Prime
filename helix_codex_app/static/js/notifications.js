/* Notification centre: header bell + badge, list styles, live badge script.
 *
 * HelixBadge drives the [data-notification-badge] element in the shell
 * header. One EventSource per page opens the account's stream, whose first
 * frame carries the current unread count; later frames bump or clear it.
 * The notification list page also hooks "Mark read" buttons onto
 * HelixBadge.apply so the header badge moves the instant a row is read.
 */
(function () {
  var RETRY_MS = [1000, 2000, 4000, 8000];

  function clamp(value) {
    var n = parseInt(value, 10);
    if (isNaN(n) || n < 0) return 0;
    return n;
  }

  window.HelixBadge = {
    apply: function (unread) {
      var badge = document.querySelector("[data-notification-badge]");
      if (!badge) return;
      var count = clamp(unread);
      badge.hidden = count === 0;
      badge.textContent = count > 99 ? "99+" : String(count);
    },
  };

  var badge = document.querySelector("[data-notification-badge]");
  if (!badge) return;

  var attempt = 0;
  var source = null;

  var connect = function () {
    source = new EventSource("/app/api/notifications/stream");
    source.addEventListener("unread_count", function (event) {
      attempt = 0;
      var data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        return;
      }
      window.HelixBadge.apply(data.unread);
    });
    source.onerror = function () {
      if (source) source.close();
      var delay = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];
      attempt += 1;
      setTimeout(connect, delay);
    };
  };
  connect();
})();