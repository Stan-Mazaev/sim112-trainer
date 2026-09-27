(function () {
  window.__DEMO_MODE__ = true;

  const SCENARIOS = [
    // Реальные билеты 20/23/25/27 — из проекта
    { id: "ticket_20_case_01", ticket_number: 20, case_number: 1, difficulty: "normal",
      situation: "Дерутся 3 человека, без пострадавших, без оружия" },
    { id: "ticket_20_case_02", ticket_number: 20, case_number: 2, difficulty: "normal",
      situation: "Женщина, речь невнятная, лицо перекошено" },
    { id: "ticket_20_case_03", ticket_number: 20, case_number: 3, difficulty: "extreme",
      situation: "Изнасилование, женщина ~30 лет, травмы" },
    { id: "ticket_23_case_01", ticket_number: 23, case_number: 1, difficulty: "normal",
      situation: "Скандал с пьяным мужем, травма головы" },
    { id: "ticket_23_case_02", ticket_number: 23, case_number: 2, difficulty: "novice",
      situation: "Повреждение барабанной перепонки, кровотечение" },
    { id: "ticket_23_case_03", ticket_number: 23, case_number: 3, difficulty: "normal",
      situation: "Потерялся ребенок 5 лет, 30 минут" },
    { id: "ticket_25_case_01", ticket_number: 25, case_number: 1, difficulty: "novice",
      situation: "Нетрезвый мужчина на остановке ругается" },
    { id: "ticket_25_case_02", ticket_number: 25, case_number: 2, difficulty: "novice",
      situation: "ДТП без пострадавших, пежо и фольксваген" },
    { id: "ticket_25_case_03", ticket_number: 25, case_number: 3, difficulty: "extreme",
      situation: "Обнаружен труп бывшей супруги" },
    { id: "ticket_27_case_01", ticket_number: 27, case_number: 1, difficulty: "normal",
      situation: "Подозрительный ВАЗ-2110 с проводами во дворе" },
    { id: "ticket_27_case_02", ticket_number: 27, case_number: 2, difficulty: "novice",
      situation: "ДТП в тоннеле, без пострадавших" },
    { id: "ticket_27_case_03", ticket_number: 27, case_number: 3, difficulty: "normal",
      situation: "Соседи делают ремонт, трещина в стене" },

    // Иллюстративные (для полноты демо-набора)
    { id: "ticket_01_case_01", ticket_number: 1, case_number: 1, difficulty: "normal",
      situation: "Возгорание мусорного контейнера" },
    { id: "ticket_01_case_02", ticket_number: 1, case_number: 2, difficulty: "normal",
      situation: "Пожар в квартире на 4 этаже" },
    { id: "ticket_01_case_03", ticket_number: 1, case_number: 3, difficulty: "extreme",
      situation: "Пожар в высотном здании, люди отрезаны" },
    { id: "ticket_04_case_01", ticket_number: 4, case_number: 1, difficulty: "normal",
      situation: "Человек потерял сознание на улице" },
    { id: "ticket_04_case_02", ticket_number: 4, case_number: 2, difficulty: "normal",
      situation: "Сильное кровотечение, нужна скорая" },
    { id: "ticket_04_case_03", ticket_number: 4, case_number: 3, difficulty: "extreme",
      situation: "Остановка сердца, нужна реанимация" },
    { id: "ticket_08_case_01", ticket_number: 8, case_number: 1, difficulty: "novice",
      situation: "ДТП без пострадавших на перекрёстке" },
    { id: "ticket_08_case_02", ticket_number: 8, case_number: 2, difficulty: "normal",
      situation: "ДТП с зажатыми людьми" },
    { id: "ticket_08_case_03", ticket_number: 8, case_number: 3, difficulty: "extreme",
      situation: "Массовое ДТП, несколько машин" },
    { id: "ticket_13_case_01", ticket_number: 13, case_number: 1, difficulty: "normal",
      situation: "Ограбление квартиры, преступники внутри" },
    { id: "ticket_13_case_02", ticket_number: 13, case_number: 2, difficulty: "normal",
      situation: "Кража из автомобиля" },
    { id: "ticket_13_case_03", ticket_number: 13, case_number: 3, difficulty: "extreme",
      situation: "Вооружённое нападение" },
  ];

  // Сценарии диалога для каждой категории
  const SCRIPTS = {
    "ticket_20_case_01": {
      opening: "Алло! Тут драка! Трое дерутся, но вроде без оружия!",
      turns: [
        { match: ["что случил", "что произошл", "что там"], text: "Драка! Трое мужчин, кулаками машут, один уже упал!" },
        { match: ["адрес", "где наход", "где вы"], text: "Москва, Олонецкий проезд, дом 4! За домом, дорожка в сторону кладбища!" },
        { match: ["пострадав", "есть люди", "есть ранен"], text: "Пока не вижу... один на земле лежит, но в сознании вроде!" },
        { match: ["оружие", "оружия"], text: "Нет, кулаками только! Но злые очень!" },
      ]
    },
    "ticket_20_case_02": {
      opening: "Алло! Тут женщине плохо! Лицо перекосило, говорит невнятно! Лет семьдесят!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Ей плохо стало! Лицо перекосило, речь непонятная! Инсульт наверное!" },
        { match: ["адрес", "где наход", "где вы"], text: "Дорога от Каширского шоссе в сторону деревни Истомиха, у автобусной остановки!" },
        { match: ["пострадав", "возраст", "сколько лет"], text: "Женщина, лет семьдесят! Одна, я случайно мимо шёл!" },
        { match: ["сознани", "в сознании"], text: "В сознании, но плохо соображает, рукой машет!" },
      ]
    },
    "ticket_20_case_03": {
      opening: "(плачет, шёпотом) Помогите... меня... изнасиловали... вызовите полицию...",
      turns: [
        { match: ["что случил", "что произошл"], text: "(всхлипывает) Напал на меня... на улице... я не могу говорить об этом..." },
        { match: ["адрес", "где наход", "где вы"], text: "Москва, улица Кастанаевская, дом 42, корпус 2. Я во дворе, около подъезда..." },
        { match: ["пострадав", "травмы", "боль"], text: "Да... ушибы... мне нужна и скорая тоже... пожалуйста..." },
        { match: ["полици", "полицию"], text: "Да, вызовите полицию... он может ещё быть рядом..." },
      ]
    },
    "ticket_23_case_01": {
      opening: "Алло! Тут у соседей скандал, пьяный муж буянит! Женщине голову разбили!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Муж пьяный, избил жену! Голова в крови, она на полу лежит!" },
        { match: ["адрес", "где наход"], text: "Москва, улица Тихомирова, дом 15, корпус 1, квартира 79. Второй подъезд, четвёртый этаж, код 80В!" },
        { match: ["пострадав", "сколько"], text: "Одна женщина пострадала, 28 лет. Муж пьяный, всё ещё в квартире!" },
        { match: ["скорая", "скорую"], text: "Да, скорую и полицию! Муж невменяемый, может ещё напасть!" },
      ]
    },
    "ticket_23_case_02": {
      opening: "Алло! Я ухо почистила и повредила перепонку, кровь идёт!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Чистила ухо ватной палочкой и повредила перепонку! Кровь не останавливается!" },
        { match: ["адрес", "где наход"], text: "Москва, Зеленоград, посёлок Малино, улица Лесная, дом 5." },
        { match: ["пострадав", "боль"], text: "Ухо болит сильно, немного кружится голова. Одна дома, никого нет." },
        { match: ["когда", "как давно"], text: "Минут двадцать назад, я сразу вам позвонила!" },
      ]
    },
    "ticket_23_case_03": {
      opening: "Алло! Внук потерялся! Пять лет, гулял во дворе и пропал! Полчаса уже!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Гулял во дворе, я отвернулась на минуту — его нет! Уже полчаса ищу!" },
        { match: ["адрес", "где наход"], text: "Москва, улица Домодедовская, дом 34, корпус 1. Двор у третьего подъезда!" },
        { match: ["примет", "как одет", "одежд"], text: "Степанов Гриша, 5 лет. Синяя куртка, жёлтая шапка, жёлтый шарф и варежки, синие брюки, чёрные ботинки!" },
        { match: ["когда", "время"], text: "Полчаса назад! Я уже всех соседей обошла, никто не видел!" },
      ]
    },
    "ticket_25_case_01": {
      opening: "Алло! Тут на остановке пьяный мужчина буянит, ругается, хватает людей!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Пьяный мужчина на остановке! Ругается, хватает прохожих за руки, мешает всем!" },
        { match: ["адрес", "где наход"], text: "Москва, улица Фабрициуса, остановка 62 автобуса «улица Штурвальная»!" },
        { match: ["пострадав", "травм", "03"], text: "Нет, пострадавших нет. Медицинская помощь не нужна, только полиция!" },
        { match: ["оружие", "оружия"], text: "Нет, просто руками хватает. Но люди боятся!" },
      ]
    },
    "ticket_25_case_02": {
      opening: "Алло! ДТП на МКАД, две машины, вроде без пострадавших!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Столкнулись две машины — пежо и фольксваген! Никто не пострадал, но машины перегородили полосу!" },
        { match: ["адрес", "где наход"], text: "МКАД от Варшавского шоссе в сторону Каширского! Напротив ТЦ Вегас, в левом ряду!" },
        { match: ["пострадав", "есть ранен"], text: "Нет, все целы. Никто не жалуется, обе машины своим ходом не поедут." },
        { match: ["разлив", "топлив"], text: "Разлива не вижу, только осколки на дороге." },
      ]
    },
    "ticket_25_case_03": {
      opening: "(в шоке) Алло... я пришёл к бывшей жене... соседи сказали, что собака воет четыре дня... я открыл... она мёртвая...",
      turns: [
        { match: ["что случил", "что произошл"], text: "Я открыл дверь... она на полу лежит... трупные пятна... крови много рядом..." },
        { match: ["адрес", "где наход"], text: "Московская область, город Домодедово, улица Текстильщиков, дом 31, квартира 5. Первый подъезд, первый этаж, код 5В." },
        { match: ["скорую", "03"], text: "Скорее не надо... она уже точно мёртвая. Полицию вызывайте, пожалуйста." },
        { match: ["насильствен", "признак"], text: "Кровь на полу, лужа... не знаю, что случилось. Я её не трогал." },
      ]
    },
    "ticket_27_case_01": {
      opening: "Алло! Тут подозрительная машина во дворе ночью. Сильно нагружена, под ней коробка с проводами!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Странная машина! Грязная, ночью приехала, просела сильно. Под днищем коробка с проводами!" },
        { match: ["адрес", "где наход"], text: "Москва, Тихорецкий бульвар, дом 12, корпус 1. Во дворе у входа в магазин «Билла»." },
        { match: ["марк", "номер", "описан"], text: "ВАЗ 2110, грязный. Номер — a155aт 33 регион." },
        { match: ["пострадав", "люди"], text: "Людей нет, машина пустая. Но боюсь, что это бомба!" },
      ]
    },
    "ticket_27_case_02": {
      opening: "Алло! ДТП на Садовом, две машины, вроде без пострадавших! Прямо у тоннеля!",
      turns: [
        { match: ["что случил", "что произошл"], text: "ДТП! Пежо и фольксваген столкнулись у въезда в тоннель! Никто не пострадал!" },
        { match: ["адрес", "где наход"], text: "Москва, Садовое кольцо, от проспекта Мира после улицы Малая Дмитровка, прямо у тоннеля!" },
        { match: ["пострадав", "есть ранен"], text: "Нет, никто не пострадал. Но движение перекрыто, пробка!" },
        { match: ["разлив", "топлив", "пожар"], text: "Разлива нет, пожара тоже нет. Только осколки." },
      ]
    },
    "ticket_27_case_03": {
      opening: "Алло! Соседи делают ремонт, у меня в ванной плитка отлетела, трещина пошла!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Соседи сверху ремонт делают! У меня в ванной плитка от стены отлетела, трещина около метра пошла!" },
        { match: ["адрес", "где наход"], text: "Москва, Ленинский проспект, дом 57, квартира 28. Первый подъезд, пятый этаж, код 57В." },
        { match: ["пострадав", "травм"], text: "Нет, никто не пострадал. Но страшно, что дальше отвалится!" },
        { match: ["угроза", "обрушен"], text: "Не знаю, но трещина растёт! Помогите, пожалуйста!" },
      ]
    },
    "ticket_01_case_01": {
      opening: "Алло! Тут контейнер горит! Мусорка полыхает!",
      turns: [
        { match: ["что случил", "что произошл"], text: "Горит мусорный контейнер, открытое пламя!" },
        { match: ["адрес", "где наход"], text: "Москва, около ст. Москва-Пассажирская Киевская... скорее!" },
        { match: ["пострадав", "есть люди"], text: "Нет, рядом никого. Только контейнер и трава рядом!" },
      ]
    },
  };

  // Fallback для сценариев без явного скрипта
  function buildFallbackScript(sc) {
    const generic = {
      fire: {
        opening: "Алло! Пожар! Горим, помогите!",
        turns: [
          { match: ["что случил", "что произошл"], text: "Пожар! Горит сильно, дым везде!" },
          { match: ["адрес", "где наход"], text: sc.situation + ", помогите скорее!" },
          { match: ["пострадав"], text: "Не знаю, здесь люди!" },
        ]
      },
      medical: {
        opening: "Алло! Человеку плохо, помогите!",
        turns: [
          { match: ["что случил", "что произошл"], text: "Человек без сознания, скорее!" },
          { match: ["адрес", "где наход"], text: "Адрес: " + sc.situation },
          { match: ["пострадав"], text: "Да, один человек, ему очень плохо!" },
        ]
      },
      accident: {
        opening: "Алло! Авария!",
        turns: [
          { match: ["что случил", "что произошл"], text: "ДТП! Машины столкнулись!" },
          { match: ["адрес", "где наход"], text: sc.situation },
          { match: ["пострадав"], text: "Пострадавших нет или пока не видно." },
        ]
      },
      crime: {
        opening: "Тихо... помогите, полицию...",
        turns: [
          { match: ["что случил", "что произошл"], text: "Преступление! Скорее полицию!" },
          { match: ["адрес", "где наход"], text: sc.situation },
          { match: ["пострадав"], text: "Пока никого не тронули, но страшно!" },
        ]
      },
    };
    let cat = "fire";
    const s = sc.situation.toLowerCase();
    if (/пожар|гори|дым|возгорание/.test(s)) cat = "fire";
    else if (/кров|сердц|сознани|человек|медиц|травм|ухо/.test(s)) cat = "medical";
    else if (/дтп|авари|машин|столкн/.test(s)) cat = "accident";
    else if (/ограб|краж|криминал|нападен|преступ/.test(s)) cat = "crime";
    return generic[cat];
  }

  // Session state
  let session = null;

  function findTurn(script, text, used) {
    const lower = (text || "").toLowerCase();
    for (const t of script.turns) {
      if (used.has(t)) continue;
      if (t.match.some((m) => lower.includes(m))) return t;
    }
    return null;
  }

  function jsonResponse(data) {
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  const origFetch = window.fetch.bind(window);

  window.fetch = async function (url, opts) {
    const urlStr = typeof url === "string" ? url : url.toString();

    if (!urlStr.includes("/api/v1/")) {
      return origFetch(url, opts);
    }

    const method = (opts && opts.method) || "GET";
    let body = {};
    try { body = opts && opts.body ? JSON.parse(opts.body) : {}; } catch (e) {}

    // GET scenarios
    if (urlStr.endsWith("/simulation/scenarios") && method === "GET") {
      return jsonResponse({ scenarios: SCENARIOS });
    }

    // POST start
    if (urlStr.endsWith("/simulation/start") && method === "POST") {
      const sid = body.scenario_id;
      const sc = SCENARIOS.find((s) => s.id === sid) || SCENARIOS[0];
      const script = SCRIPTS[sid] || buildFallbackScript(sc);
      session = {
        call_id: "demo-" + Math.random().toString(36).slice(2, 10),
        scenario_id: sid,
        scenario_title: `Билет ${sc.ticket_number}, случай ${sc.case_number} — ${sc.situation}`,
        cadet_name: body.cadet_name || null,
        script: script,
        used: new Set(),
        card: {},
        services: [],
        startTime: Date.now(),
        finished: false,
        panic: 60,
        compliance: 20,
        protocol: 0,
      };
      return jsonResponse({
        call_id: session.call_id,
        scenario: { id: sid, title: session.scenario_title },
        opening_line: script.opening,
        opening_audio_b64: null,
        caller_state: { panic: 60, trust: 40, cooperation: 30, compliance: 20, phase: "shock" },
        card_template: {},
      });
    }

    // POST step
    if (urlStr.endsWith("/simulation/step") && method === "POST") {
      if (!session) return jsonResponse({});
      const text = body.dispatcher_text || "";
      const turn = findTurn(session.script, text, session.used);
      let replyText;
      if (turn) {
        session.used.add(turn);
        replyText = turn.text;
      } else {
        const fallbacks = [
          "Я не знаю... не помню... пожалуйста, скорее!",
          "Не могу сосредоточиться... помогите!",
          "Что мне делать? Скажите!",
        ];
        replyText = fallbacks[Math.floor(Math.random() * fallbacks.length)];
      }

      session.panic = Math.max(15, session.panic - 4);
      session.compliance = Math.min(100, session.compliance + 6);
      session.protocol = Math.min(100, session.protocol + 6);

      return jsonResponse({
        turn: {
          caller_response_text: replyText,
          caller_state: { panic: session.panic, trust: 45, cooperation: 50, compliance: session.compliance, phase: "coordination" },
          protocol_adherence: { percent: session.protocol, filled_fields: [], missed_critical: [], missed_required: [] },
          airtime_control: { dispatcher_percent: 40, caller_percent: 60, target_min: 30, target_max: 60, in_range: true, advice: "" },
          panic_index: session.panic,
          compliance_index: session.compliance,
          trust_index: 45,
          emergency_audit: { triggers_detected: [], activations: [], response_times_sec: {}, violations: [] },
          protocol_alert: { has_violations: false, violations: [], grounding_phrases_used: [], unprofessional_phrases: [] },
        },
        caller_audio_url: null,
        caller_audio_b64: null,
      });
    }

    // POST card/update
    if (urlStr.endsWith("/simulation/card/update") && method === "POST") {
      if (!session) return jsonResponse({});
      session.card[body.field] = body.value;
      const filled = Object.entries(session.card).filter(([k, v]) =>
        v !== null && v !== undefined && v !== "" && (!Array.isArray(v) || v.length > 0)
      ).length;
      session.protocol = Math.min(100, Math.round((filled / 5) * 100));
      return jsonResponse({
        card: session.card,
        protocol_adherence: { percent: session.protocol, filled_fields: [], missed_critical: [], missed_required: [] },
      });
    }

    // POST service/activate
    if (urlStr.endsWith("/simulation/service/activate") && method === "POST") {
      if (!session) return jsonResponse({});
      if (!session.services.includes(body.service)) {
        session.services.push(body.service);
      }
      return jsonResponse({
        activation: { service: body.service, activated_at_sec: Math.round((Date.now() - session.startTime) / 1000) },
        new_violations: [],
      });
    }

    // POST end
    if (urlStr.endsWith("/simulation/end") && method === "POST") {
      if (!session) return jsonResponse({});
      const duration = Math.round((Date.now() - session.startTime) / 1000);
      const violations = [];
      if (!session.card.address) {
        violations.push({
          type: "missed_critical_field", severity: 3, detected_at_sec: duration,
          description: "Критическое поле «Адрес происшествия» не заполнено.",
          related_field: "address",
        });
      }
      if (!session.card.what_happened) {
        violations.push({
          type: "missed_required_field", severity: 2, detected_at_sec: duration,
          description: "Обязательное поле «Что случилось» не заполнено.",
          related_field: "what_happened",
        });
      }
      if (session.protocol < 80) {
        violations.push({
          type: "classification_mismatch", severity: 3, detected_at_sec: duration,
          description: "Неверный итоговый тип. Заполните ЕКП в карточке.",
        });
      }

      const weights = { missed_critical_field: 20, missed_required_field: 8, classification_mismatch: 25 };
      const grade = Math.max(0, 100 - violations.reduce((s, v) => s + (weights[v.type] || 5), 0));
      const label = grade >= 90 ? "отлично" : grade >= 75 ? "хорошо" : grade >= 60 ? "удовлетворительно" : grade >= 40 ? "неудовлетворительно" : "провал";

      const report = {
        call_id: session.call_id,
        cadet_id: 1,
        cadet_name: session.cadet_name,
        scenario_id: session.scenario_id,
        scenario_title: session.scenario_title,
        duration_sec: duration,
        protocol_adherence: { percent: session.protocol, filled_fields: [], missed_critical: [], missed_required: [] },
        airtime_control: { dispatcher_percent: 40, caller_percent: 60, target_min: 30, target_max: 60, in_range: true, advice: "" },
        emergency_audit: { triggers_detected: [], activations: [], response_times_sec: {}, violations },
        protocol_alert: { has_violations: violations.length > 0, violations, grounding_phrases_used: [], unprofessional_phrases: [] },
        final_panic_index: session.panic,
        final_compliance_index: session.compliance,
        grade,
        grade_label: label,
        recommendations: [],
        timeline: [],
        card: session.card,
        expected: null,
        created_at: new Date().toISOString(),
      };
      session.finished = true;
      session.lastReport = report;
      return jsonResponse({ report });
    }

    // GET report.pdf — отдаём статичный
    if (urlStr.includes("/report.pdf")) {
      const r = await origFetch("../sample_report.pdf");
      if (!r.ok) {
        return new Response("PDF-пример не найден", { status: 404 });
      }
      return r;
    }

    // GET instructor/sessions
    if (urlStr.includes("/simulation/instructor/sessions")) {
      if (!session) {
        return jsonResponse({ active: [], completed: [], counts: { total: 0, active: 0, completed: 0 } });
      }
      const active = !session.finished;
      const item = {
        call_id: session.call_id,
        cadet_id: 1,
        cadet_name: session.cadet_name,
        scenario_title: session.scenario_title,
        scenario_id: session.scenario_id,
        status: active ? "active" : "completed",
        started_at: new Date(session.startTime).toISOString(),
        ended_at: session.finished ? new Date().toISOString() : null,
        duration_sec: Math.round((Date.now() - session.startTime) / 1000),
        violations_count: active ? 0 : (session.lastReport?.emergency_audit?.violations?.length || 0),
      };
      return jsonResponse({
        active: active ? [item] : [],
        completed: active ? [] : [item],
        counts: { total: 1, active: active ? 1 : 0, completed: active ? 0 : 1 },
      });
    }

    // GET /{call_id} — статус
    if (method === "GET" && /\/simulation\/[^/]+$/.test(urlStr)) {
      if (!session) return jsonResponse({});
      return jsonResponse({
        call_id: session.call_id,
        status: session.finished ? "completed" : "active",
        cadet_id: 1,
        scenario_id: session.scenario_id,
        duration_sec: Math.round((Date.now() - session.startTime) / 1000),
        caller_state: { panic: session.panic, compliance: session.compliance },
        card: session.card,
        triggers_count: 0,
        activations_count: session.services.length,
        violations_count: session.lastReport?.emergency_audit?.violations?.length || 0,
      });
    }

    // DELETE /{call_id} — закрыть разбор
    if (method === "DELETE") {
      session = null;
      return jsonResponse({ ok: true });
    }

    return jsonResponse({});
  };

  // Подмена WebSocket
  const RealWebSocket = window.WebSocket;
  window.WebSocket = function (url, protocols) {
    if (typeof url !== "string" || !url.includes("/ws/")) {
      return new RealWebSocket(url, protocols);
    }

    const listeners = {};
    const sock = {
      readyState: 1,
      send: function () {},
      close: function () {},
      addEventListener: function (type, fn) {
        if (!listeners[type]) listeners[type] = [];
        listeners[type].push(fn);
      },
      removeEventListener: function () {},
    };

    setTimeout(function () {
      (listeners.open || []).forEach(function (fn) { fn({}); });

      // Для инструктора — генерируем поток событий
      if (url.includes("/ws/instructor/") && session) {
        const events = [
          { type: "call_started", at_sec: 0, payload: { scenario: session.scenario_title } },
          { type: "caller_speech", at_sec: 0, payload: { text: session.script.opening } },
        ];
        let t = 1;
        session.script.turns.forEach(function (turn) {
          events.push({ type: "dispatcher_speech", at_sec: t, payload: { text: "..." } });
          events.push({ type: "caller_speech", at_sec: t + 1, payload: { text: turn.text } });
          t += 5;
        });

        let idx = 0;
        const timer = setInterval(function () {
          if (idx >= events.length) { clearInterval(timer); return; }
          const ev = events[idx++];
          (listeners.message || []).forEach(function (fn) {
            fn({ data: JSON.stringify(ev) });
          });
        }, 700);
      }
    }, 60);

    return sock;
  };

})();