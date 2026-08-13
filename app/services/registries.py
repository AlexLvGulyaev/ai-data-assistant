from __future__ import annotations

from typing import Any

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

# Русские лейблы и краткие описания действий для read-only отображения в админке
# (функциональное ядро агента — что он умеет делать). Реестр действий пока
# кодовый; вынос в редактируемые runtime-параметры — см. roadmap (PROJECT_STATE).
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
# документацией провайдеров (см. docs/external-providers.md).
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