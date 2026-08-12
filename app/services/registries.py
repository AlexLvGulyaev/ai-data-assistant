from __future__ import annotations

"""Единый источник истины для разрешённых действий и типов графиков.

Реестры используются везде, где раньше хардкодились множества:
  - валидация в `ChartService.generate_chart`;
  - валидация ответа модели в `AIService._parse_plan`;
  - список `available_actions` в запросе к модели;
  - enum в JSON Schema structured output (генерируется из этих реестров);
  - fallback-распознавание в `ChatService._detect_chart_type`.

Добавление нового типа графика = запись в `CHART_TYPES` + реализация рендера в
`ChartService`. Контракт AI и все точки валидации подтянутся автоматически.
"""

# Разрешённые типы действий, которые модель может вернуть в `actions`.
ACTION_TYPES: tuple[str, ...] = (
    "preview",
    "analyze",
    "generate_chart",
    "generate_report",
    "save_summary",
)
ACTION_TYPES_SET: frozenset[str] = frozenset(ACTION_TYPES)

# Разрешённые типы графиков (порядок важен для отображения в подсказках модели).
CHART_TYPES: tuple[str, ...] = (
    "histogram",
    "bar",
    "line",
    "pie",
)
CHART_TYPES_SET: frozenset[str] = frozenset(CHART_TYPES)

# Человекочитаемые описания для подсказки модели при выборе типа графика.
CHART_TYPE_HINTS: dict[str, str] = {
    "histogram": "распределение числовой величины",
    "bar": "сравнение групп / средних по категориям",
    "line": "динамика по оси (например, по дате)",
    "pie": "распределение долей по категориям",
}