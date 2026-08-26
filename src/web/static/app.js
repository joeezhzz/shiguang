/* 拾光 · 看板前端逻辑 */
"use strict";

const TOPICS = ["学习方法", "考研保研", "竞赛", "生活小妙招", "就业赚钱", "其他"];
const PRIORITIES = ["高", "中", "低"];
const PERIODS = ["短期任务", "长期计划", "永久参考"];
const STATUSES = ["待处理", "进行中", "已完成", "已归档"];
const KIND_ICON = { text: "📝", image: "🖼", file: "📎" };

const state = {
  cards: [], q: "", topic: "", priority: "", period: "", status: "",
  mode: "status",        // status | topic
  view: "board",         // board | calendar
  ym: null,              // 日历当前年月 (Date)
  current: null,         // 弹窗中的卡片
};

const $ = (id) => document.getElementById(id);

/* ---------- 加载与过滤 ---------- */
async function load() {
  const r = await fetch("/api/cards");
  state.cards = await r.json();
  render();
}

function filtered() {
  const q = state.q.trim();
  return state.cards.filter((c) => {
    if (q) {
      const hay = [c.content, c.ocr_text, c.note, c.tags].filter(Boolean).join(" ");
      if (!hay.includes(q)) return false;
    }
    if (state.topic && c.topic !== state.topic) return false;
    if (state.priority && c.priority !== state.priority) return false;
    if (state.period && c.period !== state.period) return false;
    if (state.status && c.status !== state.status) return false;
    return true;
  });
}

function daysLeft(due) {
  if (!due) return null;
  const d = new Date(due + "T00:00:00");
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((d - today) / 86400000);
}

/* ---------- 卡片渲染 ---------- */
function cardHTML(c) {
  const dl = daysLeft(c.due_date);
  let dueTxt = "";
  let dueCls = "";
  if (dl !== null) {
    if (dl < 0) { dueTxt = `⏰ 已逾期 ${-dl} 天`; dueCls = "urgent"; }
    else if (dl === 0) { dueTxt = "⏰ 今天截止"; dueCls = "urgent"; }
    else if (dl <= 3) { dueTxt = `⏰ 剩 ${dl} 天`; dueCls = "soon"; }
    else { dueTxt = `⏰ 剩 ${dl} 天`; }
  }
  const tags = (c.tags || "").split(",").filter(Boolean)
    .map((t) => `<span class="tag">${esc(t)}</span>`).join("");
  const summary = c.main_point || (c.content || "").split("\n")[0];
  return `<div class="card pri-${esc(c.priority)}" data-id="${c.id}">
    <div class="card-top"><span>${KIND_ICON[c.kind] || "📝"} ${esc(c.source || "")}</span>
      <span>${esc((c.created_at || "").slice(5, 10))}</span></div>
    <div class="card-content">${esc(summary || (c.kind === "image" ? "[图片]" : "[文件]"))}</div>
    <div class="card-tags"><span class="tag topic">${esc(c.topic)}</span>${tags}</div>
    <div class="card-foot"><span class="due ${dueCls}">${dueTxt}</span>
      <span>${esc(c.period)}</span></div>
  </div>`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[m]));
}

/* ---------- 看板渲染 ---------- */
function renderBoard(list) {
  // 状态列固定 4 列；主题列用动态主题列表（内置 + 自定义）
  const groups = state.mode === "status" ? STATUSES : (topicList.length ? topicList : TOPICS);
  const by = {};
  groups.forEach((g) => (by[g] = []));
  list.forEach((c) => {
    const key = state.mode === "status" ? c.status : c.topic;
    (by[key] || (by[key] = [])).push(c);
  });
  $("board").innerHTML = groups
    .map((g) => `<div class="column"><h3><b>${g}</b><span>${(by[g] || []).length}</span></h3>
      <div class="cards">${(by[g] || []).map(cardHTML).join("")}</div></div>`)
    .join("");
}

/* ---------- 日历渲染 ---------- */
function renderCalendar(list) {
  const now = state.ym || new Date();
  const y = now.getFullYear(), m = now.getMonth();
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const byDue = {};
  list.forEach((c) => {
    if (c.due_date) (byDue[c.due_date] = byDue[c.due_date] || []).push(c);
    if (c.cal_date) (byDue[c.cal_date] = byDue[c.cal_date] || []).push(Object.assign({}, c, { _cal: true }));
  });
  const first = new Date(y, m, 1);
  const startWeekday = (first.getDay() + 6) % 7; // 周一开头
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startWeekday; i++) cells.push(`<div class="cal-cell other"></div>`);
  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(y, m, d);
    const iso = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const isToday = date.getTime() === today.getTime();
    const wd = date.getDay();
    const chips = (byDue[iso] || []).map((c) => {
      const dl = daysLeft(c.due_date);
      const cls = dl !== null && dl < 0 ? "overdue" : "";
      const tag = c._cal ? "📌 " : "";
      return `<div class="cal-chip ${cls}" data-id="${c.id}">${tag}${esc((c.content || "").split("\n")[0].slice(0, 14))}</div>`;
    }).join("");
    cells.push(`<div class="cal-cell ${wd === 0 || wd === 6 ? "weekend" : ""} ${isToday ? "today" : ""}">
      <div class="day">${d}</div>${chips}</div>`);
  }
  const title = `${y} 年 ${m + 1} 月`;
  $("board").innerHTML = `<div class="calendar-wrap">
    <div class="cal-head"><button id="cal-prev">‹</button><b>${title}</b><button id="cal-next">›</button></div>
    <div class="cal-grid"><div class="cal-cell"><div class="day">一</div></div><div class="cal-cell"><div class="day">二</div></div><div class="cal-cell"><div class="day">三</div></div><div class="cal-cell"><div class="day">四</div></div><div class="cal-cell"><div class="day">五</div></div><div class="cal-cell"><div class="day">六</div></div><div class="cal-cell"><div class="day">日</div></div>${cells.join("")}</div>
  </div>`;
  $("cal-prev").onclick = () => { state.ym = new Date(y, m - 1, 1); render(); };
  $("cal-next").onclick = () => { state.ym = new Date(y, m + 1, 1); render(); };
}

/* ---------- 渲染入口 ---------- */
function render() {
  const list = filtered();
  $("count").textContent = `${list.length} / ${state.cards.length} 条`;
  if (state.view === "calendar") {
    renderCalendar(list);
  } else {
    renderBoard(list);
  }
  // 卡片点击
  document.querySelectorAll(".card, .cal-chip").forEach((el) => {
    el.onclick = () => openModal(Number(el.dataset.id));
  });
}

/* ---------- 弹窗 ---------- */
function renderBranches(c) {
  let html = "";
  if (c.main_point) {
    html += `<div class="kv"><span>主观点</span><span class="main-point">${esc(c.main_point)}</span></div>`;
  }
  if (c.branches) {
    try {
      const brs = JSON.parse(c.branches);
      if (Array.isArray(brs) && brs.length) {
        html += `<div class="kv"><span>分支</span><span class="branches">` + brs.map((b) => {
          if (b.type === "qa") {
            return `<div class="br qa"><div class="br-q">❓ ${esc(b.q)}</div><div class="br-a">💡 ${esc(b.a)}</div></div>`;
          }
          return `<div class="br note"><div class="br-q">📌 ${esc(b.label || "补充")}</div><div class="br-a">${esc(b.text)}</div></div>`;
        }).join("") + `</span></div>`;
      }
    } catch (e) { /* 忽略损坏 JSON */ }
  }
  return html;
}

/* ---------- 详情编辑 ---------- */
let editing = false;
let topicList = [];

async function loadTopics() {
  const r = await fetch("/api/topics");
  topicList = await r.json();
  // 同步刷新主题过滤器下拉（含自定义主题），保持当前选中
  const cur = $("f-topic").value;
  $("f-topic").innerHTML = `<option value="">全部主题</option>`
    + topicList.map((t) => `<option>${t}</option>`).join("");
  $("f-topic").value = cur;
  render();  // 主题列模式需要动态主题列表（自定义主题才有自己的列）
}

function editModal() {
  const c = state.current;
  if (!c) return;
  editing = true;
  $("m-edit").textContent = "查看";
  const opts = (cur, arr) => arr
    .map((x) => `<option ${x === cur ? "selected" : ""}>${x}</option>`).join("");
  $("m-body").innerHTML = `
    <div class="kv"><span>主题</span><input id="e-topic" list="sg-topics" value="${esc(c.topic)}">
      <datalist id="sg-topics">${topicList.map((t) => `<option value="${esc(t)}">`).join("")}</datalist></div>
    <div class="kv"><span>重要度</span><select id="e-priority">${opts(c.priority, PRIORITIES)}</select></div>
    <div class="kv"><span>效用期</span><select id="e-period">${opts(c.period, PERIODS)}</select></div>
    <div class="kv"><span>截止日期</span><input id="e-due" type="date" value="${esc(c.due_date || "")}"></div>
    <div class="kv"><span>日历日期</span><input id="e-cal" type="date" value="${esc(c.cal_date || "")}"></div>
    <div class="kv"><span>提醒</span><select id="e-remind">
      <option value="" ${c.remind_days == null ? "selected" : ""}>跟随默认</option>
      <option value="0" ${c.remind_days === 0 ? "selected" : ""}>到期当天</option>
      <option value="1" ${c.remind_days === 1 ? "selected" : ""}>提前1天</option>
      <option value="3" ${c.remind_days === 3 ? "selected" : ""}>提前3天</option>
      <option value="7" ${c.remind_days === 7 ? "selected" : ""}>提前7天</option>
      <option value="-1" ${c.remind_days === -1 ? "selected" : ""}>不提醒</option>
    </select></div>
    <div class="kv"><span>备注</span><textarea id="e-note" rows="3">${esc(c.note || "")}</textarea></div>
    <div class="edit-actions">
      <button id="e-save">💾 保存修改</button>
      <button id="e-cancel">取消</button>
    </div>`;
  $("e-save").onclick = saveEdit;
  $("e-cancel").onclick = () => openModal(c.id);
}

async function saveEdit() {
  const c = state.current;
  if (!c) return;
  const fields = {
    topic: $("e-topic").value.trim() || "其他",
    priority: $("e-priority").value,
    period: $("e-period").value,
    due_date: $("e-due").value || null,
    cal_date: $("e-cal").value || null,
    remind_days: $("e-remind").value === "" ? null : parseInt($("e-remind").value, 10),
    note: $("e-note").value.trim() || null,
  };
  const r = await fetch(`/api/cards/${c.id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  const d = await r.json();
  Object.assign(c, d.card);
  loadTopics();          // 可能新增了自定义主题
  openModal(c.id);       // 回查看模式
}

function openModal(id) {
  const c = state.cards.find((x) => x.id === id);
  if (!c) return;
  state.current = c;
  editing = false;
  $("m-edit").textContent = "✏️ 编辑";
  $("m-title").textContent = `卡片 #${c.id} · ${c.topic}`;
  const dl = daysLeft(c.due_date);
  const dueTxt = dl === null ? "无" : (dl < 0 ? `${-dl} 天前已到期` : (dl === 0 ? "今天到期" : `剩 ${dl} 天`));
  const img = c.kind === "image" && c.media_path
    ? `<img class="zoomable" src="/media/${c.media_path.replace(/^media[\\/]/, "")}" alt="media" title="点击放大">` : "";
  const file = c.kind === "file" && c.media_path
    ? `<div class="kv"><span>文件</span><span>${esc(c.media_path)}</span></div>` : "";
  const branchesHtml = renderBranches(c);
  const isChat = !!c.main_point;
  const contentHtml = isChat
    ? `<details class="raw"><summary>查看原始聊天记录</summary><pre>${esc(c.content || "")}</pre></details>`
    : `<div class="kv"><span>内容</span><span style="white-space:pre-wrap">${esc(c.content || "（无文本）")}</span></div>`;
  $("m-body").innerHTML = `
    ${branchesHtml}
    ${contentHtml}
    ${img}${file}
    ${c.ocr_text ? `<div class="kv"><span>OCR</span><span class="ocr">${esc(c.ocr_text)}</span></div>` : ""}
    <div class="kv"><span>主题</span><span>${esc(c.topic)}</span></div>
    <div class="kv"><span>重要度</span><span>${esc(c.priority)}</span></div>
    <div class="kv"><span>效用期</span><span>${esc(c.period)}</span></div>
    <div class="kv"><span>截止</span><span>${esc(c.due_date || "无")}（${dueTxt}）</span></div>
    ${c.cal_date ? `<div class="kv"><span>日历</span><span>📌 ${esc(c.cal_date)}</span></div>` : ""}
    ${c.remind_days != null ? `<div class="kv"><span>提醒</span><span>${c.remind_days < 0 ? "不提醒" : `提前 ${c.remind_days} 天`}</span></div>` : ""}
    <div class="kv"><span>来源</span><span>${esc(c.source)}</span></div>
    <div class="kv"><span>创建</span><span>${esc(c.created_at)}</span></div>
    ${c.note ? `<div class="kv"><span>备注</span><span>${esc(c.note)}</span></div>` : ""}`;
  $("m-status").innerHTML = STATUSES.map((s) => `<option ${s === c.status ? "selected" : ""}>${s}</option>`).join("");
  $("modal").classList.remove("hidden");
  // 图片点击放大
  const imgEl = $("m-body").querySelector("img.zoomable");
  if (imgEl) imgEl.onclick = () => openLightbox(imgEl.src);
}

function closeModal() { $("modal").classList.add("hidden"); state.current = null; }

/* 图片放大预览 */
function openLightbox(src) {
  $("lightbox-img").src = src;
  $("lightbox").classList.remove("hidden");
}
function closeLightbox() {
  $("lightbox").classList.add("hidden");
}

async function patchCurrent(fields) {
  const c = state.current;
  if (!c) return;
  await fetch(`/api/cards/${c.id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  Object.assign(c, fields);
  closeModal();
  render();
}

/* ---------- 事件绑定 ---------- */
function bind() {
  $("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });
  ["topic", "priority", "period", "status"].forEach((k) => {
    $(`f-${k}`).addEventListener("change", (e) => { state[k] = e.target.value; render(); });
  });
  $("sw-status").onclick = () => { state.mode = "status"; state.view = "board"; syncSwitch(); render(); };
  $("sw-topic").onclick = () => { state.mode = "topic"; state.view = "board"; syncSwitch(); render(); };
  $("sw-calendar").onclick = () => { state.view = "calendar"; syncSwitch(); render(); };
  $("m-close").onclick = closeModal;
  $("lightbox").onclick = closeLightbox;
  $("m-edit").onclick = () => { if (editing) openModal(state.current.id); else editModal(); };
  $("modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
  $("m-status").addEventListener("change", (e) => patchCurrent({ status: e.target.value }));
  $("m-del").onclick = async () => {
    if (!confirm("确认删除这张卡片？")) return;
    await fetch(`/api/cards/${state.current.id}`, { method: "DELETE" });
    state.cards = state.cards.filter((c) => c.id !== state.current.id);
    closeModal();
    render();
  };
}

function syncSwitch() {
  $("sw-status").classList.toggle("active", state.view === "board" && state.mode === "status");
  $("sw-topic").classList.toggle("active", state.view === "board" && state.mode === "topic");
  $("sw-calendar").classList.toggle("active", state.view === "calendar");
}

function initSelects() {
  $("f-topic").innerHTML = `<option value="">全部主题</option>` + TOPICS.map((t) => `<option>${t}</option>`).join("");
  $("f-priority").innerHTML = `<option value="">全部重要度</option>` + PRIORITIES.map((p) => `<option>${p}</option>`).join("");
  $("f-period").innerHTML = `<option value="">全部效用期</option>` + PERIODS.map((p) => `<option>${p}</option>`).join("");
  $("f-status").innerHTML = `<option value="">全部状态</option>` + STATUSES.map((s) => `<option>${s}</option>`).join("");
}

initSelects();
bind();
loadTopics();
load();
