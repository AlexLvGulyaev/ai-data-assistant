from __future__ import annotations

import json
import logging
import threading
from typing import Any

from app.core.config import Settings, get_settings
from app.services.registries import (
    ACTION_TYPES,
    ACTION_TYPES_HINTS_SEED,
    ACTION_TYPES_LABELS_SEED,
    AGGREGATIONS,
    AXIS_ROLES,
    CATEGORICAL_STYLES,
    CHART_TYPES,
    CHART_TYPE_HINTS,
    CHART_TYPE_LABELS_RU,
    CHART_TYPE_QUICK_PROMPTS,
    CHART_TYPE_RECIPES_SEED,
    RECIPE_KINDS,
)

logger = logging.getLogger(__name__)


class RegistryError(ValueError):
    """Невалидная запись реестра (тип графика / рецепт / действие)."""


def _default_registry() -> dict[str, Any]:
    """Начальное состояние реестра из сидов registries.py.

    Историческое поведение четырёх типов графиков сохраняется 1:1:
    pie → categorical/style=pie/sum/top 10; bar → categorical/bar/mean/top 12;
    line → timeline/limit 50; histogram → histogram/bins auto.
    """
    chart_types: dict[str, Any] = {}
    for chart_type in CHART_TYPES:
        chart_types[chart_type] = {
            "label": CHART_TYPE_LABELS_RU[chart_type],
            "hint": CHART_TYPE_HINTS[chart_type],
            "quick_prompt": CHART_TYPE_QUICK_PROMPTS[chart_type],
            "recipe": dict(CHART_TYPE_RECIPES_SEED[chart_type]),
        }
    actions = {
        action: {
            "label": ACTION_TYPES_LABELS_SEED[action],
            "hint": ACTION_TYPES_HINTS_SEED[action],
        }
        for action in ACTION_TYPES
    }
    return {"chart_types": chart_types, "actions": actions}


def coerce_recipe(raw: Any) -> dict[str, Any]:
    """Валидировать и нормализовать рецепт графика.

    Возвращает канонический рецепт только с релевантными для kind полями.
    Бросает RegistryError с человекочитаемым текстом (для статуса в админке).

    Схема:
      histogram   : {x_role, bins?}                       — bins None = авто
      categorical : {style bar|pie, x_role, y_role, agg sum|mean|count, top_n}
      timeline    : {x_role, y_role, limit}

    count не требует y_role: без числовой колонки categorical-тип
    автоматически строит частоты (исторический fallback pie/bar).
    """
    if not isinstance(raw, dict):
        raise RegistryError(f"Рецепт должен быть объектом, получено: {raw!r}")

    kind = str(raw.get("kind", "")).strip().lower()
    if kind not in RECIPE_KINDS:
        raise RegistryError(
            f"Неизвестный kind рецепта «{kind}» (доступны: {', '.join(RECIPE_KINDS)})."
        )

    normalized: dict[str, Any] = {"kind": kind}

    if kind == "categorical":
        style = str(raw.get("style", "bar")).strip().lower() or "bar"
        if style not in CATEGORICAL_STYLES:
            raise RegistryError(f"Неизвестный style «{style}» (доступны: {', '.join(CATEGORICAL_STYLES)}).")
        normalized["style"] = style
        agg = str(raw.get("agg", "")).strip().lower()
        if not agg:
            agg = "sum" if style == "pie" else "mean"
        if agg not in AGGREGATIONS:
            raise RegistryError(f"Неизвестная агрегация «{agg}» (доступны: {', '.join(AGGREGATIONS)}).")
        normalized["agg"] = agg
        normalized["x_role"] = _coerce_role(raw.get("x_role"), default="dimension")
        normalized["y_role"] = _coerce_role(raw.get("y_role"), default="numeric")
        normalized["top_n"] = _coerce_int(raw.get("top_n"), default=10, low=1, high=500, name="top_n")
        if normalized["y_role"] == "none":
            # Частотный режим: y не участвует.
            normalized["agg"] = "count"
    elif kind == "timeline":
        normalized["x_role"] = _coerce_role(raw.get("x_role"), default="datetime")
        normalized["y_role"] = _coerce_role(raw.get("y_role"), default="numeric")
        normalized["limit"] = _coerce_int(raw.get("limit"), default=50, low=2, high=2000, name="limit")
    else:  # histogram
        normalized["x_role"] = _coerce_role(raw.get("x_role"), default="numeric")
        normalized["bins"] = _coerce_optional_int(raw.get("bins"), default=None, low=2, high=200, name="bins")

    return normalized


def _coerce_role(value: Any, *, default: str) -> str:
    """Роль оси: пусто/None → kind-default; явное «none»/«null» → нет оси."""
    if value is None:
        return default
    role = str(value).strip().lower()
    if role in {"", "auto", "default"}:
        return default
    if role == "null":
        role = "none"
    if role not in AXIS_ROLES:
        raise RegistryError(f"Неизвестная роль оси «{role}» (доступны: {', '.join(AXIS_ROLES)}).")
    return role


def _coerce_int(value: Any, *, default: int, low: int, high: int, name: str) -> int:
    text = str(value).strip() if value is not None else ""
    if text in {"", "None", "null", "none"}:
        return default
    try:
        number = int(text)
    except ValueError as exc:
        raise RegistryError(f"{name} должен быть целым числом, получено: {value!r}") from exc
    if not low <= number <= high:
        raise RegistryError(f"{name} вне диапазона {low}–{high}: {number}")
    return number


def _coerce_optional_int(
    value: Any, *, default: int | None, low: int, high: int, name: str
) -> int | None:
    text = str(value).strip() if value is not None else ""
    if text in {"", "null", "none", "None", "auto", "—"}:
        return default
    return _coerce_int(text, default=default, low=low, high=high, name=name)


class RegistryRuntime:
    """Runtime-реестры агента — единый SOT (паттерн RuntimeConfig).

    Источник — JSON-файл `settings.registries_path` (по умолчанию
    `storage/registries.json`), чтение с mtime-кешем: правка файла (через
    `/admin` или файловый менеджер) применяется на следующем запросе без
    рестарта. Начальное состояние сеется из `_default_registry` при первом
    старте (ensure_initialized, идемпотентно).

    Реестр — данные, а не код:
      - типы графиков: generic-рендер `ChartService` по рецепту
        (histogram/categorical/timeline); добавление типа — запись в реестр;
      - действия (ACTION_TYPES) фиксированы кодом (исполнители — методы
        ChatService); runtime держит только лейблы/подсказки.

    Ограничение: новый *тип исполнителя* (новый kind) требует кода — в
    runtime добавляются типы графиков поверх трёх табличных kind'ов.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._path = self.settings.registries_path
        self._cache: tuple[float, dict[str, Any]] | None = None
        self._write_lock = threading.Lock()

    @property
    def path(self):
        return self._path

    # --- жизненный цикл ---

    def ensure_initialized(self) -> None:
        """Засеять реестр дефолтами при первом старте. Идемпотентно:
        существующие записи НЕ перезаписываются, добавляются только
        отсутствующие секции/типы."""
        with self._write_lock:
            existed = self._path.exists()
            data = self._read_raw()
            changed = False
            if "actions" not in data:
                data["actions"] = _default_registry()["actions"]
                changed = True
            if "chart_types" not in data:
                data["chart_types"] = _default_registry()["chart_types"]
                changed = True
            # NB: при отсутствии файла _read_raw() возвращает дефолты,
            # поэтому absent-файл материализуем даже когда changed=False.
            if changed or not existed:
                self._write_raw(data)
                logger.info("Agent registries initialized with defaults: %s", self._path)

    def reset(self) -> None:
        """Полный reseed реестра из сидов (кнопка «Сбросить реестр»)."""
        with self._write_lock:
            self._write_raw(_default_registry())
            logger.info("Agent registries reset to defaults: %s", self._path)

    # --- чтение ---

    def chart_type_keys(self) -> list[str]:
        return list(self._read().get("chart_types", {}).keys())

    def chart_types_set(self) -> frozenset[str]:
        return frozenset(self.chart_type_keys())

    def chart_entry(self, chart_type: str) -> dict[str, Any]:
        return self._read()["chart_types"][chart_type]

    def chart_recipe(self, chart_type: str) -> dict[str, Any]:
        return self.chart_entry(chart_type)["recipe"]

    def chart_label(self, chart_type: str) -> str:
        return str(self.chart_entry(chart_type).get("label") or chart_type)

    def chart_hint(self, chart_type: str) -> str:
        return str(self.chart_entry(chart_type).get("hint") or "")

    def chart_quick_prompt(self, chart_type: str) -> str:
        entry = self.chart_entry(chart_type)
        return str(entry.get("quick_prompt") or f"Построй {chart_type} для активного файла")

    def action_labels(self) -> dict[str, str]:
        return {key: entry.get("label") or key for key, entry in self.actions().items()}

    def action_hints(self) -> dict[str, str]:
        return {key: entry.get("hint") or "" for key, entry in self.actions().items()}

    def actions(self) -> dict[str, dict[str, str]]:
        """Секция действий; каждый тип из ACTION_TYPES присутствует."""
        raw = self._read().get("actions", {})
        result: dict[str, dict[str, str]] = {}
        for action in ACTION_TYPES:
            entry = raw.get(action) or {}
            result[action] = {
                "label": entry.get("label") or ACTION_TYPES_LABELS_SEED[action],
                "hint": entry.get("hint") or ACTION_TYPES_HINTS_SEED[action],
            }
        return result

    # --- запись ---

    def set_chart_registry(self, chart_types: dict[str, dict[str, Any]]) -> list[str]:
        """Полная замена секции chart_types валидированными записями.

        Каждая запись: {label, hint, quick_prompt, recipe}. Валидируется всё
        сразу («сухой» проход coerсе на вызывающей стороне не нужен — ошибки
        собираются здесь в список); при любой ошибке файл не пишется и
        исключение уходит вверх.
        """
        if not isinstance(chart_types, dict) or not chart_types:
            raise RegistryError("Реестр типов графиков не может быть пустым.")
        normalized: dict[str, Any] = {}
        for key, entry in chart_types.items():
            chart_type = str(key).strip().lower()
            if not chart_type or len(chart_type) > 40 or not chart_type.replace("_", "").replace("-", "").isalnum():
                raise RegistryError(f"Недопустимый ключ типа графика: {key!r} (латиница/цифры/подчёркивание).")
            if not isinstance(entry, dict):
                raise RegistryError(f"Запись «{chart_type}» должна быть объектом.")
            recipe = coerce_recipe(entry.get("recipe"))
            normalized[chart_type] = {
                "label": str(entry.get("label") or chart_type).strip()[:60],
                "hint": str(entry.get("hint") or "").strip()[:200],
                "quick_prompt": str(entry.get("quick_prompt") or f"Построй {chart_type} для активного файла").strip()[:240],
                "recipe": recipe,
            }
        with self._write_lock:
            data = self._read_raw()
            data["chart_types"] = normalized
            self._write_raw(data)
        logger.info("Chart registry updated: %s type(s)", len(normalized))
        return normalized

    def set_actions(self, actions: dict[str, dict[str, str]]) -> None:
        """Обновить лейблы/подсказки действий (типы фиксированы кодом)."""
        normalized: dict[str, dict[str, str]] = {}
        for action in ACTION_TYPES:
            entry = actions.get(action) or {}
            normalized[action] = {
                "label": str(entry.get("label") or ACTION_TYPES_LABELS_SEED[action]).strip()[:60],
                "hint": str(entry.get("hint") or ACTION_TYPES_HINTS_SEED[action]).strip()[:200],
            }
        with self._write_lock:
            data = self._read_raw()
            data["actions"] = normalized
            self._write_raw(data)
        logger.info("Action registry labels updated")

    # --- внутренние ---

    def _read(self) -> dict[str, Any]:
        try:
            mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            return _default_registry()
        cached = self._cache
        if cached and cached[0] == mtime:
            return cached[1]
        data = self._read_raw()
        self._cache = (mtime, data)
        return data

    def _read_raw(self) -> dict[str, Any]:
        if not self._path.exists():
            return _default_registry()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Registries file unreadable, using defaults: %s", self._path)
            return _default_registry()
        return data if isinstance(data, dict) else {}

    def _write_raw(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._cache = None  # инвалидировать кеш чтения