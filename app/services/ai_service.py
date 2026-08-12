from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.services.file_service import StoredFile
from app.services.prompt_loader import PromptLoader
from app.services.registries import ACTION_TYPES, ACTION_TYPES_SET, CHART_TYPES, CHART_TYPES_SET
from app.services.runtime_config import RuntimeConfig
from app.services.usage_service import UsageService

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime when dependency is absent
    OpenAI = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Base AI service error."""


class AIServiceConfigurationError(AIServiceError):
    """Raised when OpenAI is not configured."""


class AIServiceRequestError(AIServiceError):
    """Raised when the OpenAI API request fails."""


@dataclass
class AIPlan:
    assistant_message: str
    actions: list[dict[str, Any]]


class AIService:
    """Слой взаимодействия с языковой моделью.

    Портабельный (B): использует Chat Completions API и `OPENAI_BASE_URL`,
    поэтому провайдером может быть любой совместимый (OpenAI, GigaChat,
    YandexGPT, Gemini и т.п.). Промпт (A) грузится из версионированного файла
    через `PromptLoader` — правка применяется в runtime без рестарта. Контракт
    ответа (F) — structured output через json_schema; схема генерируется из
    реестров `ACTION_TYPES`/`CHART_TYPES` (D, E) — единый источник истины, AI не
    может вернуть действие/график, который приложение не умеет исполнять. Для
    провайдеров без structured output оператор отключает `STRUCTURED_OUTPUT`, и
    ответ парсится устойчивым парсером.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        usage_service: UsageService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = None
        self._runtime = RuntimeConfig(self.settings)
        # PromptLoader делится тем же экземпляром RuntimeConfig — override промпта
        # (system_prompt_override) читается из одного config.json.
        self._prompt_loader = PromptLoader(self.settings, runtime=self._runtime)
        self._usage = usage_service
        self._client_base_url: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openai_api_key) and OpenAI is not None

    @property
    def model_name(self) -> str:
        return self._runtime.get("openai_model")

    def plan_response(
        self,
        *,
        conversation_messages: list[dict[str, Any]],
        user_text: str,
        active_file: StoredFile | None,
        active_file_context: dict[str, Any] | None,
    ) -> AIPlan:
        if OpenAI is None:
            raise AIServiceConfigurationError(
                "Python-пакет `openai` не установлен. Выполните `pip install -r requirements.txt`."
            )
        if not self.settings.openai_api_key:
            raise AIServiceConfigurationError(
                "Не задан `OPENAI_API_KEY` в `.env`."
            )

        client = self._get_client()
        messages = self._build_messages(
            conversation_messages=conversation_messages,
            user_text=user_text,
            active_file=active_file,
            active_file_context=active_file_context,
        )
        request_kwargs: dict[str, Any] = {
            "model": self._runtime.get("openai_model"),
            "messages": messages,
        }
        # temperature отправляем только если оператор явно задал её в runtime-конфиге.
        # Иначе провайдер использует своё умолчание — это портабельно: ряд моделей
        # (gpt-5-mini и др.) не принимают произвольные значения температуры.
        if self._runtime.has("openai_temperature"):
            request_kwargs["temperature"] = self._runtime.get("openai_temperature")
        # seed отправляем только если явно задан (не None) — поддерживают не все провайдеры.
        seed = self._runtime.get("openai_seed")
        if seed is not None:
            request_kwargs["seed"] = seed
        if self._runtime.get("structured_output"):
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": self._build_response_schema(),
            }

        try:
            response = client.chat.completions.create(**request_kwargs)
        except Exception as exc:  # pragma: no cover - depends on external API/network
            logger.exception("Model request failed")
            if self._usage is not None:
                self._usage.record_error(str(exc))
            raise AIServiceRequestError(str(exc)) from exc

        # Учёт использования (токены/запросы). response.usage может быть None
        # для провайдеров, не возвращающих usage — тогда считаем только запрос.
        if self._usage is not None:
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._usage.record_success(
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    getattr(usage, "total_tokens", 0) or 0,
                )
            else:
                self._usage.record_request_only()

        raw_text = getattr(response.choices[0].message, "content", "") or ""
        plan = self._parse_plan(raw_text)
        logger.info(
            "Model plan received with %s actions (structured_output=%s, model=%s)",
            len(plan.actions),
            self._runtime.get("structured_output"),
            self._runtime.get("openai_model"),
        )
        return plan

    def _get_client(self):
        base_url = self._runtime.get("openai_base_url")
        # Пересоздаём клиент, если оператор сменил endpoint в runtime.
        if self._client is None or self._client_base_url != base_url:
            self._client = OpenAI(
                api_key=self.settings.openai_api_key,
                base_url=base_url,
            )
            self._client_base_url = base_url
        return self._client

    def test_connection(self) -> dict[str, Any]:
        """Диагностический пинг провайдера: минимальный Chat Completions-запрос
        к текущему (runtime) base_url+model. НЕ пишет в статистику использования.

        Возвращает {ok, model, base_url, latency_ms, reply} или {ok: False, error}.
        """
        if OpenAI is None:
            return {"ok": False, "error": "Пакет `openai` не установлен."}
        if not self.settings.openai_api_key:
            return {"ok": False, "error": "Не задан OPENAI_API_KEY в .env."}
        import time

        model = self._runtime.get("openai_model")
        base_url = self._runtime.get("openai_base_url")
        try:
            client = self._get_client()
            started = time.perf_counter()
            # Минимальный пинг: только model+messages. Без max_tokens и temperature —
            # портабельно (gpt-5-mini не принимает max_tokens и не поддерживает
            # произвольную temperature). Ответ на «ping» короткий, стоимость пренебрежима.
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            reply = (getattr(response.choices[0].message, "content", "") or "").strip()
            return {
                "ok": True,
                "model": model,
                "base_url": base_url,
                "latency_ms": latency_ms,
                "reply": reply,
            }
        except Exception as exc:  # noqa: BLE001 - диагностический перехват
            logger.warning("Provider test failed: %s", exc)
            return {"ok": False, "error": str(exc), "model": model, "base_url": base_url}

    # --- Сборка запроса ---

    def _build_messages(
        self,
        *,
        conversation_messages: list[dict[str, Any]],
        user_text: str,
        active_file: StoredFile | None,
        active_file_context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        system_prompt = self._prompt_loader.load_system_prompt(
            variables=self._prompt_variables()
        )
        user_content = self._build_user_content(
            conversation_messages=conversation_messages,
            user_text=user_text,
            active_file=active_file,
            active_file_context=active_file_context,
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _prompt_variables(self) -> dict[str, str]:
        provider_name = self._runtime.get("provider_name")
        provider_attribution = f" от {provider_name}" if provider_name else ""
        return {
            "specialization": self._runtime.get("assistant_specialization"),
            "provider_attribution": provider_attribution,
        }

    def _build_user_content(
        self,
        *,
        conversation_messages: list[dict[str, Any]],
        user_text: str,
        active_file: StoredFile | None,
        active_file_context: dict[str, Any] | None,
    ) -> list[dict[str, Any]] | str:
        history = []
        max_history = self._runtime.get("openai_max_history_messages")
        for message in conversation_messages[-max_history:]:
            history.append(
                {
                    "role": message.get("role", "assistant"),
                    "text": message.get("text", ""),
                }
            )

        current_request = user_text.strip() or "Пользователь загрузил файл без дополнительного текста."
        prompt_payload = {
            "current_user_message": current_request,
            "recent_messages": history,
            "active_file": active_file_context,
            "available_actions": self._build_available_actions(),
            "response_contract": {
                "assistant_message": "string",
                "actions": "array",
            },
        }

        text_block = (
            "Верни только JSON без markdown-обёртки. "
            "Строго следуй схеме ответа (assistant_message + actions).\n\n"
            + json.dumps(prompt_payload, ensure_ascii=False, indent=2)
        )

        if active_file and active_file.kind == "image":
            # Multimodal: текст + изображение. Для не-мультимодальных провайдеров
            # изображение игнорируется ими; для OpenAI-совместимых — передаётся.
            return [
                {"type": "text", "text": text_block},
                {"type": "image_url", "image_url": {"url": self._image_data_url(active_file)}},
            ]
        return text_block

    def _build_available_actions(self) -> list[dict[str, Any]]:
        """Список разрешённых действий для подсказки модели. Выводится из реестров."""
        actions: list[dict[str, Any]] = [
            {"type": "preview"},
            {"type": "analyze"},
            {
                "type": "generate_chart",
                "chart_type": " | ".join(CHART_TYPES),
                "x_column": "string | null",
                "y_column": "string | null",
            },
            {"type": "generate_report"},
            {"type": "save_summary"},
        ]
        return actions

    def _build_response_schema(self) -> dict[str, Any]:
        """JSON Schema structured output. Enum'ы генерируются из реестров."""
        return {
            "name": "data_assistant_plan",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "assistant_message": {"type": "string"},
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": list(ACTION_TYPES)},
                                "chart_type": {
                                    "type": ["string", "null"],
                                    "enum": [*CHART_TYPES, None],
                                },
                                "x_column": {"type": ["string", "null"]},
                                "y_column": {"type": ["string", "null"]},
                            },
                            "required": ["type", "chart_type", "x_column", "y_column"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["assistant_message", "actions"],
                "additionalProperties": False,
            },
        }

    # --- Разбор ответа ---

    def _parse_plan(self, raw_text: str) -> AIPlan:
        text = (raw_text or "").strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            text = text.removeprefix("json").strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Model returned non-JSON output; falling back to plain text")
            return AIPlan(assistant_message=text or "Не удалось разобрать ответ модели.", actions=[])

        assistant_message = str(payload.get("assistant_message", "")).strip()
        if not assistant_message:
            assistant_message = "Готово. Я обработал запрос."

        actions: list[dict[str, Any]] = []
        for item in payload.get("actions", []):
            if not isinstance(item, dict):
                continue
            action_type = str(item.get("type", "")).strip()
            if action_type not in ACTION_TYPES_SET:
                continue
            normalized = {"type": action_type}
            if action_type == "generate_chart":
                chart_type = str(item.get("chart_type", "bar")).strip().lower()
                normalized["chart_type"] = chart_type if chart_type in CHART_TYPES_SET else "bar"
                normalized["x_column"] = self._clean_optional_text(item.get("x_column"))
                normalized["y_column"] = self._clean_optional_text(item.get("y_column"))
            actions.append(normalized)

        return AIPlan(assistant_message=assistant_message, actions=actions[:4])

    def _clean_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _image_data_url(self, stored_file: StoredFile) -> str:
        mime_type = stored_file.content_type or "image/png"
        encoded = base64.b64encode(stored_file.path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"