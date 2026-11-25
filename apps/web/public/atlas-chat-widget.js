(function () {
  "use strict";
  var script = document.currentScript;
  if (!script) return;
  var publicId = script.getAttribute("data-widget-id");
  if (!publicId) return;
  var apiBase = script.getAttribute("data-api-base") || "";
  var sessionToken = null;
  var conversationId = null;
  var renderedMessages = 0;
  var panel = document.createElement("aside");
  panel.setAttribute("aria-label", "Customer chat");
  panel.style.cssText = "position:fixed;right:20px;bottom:72px;width:320px;max-width:calc(100vw - 40px);background:#fff;color:#111;border:1px solid #ddd;border-radius:12px;box-shadow:0 8px 30px #0002;padding:12px;display:none;z-index:2147483646;font:14px system-ui";
  var log = document.createElement("div"); log.style.cssText = "height:240px;overflow:auto;margin-bottom:8px";
  var input = document.createElement("input"); input.placeholder = "Write a message"; input.style.cssText = "width:72%;padding:8px";
  var send = document.createElement("button"); send.textContent = "Send"; send.style.cssText = "margin-left:6px;padding:8px";
  panel.append(log, input, send); document.body.appendChild(panel);
  var toggle = document.createElement("button"); toggle.textContent = "Chat"; toggle.setAttribute("aria-label", "Open chat"); toggle.style.cssText = "position:fixed;right:20px;bottom:20px;border:0;border-radius:999px;background:#4f46e5;color:#fff;padding:12px 18px;z-index:2147483646"; document.body.appendChild(toggle);
  function base() { return apiBase.replace(/\/$/, "") + "/api/v1/widget/" + encodeURIComponent(publicId); }
  function add(text, direction, sender, status) { var p = document.createElement("p"); p.textContent = (direction === "outbound" ? (sender || "ATLAS") + ": " : "You: ") + text + (status && status !== "delivered" && status !== "received" ? " (" + status + ")" : ""); log.appendChild(p); log.scrollTop = log.scrollHeight; }
  function refresh() { if (!sessionToken) return; fetch(base() + "/sessions/" + encodeURIComponent(sessionToken) + "/messages", { method: "GET", credentials: "omit" }).then(function (r) { return r.ok ? r.json() : []; }).then(function (messages) { messages.slice(renderedMessages).forEach(function (message) { add(message.body, message.direction, message.sender, message.delivery_status); }); renderedMessages = messages.length; }).catch(function () {}); }
  function start() { if (sessionToken) return Promise.resolve(); return fetch(base() + "/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "omit" }).then(function (r) { if (!r.ok) throw new Error("Chat unavailable"); return r.json(); }).then(function (data) { sessionToken = data.session_token; conversationId = data.conversation_id; add(data.welcome_message, "outbound"); renderedMessages = 1; }); }
  toggle.onclick = function () { panel.style.display = panel.style.display === "none" ? "block" : "none"; if (panel.style.display === "block") start().catch(function () { add("Chat is temporarily unavailable.", "outbound"); }); };
  send.onclick = function () { var value = input.value.trim(); if (!value || !sessionToken) return; input.value = ""; var clientId = "m-" + Date.now() + "-" + Math.random().toString(36).slice(2); add(value, "inbound", "You", "sending"); fetch(base() + "/sessions/" + encodeURIComponent(sessionToken) + "/messages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: value, client_message_id: clientId }), credentials: "omit" }).catch(function () { add("Your message could not be sent.", "outbound", "ATLAS", "error"); }); };
  setInterval(refresh, 5000);
}());
