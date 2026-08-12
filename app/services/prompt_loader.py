from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_VERSION = "v1"


class PromptLoader:
    """Загрузчик версионированных промптов из каталога `prompts/`.

    Единственный источник истины текста системного промпта — файл
    `prompts/<version>/system.md`. Чтение с mtime-кешем: правка файла
    (через `/admin` или файловым менеджером) применяется в runtime без
    рестарта процесса. Никакого override в config.json — одна точка правки,
    сам файл. Админка пишет в этот же файл (write_system_prompt).

    Переменные шаблона `system.md`:
        {{specialization}}         — роль/специализация ассистента (операторский
                                     параметр из runtime-config).
        {{provider_attribution}}   — атрибуция провайдера вида " от OpenAI"
                                     либо пустая строка (нейтральный промпт).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._text_cache: dict[Path, tuple[float, str]] = {}

    def system_prompt_path(self, version: str = DEFAULT_VERSION) -> Path:
        return self.settings.prompts_dir / version / "system.md"

    def load_system_prompt(
        self,
        version: str = DEFAULT_VERSION,
        variables: dict[str, str] | None = None,
    ) -> str:
        template = self.read_system_prompt_raw(version).strip()
        return self._interpolate(template, variables or {})

    def read_system_prompt_raw(self, version: str = DEFAULT_VERSION) -> str:
        """Сырой текст файла промпта (без интерполяции) — для редактора админки."""
        return self._read_cached(self.system_prompt_path(version))

    def write_system_prompt(self, text: str, version: str = DEFAULT_VERSION) -> None:
        """Записать промпт в файл (админка). Инвалидирует mtime-кеш."""
        path = self.system_prompt_path(version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self._text_cache.pop(path, None)
        logger.info("System prompt written: %s", path)

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