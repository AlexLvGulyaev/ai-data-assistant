from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field, model_validator
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
    """Конфигурация приложения.

    Bootstrap-параметры (стартовые, замораживаются при старте процесса):
    хост/порт, пути к каталогам, источник runtime-конфига, ключ и endpoint
    провайдера модели, каталог промптов. Операторские параметры, которые
    предполагается менять в runtime без рестарта (специализация, модель,
    лимиты, дефолты графиков), читаются из runtime-config provider'а
    (см. app/services/runtime_config.py) — здесь хранятся только их значения
    по умолчанию.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    # --- Базовые настройки приложения ---
    app_name: str = Field(default="Data Assistant", alias="APP_NAME")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    # --- Хранилища и пути ---
    max_file_size: str = Field(default="10MB", alias="MAX_FILE_SIZE")
    upload_dir: Path = Field(default=Path("storage/uploads"), alias="UPLOAD_DIR")
    output_dir: Path = Field(default=Path("storage/outputs"), alias="OUTPUT_DIR")
    storage_dir: Path = Field(default=Path("storage"), alias="STORAGE_DIR")
    templates_dir: Path = Field(default=Path("templates"), alias="TEMPLATES_DIR")
    static_dir: Path = Field(default=Path("static"), alias="STATIC_DIR")

    # --- Логирование ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Провайдер модели (B: base_url -> портабельность) ---
    # Поля названы openai_* для совместимости с env, но провайдер может быть
    # любым совместимым (GigaChat, YandexGPT, Gemini и т.п.) через OPENAI_BASE_URL.
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_max_history_messages: int = Field(default=8, alias="OPENAI_MAX_HISTORY_MESSAGES")
    # Отображаемое имя провайдера для промпта/greeting. None = нейтрально
    # (без упоминания провайдера в контенте), что корректно для любого провайдера.
    provider_name: str | None = Field(default=None, alias="PROVIDER_NAME")
    # Structured output через json_schema. True для провайдеров, поддерживающих
    # OpenAI-style structured output (OpenAI, совместимые). Для провайдеров без
    # поддержки (некоторые альтернативы) оператор выставляет False — тогда запрос
    # уходит без response_format, а ответ парсится устойчивым парсером.
    structured_output: bool = Field(default=True, alias="STRUCTURED_OUTPUT")

    # --- Промпты и специализация (A: промпт в версионированный файл) ---
    prompts_dir: Path = Field(default=Path("prompts"), alias="PROMPTS_DIR")
    assistant_specialization: str = Field(
        default="AI Data Assistant — аналитик данных общего профиля",
        alias="ASSISTANT_SPECIALIZATION",
    )

    # --- Runtime-config (вариант 3: операторские параметры без рестарта) ---
    runtime_config_path: Path = Field(
        default=Path("storage/config.json"), alias="RUNTIME_CONFIG_PATH"
    )

    # --- Админка оператора (вариант 3) ---
    # Токен доступа к /admin. None — админка отключена (403). Передаётся через
    # HTTP Basic (пользователь `admin`, пароль = токен) — браузер сам держит
    # сессию, отдельная страница логина не нужна.
    admin_token: str | None = Field(default=None, alias="ADMIN_TOKEN")

    @computed_field  # type: ignore[misc]
    @property
    def max_file_size_bytes(self) -> int:
        return parse_size_to_bytes(self.max_file_size)

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