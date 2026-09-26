# Симулятор Системы 112 — ИИ-тренажёр операторов ДДС

**Хакатон ДГОЧСиПБ + ГБУ «Система 112»** · Москва

Программный комплекс для обучения операторов дежурно-диспетчерских служб
приёму и обработке экстренных вызовов. Реализует полный цикл: эмуляция звонка
через IP-телефонию → ИИ-заявитель с эмоциональной моделью → контроль действий
курсанта → объективная оценка на основе формализованных метрик → отчёт с
экспортом в PDF.

Работает **в закрытом контуре**: все модели (STT, TTS, оценка) — локальные,
без облачных API. Офлайн-инференс.

<!-- TODO: вставить скриншоты после прогонов -->
<!-- ![АРМ оператора](docs/arm.png) -->
<!-- ![Панель инструктора](docs/instructor.png) -->
<!-- ![PDF-отчёт](docs/report_pdf.png) -->

---

## Ключевые возможности

- **Эмуляция вызова через IP-телефон** — WebSocket-канал с потоковой передачей
  PCM Int16 16 кГц моно, интеграция со звуковой гарнитурой АРМ.
- **ИИ-заявитель** — стейт-машина на 4 шкалах (паника, доверие, комплаенс,
  кооперация) с фазами *shock → panic → coordination → resolution*. Скрытые
  факты, отказы отвечать, реакции на тон и инструкции курсанта. Работает
  офлайн (шаблонный fallback) и готов к подключению локальной LLM.
- **Библиотека сценариев из билетов** — 8 билетов × 3 случая = 24 сценария из
  официального сборника задач для операторов Системы 112.
- **Классификация по ЕКП** — 1283 типа происшествий, 23 группы, классификатор
  спарсен из Excel-справочника.
- **Аудит по 15 типам нарушений** — Protocol Adherence, Airtime Control,
  Response Time, детектор нарушений с весовой матрицей.
- **Голосовой канал** — faster-whisper base (int8, CPU, ru) для STT,
  pyttsx3 / SAPI5 (Microsoft Irina) для TTS. Паника заявителя влияет на
  темп и громкость озвучки.
- **Панель инструктора** — поток событий в реальном времени (WebSocket),
  список сессий, разбор завершённых звонков.
- **Отчёт и PDF-экспорт** — оценка `100 − Σ весов нарушений`, таблицы
  соответствия эталону, карточка вызова, подпись инструктора.

---

## Архитектура

Трёхслойная: бэкенд (FastAPI) + два веб-клиента (АРМ оператора и панель
инструктора). Всё общение — REST + WebSocket. Состояние сессии живёт в памяти
процесса (LRU на 100 завершённых).

```
┌──────────────────────┐         ┌──────────────────────┐
│   frontend/arm/      │         │  frontend/instructor/│
│   АРМ оператора      │         │  Панель инструктора  │
│   (HTML/CSS/JS)      │         │  (HTML/CSS/JS)       │
└──────────┬───────────┘         └──────────┬───────────┘
           │ REST + WS /ws/call             │ REST + WS /ws/instructor
           ▼                                ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI (app/main.py)                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │   app/api/v1/endpoints/simulation.py             │   │
│  │   start / step / card-update / service-activate /│   │
│  │   end / report.pdf / sessions                    │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │                                 │
│  ┌────────────────────▼─────────────────────────────┐   │
│  │   app/sim112/session/orchestrator.py             │   │
│  │   CallOrchestrator — центр сессии                │   │
│  └──┬──────────────┬───────────────┬────────────────┘   │
│     │              │               │                    │
│  ┌──▼────┐    ┌────▼──────┐   ┌────▼──────────────┐     │
│  │caller/│    │  audit/   │   │      voice/       │     │
│  │state  │    │ triggers  │   │ stt (whisper)     │     │
│  │prompts│    │ violations│   │ tts (SAPI5)       │     │
│  │engine │    │ metrics   │   │ pipe              │     │
│  └───────┘    └───────────┘   └───────────────────┘     │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ scenarios/ (registry + ticket_*.json)           │    │
│  │ ekp/classifier.json (1283 типа)                 │    │
│  │ report/ (generator + pdf)                       │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Ядро ИИ-заявителя

Стейт-машина на 4 шкалах, детерминированные переходы. LLM (при подключении)
используется **только для озвучки** — что сказать. **Что происходит** —
определяет стейт-машина. Это даёт воспроизводимость оценки.

```
Паника     0 ───────────────► 100
Доверие    0 ───────────────► 100
Комплаенс  0 ───────────────► 100
Кооперация 0 ───────────────► 100
```

**Фазы:** `shock` (0–30с) → `panic` (30–90с) → `coordination` (90–180с) → `resolution`.

**Скрытые факты:** адрес, этаж, что случилось, пострадавшие, оружие…
Раскрываются при правильных вопросах курсанта (classifier на keyword).

### Аудит и оценка

| Метрика | Как считается |
|---|---|
| **Protocol Adherence** | % заполненных полей карточки с весами (критические × 3) |
| **Airtime Control** | Доля речи диспетчера в общем времени; норматив 30–60% |
| **Response Time** | Задержка между триггером заявителя и активацией службы |
| **Оценка (grade)** | `100 − Σ VIOLATION_WEIGHTS[violation.type]`, клип в [0, 100] |

**Веса нарушений** (`VIOLATION_WEIGHTS`):

| Тип | Вес |
|---|---:|
| `MISSED_SERVICE` | 30 |
| `MISSED_ACTIVATION` | 25 |
| `CLASSIFICATION_MISMATCH` | 25 |
| `MISSED_CRITICAL_FIELD` | 20 |
| `UNPROFESSIONAL_TONE` | 20 |
| `LATE_ACTIVATION` | 15 |
| `SIGN_MISMATCH` | 12 |
| `NO_GROUNDING_FIRST_30S` | 10 |
| `MISSED_REQUIRED_FIELD` | 8 |
| `INTERRUPTED_CALLER` | 8 |
| `AIRTIME_OUT_OF_RANGE` | 5 |
| `INAPPROPRIATE_QUESTION` | 5 |
| `MISSED_CALLER_FIO` | 5 |
| `MISSED_CALLER_ROLE` | 5 |
| `EXTRA_SERVICE` | 3 |

---

## Соответствие ТЗ

| Требование | Реализация |
|---|---|
| Эмуляция звонка на гарнитуру IP-телефона | WebSocket `/ws/call/{call_id}`, поток PCM Int16 16k, AudioWorklet в браузере |
| Панель преподавателя + внешний монитор | `frontend/instructor/`, WebSocket `/ws/instructor/{call_id}` |
| Оценка действий курсанта | `app/sim112/audit/` (Protocol Adherence, тайминги, нарушения) |
| Работа в закрытом контуре | Локальные модели, без облачных API, HF_ENDPOINT через зеркало |
| Офлайн-инференс | faster-whisper (CPU, int8), pyttsx3 через SAPI5, шаблонный fallback для LLM |

---

## Стек

| Слой | Технология |
|---|---|
| Язык | Python 3.14 |
| Web-фреймворк | FastAPI 0.115 |
| Валидация | Pydantic 2.13.5 |
| ORM | SQLAlchemy 2.0.36 + aiosqlite |
| STT | faster-whisper 1.2.1 (модель `base`, int8, CPU, ru) |
| TTS | pyttsx3 → SAPI5 → Microsoft Irina Desktop — Russian |
| PDF | reportlab 5.0.1 + DejaVu / Arial |
| Парсинг ЕКП | pandas + openpyxl |
| HTTP-клиент | httpx |
| WebSocket | встроенный в FastAPI (Starlette) |

**Установлен, но не используется:** `vosk` (оставлен как альтернатива STT).

---

## Установка и запуск

### Требования

- **Windows 10/11** — для TTS через SAPI5. На Linux потребуется RHVoice/espeak
  (см. «Известные ограничения»).
- Python 3.14
- Микрофон (для голосового режима)
- ~2 ГБ свободного места (модель whisper + зависимости)

### Шаги

```powershell
# 1. Клонирование
git clone <TODO: URL>
cd sim112_backend

# 2. Виртуальное окружение
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Зависимости
pip install -r requirements.txt
pip install reportlab           # если не в requirements.txt

# 4. Переменные окружения
$env:HF_ENDPOINT = "https://hf-mirror.com"   # зеркало для скачивания whisper

# 5. Шрифты для PDF (fallback, если нет системного Arial)
# Положить в data/fonts/:
#   DejaVuSans.ttf
#   DejaVuSans-Bold.ttf
# (см. https://github.com/dejavu-fonts/dejavu-fonts/releases)

# 6. Запуск
python -m uvicorn app.main:app --reload --port 8000
```

### Открыть в браузере

- АРМ оператора: <http://127.0.0.1:8000/arm/>
- Панель инструктора: <http://127.0.0.1:8000/instructor/>

При первом запуске faster-whisper скачает модель `base` (~150 МБ) с
`hf-mirror.com`. Модель кэшируется в `~/.cache/huggingface/`.

---

## Структура проекта

```
sim112_backend/
├── app/
│   ├── main.py                       # точка входа FastAPI
│   ├── api/v1/endpoints/
│   │   └── simulation.py             # REST-эндпоинты тренажёра
│   ├── ws/
│   │   ├── call.py                   # /ws/call — голосовой канал
│   │   └── instructor.py             # /ws/instructor — поток событий
│   ├── arka_ai/                      # переиспользовано из старого проекта
│   │   ├── engine.py                 # fallback-генератор заявителя
│   │   ├── prompts.py
│   │   ├── psychology_kb.py
│   │   ├── dlp.py
│   │   └── profile_queue.py
│   └── sim112/                       # ядро тренажёра
│       ├── schemas.py                # все Pydantic-схемы (enums, домены, API)
│       ├── caller/
│       │   ├── state.py              # стейт-машина заявителя
│       │   ├── prompts.py            # 6 сценариев + 24 билетных
│       │   └── engine.py             # движок заявителя
│       ├── audit/
│       │   ├── triggers.py           # матрица триггеров
│       │   ├── violations.py         # детектор + веса нарушений
│       │   ├── metrics.py            # Protocol Adherence, Airtime, Response Time
│       │   └── engine.py             # оркестратор аудита
│       ├── session/
│       │   ├── orchestrator.py       # центр сессии звонка
│       │   ├── card.py               # карточка вызова
│       │   ├── events.py             # EventBus
│       │   └── manager.py            # SessionManager (LRU 100)
│       ├── report/
│       │   ├── generator.py          # сборка CallReport
│       │   └── pdf.py                # экспорт в PDF (reportlab)
│       ├── voice/
│       │   ├── stt.py                # faster-whisper wrapper
│       │   ├── tts.py                # pyttsx3 wrapper
│       │   └── pipe.py               # VoicePipe-фасад
│       ├── scenarios/
│       │   ├── schemas.py            # Ticket, TicketScenario, Expected
│       │   ├── registry.py           # реестр сценариев
│       │   └── tickets/
│       │       ├── ticket_01.json
│       │       ├── ticket_04.json
│       │       ├── ticket_08.json
│       │       ├── ticket_13.json
│       │       ├── ticket_20.json
│       │       ├── ticket_23.json
│       │       ├── ticket_25.json
│       │       └── ticket_27.json
│       └── ekp/
│           └── classifier.json       # 1283 типа ЕКП, 23 группы
├── frontend/
│   ├── arm/                          # АРМ оператора
│   │   ├── index.html
│   │   ├── app.js
│   │   ├── styles.css                # тёмная серо-синяя тема ПОВ-112
│   │   └── audio-worklet.js          # захват микрофона + ресемплинг 16 кГц
│   └── instructor/                   # панель инструктора
│       ├── index.html
│       ├── app.js
│       └── styles.css
├── data/
│   └── fonts/                        # DejaVuSans*.ttf (MIT) для PDF
├── scripts/
│   ├── check_scenario.py             # валидация ticket_*.json
│   ├── find_type.py                  # поиск по классификатору ЕКП
│   └── patch_tickets.py              # точечные правки билетов
├── README.md
└── requirements.txt
```

---

## API

### REST

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/v1/simulation/start` | Начать сессию, получить `opening_line` и `opening_audio_b64` |
| POST | `/api/v1/simulation/step` | Обработать реплику курсанта, получить ответ заявителя + метрики |
| POST | `/api/v1/simulation/card/update` | Обновить поле карточки вызова |
| POST | `/api/v1/simulation/service/activate` | Активировать экстренную службу |
| POST | `/api/v1/simulation/end` | Завершить звонок, получить `CallReport` |
| GET | `/api/v1/simulation/scenarios` | Список сценариев из билетов |
| GET | `/api/v1/simulation/{call_id}` | Статус сессии |
| GET | `/api/v1/simulation/{call_id}/report.pdf` | PDF-отчёт по завершённому звонку |
| GET | `/api/v1/simulation/instructor/sessions` | Список сессий (active + completed) |
| DELETE | `/api/v1/simulation/{call_id}` | Закрыть разбор (удалить из памяти) |

### WebSocket

| Путь | Назначение |
|---|---|
| `/ws/call/{call_id}` | Голосовой канал: PCM Int16 16k ↔ STT → оркестратор → TTS → `audio_b64` |
| `/ws/instructor/{call_id}` | Трансляция всех событий из `EventBus` в панель инструктора |

---

## Сценарии из билетов

Все сценарии — в `app/sim112/scenarios/tickets/*.json`. Формат:

```json
{
  "ticket_number": 20,
  "source": "Билеты-задачи по C 112 . АГС_ГСИ.pdf",
  "scenarios": [
    {
      "id": "ticket_20_case_01",
      "case_number": 1,
      "difficulty": "normal",
      "situation": "Дерутся 3 человека, без пострадавших, без оружия",
      "address": "Москва, Олонецкий проезд, дом 4",
      "caller": {
        "fio": "Иванов Сергей Петрович",
        "role": "очевидец",
        "opening_line": "Алло! Тут драка! Трое дерутся, но вроде без оружия!",
        "initial_panic": 65,
        "hidden_facts": { }
      },
      "expected": {
        "classification_id": "15.6.2.1",
        "classification_name": "Драка на улице",
        "signs": {
          "sign_l1": "Драка",
          "sign_l2": "Улица общественное место",
          "sign_l3": "До 10 человек"
        },
        "services": ["police"],
        "victims_present": false,
        "threat_to_life": false
      }
    }
  ]
}
```

### Добавить новый билет

1. Создать `app/sim112/scenarios/tickets/ticket_NN.json` по схеме выше.
2. `python scripts\check_scenario.py ticket_NN` — валидация.
3. Перезапустить бэк — билет появится в селекторе АРМ.

### Найти ID типа в ЕКП

```powershell
python scripts\find_type.py кровотечение
python scripts\find_type.py ДТП
```

---

## Оценка курсанта

Оценка считается только по зафиксированным нарушениям:

```
grade = clamp(100 − Σ VIOLATION_WEIGHTS[v.type], 0, 100)
```

**Интерпретация:**

| Диапазон | Ярлык |
|---|---|
| ≥ 90 | отлично |
| 75–89 | хорошо |
| 60–74 | удовлетворительно |
| 40–59 | неудовлетворительно |
| < 40 | провал |

Protocol Adherence **не добавляется** в оценку отдельно — незаполненные поля
уже отражены через `MISSED_CRITICAL_FIELD` и `MISSED_REQUIRED_FIELD`.

**Отчёт экспортируется:**

- **JSON** — кнопкой «Скачать JSON» в модалке отчёта АРМ.
- **PDF** — кнопкой «Скачать PDF» (эндпоинт `/report.pdf`).

---

## Известные ограничения

- **TTS работает только на Windows.** pyttsx3 использует SAPI5 и голос
  `Microsoft Irina Desktop — Russian`. На Linux/macOS потребуется замена на
  RHVoice или espeak-ng (правки в `app/sim112/voice/tts.py`).
- **Первая загрузка whisper требует интернета.** `HF_ENDPOINT=https://hf-mirror.com`
  обязателен, если `huggingface.co` недоступен. После первой загрузки модели
  всё работает офлайн.
- **Состояние сессий — в памяти.** После рестарта процесса завершённые
  сессии теряются (LRU 100). Для сохранения истории нужна БД
  (модели `SessionState`, `CadetProfile` уже описаны в `schemas.py`).
- **LLM-путь заявителя не подключён.** Движок готов (`CallerEngine`), но
  работает в режиме `FallbackCallerGenerator` — шаблонные ответы по
  ключевым словам. Для подключения локальной LLM (например, Qwen 2.5
  через llama.cpp) нужно доработать `caller/engine.py`.
- **vosk установлен, но не используется.** Оставлен как альтернативный
  STT-движок.

---

## Roadmap

- [ ] PDF-кнопка в панели инструктора (симметрично АРМ)
- [ ] Полировка UI АРМ под реальный ПОВ-112
- [ ] Подключение локальной LLM для заявителя (Qwen 2.5 / Saiga)
- [ ] Сохранение истории сессий в SQLite
- [ ] Профиль курсанта с накоплением метрик (`CadetProfile`)
- [ ] Расширение библиотеки билетов (сейчас 8 из полного сборника)
- [ ] Метрики в реальном времени для инструктора (графики)