/* Conversation SSE: reconnect with backoff, deliver frames as DOM events.
 *
 * The chat thread opens one EventSource per conversation. Every frame is
 * re-dispatched as a "helix:chat-message" CustomEvent so the page listens on
 * the document without coupling this file to one screen. The thread also
 * uses ChatComposer.optimistic/reconcile to show a bubble the instant you hit
 * Send and swap in the server-confirmed one when htmx answers.
 */
(function () {
  var RETRY_MS = [1000, 2000, 4000, 8000];

  function scrollThread(container) {
    container.scrollTop = container.scrollHeight;
  }

  function formatTime(iso) {
    var date = new Date(iso);
    if (isNaN(date.getTime())) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  window.HelixSse = {
    openConversationStream: function (conversationId) {
      var attempt = 0;
      var source = null;
      var connect = function () {
        source = new EventSource(
          "/app/api/conversations/" + encodeURIComponent(conversationId) + "/stream"
        );
        source.addEventListener("message", function (event) {
          attempt = 0;
          var data;
          try {
            data = JSON.parse(event.data);
          } catch (err) {
            return;
          }
          document.dispatchEvent(
            new CustomEvent("helix:chat-message", {
              detail: { conversationId: conversationId, message: data },
            })
          );
        });
        source.onerror = function () {
          source.close();
          var delay = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];
          attempt += 1;
          setTimeout(connect, delay);
        };
      };
      connect();
      return source;
    },
  };

  window.HelixChat = {
    append: function (holder, message, mine) {
      if (holder.querySelector('[data-message-id="' + CSS.escape(message.message_id) + '"]')) {
        return;
      }
      var pending = holder.querySelector('[data-pending="true"]');
      if (pending) {
        return;
      }
      var row = document.createElement("div");
      row.className = "chat-bubble" + (mine ? " chat-bubble--me" : " chat-bubble--them");
      row.setAttribute("data-message-id", message.message_id);
      var body = document.createElement("p");
      body.className = "chat-bubble__body";
      body.textContent = message.body;
      var meta = document.createElement("span");
      meta.className = "chat-bubble__meta";
      meta.textContent = formatTime(message.created_at);
      row.appendChild(body);
      row.appendChild(meta);
      holder.appendChild(row);
      scrollThread(holder);
    },
  };

  window.ChatComposer = {
    optimistic: function (form) {
      var input = form.querySelector('[name="body"]');
      var text = (input.value || "").trim();
      if (!text) return;
      var targetId = form.getAttribute("hx-target") || "";
      if (targetId.charAt(0) !== "#") return;
      var holder = document.getElementById(targetId.slice(1));
      if (!holder) return;
      var row = document.createElement("div");
      row.className = "chat-bubble chat-bubble--me chat-bubble--pending";
      row.setAttribute("data-pending", "true");
      var body = document.createElement("p");
      body.className = "chat-bubble__body";
      body.textContent = text;
      row.appendChild(body);
      holder.appendChild(row);
      scrollThread(holder);
    },
    reconcile: function (event) {
      var form = event && event.target;
      if (!form || !form.classList || !form.classList.contains("composer")) return;
      var targetId = form.getAttribute("hx-target") || "";
      if (targetId.charAt(0) !== "#") return;
      var holder = document.getElementById(targetId.slice(1));
      if (!holder) return;
      var successful = event.detail && event.detail.successful;
      if (successful) {
        var pending = holder.querySelector('[data-pending="true"]');
        if (pending) pending.remove();
        var input = form.querySelector('[name="body"]');
        if (input) input.value = "";
      }
      scrollThread(holder);
    },
  };

  document.addEventListener("helix:chat-message", function (event) {
    var detail = event.detail || {};
    var message = detail.message;
    if (!message || !message.message_id) return;
    var holder = document.querySelector(
      '[data-messages][data-conversation-id="' + CSS.escape(detail.conversationId) + '"]'
    );
    if (!holder) return;
    var mine = message.sender_account_id === holder.getAttribute("data-self");
    window.HelixChat.append(holder, message, mine);
  });

  var threadContainer = document.querySelector("[data-messages][data-conversation-id]");
  if (threadContainer) {
    window.HelixSse.openConversationStream(
      threadContainer.getAttribute("data-conversation-id")
    );
  }
})();