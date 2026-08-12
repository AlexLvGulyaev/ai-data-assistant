from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


# Операторские параметры, редактируемые в runtime (через админку или прямым
# изменением файла). Секреты (OPENAI_API_KEY, ADMIN_TOKEN) сюда НЕ входят —
# они остаются в .env. Порядок = порядок вывода в админке
# (специализация → провайдер/модель → портабельность → лимиты).
RUNTIME_KEYS: tuple[str, ...] = (
    "assistant_specialization",
    "provider",
    "provider_name",
    "openai_model",
    "openai_base_url",
    "structured_output",
    "openai_temperature",
    "openai_seed",
    "openai_max_history_messages",
    "max_file_size",
    "yandex_folder_id",
)

# Единый источник истины для операторских параметров — storage/config.json.
# Начальные значения сеются из этого хардкоженного словаря при первом старте
# (ensure_initialized). Это намеренный хардкод, а не .env: одна точка правки
# умолчаний, .env не дублирует операторские параметры.
DEFAULTS: dict[str, Any] = {
    "assistant_specialization": "AI Data Assistant — аналитик данных общего профиля",
    "provider": "openai",
    "provider_name": None,
    "openai_model": "gpt-5-mini",
    "openai_base_url": "https://api.openai.com/v1",
    "structured_output": True,
    "openai_temperature": 0.0,
    "openai_seed": None,
    "openai_max_history_messages": 8,
    "max_file_size": "10MB",
    "yandex_folder_id": None,
}

# Ключи, которые всегда присутствуют в config.json после старта (always-active
# параметры). ensure_initialized сеет именно их. Опциональные (opt-in) ключи —
# provider_name, openai_temperature, openai_seed, yandex_folder_id — НЕ сеются
# и остаются отсутствующими, пока оператор их не задаст. Это нужно для
# портабельности: has("openai_temperature") возвращает False, пока температура
# не задана явно, и она НЕ отправляется в запрос — иначе провайдеры вроде
# gpt-5-mini, принимающие только умолчательную температуру, отвергают запрос.
SEEDED_KEYS: tuple[str, ...] = (
    "assistant_specialization",
    "provider",
    "openai_model",
    "openai_base_url",
    "structured_output",
    "openai_max_history_messages",
    "max_file_size",
)
OPT_IN_KEYS: tuple[str, ...] = (
    "provider_name",
    "openai_temperature",
    "openai_seed",
    "yandex_folder_id",
)


class RuntimeConfig:
    """Runtime-конфиг операторских параметров — единый SOT (вариант 3).

    Источник — JSON-файл `settings.runtime_config_path` (по умолчанию
    `storage/config.json`). Чтение с mtime-кешем: правка файла (через админку
    или файловый менеджер) применяется на следующем запросе без рестарта.

    Начальные значения сеются из хардкоженного `DEFAULTS` при первом старте
    (ensure_initialized) — только SEEDED_KEYS; opt-in ключи (temperature/seed/
    provider_name) остаются отсутствующими, пока оператор их не задаст.
    Отсутствующий ключ `get` возвращает из `DEFAULTS` (fallback), но
    `has` отличает «явно задан» от «default» — это и управляет портабельностью.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._path: Path = self.settings.runtime_config_path
        self._cache: tuple[float, dict[str, Any]] | None = None
        self._write_lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def ensure_initialized(self) -> None:
        """При первом старте (или после ручной чистки) засеять config.json
        дефолтами из DEFAULTS для SEEDED_KEYS. Идемпотентно: существующие
        ключи НЕ перезаписываются, добавляются только отсутствующие SEEDED_KEYS.
        Opt-in ключи НЕ сеются — остаются отсутствующими до явной установки.
        """
        with self._write_lock:
            data = self._read_raw()
            changed = False
            for key in SEEDED_KEYS:
                if key not in data:
                    data[key] = DEFAULTS[key]
                    changed = True
            if changed:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._cache = None
                logger.info("Runtime config initialized with defaults: %s", self._path)

    def get(self, key: str) -> Any:
        if key not in RUNTIME_KEYS:
            raise KeyError(f"Unknown runtime config key: {key}")
        data = self._read()
        if key in data:
            return data[key]
        return self._default(key)

    def has(self, key: str) -> bool:
        """True, если ключ явно присутствует в config.json (не fallback).

        Используется, чтобы отличить «оператор не задавал параметр» от «задал
        значение, совпадающее с умолчанием» — критично для портабельности:
        temperature/seed отправляются в запрос только при явной установке,
        иначе провайдер использует своё умолчание (отдельные модели не принимают
        произвольные значения). Opt-in ключи не сеются ensure_initialized,
        поэтому после чистого старта has() для них — False.
        """
        if key not in RUNTIME_KEYS:
            raise KeyError(f"Unknown runtime config key: {key}")
        return key in self._read()

    def as_dict(self) -> dict[str, Any]:
        return {key: self.get(key) for key in RUNTIME_KEYS}

    def set(self, key: str, value: Any) -> Any:
        """Записать значение в config.json. Возвращает установленное значение."""
        if key not in RUNTIME_KEYS:
            raise KeyError(f"Unknown runtime config key: {key}")
        coerced = self._coerce(key, value)
        with self._write_lock:
            data = self._read_raw()
            data[key] = coerced
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._cache = None  # инвалидировать кеш чтения
        logger.info("Runtime config updated: %s", key)
        return coerced

    def reset(self, key: str) -> Any:
        """Удалить ключ из config.json — параметр вернётся к умолчанию из DEFAULTS.

        Для opt-in ключей (temperature/seed/provider_name/yandex_folder_id)
        reset = «не задавать»: has() снова False, параметр перестаёт
        отправляться в запрос/заголовки.
        """
        if key not in RUNTIME_KEYS:
            raise KeyError(f"Unknown runtime config key: {key}")
        with self._write_lock:
            data = self._read_raw()
            data.pop(key, None)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._cache = None
        logger.info("Runtime config reset: %s", key)
        return self.get(key)

    # --- внутренние ---

    def _read(self) -> dict[str, Any]:
        try:
            mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            return {}
        cached = self._cache
        if cached and cached[0] == mtime:
            return cached[1]
        data = self._read_raw()
        self._cache = (mtime, data)
        return data

    def _read_raw(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Runtime config unreadable, using defaults: %s", self._path)
            return {}
        return data if isinstance(data, dict) else {}

    def _default(self, key: str) -> Any:
        return DEFAULTS[key]

    def _coerce(self, key: str, value: Any) -> Any:
        if key == "structured_output":
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes", "on"}
            return bool(value)
        if key == "openai_max_history_messages":
            try:
                return int(value)
            except (TypeError, ValueError):
                return self._default(key)
        if key == "openai_temperature":
            text = str(value).strip() if value is not None else ""
            if not text:
                return self._default(key)
            try:
                return max(0.0, min(2.0, float(text)))
            except ValueError:
                raise ValueError(f"Температура должна быть числом 0–2, получено: {value!r}")
        if key == "openai_seed":
            if value is None:
                return None
            text = str(value).strip()
            if not text:
                return None
            try:
                return int(text)
            except ValueError:
                raise ValueError(f"Seed должен быть целым числом, получено: {value!r}")
        if key == "provider_name":
            text = str(value).strip()
            return text or None
        if key == "provider":
            text = str(value).strip()
            if text not in ("openai", "gigachat", "yandex", "custom"):
                raise ValueError(
                    f"Провайдер должен быть одним из openai/gigachat/yandex/custom, получено: {value!r}"
                )
            return text
        if key == "yandex_folder_id":
            if value is None:
                return None
            text = str(value).strip()
            return text or None
        return str(value).strip() if value is not None else None