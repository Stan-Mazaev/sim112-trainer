"""
Движок ИИ-заявителя.

Две ветки работы:
1. Fallback (без LLM) — генератор реплик на основе CallerState.
   Работает всегда, даже без torch/transformers. Используется по умолчанию.
2. LLM (Gemma 2B) — включается переменной ENABLE_LOCAL_WEIGHTS=true.
   Загружает модель один раз, инференс через семафор (сериализация).

Обе ветки возвращают одинаковый тип CallerTurn, поэтому остальная система
не знает, какая ветка активна.

ВАЖНО: Engine НЕ решает, как заявитель себя ведёт — это делает CallerStateMachine.
Engine лишь озвучивает состояние.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from typing import Any

from app.sim112.caller.prompts import (
    CALLER_SYSTEM_PROMPT,
    build_caller_prompt,
    get_opening_line,
    sanitize_dispatcher_text,
)
from app.sim112.caller.state import CallerStateMachine, DispatcherAction, StateDelta
from app.sim112.schemas import (
    CallerState,
    CallerTurn,
    Scenario,
)


try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


_OPENING_TEMPLATES: dict[str, list[str]] = {
    "fire": [
        "Алло! Пожар! Горим! Помогите!",
        "Скорее! Горит! Дым везде!",
        "Помогите! Пожар в квартире!",
    ],
    "medical": [
        "Алло! Он не дышит! Скорее!",
        "Помогите! Человек без сознания!",
        "Скорая! Пожалуйста, скорее!",
    ],
    "accident": [
        "Алло! Авария! Люди в машине!",
        "Скорее! ДТП! Люди зажаты!",
        "Помогите! Тут машины столкнулись!",
    ],
    "crime": [
        "Тихо... пожалуйста... они здесь...",
        "Помогите... грабители... я спрятался...",
        "Скорее... они в квартире...",
    ],
    "gas": [
        "Алло! Газом пахнет! Очень сильно!",
        "Скорее! Пахнет газом! Может рвануть!",
        "Помогите! Газ! Не знаю откуда!",
    ],
}

_HIGH_PANIC_PHRASES = [
    "Пожалуйста, скорее!",
    "Я не знаю, что делать!",
    "Помогите, пожалуйста!",
    "Он/она... оно горит!",
    "Я не могу... я не могу дышать!",
    "Умоляю, приезжайте!",
]

_MEDIUM_PANIC_PHRASES = [
    "Да... да, я слушаю...",
    "Я пытаюсь...",
    "Хорошо... хорошо...",
    "Я не помню точно...",
    "Что мне делать?",
]

_CALM_PHRASES = [
    "Да, я вас слушаю.",
    "Понял.",
    "Хорошо, я сделаю.",
    "Да, я здесь.",
    "Говорите, что делать.",
]

_UNCOOPERATIVE_PHRASES = [
    "Я не знаю...",
    "Я не помню...",
    "Не могу сосредоточиться...",
    "Какой адрес? Я... я запутался...",
    "Не знаю, не знаю...",
]


KEYWORD_TO_FACT: dict[str, str] = {
    # STT-варианты "что" / "кто" — Whisper tiny путает эти слова
    "что случил": "what_happened",
    "кто случил": "what_happened",
    "то случил": "what_happened",
    "что произошл": "what_happened",
    "кто произошл": "what_happened",
    "то произошл": "what_happened",
    "что у вас": "what_happened",
    "кто у вас": "what_happened",
    "что там": "what_happened",
    "кто там": "what_happened",
    "что горит": "what_happened",
    "что пожар": "what_happened",

    # Пострадавшие
    "сколько людей": "victims",
    "сколько пострадав": "victims",
    "сколько человек": "victims",
    "кто пострадал": "victims",
    "есть ли пострадав": "victims",
    "есть пострадав": "victims",
    "есть ли кто": "victims",
    "есть люди": "victims",
    "есть дет": "victims",
    "есть ранен": "victims",
    "сколько вас": "victims",
    "пострадав": "victims",
    "ранен": "victims",
    "жертв": "victims",

    # Адрес
    "где находитесь": "address",
    "где находит": "address",
    "где вы": "address",
    "адрес": "address",
    "улиц": "address",
    "дом": "address",

    # Детали
    "этаж": "location",
    "на каком": "location",
    "подъезд": "entrance",
    "квартир": "apartment",

    # Ситуативные
    "можете выйти": "exit_status",
    "можете выбр": "exit_status",
    "отрезан": "exit_status",
    "выход": "exit_status",
}


def _select_fact_key(
    dispatcher_text: str,
    known_facts: dict,
    already_revealed: set[str],
) -> tuple[str, bool] | None:
    """
    Возвращает (fact_key, is_repeat):
    - fact_key — какой факт озвучивать
    - is_repeat — True, если факт уже был озвучен ранее
    None — если ни один известный факт не подходит под вопрос.
    """
    lowered = dispatcher_text.lower()
    for keyword, fact_key in KEYWORD_TO_FACT.items():
        if keyword in lowered and fact_key in known_facts:
            return fact_key, fact_key in already_revealed
    return None


class FallbackCallerGenerator:
    """
    Простой генератор реплик заявителя без LLM.
    Работает по правилам: фаза + паника + cooperation → фраза.
    """

    def __init__(self, scenario_id: str):
        self.category = self._extract_category(scenario_id)

    @staticmethod
    def _extract_category(scenario_id: str) -> str:
        sid = str(scenario_id).lower()
        if "fire" in sid:
            return "fire"
        if "medical" in sid:
            return "medical"
        if "accident" in sid:
            return "accident"
        if "crime" in sid:
            return "crime"
        if "gas" in sid:
            return "gas"
        return "fire"

    def opening(self) -> str:
        templates = _OPENING_TEMPLATES.get(self.category, _OPENING_TEMPLATES["fire"])
        return random.choice(templates)

    def generate(
        self,
        state: CallerState,
        last_dispatcher_text: str,
        known_facts: dict[str, Any],
        already_revealed: set[str],
        action: DispatcherAction,
    ) -> tuple[str, list[str]]:
        """Возвращает (text, revealed_facts)."""

        if action == DispatcherAction.UNPROFESSIONAL:
            text = random.choice([
                "Зачем вы так со мной?! Мне страшно!",
                "Я вам звоню за помощью, а вы...",
                "(плачет) Пожалуйста... не кричите на меня...",
            ])
            return text, []

        if action == DispatcherAction.GROUNDING:
            text = random.choice([
                "Да... да, я вас слышу... я пытаюсь...",
                "Хорошо... хорошо... я дышу...",
                "Спасибо... я слушаю...",
            ])
            return text, []

        if action == DispatcherAction.RELEVANT_QUESTION:
            selected = _select_fact_key(
                last_dispatcher_text, known_facts, already_revealed,
            )

            if selected is None:
                text = random.choice([
                    "Я не знаю... я не помню...",
                    "Не могу сосредоточиться...",
                    "Пожалуйста, скорее...",
                ])
                return text, []

            fact_key, is_repeat = selected
            value = known_facts[fact_key]

            if is_repeat:
                text = random.choice([
                    f"Я же сказал: {value}!",
                    f"Ну сколько можно... {value}.",
                    f"Повторяю: {value}.",
                ])
                return text, []  # повторно не помечаем

            if fact_key in ("address", "full_address"):
                text = random.choice([
                    f"Адрес... {value}... скорее!",
                    f"Да, да, {value}!",
                    f"{value}, быстрее!",
                ])
            elif fact_key in ("floor", "location", "entrance", "apartment"):
                text = random.choice([f"{value}...", f"{value}, кажется..."])
            elif fact_key == "victims":
                text = random.choice([f"{value}... со мной!", f"{value}, скорее!"])
            else:
                text = f"{value}..."

            return text, [fact_key]

        if action == DispatcherAction.INSTRUCTION:
            text = random.choice([
                "Хорошо, я делаю!",
                "Понял, делаю!",
                "Да, да, я пытаюсь!",
            ])
            return text, []

        if action == DispatcherAction.REPEATED_QUESTION:
            text = random.choice([
                "Я же сказал уже!",
                "Вы не слышите меня?!",
                "Я уже говорил...",
            ])
            return text, []

        if action == DispatcherAction.SILENCE:
            text = random.choice([
                "Алло?! Вы здесь?!",
                "Вы меня слышите?!",
                "Скажите что-нибудь!",
            ])
            return text, []

        if state.panic >= 70:
            text = random.choice(_HIGH_PANIC_PHRASES)
        elif state.panic >= 40:
            text = random.choice(_MEDIUM_PANIC_PHRASES)
        elif state.cooperation < 30:
            text = random.choice(_UNCOOPERATIVE_PHRASES)
        else:
            text = random.choice(_CALM_PHRASES)

        return text, []


class LLMCallerGenerator:
    """
    Обёртка над Gemma 2B для генерации реплик заявителя.
    Загружается один раз. Инференс сериализован через asyncio.Lock.
    """

    def __init__(self, model_name: str = "google/gemma-2-2b-it", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.model = None
        self.tokenizer = None
        self._lock = asyncio.Lock()
        self._load()

    def _load(self):
        if not HAS_TRANSFORMERS:
            raise RuntimeError(
                "LLMCallerGenerator требует transformers + torch. "
                "Установи requirements-ml.txt или используй FallbackCallerGenerator."
            )
        try:
            print(f"[CallerEngine] Загрузка {self.model_name} на {self.device}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True,
            ).to(self.device)
            print("[CallerEngine] Модель загружена.")
        except Exception as exc:
            print(f"[CallerEngine] Не удалось загрузить модель: {exc}")
            self.model = None
            self.tokenizer = None

    def _run_inference(self, prompt: str) -> str:
        with torch.inference_mode():
            messages = [
                {"role": "system", "content": CALLER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            text_prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self.tokenizer(text_prompt, return_tensors="pt").to(self.device)
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=120,
                do_sample=True,
                temperature=0.8,
                top_p=0.9,
                use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )
            response = self.tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:],
                skip_special_tokens=True,
            )
            return response

    async def generate(
        self,
        state: CallerState,
        scenario: Scenario,
        history: list[dict[str, Any]],
        last_dispatcher_text: str,
        revealable_facts: dict[str, Any],
    ) -> CallerTurn:
        clean_text = sanitize_dispatcher_text(last_dispatcher_text)

        prompt = build_caller_prompt(
            scenario=scenario,
            state=state,
            history=history,
            last_dispatcher_text=clean_text,
            revealable_facts=revealable_facts,
        )

        async with self._lock:
            raw = await asyncio.to_thread(self._run_inference, prompt)

        text, revealed = self._parse_response(raw)
        return CallerTurn(text=text, revealed_facts=revealed, state_delta={})

    @staticmethod
    def _parse_response(raw: str) -> tuple[str, list[str]]:
        """Парсит JSON из ответа LLM. Если не получилось — вытаскивает текст грубо."""
        raw = raw.strip()

        m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                text = str(data.get("text", "")).strip()
                revealed = list(data.get("revealed_facts", []))
                if text:
                    return text, revealed
            except json.JSONDecodeError:
                pass

        return raw[:300].strip(), []


class CallerEngine:
    """
    Фасад над генератором заявителя.

    - Загружает FallbackCallerGenerator всегда.
    - Если ENABLE_LOCAL_WEIGHTS=true и есть ML-стек — догружает LLM.
    - Хранит CallerStateMachine для каждого звонка (передаётся снаружи).
    """

    def __init__(self):
        self.fallback: FallbackCallerGenerator | None = None
        self.llm: LLMCallerGenerator | None = None

        enable_llm = os.getenv("ENABLE_LOCAL_WEIGHTS", "false").lower() == "true"
        if enable_llm and HAS_TRANSFORMERS:
            try:
                self.llm = LLMCallerGenerator()
            except Exception as exc:
                print(f"[CallerEngine] LLM не запущена, работаем на fallback: {exc}")
                self.llm = None

    def initialize_for_scenario(self, scenario: Scenario) -> None:
        """Инициализирует fallback-генератор под конкретный сценарий."""
        self.fallback = FallbackCallerGenerator(scenario.id)

    def get_opening(self, scenario: Scenario) -> str:
        """Открывающая реплика — всегда берётся из сценария (без LLM)."""
        return get_opening_line(scenario)

    async def respond(
        self,
        *,
        state_machine: CallerStateMachine,
        scenario: Scenario,
        dispatcher_text: str,
        history: list[dict[str, Any]],
        duration_sec: float = 3.0,
    ) -> tuple[CallerTurn, DispatcherAction, StateDelta]:
        """
        Главный метод: обрабатывает реплику курсанта и возвращает ответ заявителя.

        Шаги:
        1. Применяем реплику к стейт-машине (детерминированно).
        2. Собираем revealable_facts (что заявитель МОЖЕТ сейчас озвучить).
        3. Генерируем текст (LLM или fallback).
        4. Помечаем раскрытые факты в стейт-машине.
        """

        if self.fallback is None:
            self.initialize_for_scenario(scenario)

        action, delta = state_machine.apply_dispatcher_turn(dispatcher_text, duration_sec)

        # Для LLM — только факты, которые можно раскрыть сейчас (can_reveal).
        revealable: dict[str, Any] = {}
        for key, value in state_machine.unrevealed_facts().items():
            if state_machine.can_reveal(key):
                revealable[key] = value

        # Для fallback — все известные факты (включая уже раскрытые, чтобы не терять память).
        known_facts = dict(state_machine.state.hidden_facts)
        already_revealed = set(state_machine.state.revealed_facts)

        if self.llm is not None and self.llm.model is not None:
            turn = await self.llm.generate(
                state=state_machine.state,
                scenario=scenario,
                history=history,
                last_dispatcher_text=dispatcher_text,
                revealable_facts=revealable,
            )
        else:
            clean = sanitize_dispatcher_text(dispatcher_text)
            text, revealed = self.fallback.generate(
                state=state_machine.state,
                last_dispatcher_text=clean,
                known_facts=known_facts,
                already_revealed=already_revealed,
                action=action,
            )
            turn = CallerTurn(text=text, revealed_facts=revealed, state_delta={})

        if turn.revealed_facts:
            state_machine.reveal_facts(turn.revealed_facts)

        return turn, action, delta


_engine_instance: CallerEngine | None = None


def get_caller_engine() -> CallerEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = CallerEngine()
    return _engine_instance