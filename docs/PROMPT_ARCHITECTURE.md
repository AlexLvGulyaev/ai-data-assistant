# 📝 PROMPT_ARCHITECTURE.md — Data Assistant

**Проект:** ai-data-assistant
**Версия:** 1.0
**Дата:** 2026-08-13
**Статус:** Актуален — as-built конфигурация промпта и валидации ответа модели

---

## 🎯 1. Назначение

Этот документ фиксирует структуру промпта, который `AIService` отправляет
LLM, и контракт ответа модели. Промпт собирается в `app/services/ai_service.py`
(`plan_response`) на основе системного промпта из файла, контекста активного
файла и истории диалога; ответ валидируется по реестрам
`app/services/registries.py`.

---

## 🧩 2. Состав промпта

| Часть | Источник | Назначение |
|-------|----------|------------|
| System Prompt | `prompts/v1/system.md` (через `PromptLoader`) | Роль, правила выбора действий, формат ответа |
| File Context | `FileService` + `AnalysisService` | Preview/summary/колонки активного файла |
| Conversation History | `chat_service` (JSON в `storage/chats/`) | Последние N сообщений (runtime-параметр `openai_max_history_messages`) |
| User Message | параметр `message_text` | Вопрос/задача пользователя |
| Available Actions | `registries.ACTION_TYPES` + `CHART_TYPE_HINTS` | Подсказка модели: какие действия и графики разрешены |
| Response Schema | `registries.ACTION_TYPES`/`CHART_TYPES` → `_build_response_schema` | Строгий контракт ответа (json_schema strict) — когда `structured_output=true` |

---

## 🧠 3. System Prompt

Единый SOT текста промпта — файл `prompts/v1/system.md` (не config.json).
`PromptLoader` читает его с mtime-кешем; оператор правит через `/admin`
(POST `/admin/prompt` пишет в файл) или файловым менеджером — применяется на
следующем запросе без рестарта. Текущий промпт (`v1`):

```text
Ты — {{specialization}} для веб-приложения на русском языке.
Ты отвечаешь как реальный ИИ{{provider_attribution}}, помогаешь анализировать таблицы и изображения,
объясняешь выводы простым языком и при необходимости выбираешь действия для приложения.

Не придумывай действия вне разрешённого списка.
Если пользователь просит график, отчёт, анализ или сохранение, добавь соответствующее действие в `actions`.
Если пользователь просит отчёт (DOCX) — верни только `generate_report`. Не добавляй `generate_chart` отдельным действием: отчёт сам включит графики. `generate_chart` добавляй только когда график — самостоятельный результат запроса, а не часть отчёта.
Если активный файл — изображение, используй визуальное содержимое изображения в ответе.
Если активный файл — таблица, опирайся на переданные поля, preview, summary и признаки колонок.
Если действий не требуется, верни пустой список `actions`.

Доступные типы графиков для действия `generate_chart`: `histogram`, `bar`, `line`, `pie`.
Выбирай тип осмысленно: `pie` — для распределения долей по категориям,
`histogram` — для распределения числовой величины, `bar` — для сравнения групп,
`line` — для динамики по оси (например, по дате).
Если тип графика не уточнён («построй график») — выбирай `histogram`. «Диаграмма» без уточнения = `bar`. Не повторяй тип из предыдущего хода только из-за истории — выбирай тип по смыслу текущего запроса.
Всегда отвечай строго JSON по схеме: объект с полями `assistant_message` (string) и `actions` (array).
```

### 🔧 3.1. Плейсхолдеры

| Плейсхолдер | Значение | Источник |
|------------|----------|----------|
| `{{specialization}}` | Роль ассистента | `runtime.assistant_specialization` ( seeded: «аналитик данных общего профиля») |
| `{{provider_attribution}}` | ` от {provider_name}` либо пусто | `runtime.provider_name` (opt-in; `null` → нейтрально) |

`PromptLoader._interpolate` подставляет значения из `RuntimeConfig`. Промпт
нейтрален по провайдеру: при `provider_name=null` контент не содержит имени
провайдера — корректно для GigaChat, YandexGPT и любого провайдера.

### 📁 3.2. Версионирование

Каталог `prompts/v1/` — версия `v1`. Переключение версий — через смену
каталога в `PROMPTS_DIR` (без правки кода). В production `prompts/` смонтирован
volume (`./prompts:/app/prompts`), правки переживают пересборку.

---

## 📄 4. Контекст файла

В user-сообщение `AIService` вкладывает контекст активного файла (через
`ChatService`):

- **Таблица:** первые строки (preview), число строк/колонок, numeric-колонки,
  признаки колонок (тип, NaN-профиль), краткая сводка.
- **Изображение:** передаётся как `image_url` (data URL) — мультимодальный
  блок рядом с текстом (Chat Completions API). GigaChat не поддерживает
  `image_url` → мультимедийные блоки сглаживаются в текст.

Контекст даёт модели факты для ответа и выбора колонок графика.

---

## 💬 5. История диалога

Последние N сообщений разговора включаются в промпт
(`runtime.openai_max_history_messages`, seeded). История берётся из JSON-файла
разговора (`storage/chats/`). N=0 → только текущий запрос (без контекста
диалога).

---

## 🗂️ 6. Доступные действия (available_actions)

`AIService._build_available_actions` формирует подсказку модели из реестров
`app/services/registries.py`:

| Действие | Код | Описание (для модели) |
|---------|-----|----------------------|
| Предпросмотр файла | `preview` | показать содержимое/структуру файла |
| Анализ данных | `analyze` | описательная статистика по таблице |
| Построить график | `generate_chart` | визуализация выбранной метрики |
| Сформировать отчёт (DOCX) | `generate_report` | DOCX-отчёт по данным файла |
| Сохранить выжимку | `save_summary` | сохранить выжимку диалога в storage |

Типы графиков (`generate_chart`) и эвристики выбора:

| Тип | Когда выбирать |
|-----|----------------|
| `histogram` | распределение числовой величины (по умолчанию, если тип не уточнён) |
| `bar` | сравнение групп / средних по категориям («диаграмма» без уточнения) |
| `line` | динамика по оси (например, по дате) |
| `pie` | распределение долей по категориям |

Реестр — единый источник истины: те же `ACTION_TYPES`/`CHART_TYPES` используются
в валидации ответа, JSON-схеме и UI-чипах. Модель не может вернуть действие или
график, отсутствующий в реестре.

---

## 🔒 7. Контракт ответа (structured output)

Когда `runtime.structured_output == true`, запрос отправляется с
`response_format = {type: "json_schema", json_schema: …}` (strict). Схема
генерируется из реестров (`AIService._build_response_schema`):

```json
{
  "type": "object",
  "properties": {
    "assistant_message": { "type": "string" },
    "actions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "type": { "type": "string", "enum": ["preview","analyze","generate_chart","generate_report","save_summary"] },
          "chart_type": { "type": ["string","null"], "enum": ["histogram","bar","line","pie", null] },
          "x_column": { "type": ["string","null"] },
          "y_column": { "type": ["string","null"] }
        },
        "required": ["type","chart_type","x_column","y_column"],
        "additionalProperties": false
      }
    }
  },
  "required": ["assistant_message","actions"],
  "additionalProperties": false
}
```

Enum'ы `type` и `chart_type` — из реестров, поэтому контракт и реестр не
расходятся. См. [`API_CONTRACT.md`](API_CONTRACT.md) §4.

---

## 🛡️ 8. Валидация и fallback-парсер

После ответа модели выполняется валидация в `AIService._parse_plan`:

- **Structured output вкл** — модель возвращает строгий JSON по схеме; парсер
  читает `assistant_message` + `actions` и валидирует каждое действие и тип
  графика по реестрам (`ACTION_TYPES_SET`/`CHART_TYPES_SET`).
- **Structured output выкл** (GigaChat, YandexGPT) или невалидный JSON —
  fallback-парсер: удаляет markdown-обёртку ` ```json … ``` `, извлекает JSON
  из свободного текста и валидирует против тех же реестров.
- Невалидные действия/графики отбрасываются; контракт потребителя (`AIPlan`)
  не меняется между режимами.

Контракт потребителя (`AIPlan`, `ai_service`) — `assistant_message: str` +
`actions: list[dict]`; его исполняет `ChatService._apply_actions`.

---

## 🔧 9. Параметры LLM (runtime)

Все параметры читаются из `RuntimeConfig` на каждом запросе — правки через
`/admin` применяются без рестарта.

| Параметр | Runtime-ключ | Seeded | Назначение |
|----------|--------------|--------|------------|
| Модель | `openai_model` | да | Имя модели (generic; для Yandex — URI с `<folder_id>`) |
| Endpoint | `openai_base_url` | да | OpenAI-совместимый endpoint |
| Провайдер (пресет) | `provider` | да | `openai`/`gigachat`/`yandex`/`custom` — определяет код-путь |
| structured_output | `structured_output` | да | Строгий json_schema (true) или fallback-парсер (false) |
| История | `openai_max_history_messages` | да | Сколько сообщений включать в промпт |
| Специализация | `assistant_specialization` | да | Роль → `{{specialization}}` |
| Имя провайдера | `provider_name` | нет (opt-in) | → `{{provider_attribution}}` (null = нейтрально) |
| Температура | `openai_temperature` | нет (opt-in) | Отправляется только если `has()=True` |
| Seed | `openai_seed` | нет (opt-in) | Отправляется только если `has()=True` |
| Yandex folder_id | `yandex_folder_id` | нет (opt-in) | Подстановка в URI и заголовок `x-folder-id` |

> **Почему температура/seed — opt-in.** Модели вроде `gpt-5-mini` принимают
> только умолчательную температуру и отвергают любое иное значение. Поэтому
> `ensure_initialized` не сеет `openai_temperature`/`openai_seed`: после чистого
> старта `has()=False` и параметр **не отправляется**. Оператор, явно задавший
> значение в `/admin`, получает `has()=True` — оно уходит в запрос. Это
> портабельность между провайдерами.

Секреты (`OPENAI_API_KEY`, `GIGACHAT_AUTH_KEY`, `ADMIN_TOKEN`) в промпт и в
`config.json` **не входят** — только в `.env`.

---

## 📚 10. Связанные документы

- [🏗️ `ARCHITECTURE.md`](ARCHITECTURE.md) — место `AIService`/`PromptLoader` в архитектуре, три источника истины.
- [🔌 `API_CONTRACT.md`](API_CONTRACT.md) §4 — схема structured output и мультимодал.
- [🤖 `EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры и ограничения провайдеров LLM.
- [🎛️ `OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — управление промптом и параметрами через `/admin`.
- [📊 `PROJECT_STATE.md`](PROJECT_STATE.md) — актуальный статус проекта.