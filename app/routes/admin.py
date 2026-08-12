from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

from app.core.config import get_settings
from app.services.ai_service import AIService
from app.services.prompt_loader import PromptLoader
from app.services.registries import (
    PRESET_FIELD_MAP,
    PROVIDER_ORDER,
    PROVIDER_PRESETS,
)
from app.services.runtime_config import RUNTIME_KEYS, RuntimeConfig
from app.services.usage_service import UsageService


logger = logging.getLogger(__name__)

settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))

# Один общий экземпляр runtime-конфига для админки. Сервисы (ai_service,
# file_service) держат свои экземпляры, но все читают один и тот же JSON-файл
# через mtime-кеш — запись здесь видна им на следующем запросе без рестарта.
runtime = RuntimeConfig(settings)
# PromptLoader — для редактора системного промпта: читает/пишет файл
# prompts/v1/system.md (единый SOT текста промпта).
prompt_loader = PromptLoader(settings)
# ai_service для диагностического теста провайдера и usage_service для dashboard
# статистики — каждый читает/пишет свои файлы в storage/ (общие с экземплярами
# в pages.py через mtime-кеш).
ai_service = AIService(settings)
usage_service = UsageService(settings)

security = HTTPBasic(auto_error=False)

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Метаданные операторских параметров для UI ---
# `help` — подробный комментарий, показываемый тултипом при наведении на лейбл
# (паттерн AI Curator: .admin-tooltip/.admin-tooltip__text, чистый CSS).

PARAM_META: dict[str, dict[str, Any]] = {
    "assistant_specialization": {
        "label": "Специализация",
        "kind": "text",
        "help": "Роль/профиль ассистента. Подставляется в системный промпт на место "
        "{{specialization}} — задаёт тон и область экспертизы. Применяется на "
        "следующем запросе без рестарта.",
    },
    "provider": {
        "label": "Провайдер",
        "kind": "preset",
        "help": "Пресет провайдера модели: OpenAI (эталон, drop-in), GigaChat (Сбер, "
        "OAuth-адаптер), YandexGPT (folder_id + header) или «Свой» (любой "
        "OpenAI-совместимый endpoint). Выбор пресета заполняет endpoint, модель, "
        "имя и флаг structured_output. Секреты — в .env.",
    },
    "provider_name": {
        "label": "Имя провайдера",
        "kind": "text",
        "placeholder": "(пусто = нейтрально)",
        "help": "Отображаемое имя провайдера. Подставляется в системный промпт на место "
        "{{provider_attribution}} как « от <имя>». Пусто — промпт не упоминает "
        "провайдера (нейтрально). На сам запрос к модели не влияет, только на текст.",
    },
    "openai_model": {
        "label": "Модель",
        "kind": "text",
        "help": "Имя модели. OpenAI: gpt-5-mini, gpt-4o-mini и т.п. GigaChat: GigaChat-Max, "
        "GigaChat-Pro. YandexGPT: URI вида gpt://<folder_id>/yandexgpt/latest — "
        "folder_id подставляется автоматически из одноимённого параметра.",
    },
    "openai_base_url": {
        "label": "Endpoint (base_url)",
        "kind": "text",
        "help": "OpenAI-совместимый endpoint провайдера. Для GigaChat это адрес API "
        "(OAuth-обмен идёт отдельно в адаптере). Смена применяется на следующем "
        "запросе — клиент пересоздаётся автоматически.",
    },
    "structured_output": {
        "label": "Structured output",
        "kind": "bool",
        "help": "Вкл — модель отвечает по строгой json_schema (действия и графики — из "
        "реестров). Поддерживают OpenAI и «Свой». Выкл — свободный текст, разбирается "
        "устойчивым парсером. GigaChat и YandexGPT не поддерживают json_schema strict "
        "— для них пресет выключает этот флаг.",
    },
    "openai_temperature": {
        "label": "Температура",
        "kind": "float",
        "help": "Креативность ответа 0–2. Отправляется ТОЛЬКО если явно задана (не "
        "сброшена). Важно: gpt-5-mini и ряд моделей принимают только умолчательную "
        "температуру — при заданном значении они отвергают запрос. Если не уверены — "
        "сбросьте (пусто).",
    },
    "openai_seed": {
        "label": "Seed",
        "kind": "int",
        "placeholder": "(пусто = не задавать)",
        "help": "Целое число для воспроизводимости ответов. Поддерживают не все "
        "провайдеры. Пусто — параметр не отправляется, провайдер использует своё "
        "умолчание.",
    },
    "openai_max_history_messages": {
        "label": "История в запросе",
        "kind": "int",
        "help": "Сколько последних сообщений чата передаётся в модель вместе с текущим "
        "запросом. Больше — контекстнее ответ, но дороже по токенам.",
    },
    "max_file_size": {
        "label": "Лимит файла",
        "kind": "text",
        "help": "Максимальный размер загружаемого файла (например 10MB, 5MB). "
        "Применяется к следующей загрузке.",
    },
    "yandex_folder_id": {
        "label": "Yandex folder_id",
        "kind": "text",
        "placeholder": "(только для YandexGPT)",
        "help": "Идентификатор каталога (folder) Yandex Cloud. Нужен только для пресета "
        "YandexGPT: подставляется в URI модели и в заголовок x-folder-id. Без него "
        "YandexGPT не работает. Для остальных провайдеров игнорируется.",
    },
}

# Поля, живущие в секции «Провайдер» (заполняются пресетом, но редактируются и
# по отдельности). Порядок = порядок вывода.
PROVIDER_FIELD_KEYS: tuple[str, ...] = (
    "openai_model",
    "openai_base_url",
    "provider_name",
    "structured_output",
)
# Поля компактной сетки операторских параметров (справа под секцией провайдера).
GENERAL_FIELD_KEYS: tuple[str, ...] = (
    "assistant_specialization",
    "openai_temperature",
    "openai_seed",
    "openai_max_history_messages",
    "max_file_size",
    "yandex_folder_id",
)
# Все ключи, кроме `provider` (он редактируется пресетами, не как обычное поле).
PARAM_ORDER = [k for k in RUNTIME_KEYS if k != "provider"]


def _require_admin(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    """Доступ к админке. Если ADMIN_TOKEN не задан — панель отключена (403).
    Иначе требуется HTTP Basic (пользователь `admin`, пароль = токен)."""
    token = settings.admin_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Админка отключена: задайте ADMIN_TOKEN в .env для доступа к /admin.",
        )
    if credentials is None or credentials.username != "admin" or credentials.password != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин/пароль.",
            headers={"WWW-Authenticate": "Basic"},
        )


def _param_row(key: str) -> dict[str, Any]:
    """Собрать строку-описание параметра для рендера карточки в UI."""
    meta = PARAM_META.get(key, {"label": key, "kind": "text"})
    value = runtime.get(key)
    return {
        "key": key,
        "label": meta["label"],
        "help": meta.get("help", ""),
        "kind": meta["kind"],
        "placeholder": meta.get("placeholder", ""),
        "value": value,
        "display": _display_value(value),
    }


def _param_rows(keys) -> list[dict[str, Any]]:
    return [_param_row(key) for key in keys]


def _provider_presets() -> list[dict[str, Any]]:
    """Список пресетов для чипов с пометкой активного."""
    active = runtime.get("provider")
    rows: list[dict[str, Any]] = []
    for key in PROVIDER_ORDER:
        preset = PROVIDER_PRESETS[key]
        rows.append(
            {
                "key": key,
                "label": preset["label"],
                "active": key == active,
            }
        )
    return rows


def _provider_section_context() -> dict[str, Any]:
    return {
        "provider_presets": _provider_presets(),
        "provider_fields": _param_rows(PROVIDER_FIELD_KEYS),
        "provider": runtime.get("provider"),
    }


def _display_value(value: Any) -> str:
    if value is None:
        return "— (по умолчанию / нейтрально)"
    if isinstance(value, bool):
        return "Вкл" if value else "Выкл"
    text = str(value)
    if len(text) > 80:
        return f"{text[:77]}…"
    return text


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_panel(request: Request, _: None = Depends(_require_admin)):
    context = {
        "request": request,
        "page_title": "Админка оператора | Data Assistant",
        "general_params": _param_rows(GENERAL_FIELD_KEYS),
        "runtime_config_path": str(runtime.path),
        "prompt_text": prompt_loader.read_system_prompt_raw(),
        "prompt_path": str(prompt_loader.system_prompt_path()),
        "usage": usage_service.as_dict(),
        "usage_path": str(usage_service.path),
        "admin_enabled": True,
        "status_message": None,
        "status_kind": None,
        **_provider_section_context(),
    }
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse("partials/admin_content.html", context)
    return templates.TemplateResponse("admin.html", context)


@router.post("/provider", response_class=HTMLResponse)
async def admin_apply_preset(
    request: Request,
    preset: str = Form(...),
    _: None = Depends(_require_admin),
):
    """Применить пресет провайдера: записать `provider` + 4 поля (endpoint,
    модель, имя, structured_output) из реестра пресетов в config.json.

    Перерисовывает секцию «Провайдер» целиком (активный чип + новые значения
    полей). Применяется на следующем запросе без рестарта.
    """
    if preset not in PROVIDER_PRESETS:
        return templates.TemplateResponse(
            "partials/admin_status.html",
            {
                "request": request,
                "status_message": f"Неизвестный пресет: {preset}",
                "status_kind": "error",
            },
        )
    data = PROVIDER_PRESETS[preset]
    try:
        runtime.set("provider", preset)
        for runtime_key, preset_key in PRESET_FIELD_MAP.items():
            runtime.set(runtime_key, data[preset_key])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Admin preset apply failed (%s): %s", preset, exc)
        return templates.TemplateResponse(
            "partials/admin_status.html",
            {
                "request": request,
                "status_message": f"Ошибка применения пресета «{data['label']}»: {exc}",
                "status_kind": "error",
            },
        )
    label = data["label"]
    return templates.TemplateResponse(
        "partials/admin_provider.html",
        {
            "request": request,
            "provider_status_message": (
                f"Применён пресет «{label}». Endpoint, модель, имя и "
                f"structured_output обновлены. Применится на следующем запросе."
            ),
            "provider_status_kind": "ok",
            **_provider_section_context(),
        },
    )


@router.post("/test", response_class=HTMLResponse)
async def admin_test_provider(request: Request, _: None = Depends(_require_admin)):
    """Диагностический тест провайдера: пинг текущего base_url+model.
    Не пишет в статистику использования (см. AIService.test_connection)."""
    result = ai_service.test_connection()
    if result.get("ok"):
        message = (
            f"✓ Провайдер отвечает. Модель «{result.get('model')}» "
            f"({result.get('base_url')}), латентность {result.get('latency_ms')} мс. "
            f"Ответ: «{result.get('reply')}»."
        )
        status_kind = "ok"
    else:
        message = (
            f"✕ Провайдер недоступен. Модель «{result.get('model')}» "
            f"({result.get('base_url')}): {result.get('error')}"
        )
        status_kind = "error"
    return templates.TemplateResponse(
        "partials/admin_status.html",
        {
            "request": request,
            "status_message": message,
            "status_kind": status_kind,
        },
    )


@router.post("/prompt", response_class=HTMLResponse)
async def admin_save_prompt(
    request: Request,
    content: str = Form(...),
    _: None = Depends(_require_admin),
):
    """Сохранить системный промпт в файл prompts/v1/system.md (единый SOT).

    Запись идёт напрямую в файл-источник истины (не в config.json).
    Применяется на следующем запросе через mtime-кеш PromptLoader'а.
    """
    try:
        prompt_loader.write_system_prompt(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Admin prompt save failed: %s", exc)
        return templates.TemplateResponse(
            "partials/admin_status.html",
            {
                "request": request,
                "status_message": f"Ошибка сохранения промпта: {exc}",
                "status_kind": "error",
            },
        )
    return templates.TemplateResponse(
        "partials/admin_status.html",
        {
            "request": request,
            "status_message": "Системный промпт сохранён. Применится на следующем запросе без рестарта.",
            "status_kind": "ok",
            "updated_key": "__prompt__",
        },
    )


@router.post("/update", response_class=HTMLResponse)
async def admin_update(
    request: Request,
    key: str = Form(...),
    value: str = Form(""),
    _: None = Depends(_require_admin),
):
    if key not in RUNTIME_KEYS:
        return templates.TemplateResponse(
            "partials/admin_status.html",
            {
                "request": request,
                "status_message": f"Неизвестный параметр: {key}",
                "status_kind": "error",
            },
        )
    label = PARAM_META.get(key, {}).get("label", key)
    try:
        coerced = runtime.set(key, value)
    except Exception as exc:  # noqa: BLE001 - любая ошибка coerce/записи показывается оператору
        logger.warning("Admin update failed for %s: %s", key, exc)
        return templates.TemplateResponse(
            "partials/admin_status.html",
            {
                "request": request,
                "status_message": f"Ошибка сохранения «{label}»: {exc}",
                "status_kind": "error",
            },
        )

    return templates.TemplateResponse(
        "partials/admin_status.html",
        {
            "request": request,
            "status_message": f"«{label}» → {_display_value(coerced)}. Применится на следующем запросе без рестарта.",
            "status_kind": "ok",
            "updated_key": key,
            "updated_display": _display_value(coerced),
        },
    )


@router.post("/reset", response_class=HTMLResponse)
async def admin_reset(
    request: Request,
    key: str = Form(...),
    _: None = Depends(_require_admin),
):
    """Сброс параметра к значению по умолчанию (удаление ключа из файла)."""
    if key not in RUNTIME_KEYS:
        return templates.TemplateResponse(
            "partials/admin_status.html",
            {
                "request": request,
                "status_message": f"Неизвестный параметр: {key}",
                "status_kind": "error",
            },
        )
    label = PARAM_META.get(key, {}).get("label", key)
    try:
        default_value = runtime.reset(key)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            "partials/admin_status.html",
            {
                "request": request,
                "status_message": f"Ошибка сброса «{label}»: {exc}",
                "status_kind": "error",
            },
        )
    return templates.TemplateResponse(
        "partials/admin_status.html",
        {
            "request": request,
            "status_message": f"«{label}» сброшен к умолчанию: {_display_value(default_value)}.",
            "status_kind": "ok",
            "updated_key": key,
            "updated_display": _display_value(default_value),
            "reset_key": key,
        },
    )