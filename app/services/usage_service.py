from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Счётчики, хранимые в JSON-файле (storage/usage.json). Персистентны через
# смонтированный volume, как и config.json. mtime-кеш + write-lock по образцу
# RuntimeConfig. Запись ведёт AIService после каждого запроса к модели; чтение —
# админка для dashboard статистики. Диагностический test_connection сюда НЕ пишет.
ZERO_COUNTERS: dict[str, Any] = {
    "total_requests": 0,
    "total_errors": 0,
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "total_tokens": 0,
    "last_request_at": None,
    "last_error_at": None,
    "last_error_message": None,
    "started_at": None,
}


class UsageService:
    """Счётчик использования модели (запросы, токены, ошибки).

    Источник — JSON-файл `storage/usage.json`. Чтение с mtime-кешем,
    атомарная запись под локом. Несколько экземпляров (AIService в pages.py,
    UsageService в admin.py) читают/пишут один файл — счётчики агрегируются
    корректно, т.к. каждый экземпляр инвалидирует свой кеш при записи и
    сверяет mtime при чтении.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._path: Path = self.settings.storage_dir / "usage.json"
        self._cache: tuple[float, dict[str, Any]] | None = None
        self._write_lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def as_dict(self) -> dict[str, Any]:
        """Текущие счётчики для отображения (с fallback на нули)."""
        data = self._read()
        merged = {**ZERO_COUNTERS, **data}
        return merged

    def record_success(self, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        with self._write_lock:
            data = {**ZERO_COUNTERS, **self._read_raw()}
            data["total_requests"] = int(data["total_requests"]) + 1
            data["total_prompt_tokens"] = int(data["total_prompt_tokens"]) + int(prompt_tokens or 0)
            data["total_completion_tokens"] = int(data["total_completion_tokens"]) + int(completion_tokens or 0)
            data["total_tokens"] = int(data["total_tokens"]) + int(total_tokens or 0)
            data["last_request_at"] = self._now_iso()
            if data["started_at"] is None:
                data["started_at"] = data["last_request_at"]
            self._write(data)
        logger.info("Usage recorded: +1 request, %s tokens", total_tokens)

    def record_request_only(self) -> None:
        """Запрос без usage (провайдер не вернул usage) — считаем только запрос."""
        with self._write_lock:
            data = {**ZERO_COUNTERS, **self._read_raw()}
            data["total_requests"] = int(data["total_requests"]) + 1
            data["last_request_at"] = self._now_iso()
            if data["started_at"] is None:
                data["started_at"] = data["last_request_at"]
            self._write(data)

    def record_error(self, message: str) -> None:
        with self._write_lock:
            data = {**ZERO_COUNTERS, **self._read_raw()}
            data["total_requests"] = int(data["total_requests"]) + 1
            data["total_errors"] = int(data["total_errors"]) + 1
            now = self._now_iso()
            data["last_request_at"] = now
            data["last_error_at"] = now
            data["last_error_message"] = str(message)[:300]
            if data["started_at"] is None:
                data["started_at"] = now
            self._write(data)
        logger.info("Usage recorded: +1 error")

    # --- внутренние ---

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=UTC).isoformat()

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
            logger.warning("Usage file unreadable, starting from zeros: %s", self._path)
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._cache = None  # инвалидировать кеш чтения