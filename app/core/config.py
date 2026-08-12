from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Корневой каталог проекта. В Docker это WORKDIR /app.
BASE_DIR = Path(__file__).resolve().parents[2]

_SIZE_PATTERN = re.compile(r"^\s*(\d+)\s*(B|KB|MB|GB)?\s*$", re.IGNORECASE)
_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}


def parse_size_to_bytes(raw_value: str) -> int:
    match = _SIZE_PATTERN.match(raw_value or "")
    if not match:
        raise ValueError(f"Invalid size format: {raw_value!r}")
    amount = int(match.group(1))
    unit = (match.group(2) or "B").upper()
    return amount * _SIZE_UNITS[unit]


class Settings(BaseSettings):
    """Конфигурация приложения — ТОЛЬКО секреты и bootstrap.

    Здесь живут только параметры, которыми реально управляет окружение
    процесса (`.env`): секреты (OPENAI_API_KEY, ADMIN_TOKEN) и bootstrap
    (хост/порт, логирование, пути к каталогам, путь к runtime-конфигу).
    Все они требуют рестарта процесса при смене.

    Операторские параметры (специализация, модель, endpoint, температура,
    лимиты файла и т.п.) единственным источником истины имеют
    `storage/config.json` (см. app/services/runtime_config.py): начальные
    значения сеются из хардкоженного DEFAULTS при первом старте, дальше
    оператор правит их через `/admin` или файлом — без рестарта. В `.env`
    операторских параметров НЕТ — это намеренно (одна точка правки).
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    # --- Базовые настройки приложения (bootstrap) ---
    app_name: str = Field(default="Data Assistant", alias="APP_NAME")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Хранилища и пути (bootstrap) ---
    upload_dir: Path = Field(default=Path("storage/uploads"), alias="UPLOAD_DIR")
    output_dir: Path = Field(default=Path("storage/outputs"), alias="OUTPUT_DIR")
    storage_dir: Path = Field(default=Path("storage"), alias="STORAGE_DIR")
    templates_dir: Path = Field(default=Path("templates"), alias="TEMPLATES_DIR")
    static_dir: Path = Field(default=Path("static"), alias="STATIC_DIR")

    # --- Промпты (bootstrap): каталог версионированных промптов ---
    # Сам системный промпт — файл prompts/v1/system.md — единственный SOT
    # текста промпта; оператор правит его напрямую (через `/admin` или файлом).
    prompts_dir: Path = Field(default=Path("prompts"), alias="PROMPTS_DIR")

    # --- Runtime-config (bootstrap): путь к JSON операторских параметров ---
    runtime_config_path: Path = Field(
        default=Path("storage/config.json"), alias="RUNTIME_CONFIG_PATH"
    )

    # --- Секреты (только .env, рестарт) ---
    # Поля названы openai_* для совместимости с env, но провайдер может быть
    # любым совместимым (GigaChat, YandexGPT, Gemini и т.п.) — endpoint/model
    # задаются оператором в runtime-конфиге, здесь — только секрет.
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    # Токен доступа к /admin. None — админка отключена (403). Передаётся через
    # HTTP Basic (пользователь `admin`, пароль = токен) — браузер сам держит
    # сессию, отдельная страница логина не нужна.
    admin_token: str | None = Field(default=None, alias="ADMIN_TOKEN")

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        """Приводим относительные пути к абсолютным относительно BASE_DIR."""
        for name in (
            "upload_dir",
            "output_dir",
            "storage_dir",
            "templates_dir",
            "static_dir",
            "prompts_dir",
            "runtime_config_path",
        ):
            value = getattr(self, name)
            if not value.is_absolute():
                setattr(self, name, (BASE_DIR / value))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()