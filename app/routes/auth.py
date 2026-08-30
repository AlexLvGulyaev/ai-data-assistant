from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    issue_session_token,
    safe_next_url,
    verify_session_token,
)
from app.core.config import get_settings

settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))

router = APIRouter()


@router.get("/login")
async def login_page(request: Request, next: str = "/"):
    """Страница входа по общему паролю.

    Без APP_PASSWORD пароль не нужен — сразу в чат. /health доступен без
    пароля (exempt в middleware), поэтому Docker healthcheck не логинится.
    Уже залогиненный пользователь — тоже сразу в чат (target страницы /login).
    """
    if not settings.app_password:
        return RedirectResponse(url="/", status_code=303)
    if verify_session_token(settings.app_password, request.cookies.get(SESSION_COOKIE, "")):
        return RedirectResponse(url=safe_next_url(next), status_code=303)
    context = _login_context(request, next_url=next, error_message=None)
    return templates.TemplateResponse("login.html", context)


@router.post("/login")
async def login_submit(request: Request, password: str = Form(default=""), next: str = Form(default="/")):
    if not settings.app_password or secrets.compare_digest(
        password.encode("utf-8"), settings.app_password.encode("utf-8")
    ):
        response = RedirectResponse(url=safe_next_url(next), status_code=303)
        secure_cookie = request.url.scheme == "https"
        response.set_cookie(
            SESSION_COOKIE,
            issue_session_token(settings.app_password),
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=secure_cookie,
            path="/",
        )
        return response
    context = _login_context(
        request, next_url=next, error_message="Неверный пароль. Попробуйте ещё раз."
    )
    return templates.TemplateResponse("login.html", context, status_code=401)


@router.get("/logout")
async def logout():
    """Выход: сброс cookie сессии (пароль можно не менять)."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def _login_context(request: Request, next_url: str, error_message: str | None) -> dict[str, Any]:
    return {
        "request": request,
        "page_title": "Вход | Data Assistant",
        "next_url": safe_next_url(next_url),
        "error_message": error_message,
    }