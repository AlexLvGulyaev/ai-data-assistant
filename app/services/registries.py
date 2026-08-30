from __future__ import annotations

from typing import Any

"""Дефолты реестров агента и пресеты провайдеров.

Историческая роль «единого источника истины для разрешённых действий и типов
графиков» расширена: реестры сеются из этого модуля в runtime-файл
`storage/registries.json` (см. app/services/registry_runtime.py) и дальше
живут в runtime — правятся оператором через `/admin` без рестарта. Здесь
остаётся только СИД (начальное состояние) и неизменяемая кодовая часть:

  - действия (`ACTION_TYPES`) — фиксированы кодом: у каждого типа есть
    Python-исполнитель в `ChatService`; реестр держит лишь лейблы/подсказки;
  - типы графиков — данные: каждая запись кода не требует. Рецепт
    (`recipe`) описывает generic-рендер одним из трёх табличных kind'ов
    (histogram / categorical / timeline, опционально style для categorical).

Порядок типов в реестре важен: он идёт в подсказки модели enum'ом и в
UI-чипы чата.
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

# Русские лейблы и краткие описания действий. После выноса реестра в runtime
# (storage/registries.json, секция actions, редактируется в /admin) этот
# словарь — только СИД при первом старте.
ACTION_TYPE_LABELS_RU: dict[str, str] = {
    "preview": "Предпросмотр файла",
    "analyze": "Анализ данных",
    "generate_chart": "Построить график",
    "generate_report": "Сформировать отчёт (DOCX)",
    "save_summary": "Сохранить выжимку",
}
ACTION_TYPE_HINTS_RU: dict[str, str] = {
    "preview": "показать содержимое/структуру файла",
    "analyze": "описательная статистика по таблице",
    "generate_chart": "визуализация выбранной метрики",
    "generate_report": "DOCX-отчёт по данным файла",
    "save_summary": "сохранить выжимку диалога в storage",
}

# СИД реестра действий (секция actions в storage/registries.json — лейблы и
# подсказки редактируются оператором; сами типы фиксированы кодом).
ACTION_TYPES_LABELS_SEED: dict[str, str] = dict(ACTION_TYPE_LABELS_RU)
ACTION_TYPES_HINTS_SEED: dict[str, str] = dict(ACTION_TYPE_HINTS_RU)

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

# Русские лейблы для UI-чипов выбора типа графика (quick-grid picker).
CHART_TYPE_LABELS_RU: dict[str, str] = {
    "histogram": "Гистограмма",
    "bar": "Столбчатый",
    "line": "Линейный",
    "pie": "Круговая",
}

# Промпты быстрых кнопок по типу графика со осмысленными осями по умолчанию.
# Строятся из реестра CHART_TYPES — единый источник истины для UI-чипов.
# Промпты намеренно не хардкодят имена колонок (файл-агностичны): они задаёт
# смысл осей, а модель/сервис выбирает подходящие колонки из контекста файла.
CHART_TYPE_QUICK_PROMPTS: dict[str, str] = {
    "histogram": "Построй histogram для активного файла",
    "bar": "Построй bar chart: сравни средние основной числовой метрики по категориальной колонке",
    "line": "Построй line chart: динамику основной числовой метрики по оси даты",
    "pie": "Построй pie chart: доли основной числовой метрики по категориальной колонке",
}


# --- Декларативные рецепты графиков (Вариант 4: chart spec как данные) ---

# Generic-исполнители (kind) — код в ChartService; всё остальное — данные:
#   - `histogram`   : распределение числовой колонки (bins; None = авто).
#   - `categorical` : dimension × numeric (объединение категорий), agg
#                     sum/mean/count, top_n; style bar|pie задаёт отрисовку.
#   - `timeline`    : datetime × numeric-точки, limit.
#
# `x_role`/`y_role` — роль колонки при выборе оси по умолчанию
# (dimension = категориальные + даты, как исторически для pie/bar; numeric;
# datetime). Поведение существующих четырёх типов сохранено 1:1:
#   pie → categorical/style=pie/sum/top 10;  bar → categorical/bar/mean/top 12;
#   line → timeline/limit 50;                histogram → histogram/bins auto.
CHART_TYPE_RECIPES_SEED: dict[str, dict[str, Any]] = {
    "histogram": {"kind": "histogram", "x_role": "numeric", "bins": None},
    "bar": {
        "kind": "categorical",
        "style": "bar",
        "x_role": "dimension",
        "y_role": "numeric",
        "agg": "mean",
        "top_n": 12,
    },
    "line": {"kind": "timeline", "x_role": "datetime", "y_role": "numeric", "limit": 50},
    "pie": {
        "kind": "categorical",
        "style": "pie",
        "x_role": "dimension",
        "y_role": "numeric",
        "agg": "sum",
        "top_n": 10,
    },
}

# Допустимые значения полей рецепта (валидатор — registry_runtime.py).
RECIPE_KINDS: tuple[str, ...] = ("histogram", "categorical", "timeline")
CATEGORICAL_STYLES: tuple[str, ...] = ("bar", "pie")
AGGREGATIONS: tuple[str, ...] = ("sum", "mean", "count")
AXIS_ROLES: tuple[str, ...] = ("dimension", "numeric", "datetime", "none")


# --- Провайдеры модели ---

# Пресеты провайдеров для админки `/admin`. Каждый пресет описывает параметры,
# которые оператор применяет одним кликом (endpoint, модель, имя провайдера для
# атрибуции, флаг structured_output), и режим аутентификации `auth_mode`, по
# которому `AIService` выбирает код-путь запроса:
#   - `openai_key`    : OpenAI SDK, ключ-секрет как Bearer (OpenAI, «Свой»).
#   - `gigachat_oauth`: GigaChat-адаптер (OAuth-обмен ключа на access token
#                       per-request; structured_output не поддерживается).
#   - `yandex_folder` : OpenAI SDK + default_headers `x-folder-id` (+ opt
#                       `x-data-logging-enabled: false`); folder_id — отдельный
#                       runtime-ключ `yandex_folder_id`.
# Поля `base_url`/`default_model` пресета пишет операторский выбор в
# `config.json` (ключи `openai_base_url`/`openai_model` — исторический префикс,
# фактически это generic endpoint/model). Значения сверены с официальной
# документацией провайдеров (см. docs/EXTERNAL_PROVIDERS.md).
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "provider_name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-5-mini",
        "structured_output": True,
        "auth_mode": "openai_key",
    },
    "gigachat": {
        "label": "GigaChat (Сбер)",
        "provider_name": "GigaChat",
        "base_url": "https://gigachat.devices.sberbank.ru/api/v1",
        "default_model": "GigaChat-Max",
        "structured_output": False,
        "auth_mode": "gigachat_oauth",
        "token_url": "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        "scope": "GIGACHAT_API_PERS",
    },
    "yandex": {
        "label": "YandexGPT",
        "provider_name": "YandexGPT",
        "base_url": "https://llm.api.cloud.yandex.net/v1",
        "default_model": "gpt://<folder_id>/yandexgpt/latest",
        "structured_output": False,
        "auth_mode": "yandex_folder",
    },
    "custom": {
        "label": "Свой (OpenAI-совместимый)",
        "provider_name": None,
        "base_url": "",
        "default_model": "",
        "structured_output": True,
        "auth_mode": "openai_key",
    },
}

# Порядок вывода пресетов в UI (OpenAI — эталон/умолчание — первым).
PROVIDER_ORDER: tuple[str, ...] = ("openai", "gigachat", "yandex", "custom")

# Какие runtime-ключи заполняет выбор пресета, и из какого поля пресета берётся
# значение. Ключи runtime исторически имеют префикс openai_ (фактически это
# generic endpoint/model); поля пресета названы семантически — поэтому отображение
# явное. `provider` (preset key) пишется отдельно от этих полей.
PRESET_FIELD_MAP: dict[str, str] = {
    "openai_base_url": "base_url",
    "openai_model": "default_model",
    "provider_name": "provider_name",
    "structured_output": "structured_output",
}