const API_BASE = "/api/v1";

const state = {
  ws: null,
  callId: null,
  sessionStatus: null,
  violations: [],
  actions: [],
  startTime: null,
};

const $ = (id) => document.getElementById(id);

const dom = {
  connectionStatus:   $("connection-status"),
  sessionsActive:     $("sessions-active"),
  sessionsCompleted:  $("sessions-completed"),
  btnRefresh:         $("btn-refresh"),
  eventsLog:          $("events-log"),
  callIdLabel:        $("call-id-label"),
  sCadet:             $("s-cadet"),
  sScenario:          $("s-scenario"),
  sDuration:          $("s-duration"),
  actionsList:        $("actions-list"),
  violationsList:     $("violations-list"),

  currentSessionLabel: $("current-session-label"),
  btnDownloadPdf:      $("btn-download-pdf"),
  btnCloseReview:      $("btn-close-review"),
};

function fmtTime(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function shortId(id) {
  return id ? id.slice(0, 8) : "—";
}

async function loadSessions() {
  try {
    const res = await fetch(`${API_BASE}/simulation/instructor/sessions`);
    const data = await res.json();
    renderSessions(data.active || [], data.completed || []);
    syncCurrentSessionStatus(data.active || [], data.completed || []);

    if (!state.ws && !state.callId && (data.active || []).length > 0) {
      const first = data.active[0];
      connectToSession(first.call_id, first);
    }
  } catch (e) {
    console.error("loadSessions:", e);
  }
}

function renderSessions(active, completed) {
  renderSessionGroup(dom.sessionsActive, active, "Нет активных звонков", false);
  renderSessionGroup(dom.sessionsCompleted, completed, "Пока ничего не завершено", true);
}

function syncCurrentSessionStatus(active, completed) {
  if (!state.callId) return;
  const all = [...active, ...completed];
  const cur = all.find((s) => s.call_id === state.callId);
  if (!cur) return;
  if (cur.status !== state.sessionStatus) {
    state.sessionStatus = cur.status;
    updatePdfButton();
  }
}

function updatePdfButton() {
  if (!dom.btnDownloadPdf) return;
  const canDownload =
    !!state.callId && state.sessionStatus === "completed";
  dom.btnDownloadPdf.disabled = !canDownload;
}

function renderSessionGroup(container, sessions, emptyText, isCompleted) {
  if (!sessions.length) {
    container.innerHTML = `<div class="empty">${emptyText}</div>`;
    return;
  }

  container.innerHTML = "";
  sessions.forEach((s) => {
    const div = document.createElement("div");
    div.className = "session-item";
    if (isCompleted) div.classList.add("completed");
    if (s.call_id === state.callId) div.classList.add("active");

    let meta = `курсант #${s.cadet_id} · ${fmtTime(s.duration_sec)}`;
    if (isCompleted) {
      meta += ` · нарушений: ${s.violations_count}`;
    }
    meta += ` · id ${shortId(s.call_id)}`;

    div.innerHTML = `
      <span class="session-scenario">${s.scenario_title || s.scenario_id}</span>
      <span class="session-meta">${meta}</span>
    `;
    div.addEventListener("click", () => connectToSession(s.call_id, s));
    container.appendChild(div);
  });
}

function connectToSession(callId, sessionMeta) {

  if (state.callId === callId && state.ws && state.ws.readyState === WebSocket.OPEN) {
    return;
  }

  if (state.ws) {
    try { state.ws.close(); } catch (_) {}
    state.ws = null;
  }

  if (dom.currentSessionLabel) {
    dom.currentSessionLabel.textContent = `Сессия: ${shortId(callId)}`;
  }
  if (dom.btnCloseReview) {
    dom.btnCloseReview.disabled = false;
  }

  state.callId = callId;
  state.sessionStatus = sessionMeta ? sessionMeta.status : null;
  state.violations = [];
  state.actions = [];
  state.startTime = sessionMeta ? new Date(sessionMeta.started_at) : new Date();
  updatePdfButton();

  dom.callIdLabel.textContent = `· ${shortId(callId)}`;
  dom.sCadet.textContent = sessionMeta ? `#${sessionMeta.cadet_id}` : "—";
  dom.sScenario.textContent = sessionMeta ? (sessionMeta.scenario_title || sessionMeta.scenario_id) : "—";
  dom.eventsLog.innerHTML = "";
  dom.violationsList.innerHTML = '<div class="empty">Нарушений нет</div>';
  dom.actionsList.innerHTML = '<div class="empty">—</div>';

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/instructor/${callId}`;

  try {
    const ws = new WebSocket(url);
    state.ws = ws;

    ws.addEventListener("open", () => {
      dom.connectionStatus.textContent = "Подключено";
      dom.connectionStatus.className = "instr-status connected";
    });

    ws.addEventListener("message", (ev) => {
      try {
        const data = JSON.parse(ev.data);
        handleWsMessage(data);
      } catch (e) {
        console.error("Не удалось распарсить сообщение WS:", e);
      }
    });

    ws.addEventListener("close", () => {
      dom.connectionStatus.textContent = "Отключено";
      dom.connectionStatus.className = "instr-status";
    });

    ws.addEventListener("error", () => {
      dom.connectionStatus.textContent = "Ошибка подключения";
      dom.connectionStatus.className = "instr-status error";
    });
  } catch (e) {
    console.error("WebSocket error:", e);
    dom.connectionStatus.textContent = "Ошибка: " + e.message;
    dom.connectionStatus.className = "instr-status error";
  }
}

function handleWsMessage(data) {

  if (data.type === "history") {
    (data.events || []).forEach(renderEvent);
    return;
  }

  if (data.type) {
    renderEvent(data);
  }
}

function renderEvent(evt) {
  const type = evt.type || "unknown";
  const payload = evt.payload || {};
  const atSec = evt.at_sec != null ? fmtTime(evt.at_sec) : "—";

  if (evt.at_sec != null) {
    dom.sDuration.textContent = fmtTime(evt.at_sec);
  }

  const row = document.createElement("div");
  row.className = `event-row evt-${type}`;

  const summary = summarizeEvent(type, payload);

  row.innerHTML = `
    <span class="event-time">${atSec}</span>
    <span class="event-type">${type}</span>
    <span class="event-payload">${summary}</span>
  `;

  dom.eventsLog.appendChild(row);
  dom.eventsLog.scrollTop = dom.eventsLog.scrollHeight;

  if (type === "dispatcher_speech") {
    addAction(`Реплика: «${payload.text || ""}»`);
  } else if (type === "service_activated") {
    addAction(`Оповещена служба: ${payload.service || ""}`);
  } else if (type === "card_field_updated") {
    addAction(`Карточка: ${payload.field} = ${payload.value}`);
  } else if (type === "violation_detected") {
    addViolation(payload);
  }
}

function summarizeEvent(type, payload) {
  switch (type) {
    case "call_started":
      return `Сессия создана: ${payload.scenario || ""}`;
    case "caller_speech":
      return `Заявитель: «${payload.text || ""}»`;
    case "dispatcher_speech":
      return `Диспетчер: «${payload.text || ""}»`;
    case "card_field_updated":
      return `${payload.field} = ${payload.value}`;
    case "service_activated":
      return `Служба: ${payload.service}`;
    case "violation_detected":
      return `${payload.type} (sev ${payload.severity}): ${payload.description}`;
    case "trigger_detected":
      return `Триггер: ${payload.key} (${payload.phrase})`;
    case "call_ended":
      return `Звонок завершён: ${payload.reason || ""}`;
    default:
      return JSON.stringify(payload).slice(0, 200);
  }
}

function addAction(text) {
  if (state.actions.length === 0) {
    dom.actionsList.innerHTML = "";
  }
  state.actions.push(text);

  const div = document.createElement("div");
  div.className = "action-row";
  div.textContent = text;
  dom.actionsList.appendChild(div);
  dom.actionsList.scrollTop = dom.actionsList.scrollHeight;
}

function addViolation(v) {
  if (state.violations.length === 0) {
    dom.violationsList.innerHTML = "";
  }
  state.violations.push(v);

  const sev = v.severity;
  const cls = sev === 4 || sev === "4" ? "sev-critical"
            : sev === 3 || sev === "3" ? "sev-high"
            : "";

  const div = document.createElement("div");
  div.className = `violation ${cls}`;
  div.innerHTML = `
    <span class="violation-type">${v.type || "unknown"}</span>
    ${v.description || ""}
  `;
  dom.violationsList.appendChild(div);
}

async function downloadReportPdf() {
  if (!state.callId) return;
  try {
    const res = await fetch(
      `${API_BASE}/simulation/${state.callId}/report.pdf`
    );
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`${res.status}: ${t}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `report_${state.callId}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error("downloadReportPdf:", e);
    alert("Не удалось скачать PDF: " + e.message);
  }
}

async function closeReview() {
  if (!state.callId) return;

  const confirmed = confirm(
    `Закрыть разбор сессии ${shortId(state.callId)}?\n` +
    `Сессия будет удалена из памяти.`
  );
  if (!confirmed) return;

  try {
    const res = await fetch(`${API_BASE}/simulation/${state.callId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    if (state.ws) {
      state.ws.close();
      state.ws = null;
    }
    state.callId = null;
    state.sessionStatus = null;
    state.violations = [];
    state.actions = [];
    updatePdfButton();

    dom.callIdLabel.textContent = "";
    dom.currentSessionLabel.textContent = "Сессия не выбрана";
    dom.btnCloseReview.disabled = true;
    dom.eventsLog.innerHTML = '<div class="empty">Сессия закрыта. Выберите другую.</div>';
    dom.violationsList.innerHTML = '<div class="empty">Нарушений нет</div>';
    dom.actionsList.innerHTML = '<div class="empty">—</div>';
    dom.sCadet.textContent = "—";
    dom.sScenario.textContent = "—";
    dom.sDuration.textContent = "00:00";

    loadSessions();
  } catch (e) {
    console.error("closeReview:", e);
    alert("Не удалось закрыть разбор: " + e.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  dom.btnRefresh.addEventListener("click", loadSessions);

  if (dom.btnDownloadPdf) {
    dom.btnDownloadPdf.addEventListener("click", downloadReportPdf);
  }

  if (dom.btnCloseReview) {
    dom.btnCloseReview.addEventListener("click", closeReview);
  }

  loadSessions();

  setInterval(loadSessions, 5000);
});