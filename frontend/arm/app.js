const API_BASE = "/api/v1";
const TICK_MS = 1000;

// Набор кнопок служб (для UI). Значения совпадают с ServiceType в схеме.
const SERVICES = [
  { value: "fire",      label: "МЧС (Пожарная)",       code: "101" },
  { value: "police",    label: "Полиция",               code: "102" },
  { value: "ambulance", label: "Скорая помощь",         code: "103" },
  { value: "gkh",       label: "ДДС района (ГКХ)",      code: "—"   },
  { value: "gas",       label: "Аварийная газовая",     code: "104" },
  { value: "metro",     label: "Метрополитен",          code: "—"   },
  { value: "lift",      label: "Мослифт",               code: "—"   },
  { value: "water",     label: "Мосводоканал",          code: "—"   },
  { value: "heat",      label: "МОЭК (отопление)",      code: "—"   },
  { value: "power",     label: "МОЭС (электричество)", code: "—"   },
  { value: "roads",     label: "Дорожные службы",       code: "—"   },
];

// Состояние сессии
const state = {
  callId: null,
  active: false,
  timerSec: 0,
  timerHandle: null,
  card: {},
  lastReport: null,
  violationsSeen: new Set(),
  violationCount: 0,

  // Голосовой режим
  inputMode: "text",     // "text" или "voice"
  callWs: null,          // WebSocket для голосового канала
  callWsReady: false,
  mediaStream: null,
  audioContext: null,
  audioWorkletNode: null,
  mediaSource: null,
  isRecording: false,
};

// ============================================================================
// DOM — ссылки
// ============================================================================

const $ = (id) => document.getElementById(id);

const dom = {
  callStatus:      $("call-status"),
  timer:           $("timer"),
  phoneTimer:      $("phone-timer"),
  phoneCaller:     $("phone-caller"),
  btnAccept:       $("btn-accept"),
  btnEnd:          $("btn-end"),
  cadetName:       $("cadet-name"),
  dialogLog:       $("dialog-log"),
  dispatcherText:  $("dispatcher-text"),
  btnSend:         $("btn-send"),
  scenarioSelect:  $("scenario-select"),
  servicesList:    $("services-list"),
  violationsList:  $("violations-list"),
  metricProtocol:  $("metric-protocol"),
  metricProtocolBar: $("metric-protocol-bar"),
  metricPanic:     $("metric-panic"),
  metricPanicBar:  $("metric-panic-bar"),
  metricCompliance:$("metric-compliance"),
  metricComplianceBar: $("metric-compliance-bar"),
  violationsBadge: $("violations-badge"),
  btnSaveCard:     $("btn-save-card"),
  btnCloseCard:    $("btn-close-card"),

  // Поля карточки
  card: {
    callerFio:          $("card-caller-fio"),
    callerRole:         $("card-caller-role"),
    callerPhone:        $("card-caller-phone"),
    address:            $("card-address"),
    whatHappened:       $("card-what-happened"),
    victims:            $("card-victims"),
    threat:             $("card-threat"),
    signL1:             $("card-sign-l1"),
    signL2:             $("card-sign-l2"),
    signL3:             $("card-sign-l3"),
    classificationId:   $("card-classification-id"),
    classificationName: $("card-classification-name"),
  },

  // Модалка отчёта
  reportModal:       $("report-modal"),
  reportGradeCircle: $("report-grade-circle"),
  reportGradeValue:  $("report-grade-value"),
  reportGradeLabel:  $("report-grade-label"),
  reportGradeSub:    $("report-grade-sub"),
  reportMetrics:     $("report-metrics"),
  reportViolations:  $("report-violations"),
  reportTimeline:    $("report-timeline"),

  // Голосовой режим
  inputTextMode:  document.querySelector(".input-text-mode"),
  inputVoiceMode: document.querySelector(".input-voice-mode"),
  btnVoice:       $("btn-voice"),
  voiceStatus:    $("voice-status"),
};

// ============================================================================
// УТИЛИТЫ
// ============================================================================

function fmtTime(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${m}:${s}`;
}

async function api(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);

  const res = await fetch(API_BASE + path, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${method} ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

// ============================================================================
// UI — ОТРИСОВКА
// ============================================================================

function renderServices() {
  dom.servicesList.innerHTML = "";
  SERVICES.forEach((svc) => {
    const btn = document.createElement("button");
    btn.className = "service-btn";
    btn.dataset.service = svc.value;
    btn.disabled = true;
    btn.innerHTML = `
      <span>${svc.label}</span>
      <span class="status-badge">${svc.code}</span>
    `;
    btn.addEventListener("click", () => activateService(svc.value, btn));
    dom.servicesList.appendChild(btn);
  });
}

function setServicesEnabled(enabled) {
  document.querySelectorAll(".service-btn").forEach((btn) => {
    if (!btn.classList.contains("activated")) {
      btn.disabled = !enabled;
    }
  });
}

function addDialogMessage(role, text, atSec) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const meta = document.createElement("span");
  meta.className = "msg-meta";
  meta.textContent = `[${fmtTime(atSec)}] ${role === "caller" ? "Заявитель" : "Диспетчер"}`;
  const body = document.createElement("div");
  body.textContent = text;
  div.appendChild(meta);
  div.appendChild(body);
  dom.dialogLog.appendChild(div);
  dom.dialogLog.scrollTop = dom.dialogLog.scrollHeight;
}

function renderViolations(violations) {
  if (!violations || violations.length === 0) {
    dom.violationsList.innerHTML = '<div class="empty-state">Нарушений нет</div>';
    updateViolationsBadge(0);
    return;
  }

  let hasNewCritical = false;
  violations.forEach((v) => {
    const key = `${v.type}:${v.detected_at_sec ?? 0}:${v.related_field || ""}`;
    if (state.violationsSeen.has(key)) return;
    state.violationsSeen.add(key);
    if (Number(v.severity) >= 3) hasNewCritical = true;
  });

  state.violationCount = violations.length;
  updateViolationsBadge(state.violationCount);

  dom.violationsList.innerHTML = "";
  violations.forEach((v) => {
    const sev = Number(v.severity);
    const cls = sev >= 4 ? "sev-critical" : sev >= 3 ? "sev-high" : "";
    const div = document.createElement("div");
    div.className = `violation ${cls}`;
    div.innerHTML = `
      <span class="violation-type">${v.type}</span>
      ${v.description}
    `;
    dom.violationsList.appendChild(div);
  });

  if (hasNewCritical) {
    dom.violationsList.classList.remove("pulse");
    void dom.violationsList.offsetWidth;
    dom.violationsList.classList.add("pulse");
    setTimeout(() => dom.violationsList.classList.remove("pulse"), 1600);
  }
}

function updateViolationsBadge(n) {
  if (!dom.violationsBadge) return;
  dom.violationsBadge.textContent = n;
  dom.violationsBadge.classList.toggle("zero", n === 0);
}

function updateMetrics(turn) {
  if (!turn) return;

  if (turn.protocol_adherence) {
    setMetric("protocol", turn.protocol_adherence.percent, 100, false);
  }
  if (typeof turn.panic_index === "number") {
    setMetric("panic", turn.panic_index, 100, true);
  }
  if (typeof turn.compliance_index === "number") {
    setMetric("compliance", turn.compliance_index, 100, false);
  }
}

function setMetric(key, value, max, invert) {
  const elVal = document.getElementById(`metric-${key}`);
  const elBar = document.getElementById(`metric-${key}-bar`);
  if (!elVal || !elBar) return;

  elVal.textContent = value;

  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  elBar.style.width = pct + "%";

  elBar.classList.remove("good", "warn", "bad");
  let level;
  if (invert) {
    level = value >= 70 ? "bad" : value >= 40 ? "warn" : "good";
  } else {
    level = value >= 80 ? "good" : value >= 60 ? "warn" : "bad";
  }
  elBar.classList.add(level);
}

// ============================================================================
// ТАЙМЕР
// ============================================================================

function startTimer() {
  state.timerSec = 0;
  state.timerHandle = setInterval(() => {
    state.timerSec += 1;
    const t = fmtTime(state.timerSec);
    dom.timer.textContent = t;
    dom.phoneTimer.textContent = t;
  }, TICK_MS);
}

function stopTimer() {
  if (state.timerHandle) {
    clearInterval(state.timerHandle);
    state.timerHandle = null;
  }
}

// ============================================================================
// ВОЛНА (фейковая осциллограмма)
// ============================================================================

const waveCtx = document.getElementById("waveform").getContext("2d");
let wavePhase = 0;

function drawWave() {
  const c = waveCtx;
  const w = c.canvas.width;
  const h = c.canvas.height;

  c.fillStyle = "#1a2029";
  c.fillRect(0, 0, w, h);

  c.strokeStyle = state.active ? "#4a90c9" : "#3b4859";
  c.lineWidth = 2;
  c.beginPath();

  const mid = h / 2;
  for (let x = 0; x < w; x++) {
    const amp = state.active ? 15 + Math.sin(x * 0.05 + wavePhase) * 8 : 2;
    const y = mid + Math.sin(x * 0.1 + wavePhase) * amp * Math.random() * 0.5;
    if (x === 0) c.moveTo(x, y);
    else c.lineTo(x, y);
  }
  c.stroke();

  wavePhase += 0.15;
  requestAnimationFrame(drawWave);
}

// ============================================================================
// ГОЛОС ЗАЯВИТЕЛЯ
// ============================================================================

let _currentAudio = null;

function playAudioBase64(b64) {
  if (!b64) return;
  try {
    // Останавливаем предыдущее, если оно играет
    if (_currentAudio) {
      try {
        _currentAudio.pause();
        _currentAudio.currentTime = 0;
      } catch (_) { /* игнорируем */ }
      _currentAudio = null;
    }

    const audio = new Audio(`data:audio/wav;base64,${b64}`);
    _currentAudio = audio;

    const playPromise = audio.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch((e) => {
        // AbortError — это норма, когда мы сами прервали предыдущее
        if (e && e.name !== "AbortError") {
          console.warn("Не удалось воспроизвести голос заявителя:", e);
        }
      });
    }
  } catch (e) {
    console.error("Ошибка воспроизведения аудио:", e);
  }
}

// ============================================================================
// API-ДЕЙСТВИЯ
// ============================================================================

async function loadScenarios() {
  try {
    const res = await fetch(`${API_BASE}/simulation/scenarios`);
    const data = await res.json();
    const list = data.scenarios || [];

    const byTicket = new Map();
    list.forEach((sc) => {
      if (!byTicket.has(sc.ticket_number)) byTicket.set(sc.ticket_number, []);
      byTicket.get(sc.ticket_number).push(sc);
    });

    const select = dom.scenarioSelect;
    select.innerHTML = '<option value="">— выберите сценарий —</option>';

    const diffMark = { novice: "●○○", normal: "●●○", extreme: "●●●" };

    [...byTicket.keys()].sort((a, b) => a - b).forEach((num) => {
      const group = document.createElement("optgroup");
      group.label = `Билет ${num}`;
      byTicket.get(num).forEach((sc) => {
        const opt = document.createElement("option");
        opt.value = sc.id;
        opt.textContent = `${diffMark[sc.difficulty] || ""}  Случай ${sc.case_number} — ${sc.situation}`;
        group.appendChild(opt);
      });
      select.appendChild(group);
    });
  } catch (e) {
    console.error("loadScenarios:", e);
  }
}

async function acceptCall() {
  // Защита от двойного клика
  if (state.active || state.callId) return;

  const sid = dom.scenarioSelect.value;
  if (!sid) {
    alert("Выберите сценарий из списка");
    return;
  }

  // Блокируем кнопку ДО запроса
  dom.btnAccept.disabled = true;
  dom.callStatus.textContent = "Соединение...";

  try {
    const res = await api("POST", "/simulation/start", {
      cadet_id: 1,
      cadet_name: dom.cadetName.value.trim() || null,
      scenario_id: sid,
      difficulty: "normal",
    });
    state.callId = res.call_id;
    state.active = true;

    dom.phoneCaller.textContent = "+7 (—)";
    dom.callStatus.textContent = "Звонок активен";
    dom.callStatus.classList.add("active");
    dom.btnEnd.disabled = false;
    dom.dispatcherText.disabled = false;
    dom.btnSend.disabled = false;
    dom.btnSaveCard.disabled = false;
    dom.btnCloseCard.disabled = false;

    // Открываем голосовой канал
    try {
      await openCallWs(state.callId);
      if (state.inputMode === "voice") {
        dom.btnVoice.disabled = false;
      }
    } catch (e) {
      console.error("Голосовой канал не поднялся:", e);
      dom.voiceStatus.textContent = "Голосовой канал недоступен";
    }

    setServicesEnabled(true);
    startTimer();

    if (res.opening_line) {
      addDialogMessage("caller", res.opening_line, 0);
    }
    if (res.opening_audio_b64) {
      playAudioBase64(res.opening_audio_b64);
    }
  } catch (e) {
    // При ошибке разблокируем кнопку назад
    dom.btnAccept.disabled = false;
    dom.callStatus.textContent = "Ожидание вызова";
    console.error(e);
    alert("Не удалось начать звонок: " + e.message);
  }
}

async function sendDispatcherSpeech() {
  const text = dom.dispatcherText.value.trim();
  if (!text || !state.active) return;

  dom.dispatcherText.value = "";
  addDialogMessage("dispatcher", text, state.timerSec);

  try {
    const res = await api("POST", "/simulation/step", {
      call_id: state.callId,
      dispatcher_text: text,
      duration_sec: 3.0,
    });
    const turn = res.turn;
    if (turn && turn.caller_response_text) {
      addDialogMessage("caller", turn.caller_response_text, state.timerSec);
    }
    if (res.caller_audio_b64) {
      playAudioBase64(res.caller_audio_b64);
    }
    updateMetrics(turn);
  } catch (e) {
    console.error(e);
  }
}

async function saveCardField(field, value) {
  if (!state.callId) return;
  try {
    const res = await api("POST", "/simulation/card/update", {
      call_id: state.callId,
      field,
      value,
    });
    if (res.protocol_adherence) {
      setMetric("protocol", res.protocol_adherence.percent, 100, false);
    }
  } catch (e) {
    console.error(`saveCardField(${field}):`, e);
  }
}

async function activateService(service, btn) {
  if (!state.active) return;

  // Если уже активирована — не отправляем повторно
  if (btn.classList.contains("activated")) return;

  try {
    const res = await api("POST", "/simulation/service/activate", {
      call_id: state.callId,
      service,
    });
    btn.classList.add("activated");
    btn.querySelector(".status-badge").textContent = "Активирована";
    if (res.new_violations) {
      renderViolations(res.new_violations);
    }
  } catch (e) {
    console.error(e);
    // 422 = служба не в списке допустимых. Показываем пользователю.
    if (String(e.message).includes("422")) {
      btn.querySelector(".status-badge").textContent = "Недоступно";
      btn.disabled = true;
    }
  }
}

async function endCall() {
  if (!state.active) return;
  try {
    const res = await api("POST", "/simulation/end", {
      call_id: state.callId,
      reason: "completed",
    });

    const report = res.report;
    showReport(report);

    // Сбрасываем только UI звонка, но модалку оставляем открытой
    state.active = false;
    state.callId = null;
    stopTimer();
    state.timerSec = 0;
    dom.timer.textContent = "00:00";
    dom.phoneTimer.textContent = "00:00";
    dom.callStatus.textContent = "Звонок завершён";
    dom.callStatus.classList.remove("active");
    dom.btnAccept.disabled = true;
    dom.btnEnd.disabled = true;
    dom.dispatcherText.disabled = true;
    dom.btnSend.disabled = true;
    dom.btnSaveCard.disabled = true;
    dom.btnCloseCard.disabled = true;
    setServicesEnabled(false);

    // Запоминаем последний отчёт для скачивания
    state.lastReport = report;
  } catch (e) {
    console.error(e);
    alert("Ошибка завершения: " + e.message);
  }
}

// ============================================================================
// МОДАЛКА ОТЧЁТА
// ============================================================================

function showReport(report) {
  const grade = report.grade || 0;
  const label = report.grade_label || "—";

  // Оценка
  dom.reportGradeValue.textContent = grade;
  dom.reportGradeLabel.textContent = label;

  const gradeCircle = dom.reportGradeCircle;
  gradeCircle.className = "grade-circle";
  if (grade >= 90) gradeCircle.classList.add("grade-excellent");
  else if (grade >= 75) gradeCircle.classList.add("grade-good");
  else if (grade >= 60) gradeCircle.classList.add("grade-fair");
  else gradeCircle.classList.add("grade-poor");

  // Подзаголовок: сколько нарушений
  const violations = (report.emergency_audit && report.emergency_audit.violations) || [];
  dom.reportGradeSub.textContent =
    violations.length === 0
      ? "Нарушений нет"
      : `Нарушений: ${violations.length}`;

  // Метрики
  dom.reportMetrics.innerHTML = "";
  const pa = report.protocol_adherence || {};
  const ac = report.airtime_control || {};
  addMetric("Соблюдение протокола", `${pa.percent ?? 0}%`);
  addMetric("Доля речи диспетчера", `${ac.dispatcher_percent ?? 0}%`);
  addMetric("Индекс паники", `${report.final_panic_index ?? "—"}`);
  addMetric("Комплаенс", `${report.final_compliance_index ?? "—"}`);

  // Нарушения
  dom.reportViolations.innerHTML = "";
  if (violations.length === 0) {
    dom.reportViolations.innerHTML = '<div class="empty">Нарушений нет</div>';
  } else {
    violations.forEach((v) => {
      const sev = v.severity;
      const cls = sev === 4 || sev === "4" ? "sev-critical"
                : sev === 3 || sev === "3" ? "sev-high"
                : "";
      const typeLabel = v.type || "violation";
      const div = document.createElement("div");
      div.className = `report-violation ${cls}`;
      div.innerHTML = `
        <span class="v-type">${typeLabel}</span>
        ${v.description || ""}
      `;
      dom.reportViolations.appendChild(div);
    });
  }

  // Таймлайн — только ключевые события (реплики + службы + нарушения)
  dom.reportTimeline.innerHTML = "";
  const timeline = report.timeline || [];
  const keyEvents = timeline.filter((e) =>
    ["caller_speech", "dispatcher_speech", "service_activated",
     "violation_detected", "call_ended"].includes(e.type)
  );
  if (keyEvents.length === 0) {
    dom.reportTimeline.innerHTML = '<div class="empty">—</div>';
  } else {
    keyEvents.forEach((e) => {
      const t = e.at_sec != null ? fmtTime(e.at_sec) : "—";
      let text = "";
      if (e.type === "caller_speech") text = `Заявитель: ${e.payload.text}`;
      else if (e.type === "dispatcher_speech") text = `Диспетчер: ${e.payload.text}`;
      else if (e.type === "service_activated") text = `Служба: ${e.payload.service}`;
      else if (e.type === "violation_detected") text = `Нарушение: ${e.payload.type}`;
      else if (e.type === "call_ended") text = `Звонок завершён`;

      const div = document.createElement("div");
      div.className = "tl-row";
      div.innerHTML = `<span class="tl-time">${t}</span><span class="tl-text">${text}</span>`;
      dom.reportTimeline.appendChild(div);
    });
  }

  // Показываем модалку
  dom.reportModal.classList.remove("hidden");
}

function addMetric(label, value) {
  const div = document.createElement("div");
  div.className = "report-metric";
  div.innerHTML = `<span class="label">${label}</span><span class="value">${value}</span>`;
  dom.reportMetrics.appendChild(div);
}

function hideReport() {
  dom.reportModal.classList.add("hidden");

  // Если пользователь закрыл модалку завершённого звонка —
  // возвращаем ARM в стартовое состояние, чтобы можно было
  // принять новый вызов.
  if (!state.active && !state.callId) {
    resetUI();
  }
}

function downloadReport() {
  if (!state.lastReport) return;
  const blob = new Blob(
    [JSON.stringify(state.lastReport, null, 2)],
    { type: "application/json;charset=utf-8" }
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `report_${state.callId || "call"}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function downloadReportPdf() {
  const callId = state.lastReport?.call_id;
  if (!callId) {
    alert("Нет данных отчёта для экспорта");
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/simulation/${callId}/report.pdf`);
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`${res.status}: ${t}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `report_${callId}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error(e);
    alert("Не удалось скачать PDF: " + e.message);
  }
}

function resetUI() {
  // Закрываем голосовой канал
  if (state.callWs) {
    try { state.callWs.close(); } catch (_) {}
    state.callWs = null;
    state.callWsReady = false;
  }
  state.isRecording = false;
  dom.btnVoice.classList.remove("recording");
  dom.btnVoice.disabled = true;
  dom.voiceStatus.textContent = "";

  state.active = false;
  state.callId = null;
  state.lastReport = null;
  state.violationsSeen = new Set();
  state.violationCount = 0;
  stopTimer();
  state.timerSec = 0;

  dom.callStatus.textContent = "Ожидание вызова";
  dom.callStatus.classList.remove("active");
  dom.timer.textContent = "00:00";
  dom.phoneTimer.textContent = "00:00";
  dom.btnAccept.disabled = false;
  dom.btnEnd.disabled = true;
  dom.dispatcherText.disabled = true;
  dom.btnSend.disabled = true;
  dom.btnSaveCard.disabled = true;
  dom.btnCloseCard.disabled = true;

  dom.dialogLog.innerHTML = "";

  // Очищаем поля карточки
  dom.card.callerFio.value = "";
  dom.card.callerRole.value = "";
  dom.card.callerPhone.value = "";
  dom.card.address.value = "";
  dom.card.whatHappened.value = "";
  dom.card.victims.checked = false;
  dom.card.threat.checked = false;
  dom.card.signL1.value = "";
  dom.card.signL2.value = "";
  dom.card.signL3.value = "";
  dom.card.classificationId.value = "";
  dom.card.classificationName.value = "";

  renderViolations([]);
  setMetric("protocol", 0, 100, false);
  dom.metricProtocol.textContent = "0%";
  dom.metricPanic.textContent = "—";
  dom.metricCompliance.textContent = "—";
  if (dom.metricPanicBar) dom.metricPanicBar.style.width = "0%";
  if (dom.metricComplianceBar) dom.metricComplianceBar.style.width = "0%";

  document.querySelectorAll(".service-btn").forEach((btn) => {
    btn.classList.remove("activated");
    btn.disabled = true;
    btn.querySelector(".status-badge").textContent =
      SERVICES.find((s) => s.value === btn.dataset.service).code;
  });

  // В самом конце — переключаем режим на текст
  switchInputMode("text");
}

// ============================================================================
// ПОДПИСКИ НА ПОЛЯ КАРТОЧКИ
// ============================================================================

function bindCardFields() {
  const map = {
    callerFio:          "caller_fio",
    callerRole:         "caller_role",
    callerPhone:        "caller_phone",
    address:            "address",
    whatHappened:       "what_happened",
    signL1:             "sign_l1",
    signL2:             "sign_l2",
    signL3:             "sign_l3",
    classificationId:   "classification_id",
    classificationName: "classification_name",
  };
  Object.entries(map).forEach(([domKey, apiField]) => {
    const el = dom.card[domKey];
    el.addEventListener("change", () => saveCardField(apiField, el.value));
  });

  dom.card.victims.addEventListener("change", () =>
    saveCardField("victims_present", dom.card.victims.checked));
  dom.card.threat.addEventListener("change", () =>
    saveCardField("threat_to_life", dom.card.threat.checked));
}

// ============================================================================
// ДЕКОРАТИВНЫЕ КНОПКИ ТЕЛЕФОНИИ
// ============================================================================

function bindPhoneControls() {
  const toggle = (btn, cls) => {
    if (!btn) return;
    btn.addEventListener("click", () => btn.classList.toggle(cls));
  };
  toggle($("btn-mute"), "active");
  toggle($("btn-hold"), "active");
  toggle($("btn-transfer"), "active");
}

// ============================================================================
// INIT
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  renderServices();
  renderViolations([]);
  drawWave();

  // Инициализируем кнопки в стартовое состояние:
  // btn-accept включен, остальное — выключено
  resetUI();

  dom.btnAccept.addEventListener("click", acceptCall);
  dom.btnEnd.addEventListener("click", endCall);
  dom.btnCloseCard.addEventListener("click", endCall);
  dom.btnSend.addEventListener("click", sendDispatcherSpeech);
  dom.dispatcherText.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendDispatcherSpeech();
  });

  dom.btnSaveCard.addEventListener("click", () => {
    // Все поля уже отправляются на сервер при изменении (autosave),
    // поэтому кнопка — просто визуальное подтверждение курсанту.
    const orig = dom.btnSaveCard.textContent;
    dom.btnSaveCard.textContent = "Сохранено ✓";
    dom.btnSaveCard.disabled = true;
    setTimeout(() => {
      dom.btnSaveCard.textContent = orig;
      dom.btnSaveCard.disabled = false;
    }, 1500);
  });

  bindCardFields();

  // Обработчики модалки отчёта
  dom.reportModal.querySelectorAll("#btn-close-modal, #btn-close-modal-x").forEach((btn) => {
    btn.addEventListener("click", hideReport);
  });
  document.getElementById("btn-download-json").addEventListener("click", downloadReport);
  document.getElementById("btn-download-pdf").addEventListener("click", downloadReportPdf);

  // ФИО курсанта — из localStorage
  const _CADET_KEY = "sim112_cadet_name";
  const savedName = localStorage.getItem(_CADET_KEY) || "";
  if (savedName) dom.cadetName.value = savedName;
  dom.cadetName.addEventListener("change", () => {
    localStorage.setItem(_CADET_KEY, dom.cadetName.value.trim());
  });

  bindVoiceButton();

  bindPhoneControls();

  loadScenarios();
});

// ============================================================================
// ГОЛОСОВОЙ КАНАЛ (WebSocket + AudioWorklet)
// ============================================================================

async function openCallWs(callId) {
  if (state.callWs) {
    state.callWs.close();
    state.callWs = null;
  }

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/call/${callId}`;

  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    state.callWs = ws;

    ws.addEventListener("open", () => {
      state.callWsReady = true;
      dom.voiceStatus.textContent = "Готово к записи";
      resolve();
    });

    ws.addEventListener("message", (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        handleCallWsMessage(msg);
      } catch (e) {
        console.error("WS call parse:", e);
      }
    });

    ws.addEventListener("close", () => {
      state.callWsReady = false;
      state.callWs = null;
      dom.voiceStatus.textContent = "Канал закрыт";
    });

    ws.addEventListener("error", (e) => {
      console.error("WS call error:", e);
      reject(e);
    });
  });
}

function handleCallWsMessage(msg) {
  switch (msg.type) {
    case "audio_ack":
      dom.voiceStatus.textContent = "Запись...";
      break;

    case "stt_result":
      if (msg.text) {
        addDialogMessage("dispatcher", msg.text, state.timerSec);
      } else {
        dom.voiceStatus.textContent = "Не распознано, попробуйте ещё раз";
      }
      break;

    case "caller_response":
      if (msg.text) {
        addDialogMessage("caller", msg.text, state.timerSec);
      }
      if (msg.audio_b64) {
        playAudioBase64(msg.audio_b64);
      }
      // Сбрасываем статус после получения ответа
      dom.voiceStatus.textContent = "Готово к записи";
      break;

    case "turn":
      if (msg.metrics) {
        if (msg.metrics.protocol_percent != null) {
          setMetric("protocol", msg.metrics.protocol_percent, 100, false);
        }
        if (msg.metrics.panic_index != null) {
          setMetric("panic", msg.metrics.panic_index, 100, true);
        }
        if (msg.metrics.compliance_index != null) {
          setMetric("compliance", msg.metrics.compliance_index, 100, false);
        }
      }
      // Сбрасываем статус — цикл ответа завершён
      dom.voiceStatus.textContent = "Готово к записи";
      break;

    case "error":
      console.warn("Ошибка голосового канала:", msg.message);
      dom.voiceStatus.textContent = `Ошибка: ${msg.message}`;
      break;
  }
}

async function startRecording() {
  if (state.isRecording || !state.callWsReady) return;
  state.isRecording = true;
  dom.btnVoice.classList.add("recording");
  dom.voiceStatus.textContent = "Слушаю...";

  try {
    // 1. Открываем AudioContext на 16 кГц (совпадает с Whisper)
    if (!state.audioContext) {
      state.audioContext = new AudioContext({ sampleRate: 16000 });
      await state.audioContext.audioWorklet.addModule("audio-worklet.js");
    }
    if (state.audioContext.state === "suspended") {
      await state.audioContext.resume();
    }

    // 2. Запрашиваем микрофон
    state.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });

    // 3. Собираем граф: MediaStreamSource → Worklet → (никуда)
    state.mediaSource = state.audioContext.createMediaStreamSource(state.mediaStream);
    state.audioWorkletNode = new AudioWorkletNode(state.audioContext, "pcm-processor");

    // 4. Слушаем чанки от воркл ета
    state.audioWorkletNode.port.onmessage = (ev) => {
      if (!state.isRecording || !state.callWsReady) return;
      const buf = ev.data;             // ArrayBuffer с Int16
      const b64 = arrayBufferToBase64(buf);
      state.callWs.send(JSON.stringify({ type: "audio_chunk", data: b64 }));
    };

    state.mediaSource.connect(state.audioWorkletNode);
    // Не подключаем к destination — не хотим слышать себя

    // 5. Сигналим серверу о начале
    state.callWs.send(JSON.stringify({ type: "audio_start" }));
  } catch (e) {
    console.error("Не удалось начать запись:", e);
    dom.voiceStatus.textContent = "Нет доступа к микрофону";
    stopRecording();
  }
}

function stopRecording() {
  if (!state.isRecording) return;
  state.isRecording = false;
  dom.btnVoice.classList.remove("recording");

  // Сообщаем серверу, что фраза закончилась
  if (state.callWsReady) {
    try {
      state.callWs.send(JSON.stringify({ type: "audio_end" }));
    } catch (_) {}
  }

  // Отключаем граф
  try {
    if (state.audioWorkletNode) {
      state.audioWorkletNode.disconnect();
      state.audioWorkletNode = null;
    }
    if (state.mediaSource) {
      state.mediaSource.disconnect();
      state.mediaSource = null;
    }
    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach((t) => t.stop());
      state.mediaStream = null;
    }
  } catch (e) {
    console.error("Ошибка остановки записи:", e);
  }

  dom.voiceStatus.textContent = "Обработка...";
}

function arrayBufferToBase64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) {
    bin += String.fromCharCode(bytes[i]);
  }
  return btoa(bin);
}

function switchInputMode(mode) {
  state.inputMode = mode;
  if (mode === "voice") {
    dom.inputTextMode.classList.add("hidden");
    dom.inputVoiceMode.classList.remove("hidden");
    dom.btnVoice.disabled = !state.active;
  } else {
    dom.inputVoiceMode.classList.add("hidden");
    dom.inputTextMode.classList.remove("hidden");
    dom.dispatcherText.disabled = !state.active;
    dom.btnSend.disabled = !state.active;
  }
}

function bindVoiceButton() {
  // Удерживание = запись. Отпускание = стоп.
  const btn = dom.btnVoice;

  btn.addEventListener("mousedown", startRecording);
  btn.addEventListener("mouseup", stopRecording);
  btn.addEventListener("mouseleave", () => { if (state.isRecording) stopRecording(); });

  // Тач (мобильные)
  btn.addEventListener("touchstart", (e) => { e.preventDefault(); startRecording(); });
  btn.addEventListener("touchend", (e) => { e.preventDefault(); stopRecording(); });

  // Радиокнопки режима
  document.querySelectorAll('input[name="input-mode"]').forEach((radio) => {
    radio.addEventListener("change", (e) => switchInputMode(e.target.value));
  });
}