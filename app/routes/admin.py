from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

from app.core.config import get_settings
from app.services.runtime_config import RUNTIME_KEYS, RuntimeConfig


logger = logging.getLogger(__name__)

settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))

# Один общий экземпляр runtime-конфига для админки. Сервисы (ai_service,
# file_service) держат свои экземпляры, но все читают один и тот же JSON-файл
# через mtime-кеш — запись здесь видна им на следующем запросе без рестарта.
runtime = RuntimeConfig(settings)

security = HTTPBasic(auto_error=False)

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Метаданные операторских параметров для UI ---

PARAM_META: dict[str, dict[str, Any]] = {
    "assistant_specialization": {
        "label": "Специализация ассистента",
        "hint": "Роль/профиль ассистента в системном промпте. Применяется на следующем запросе.",
        "kind": "text",
    },
    "provider_name": {
        "label": "Имя провайдера (для промпта)",
        "hint": "Отображаемое имя провайдера в контенте. Пусто — нейтрально (без упоминания).",
        "kind": "text",
        "placeholder": "(пусто = нейтрально)",
    },
    "openai_model": {
        "label": "Модель",
        "hint": "Имя модели провайдера, например gpt-5-mini, gigachat-pro.",
        "kind": "text",
    },
    "openai_base_url": {
        "label": "Endpoint провайдера (base_url)",
        "hint": "OpenAI-совместимый endpoint. Смена применяет новый клиент на следующем запросе.",
        "kind": "text",
    },
    "structured_output": {
        "label": "Structured output (json_schema)",
        "hint": "Вкл — строгий контракт ответа (для поддерживающих провайдеров). Выкл — свободный ответ с устойчивым парсером.",
        "kind": "bool",
    },
    "openai_max_history_messages": {
        "label": "Сообщений истории в запросе",
        "hint": "Сколько последних сообщений чата передаётся в модель.",
        "kind": "int",
    },
    "max_file_size": {
        "label": "Лимит размера файла",
        "hint": "Например 10MB, 5MB. Применяется к следующей загрузке.",
        "kind": "text",
    },
}

# Порядок вывода в UI.
PARAM_ORDER = list(RUNTIME_KEYS)


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


def _ordered_params() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current = runtime.as_dict()
    for key in PARAM_ORDER:
        meta = PARAM_META.get(key, {"label": key, "hint": "", "kind": "text"})
        value = current.get(key)
        rows.append(
            {
                "key": key,
                "label": meta["label"],
                "hint": meta["hint"],
                "kind": meta["kind"],
                "placeholder": meta.get("placeholder", ""),
                "value": value,
                "display": _display_value(value),
            }
        )
    return rows


def _display_value(value: Any) -> str:
    if value is None:
        return "— (по умолчанию / нейтрально)"
    if isinstance(value, bool):
        return "Вкл" if value else "Выкл"
    return str(value)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_panel(request: Request, _: None = Depends(_require_admin)):
    context = {
        "request": request,
        "page_title": "Админка оператора | Data Assistant",
        "params": _ordered_params(),
        "runtime_config_path": str(runtime.path),
        "admin_enabled": True,
        "status_message": None,
        "status_kind": None,
    }
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse("partials/admin_content.html", context)
    return templates.TemplateResponse("admin.html", context)


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