from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.services.file_service import StoredFile
from app.services.gigachat_adapter import GigaChatAdapter, GigaChatError
from app.services.prompt_loader import PromptLoader
from app.services.registries import (
    ACTION_TYPES,
    ACTION_TYPES_SET,
    PROVIDER_PRESETS,
)
from app.services.registry_runtime import RegistryRuntime
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

    Мультипровайдерный: провайдер выбирается пресетом в runtime-конфиге
    (`provider` — openai/gigachat/yandex/custom). Маршрутизация:
      - openai / yandex / custom — OpenAI SDK (для yandex добавляются
        default_headers `x-folder-id` + подстановка folder_id в модель);
      - gigachat — GigaChat-адаптер (OAuth-обмен authorization key на access
        token per-request; без structured_output — ответ парсится устойчивым
        парсером free-text).

    Промпт грузится из версионированного файла через `PromptLoader` — единый
    SOT текста промпта, правка применяется в runtime без рестарта. Контракт
    ответа (structured output через json_schema) генерируется из реестров
    (действия — код, `ACTION_TYPES`; типы графиков — runtime-реестр
    `storage/registries.json`) — единый источник истины, AI не может вернуть
    действие/график, который приложение не умеет исполнять. Для провайдеров без
    structured output оператор отключает `STRUCTURED_OUTPUT`, и ответ парсится
    устойчивым парсером.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        usage_service: UsageService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = None
        self._client_signature: tuple[str, ...] | None = None
        self._gigachat: GigaChatAdapter | None = None
        self._gigachat_signature: tuple[str, ...] | None = None
        self._runtime = RuntimeConfig(self.settings)
        # Runtime-реестры (типы графиков enum'ом в контракт модели; лейблы
        # действий) — mtime-кеш, правка через /admin видна на след. запросе.
        self._registry = RegistryRuntime(self.settings)
        # PromptLoader читает сам файл промпта (единственный SOT); runtime-конфиг
        # держит только операторские параметры для интерполяции шаблона.
        self._prompt_loader = PromptLoader(self.settings)
        self._usage = usage_service

    @property
    def enabled(self) -> bool:
        provider = self._provider()
        if provider == "gigachat":
            return bool(self.settings.gigachat_auth_key)
        # openai / yandex / custom — OpenAI SDK + api_key (для yandex это
        # API-ключ Yandex как Bearer; folder_id — отдельный runtime-ключ).
        return bool(self.settings.openai_api_key) and OpenAI is not None

    @property
    def model_name(self) -> str:
        return self._runtime.get("openai_model")

    @property
    def provider_name(self) -> str:
        # Отображаемое имя провайдера (из runtime/presета). Пусто для «Своего»
        # без имени — тогда UI показывает нейтральный fallback («AI»).
        return self._runtime.get("provider_name") or ""

    def _provider(self) -> str:
        return self._runtime.get("provider")

    def _preset(self) -> dict[str, Any]:
        return PROVIDER_PRESETS[self._provider()]

    def _is_gigachat(self) -> bool:
        return self._provider() == "gigachat"

    def _effective_model(self) -> str:
        """Текущая модель с подстановкой Yandex folder_id в плейсхолдер."""
        model = self._runtime.get("openai_model")
        if self._provider() == "yandex" and "<folder_id>" in model:
            folder_id = self._runtime.get("yandex_folder_id")
            if folder_id:
                return model.replace("<folder_id>", str(folder_id))
        return model

    def plan_response(
        self,
        *,
        conversation_messages: list[dict[str, Any]],
        user_text: str,
        active_file: StoredFile | None,
        active_file_context: dict[str, Any] | None,
    ) -> AIPlan:
        provider = self._provider()
        if provider == "gigachat":
            return self._plan_via_gigachat(
                conversation_messages=conversation_messages,
                user_text=user_text,
                active_file=active_file,
                active_file_context=active_file_context,
            )
        return self._plan_via_openai(
            conversation_messages=conversation_messages,
            user_text=user_text,
            active_file=active_file,
            active_file_context=active_file_context,
        )

    # --- OpenAI SDK путь (openai / yandex / custom) ---

    def _plan_via_openai(
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

        client = self._get_openai_client()
        messages = self._build_messages(
            conversation_messages=conversation_messages,
            user_text=user_text,
            active_file=active_file,
            active_file_context=active_file_context,
        )
        request_kwargs: dict[str, Any] = {
            "model": self._effective_model(),
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
            "Model plan received with %s actions (structured_output=%s, model=%s, provider=%s)",
            len(plan.actions),
            self._runtime.get("structured_output"),
            self._runtime.get("openai_model"),
            self._provider(),
        )
        return plan

    def _get_openai_client(self):
        """OpenAI SDK клиент. Пересоздаётся при смене endpoint/провайдера/folder_id.

        Для yandex добавляются default_headers (`x-folder-id`, `x-data-logging-
        enabled: false`) — folder_id берётся из runtime-ключа `yandex_folder_id`.
        """
        base_url = self._runtime.get("openai_base_url")
        provider = self._provider()
        folder_id = self._runtime.get("yandex_folder_id") if provider == "yandex" else None
        signature = (base_url, provider, folder_id or "")
        if self._client is None or self._client_signature != signature:
            default_headers: dict[str, str] | None = None
            if provider == "yandex" and folder_id:
                default_headers = {
                    "x-folder-id": str(folder_id),
                    "x-data-logging-enabled": "false",
                }
            self._client = OpenAI(
                api_key=self.settings.openai_api_key,
                base_url=base_url,
                default_headers=default_headers,
            )
            self._client_signature = signature
        return self._client

    # --- GigaChat путь (OAuth-адаптер, без structured_output) ---

    def _get_gigachat_adapter(self) -> GigaChatAdapter:
        preset = self._preset()
        base_url = self._runtime.get("openai_base_url") or preset["base_url"]
        signature = (base_url, preset["token_url"], preset["scope"])
        if self._gigachat is None or self._gigachat_signature != signature:
            self._gigachat = GigaChatAdapter(
                base_url=base_url,
                token_url=preset["token_url"],
                scope=preset["scope"],
                auth_key=self.settings.gigachat_auth_key or "",
                ca_bundle=self.settings.gigachat_ca_bundle,
            )
            self._gigachat_signature = signature
        return self._gigachat

    def _plan_via_gigachat(
        self,
        *,
        conversation_messages: list[dict[str, Any]],
        user_text: str,
        active_file: StoredFile | None,
        active_file_context: dict[str, Any] | None,
    ) -> AIPlan:
        if not self.settings.gigachat_auth_key:
            raise AIServiceConfigurationError(
                "Выбран провайдер GigaChat, но не задан `GIGACHAT_AUTH_KEY` в `.env`."
            )
        messages = self._build_messages(
            conversation_messages=conversation_messages,
            user_text=user_text,
            active_file=active_file,
            active_file_context=active_file_context,
        )
        # GigaChat-адаптер работает с plain-text content (без multimodal-блоков).
        messages = self._flatten_messages_for_gigachat(messages)
        temperature = self._runtime.get("openai_temperature") if self._runtime.has("openai_temperature") else None
        adapter = self._get_gigachat_adapter()
        try:
            result = adapter.chat_completions(
                model=self._runtime.get("openai_model"),
                messages=messages,
                temperature=temperature,
            )
        except GigaChatError as exc:
            logger.exception("GigaChat request failed")
            if self._usage is not None:
                self._usage.record_error(str(exc))
            raise AIServiceRequestError(str(exc)) from exc

        if self._usage is not None:
            usage = result.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens") or 0
            completion_tokens = usage.get("completion_tokens") or 0
            total_tokens = usage.get("total_tokens")
            if total_tokens is not None:
                self._usage.record_success(prompt_tokens, completion_tokens, total_tokens)
            else:
                self._usage.record_request_only()

        raw_text = result.get("content", "") or ""
        plan = self._parse_plan(raw_text)
        logger.info(
            "Model plan received with %s actions (gigachat, structured_output=False, model=%s)",
            len(plan.actions),
            self._runtime.get("openai_model"),
        )
        return plan

    def _flatten_messages_for_gigachat(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """GigaChat принимает plain-text content. Multimodal-блоки (изображения)
        превращаем в текст — GigaChat не поддерживает image_url в нашем контракте.
        """
        flat: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                flat.append({"role": message.get("role", "user"), "content": "\n".join(text_parts)})
            else:
                flat.append(message)
        return flat

    def test_connection(self) -> dict[str, Any]:
        """Диагностический пинг провайдера: минимальный Chat Completions-запрос
        к текущему (runtime) base_url+model. НЕ пишет в статистику использования.

        Маршрутизируется по провайдеру: GigaChat — через адаптер (OAuth), прочие —
        через OpenAI SDK (для yandex с default_headers). Возвращает
        {ok, model, base_url, provider, latency_ms, reply} или {ok: False, error}.
        """
        provider = self._provider()
        model = self._runtime.get("openai_model")
        base_url = self._runtime.get("openai_base_url")
        if provider == "gigachat":
            return self._test_gigachat(model=model, base_url=base_url)
        return self._test_openai(model=model, base_url=base_url)

    def _test_openai(self, *, model: str, base_url: str) -> dict[str, Any]:
        if OpenAI is None:
            return {"ok": False, "error": "Пакет `openai` не установлен.", "provider": self._provider()}
        if not self.settings.openai_api_key:
            return {"ok": False, "error": "Не задан OPENAI_API_KEY в .env.", "provider": self._provider()}
        import time

        try:
            client = self._get_openai_client()
            started = time.perf_counter()
            # Минимальный пинг: только model+messages. Без max_tokens и temperature —
            # портабельно (gpt-5-mini не принимает max_tokens и не поддерживает
            # произвольную temperature). Ответ на «ping» короткий, стоимость пренебрежима.
            response = client.chat.completions.create(
                model=self._effective_model(),
                messages=[{"role": "user", "content": "ping"}],
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            reply = (getattr(response.choices[0].message, "content", "") or "").strip()
            return {
                "ok": True,
                "provider": self._provider(),
                "model": model,
                "base_url": base_url,
                "latency_ms": latency_ms,
                "reply": reply,
            }
        except Exception as exc:  # noqa: BLE001 - диагностический перехват
            logger.warning("Provider test failed: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "provider": self._provider(),
                "model": model,
                "base_url": base_url,
            }

    def _test_gigachat(self, *, model: str, base_url: str) -> dict[str, Any]:
        if not self.settings.gigachat_auth_key:
            return {
                "ok": False,
                "error": "Выбран GigaChat, но не задан GIGACHAT_AUTH_KEY в .env.",
                "provider": "gigachat",
                "model": model,
                "base_url": base_url,
            }
        try:
            adapter = self._get_gigachat_adapter()
            result = adapter.chat_completions(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
            )
            return {
                "ok": True,
                "provider": "gigachat",
                "model": result.get("model", model),
                "base_url": base_url,
                "latency_ms": int(result.get("latency_ms", 0)),
                "reply": (result.get("content", "") or "").strip(),
            }
        except Exception as exc:  # noqa: BLE001 - диагностический перехват
            logger.warning("GigaChat test failed: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "provider": "gigachat",
                "model": model,
                "base_url": base_url,
            }

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
        """Список разрешённых действий для подсказки модели. Типы действий —
        код; enum типов графиков — из runtime-реестра."""
        actions: list[dict[str, Any]] = [
            {"type": "preview"},
            {"type": "analyze"},
            {
                "type": "generate_chart",
                "chart_type": " | ".join(self._registry.chart_type_keys()),
                "x_column": "string | null",
                "y_column": "string | null",
            },
            {"type": "generate_report"},
            {"type": "save_summary"},
        ]
        return actions

    def _build_response_schema(self) -> dict[str, Any]:
        """JSON Schema structured output. Enum'ы генерируются из реестров
        (runtime: chart_type — из реестра типов графиков)."""
        chart_types = self._registry.chart_type_keys()
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
                                    "enum": [*chart_types, None],
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
                chart_type = str(item.get("chart_type", "")).strip().lower()
                if chart_type not in self._registry.chart_types_set():
                    chart_type = self._fallback_chart_type()
                normalized["chart_type"] = chart_type
                normalized["x_column"] = self._clean_optional_text(item.get("x_column"))
                normalized["y_column"] = self._clean_optional_text(item.get("y_column"))
            actions.append(normalized)

        return AIPlan(assistant_message=assistant_message, actions=actions[:4])

    def _fallback_chart_type(self) -> str:
        """Тип графика-умолчание, если модель вернула неизвестный/пустой:
        исторический «bar», когда он есть в реестре, иначе первый тип."""
        keys = self._registry.chart_type_keys()
        return "bar" if "bar" in keys else (keys[0] if keys else "")

    def _clean_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _image_data_url(self, stored_file: StoredFile) -> str:
        mime_type = stored_file.content_type or "image/png"
        encoded = base64.b64encode(stored_file.path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"