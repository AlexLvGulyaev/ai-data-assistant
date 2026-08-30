"""Аутентификация общего пароля (APP_PASSWORD) — cookie-сессия и middleware.

Модель доступа — один общий пароль приложения (демо-режим): знающий пароль —
легитимный пользователь; изоляции пользователей и персональных сессий нет.

Cookie `ada_session` = "<issued_ts>.<HMAC-SHA256(secret, issued_ts)>", где
secret = SHA-256(APP_PASSWORD). Пароль нигде не хранится и не передаётся после
логина: подделать issued_ts нельзя без секрета, смена пароля инвалидирует все
сессии (меняется секрет), сессия протухает по возрасту issued_ts.

Пустой/незаданный APP_PASSWORD — аутентификация выключена, прежнее поведение
открытого демо. /admin не exempt: HTTP Basic (ADMIN_TOKEN) остаётся вторым
фактором поверх общего пароля.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

SESSION_COOKIE = "ada_session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 дней

# Пути, доступные без пароля: healthcheck (Docker/Traefik), сама страница
# логина и статика (CSS/JS нужны странице логина). /login/logout — GET/POST.
EXEMPT_PATHS = ("/health", "/login", "/logout", "/favicon.ico")
EXEMPT_PREFIXES = ("/static",)


def _session_secret(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()


def issue_session_token(password: str, issued_at: int | None = None) -> str:
    issued = int(issued_at if issued_at is not None else time.time())
    signature = hmac.new(
        _session_secret(password), str(issued).encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{issued}.{signature}"


def verify_session_token(
    password: str, token: str, max_age: int = SESSION_MAX_AGE_SECONDS
) -> bool:
    try:
        issued_text, signature = token.split(".", 1)
        issued = int(issued_text)
    except ValueError:
        return False
    expected = hmac.new(
        _session_secret(password), issued_text.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    return 0 <= time.time() - issued <= max_age


def safe_next_url(raw: str | None) -> str:
    """Валидный внутренний редирект: только относительный путь внутри «/»."""
    if not raw or not raw.startswith("/"):
        return "/"
    return "/" + raw.lstrip("/")


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """Общий пароль на весь UI чата (чат, загрузки, /storage, артефакты).

    GET-навигация без валидной сессии — 303 на /login?next=…; API/htmx-запросы
    (не-GET и HX-Request) — 401 JSON (htmx/fetch редиректы не следуют).
    """

    def __init__(self, app: Any, settings: Any) -> None:
        super().__init__(app)
        self._settings = settings

    def _is_exempt(self, path: str) -> bool:
        return path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES)

    async def dispatch(self, request, call_next):  # type: ignore[override]
        password = self._settings.app_password
        if not password or self._is_exempt(request.url.path):
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE, "")
        if verify_session_token(password, token):
            return await call_next(request)

        if request.method == "GET" and request.headers.get("HX-Request") != "true":
            next_url = quote(request.url.path, safe="/")
            return RedirectResponse(url=f"/login?next={next_url}", status_code=303)
        return JSONResponse(
            {"detail": "Требуется вход: откройте страницу приложения и войдите с паролем."},
            status_code=401,
        )