from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Операторские параметры, редактируемые в runtime (через админку или прямым
# изменением файла). Значения по умолчанию берутся из Settings (startup env).
# Секреты (OPENAI_API_KEY) сюда НЕ входят — они остаются в .env.
# Порядок = порядок вывода в админке (группы: промпт → провайдер/модель → лимиты).
RUNTIME_KEYS: tuple[str, ...] = (
    "assistant_specialization",
    "system_prompt_override",
    "provider_name",
    "openai_model",
    "openai_base_url",
    "structured_output",
    "openai_temperature",
    "openai_seed",
    "openai_max_history_messages",
    "max_file_size",
)


class RuntimeConfig:
    """Runtime-конфиг операторских параметров (вариант 3).

    Источник — JSON-файл `settings.runtime_config_path` (по умолчанию
    `storage/config.json`). Чтение с mtime-кешем: правка файла (через админку
    или файловый менеджер) применяется на следующем запросе без рестарта.
    Отсутствующие ключи берутся из стартовых настроек (fallback).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._path: Path = self.settings.runtime_config_path
        self._cache: tuple[float, dict[str, Any]] | None = None
        self._write_lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def get(self, key: str) -> Any:
        if key not in RUNTIME_KEYS:
            raise KeyError(f"Unknown runtime config key: {key}")
        data = self._read()
        if key in data:
            return data[key]
        return self._default(key)

    def has(self, key: str) -> bool:
        """True, если ключ явно задан в файле runtime-конфига (не fallback на .env).

        Используется, чтобы отличить «оператор не задавал параметр» от «задал
        значение, совпадающее с умолчанием» — важно для портабельности: некоторые
        параметры (temperature) отправляются в запрос только при явной установке,
        иначе провайдер использует своё умолчание (отдельные модели не принимают
        произвольные значения).
        """
        if key not in RUNTIME_KEYS:
            raise KeyError(f"Unknown runtime config key: {key}")
        return key in self._read()

    def as_dict(self) -> dict[str, Any]:
        return {key: self.get(key) for key in RUNTIME_KEYS}

    def set(self, key: str, value: Any) -> Any:
        """Записать значение в файл конфига. Возвращает установленное значение."""
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
        """Удалить ключ из файла — параметр вернётся к умолчанию из Settings."""
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
        s = self.settings
        defaults = {
            "assistant_specialization": s.assistant_specialization,
            "system_prompt_override": None,
            "provider_name": s.provider_name,
            "openai_model": s.openai_model,
            "openai_base_url": s.openai_base_url,
            "structured_output": s.structured_output,
            "openai_temperature": s.openai_temperature,
            "openai_seed": s.openai_seed,
            "openai_max_history_messages": s.openai_max_history_messages,
            "max_file_size": s.max_file_size,
        }
        return defaults[key]

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
        if key == "system_prompt_override":
            if value is None:
                return None
            text = str(value).strip()
            return text or None
        if key == "provider_name":
            text = str(value).strip()
            return text or None
        return str(value).strip() if value is not None else None