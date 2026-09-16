"use strict";
const $ = id => document.getElementById(id);
let items = [], current = null, busy = false, commentTimer, toastTimer;
const complete = item => Boolean(item.meaning_preserved && item.naturalness);
const matches = item => {
  switch ($("filter").value) {
    case "unreviewed": return !complete(item);
    case "meaning_ng": return item.meaning_preserved === "NG";
    case "naturalness_ng": return item.naturalness === "NG";
    case "any_ng": return item.meaning_preserved === "NG" || item.naturalness === "NG";
    default: return true;
  }
};
const filtered = () => items.filter(matches);
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "通信に失敗しました");
  return data;
}
function error(error) { $("error").textContent = error.message; $("error").hidden = false; }
function lock(value) {
  busy = value;
  document.querySelectorAll("button, select, textarea, #auto-next").forEach(element => element.disabled = value);
  if (!value) navigation();
}
function navigation() {
  const list = filtered(), index = list.findIndex(item => item.instance_id === current?.instance_id);
  $("count").textContent = `${list.length} 件`;
  $("position").textContent = index >= 0 ? `${index + 1} / ${list.length}` : "";
  $("previous").disabled = busy || index <= 0;
  $("next").disabled = busy || index < 0 || index >= list.length - 1;
  $("jump").disabled = busy || !items.some(item => !complete(item));
}
function overview() {
  const reviewed = items.filter(complete).length;
  $("progress-label").textContent = `${reviewed} / ${items.length} 判定済み`;
  $("progress").max = items.length || 1;
  $("progress").value = reviewed;
  $("completion").textContent = items.length && reviewed === items.length ? "すべての判定が完了しました" : "";
  const counts = {all: items.length, unreviewed: items.length - reviewed,
    meaning_ng: items.filter(i => i.meaning_preserved === "NG").length,
    naturalness_ng: items.filter(i => i.naturalness === "NG").length,
    any_ng: items.filter(i => i.meaning_preserved === "NG" || i.naturalness === "NG").length};
  const labels = {all: "すべて", unreviewed: "未判定", meaning_ng: "意味NG", naturalness_ng: "不自然", any_ng: "NG全部"};
  for (const option of $("filter").options) option.textContent = `${labels[option.value]} (${counts[option.value]})`;
  navigation();
}
function reviewState() {
  document.querySelectorAll("button[data-field]").forEach(button => {
    button.setAttribute("aria-pressed", String(Boolean(button.dataset.value) && current[button.dataset.field] === button.dataset.value));
  });
  $("reviewed-at").textContent = current.reviewed_at ? `最終保存：${new Date(current.reviewed_at).toLocaleString("ja-JP")}` : "まだ判定されていません";
}
function render() {
  $("card").hidden = !current; $("empty").hidden = Boolean(current);
  if (!current) { navigation(); return; }
  $("number").textContent = `#${String(current.number).padStart(2, "0")}`;
  $("instance-id").textContent = current.instance_id;
  $("original").replaceChildren(); $("rewritten").replaceChildren();
  for (const part of current.diff) {
    for (const side of ["original", "rewritten"]) {
      if (!part[side]) continue;
      const node = document.createElement(part.type === "equal" ? "span" : side === "original" ? "del" : "ins");
      node.textContent = part[side]; $(side).append(node);
    }
  }
  $("reference").replaceChildren();
  for (const [key, value] of Object.entries(current.reference)) {
    const term = document.createElement("dt"), description = document.createElement("dd");
    term.textContent = key; description.textContent = value || "（空欄）";
    $("reference").append(term, description);
  }
  $("comment").value = current.review_comment;
  reviewState(); navigation();
}
async function load(id) {
  const next = id ? await api(`/api/items/${encodeURIComponent(id)}`) : null;
  current = next; render();
}
async function persist(changes) {
  $("save-status").textContent = "保存中…";
  const result = await api(`/api/items/${encodeURIComponent(current.instance_id)}/review`, {
    method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(changes)
  });
  current = result.item;
  Object.assign(items.find(item => item.instance_id === current.instance_id), {
    meaning_preserved: current.meaning_preserved, naturalness: current.naturalness
  });
  $("save-status").textContent = "保存済み";
  $("error").hidden = true;
  reviewState(); overview();
  $("toast").textContent = "保存しました"; $("toast").hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").hidden = true, 1800);
}
async function flushComment() {
  clearTimeout(commentTimer);
  if (current && $("comment").value !== current.review_comment) await persist({review_comment: $("comment").value});
}
async function action(fn) {
  if (busy) return;
  lock(true);
  try { await fn(); }
  catch (failure) { $("save-status").textContent = "未保存 / エラー"; error(failure); }
  finally { lock(false); }
}
function nextUnreviewed() {
  const index = items.findIndex(item => item.instance_id === current?.instance_id);
  return [...items.slice(index + 1), ...items.slice(0, index + 1)].find(item => !complete(item));
}
async function judge(field, value) {
  if (busy || !current) return;
  const button = document.querySelector(`button[data-field="${field}"][data-value="${value}"]`);
  const label = button.innerHTML;
  button.textContent = "保存中…";
  await action(async () => {
    clearTimeout(commentTimer);
    const wasComplete = complete(current), oldNumber = current.number;
    const changes = {[field]: value};
    if ($("comment").value !== current.review_comment) changes.review_comment = $("comment").value;
    await persist(changes);
    if ($("auto-next").checked && !wasComplete && complete(current)) {
      const next = nextUnreviewed();
      if (next) { $("filter").value = "all"; previousFilter = "all"; await load(next.instance_id); return; }
    }
    if (!matches(current)) {
      const list = filtered();
      await load((list.find(item => item.number > oldNumber) || list[list.length - 1])?.instance_id);
    }
  });
  button.innerHTML = label;
}
document.querySelectorAll("button[data-field]").forEach(button => button.addEventListener("click", () => judge(button.dataset.field, button.dataset.value)));
$("comment").addEventListener("input", () => {
  $("save-status").textContent = "未保存…";
  clearTimeout(commentTimer); commentTimer = setTimeout(() => action(flushComment), 650);
});
for (const [id, offset] of [["previous", -1], ["next", 1]]) {
  $(id).addEventListener("click", () => action(async () => {
    await flushComment();
    const list = filtered(), index = list.findIndex(item => item.instance_id === current?.instance_id);
    if (list[index + offset]) await load(list[index + offset].instance_id);
  }));
}
let previousFilter = "all";
$("filter").addEventListener("change", () => action(async () => {
  try { await flushComment(); } catch (failure) { $("filter").value = previousFilter; throw failure; }
  previousFilter = $("filter").value;
  await load(filtered().find(item => item.instance_id === current?.instance_id)?.instance_id || filtered()[0]?.instance_id);
}));
$("jump").addEventListener("click", () => action(async () => {
  await flushComment(); const next = nextUnreviewed();
  if (next) { $("filter").value = "all"; previousFilter = "all"; await load(next.instance_id); }
}));
try { $("auto-next").checked = localStorage.getItem("auto-next") === "true"; } catch (_) {}
$("auto-next").addEventListener("change", () => { try { localStorage.setItem("auto-next", $("auto-next").checked); } catch (_) {} });
document.addEventListener("keydown", event => {
  if (busy || !current || event.ctrlKey || event.altKey || event.metaKey || event.isComposing || /INPUT|TEXTAREA|SELECT|BUTTON|SUMMARY/.test(event.target.tagName)) return;
  const shortcuts = {"1": ["meaning_preserved", "OK"], "2": ["meaning_preserved", "NG"], "3": ["naturalness", "OK"], "4": ["naturalness", "NG"]};
  if (shortcuts[event.key]) { event.preventDefault(); judge(...shortcuts[event.key]); }
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); $(event.key === "ArrowLeft" ? "previous" : "next").click(); }
});
window.addEventListener("beforeunload", event => {
  if (busy || (current && $("comment").value !== current.review_comment)) { event.preventDefault(); event.returnValue = ""; }
});
action(async () => {
  items = await api("/api/items"); overview(); await load(items[0]?.instance_id);
  $("save-status").textContent = "自動保存 ON";
});
