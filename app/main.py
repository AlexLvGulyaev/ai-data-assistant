from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.auth import PasswordAuthMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.routes.actions import router as actions_router
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.pages import router as pages_router
from app.routes.upload import router as upload_router
from app.services.file_service import FileService
from app.services.registry_runtime import RegistryRuntime
from app.services.runtime_config import RuntimeConfig


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    FileService(settings).ensure_storage()
    # Засеять config.json дефолтами из DEFAULTS при первом старте — это делает
    # storage/config.json единым SOT операторских параметров (без дублирования
    # в .env). Идемпотентно: существующие ключи не трогаются.
    RuntimeConfig(settings).ensure_initialized()
    # Аналогично — реестры агента (типы графиков с рецептами + лейблы действий):
    # seed из registries.py → storage/registries.json, дальше — runtime.
    RegistryRuntime(settings).ensure_initialized()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
# Общий пароль (APP_PASSWORD) на весь UI чата: пусто — выключено (открытый
# демо-режим). /admin не exempt — HTTP Basic остаётся вторым фактором.
app.add_middleware(PasswordAuthMiddleware, settings=settings)
app.include_router(auth_router)
app.include_router(pages_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(actions_router)
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.mount("/storage", StaticFiles(directory=str(settings.storage_dir)), name="storage")
