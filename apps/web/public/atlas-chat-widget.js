(function () {
  "use strict";

  var script = document.currentScript;
  var publicId = script && script.getAttribute("data-widget-id");
  if (!publicId) return;

  var apiBase = (script.getAttribute("data-api-base") || new URL(script.src).origin).replace(/\/$/, "");
  var endpoint = apiBase + "/api/v1/widget/" + encodeURIComponent(publicId);
  var sessionToken;
  var starting;
  var refreshing = false;
  var renderedMessages = 0;
  var pendingMessage;
  var sending = false;

  var panel = document.createElement("aside");
  panel.id = "atlas-customer-chat";
  panel.setAttribute("aria-label", "Customer chat");
  panel.hidden = true;
  panel.style.cssText = "position:fixed;right:20px;bottom:72px;width:320px;max-width:calc(100vw - 40px);box-sizing:border-box;background:#fff;color:#111;border:1px solid #ddd;border-radius:12px;box-shadow:0 8px 30px #0002;padding:12px;z-index:2147483646;font:14px system-ui";

  var log = document.createElement("div");
  log.setAttribute("role", "log");
  log.setAttribute("aria-label", "Chat messages");
  log.style.cssText = "height:240px;overflow:auto;margin-bottom:8px;overflow-wrap:anywhere";

  var status = document.createElement("p");
  status.setAttribute("role", "status");
  status.style.cssText = "margin:0 0 8px";

  var form = document.createElement("form");
  form.style.cssText = "display:flex;gap:8px";
  var input = document.createElement("input");
  input.setAttribute("aria-label", "Chat message");
  input.placeholder = "Write a message";
  input.maxLength = 5000;
  input.disabled = true;
  input.style.cssText = "flex:1;min-width:0;padding:8px";
  var send = document.createElement("button");
  send.type = "submit";
  send.textContent = "Send";
  send.disabled = true;
  send.style.cssText = "padding:8px";

  form.append(input, send);
  panel.append(log, status, form);
  document.body.appendChild(panel);

  var toggle = document.createElement("button");
  toggle.type = "button";
  toggle.textContent = "Chat";
  toggle.setAttribute("aria-label", "Customer chat");
  toggle.setAttribute("aria-controls", panel.id);
  toggle.setAttribute("aria-expanded", "false");
  toggle.style.cssText = "position:fixed;right:20px;bottom:20px;border:0;border-radius:999px;background:#4f46e5;color:#fff;padding:12px 18px;z-index:2147483646";
  document.body.appendChild(toggle);

  function add(text, sender) {
    var message = document.createElement("p");
    message.textContent = sender + ": " + text;
    log.appendChild(message);
    log.scrollTop = log.scrollHeight;
  }

  function readJson(response) {
    if (!response.ok) throw new Error("Chat request failed");
    return response.json();
  }

  function messagesUrl() {
    return endpoint + "/sessions/" + encodeURIComponent(sessionToken) + "/messages";
  }

  function refresh() {
    if (!sessionToken || refreshing || panel.hidden) return;
    refreshing = true;
    fetch(messagesUrl(), { credentials: "omit" })
      .then(readJson)
      .then(function (messages) {
        messages.slice(renderedMessages).forEach(function (message) {
          add(message.body, message.direction === "inbound" ? "You" : message.sender || "ATLAS");
        });
        renderedMessages = messages.length;
      })
      .catch(function () {
        if (!sending && !pendingMessage) status.textContent = "Could not refresh chat. Retrying.";
      })
      .finally(function () { refreshing = false; });
  }

  function start() {
    if (sessionToken) {
      input.focus();
      refresh();
      return;
    }
    if (starting) return;
    status.textContent = "Connecting…";
    starting = fetch(endpoint + "/sessions", { method: "POST", credentials: "omit" })
      .then(readJson)
      .then(function (data) {
        sessionToken = data.session_token;
        add(data.welcome_message, "ATLAS");
        status.textContent = "";
        input.disabled = false;
        if (!panel.hidden) input.focus();
      })
      .catch(function () {
        status.textContent = "Chat is temporarily unavailable. Reopen chat to try again.";
      })
      .finally(function () { starting = null; });
  }

  toggle.onclick = function () {
    panel.hidden = !panel.hidden;
    toggle.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) start();
  };

  input.oninput = function () {
    if (pendingMessage && pendingMessage.message !== input.value.trim()) pendingMessage = null;
    send.disabled = sending || !input.value.trim();
  };

  form.onsubmit = function (event) {
    event.preventDefault();
    var message = input.value.trim();
    if (!message || !sessionToken || sending) return;

    pendingMessage = pendingMessage || {
      message: message,
      client_message_id: globalThis.crypto?.randomUUID?.() || "m-" + Date.now() + "-" + Math.random().toString(36).slice(2)
    };
    sending = true;
    input.disabled = true;
    send.disabled = true;
    status.textContent = "Sending…";
    fetch(messagesUrl(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pendingMessage),
      credentials: "omit"
    })
      .then(readJson)
      .then(function () {
        pendingMessage = null;
        input.value = "";
        status.textContent = "";
        refresh();
      })
      .catch(function () { status.textContent = "Message could not be sent. Try again."; })
      .finally(function () {
        sending = false;
        input.disabled = false;
        send.disabled = !input.value.trim();
        if (!panel.hidden) input.focus();
      });
  };

  setInterval(refresh, 5000);
}());
