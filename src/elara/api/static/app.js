"use strict";
const $ = id => document.getElementById(id);
const launchToken = new URLSearchParams(location.hash.slice(1)).get("token");
if (launchToken) { sessionStorage.setItem("elaraToken", launchToken); history.replaceState(null, "", "/"); }
const token = sessionStorage.getItem("elaraToken") || "";
let active = null, busy = false, attached = [], loadVersion = 0;
function notice(message) { $("notice").textContent = message; $("notice").hidden = !message; }
async function api(path, options = {}) {
  const response = await fetch(`/api/${path}`, { ...options, headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json", ...options.headers } });
  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try { const parsed = JSON.parse(text); message = typeof parsed.detail === "string" ? parsed.detail : "Check your input: memory keys use lowercase letters, values are limited to 500 characters, and attachments to 16,000 characters."; } catch {}
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json();
}
function button(text, handler, className = "quiet") { const el = document.createElement("button"); el.type = "button"; el.className = className; el.textContent = text; el.onclick = handler; return el; }
function turn(role, content) {
  const el = document.createElement("article"); el.className = `turn ${role}`;
  const label = document.createElement("div"); label.className = "turn-label"; label.textContent = role === "user" ? "YOU" : "ELARA";
  const body = document.createElement("div"); body.className = "turn-content"; body.textContent = content;
  el.append(label, body); $("turns").append(el); $("welcome").hidden = true;
  $("messages").scrollTop = $("messages").scrollHeight; return el;
}
function setBusy(value) {
  busy = value;
  for (const id of ["send", "message", "new-chat", "delete-chat", "attach", "recall"]) $(id).disabled = value;
  $("send").textContent = value ? "Thinking…" : "Send ↑";
}
async function refreshSessions() {
  const items = await api("sessions"); $("sessions").replaceChildren(); $("session-count").textContent = items.length;
  for (const item of items) {
    const el = button(item.title, () => { if (!busy) openSession(item.id).catch(e => notice(e.message)); }, `session${item.id === active ? " active" : ""}`);
    el.title = item.title; if (item.id === active) el.setAttribute("aria-current", "page"); $("sessions").append(el);
  }
  return items;
}
async function openSession(id) {
  const version = ++loadVersion;
  const data = await api(`sessions/${id}`);
  if (version !== loadVersion || busy) return;
  active = id; attached = []; renderAttachments(); $("message").value = ""; $("turns").replaceChildren();
  $("welcome").hidden = data.turns.length > 0; $("delete-chat").hidden = false;
  $("chat-title").textContent = data.turns[0]?.content.slice(0, 64) || "A little space to think.";
  for (const item of data.turns) turn(item.role, item.content);
  notice(""); await refreshSessions();
}
$("new-chat").onclick = () => {
  if (busy) return; ++loadVersion; active = null; $("turns").replaceChildren(); $("welcome").hidden = false;
  $("delete-chat").hidden = true; $("chat-title").textContent = "A little space to think.";
  $("message").value = ""; attached = []; renderAttachments(); notice(""); refreshSessions().catch(e => notice(e.message)); $("message").focus();
};
$("delete-chat").onclick = async () => {
  if (!active || busy || !confirm("Delete this conversation? Memories, audit metadata, and backups are retained.")) return;
  try { await api(`sessions/${active}`, { method: "DELETE" }); $("new-chat").click(); } catch (e) { notice(e.message); }
};
$("composer").onsubmit = async event => {
  event.preventDefault(); const message = $("message").value.trim(); if (!message || busy) return;
  ++loadVersion; notice(""); setBusy(true); let userTurn, pending;
  try {
    if (!active) { const session = await api("sessions", { method: "POST" }); active = session.id; }
    userTurn = turn("user", message); pending = turn("assistant", "Taking a moment to think…"); pending.classList.add("pending");
    const answer = await api("chat", { method: "POST", body: JSON.stringify({ session_id: active, message, recall: $("recall").checked, attachments: attached }) });
    pending.remove(); pending = null; turn("assistant", answer.message); $("message").value = "";
    if ($("turns").children.length <= 2) $("chat-title").textContent = message.slice(0, 64);
    $("delete-chat").hidden = false;
    await refreshSessions().catch(e => notice(e.message));
  } catch (e) {
    pending?.remove(); userTurn?.remove(); notice(e.message + " Your draft is kept. If the connection dropped, reopen the conversation before retrying.");
    $("welcome").hidden = $("turns").children.length > 0;
  } finally { setBusy(false); $("message").focus(); }
};
$("message").onkeydown = event => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("composer").requestSubmit(); } };
for (const el of document.querySelectorAll("[data-prompt]")) el.onclick = () => { $("message").value = el.dataset.prompt; $("message").focus(); };
function renderAttachments() {
  $("attachments").replaceChildren();
  attached.forEach((file, index) => $("attachments").append(button(`${file.path} ×`, () => { if (!busy) { attached.splice(index, 1); renderAttachments(); } }, "file-chip")));
}
$("attach").onclick = () => $("file-input").click();
$("file-input").onchange = async event => {
  const files = [...event.target.files], version = loadVersion; event.target.value = "";
  try {
    const next = [...attached];
    for (const file of files) {
      if (!/\.(txt|md|csv|json|toml)$/i.test(file.name) || file.size > 65536) throw new Error("Choose UTF-8 text files up to 64 KiB (.txt, .md, .csv, .json, .toml).");
      const content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      next.push({ path: file.name, content });
    }
    if (next.length > 8 || next.reduce((n, f) => n + f.content.length, 0) > 16000) throw new Error("Attach up to eight files, totalling at most 16,000 characters.");
    if (busy || version !== loadVersion) return; attached = next; renderAttachments(); notice("Attachments are sent to local Ollama with each message here. Reselect a file to load edits; replies may quote its contents.");
  } catch (e) { notice(e.message); }
};
async function refreshMemories() {
  const facts = await api("memories"); $("memory-list").replaceChildren();
  if (!facts.length) { const empty = document.createElement("p"); empty.className = "muted"; empty.textContent = "A fresh start. Add something you'd like ELARA to remember."; $("memory-list").append(empty); }
  for (const fact of facts) {
    const card = document.createElement("div"); card.className = "memory-card";
    const key = document.createElement("strong"); key.textContent = fact.key;
    const value = document.createElement("p"); value.textContent = fact.value;
    const actions = document.createElement("div"); actions.className = "actions";
    actions.append(button("Edit", () => { $("memory-key").value = fact.key; $("memory-value").value = fact.value; $("memory-value").focus(); }), button("Forget", async () => {
      if (!confirm(`Forget '${fact.key}'? Earlier chats and backups are retained.`)) return;
      try { await api(`memories/${encodeURIComponent(fact.key)}`, { method: "DELETE" }); await refreshMemories(); } catch (e) { notice(e.message); }
    }, "quiet danger"));
    card.append(key, value, actions); $("memory-list").append(card);
  }
}
$("memory-toggle").onclick = () => { $("memory-panel").hidden = !$("memory-panel").hidden; if (!$("memory-panel").hidden) refreshMemories().catch(e => notice(e.message)); };
$("memory-close").onclick = () => { $("memory-panel").hidden = true; $("memory-toggle").focus(); };
$("memory-form").onsubmit = async event => {
  event.preventDefault();
  try { await api("memories", { method: "PUT", body: JSON.stringify({ key: $("memory-key").value.trim(), value: $("memory-value").value.trim() }) }); event.target.reset(); await refreshMemories(); notice(""); }
  catch (e) { notice(e.message); }
};
async function start() {
  try {
    const status = await api("status"); $("model-label").textContent = status.model || "Offline simulation";
    $("mode").textContent = status.provider === "mock" ? "SIMULATION" : "LOCAL OLLAMA";
    if (status.provider === "mock") { $("recall").checked = false; notice("Simulation mode: open with scripts/ui.ps1 for your local Ollama model."); }
    await refreshSessions();
  } catch (e) { notice(e.message); $("model-label").textContent = "Connection unavailable"; }
}
start();
