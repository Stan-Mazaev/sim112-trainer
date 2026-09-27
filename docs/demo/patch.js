(function () {
  function injectBanner() {
    const bar = document.createElement("div");
    bar.id = "demo-banner";
    bar.innerHTML =
      '<strong>🎬 Демо-режим</strong> · STT/TTS отключены, ответы заявителя из предзаписанных данных. ' +
      'Полная версия — в <a href="https://github.com/Stan-Mazaev/sim112-trainer" target="_blank">репозитории</a>.';
    bar.style.cssText = [
      "position: fixed", "top: 0", "left: 0", "right: 0", "z-index: 99999",
      "background: #2c3a4d", "color: #d8dee9",
      "padding: 8px 16px", "font-size: 12.5px",
      "text-align: center", "font-family: -apple-system, Segoe UI, sans-serif",
      "border-bottom: 1px solid #4a90c9",
    ].join(";");
    bar.querySelectorAll("a").forEach(function (a) {
      a.style.color = "#4a90c9";
    });
    document.body.insertBefore(bar, document.body.firstChild);
    // сдвигаем контент вниз
    document.body.style.paddingTop = "36px";
  }

  // Отключаем WebSocket-канал для голоса
  window.openCallWs = async function (callId) {
    const vs = document.getElementById("voice-status");
    if (vs) vs.textContent = "🎬 Голосовой канал в демо отключён";
    return Promise.resolve();
  };

  // Отключаем захват микрофона
  window.startRecording = async function () {
    const vs = document.getElementById("voice-status");
    if (vs) {
      vs.textContent = "🎬 Демо: голосовой ввод недоступен";
      setTimeout(function () { vs.textContent = ""; }, 2500);
    }
  };

  document.addEventListener("DOMContentLoaded", injectBanner);
})();