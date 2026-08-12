from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_VERSION = "v1"


class PromptLoader:
    """Загрузчик версионированных промптов и схем из каталога `prompts/`.

    Чтение с mtime-кешем: правка файлов `system.md` / `response-schema.json`
    применяется в runtime без рестарта процесса (вариант 3 — оператор без
    программиста). Используется вместе с runtime-config provider'ом для
    подстановки операторских параметров в шаблон.

    Переменные шаблона `system.md`:
        {{specialization}}         — роль/специализация ассистента.
        {{provider_attribution}}   — атрибуция провайдера вида " от OpenAI"
                                     либо пустая строка (нейтральный промпт).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._text_cache: dict[Path, tuple[float, str]] = {}

    def load_system_prompt(
        self,
        version: str = DEFAULT_VERSION,
        variables: dict[str, str] | None = None,
    ) -> str:
        path = self.settings.prompts_dir / version / "system.md"
        template = self._read_cached(path).strip()
        return self._interpolate(template, variables or {})

    def load_response_schema(self, version: str = DEFAULT_VERSION) -> dict[str, Any]:
        path = self.settings.prompts_dir / version / "response-schema.json"
        return json.loads(self._read_cached(path))

    def _read_cached(self, path: Path) -> str:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Промпт-файл не найден: {path}") from exc
        cached = self._text_cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        text = path.read_text(encoding="utf-8")
        self._text_cache[path] = (mtime, text)
        logger.debug("Loaded prompt file %s (mtime=%s)", path, mtime)
        return text

    @staticmethod
    def _interpolate(template: str, variables: dict[str, str]) -> str:
        text = template
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", value)
        return text