# Data Assistant · ARCHITECTURE

**Проект:** ai-data-assistant
**Дата:** 2026-08-12

---

## 1. Обзор

Data Assistant — веб-приложение для анализа данных в чате. Пользователь загружает файл и общается с AI-ассистентом; модель планирует действия, приложение исполняет их локально (графики, отчёты, метрики).

Ключевая архитектурная идея: **разделение bootstrap-параметров (стартовых, требуют рестарта) и операторских параметров (runtime, меняются без рестарта)** — вариант 3.

```
Пользователь ──HTTP──► FastAPI (routes) ──► ChatService (оркестрация)
                                              │
                                              ├──► AIService (Chat Completions + structured output)
                                              ├──► FileService (загрузка, чтение данных)
                                              ├──► AnalysisService (метрики)
                                              ├──► ChartService (histogram/bar/line/pie)
                                              └──► ReportService (DOCX)
                                                        │
AIService ──читает runtime──► RuntimeConfig (JSON + mtime-кеш) ◄──пишет── /admin (HTMX)
AIService ──читает промпт──► PromptLoader (prompts/v1/system.md, mtime-кеш)
AIService ──читает реестры──► registries (ACTION_TYPES, CHART_TYPES) — единый источник истины
```

---

## 2. Слои

| Слой | Назначение | Ключевые файлы |
|------|------------|----------------|
| **Routes** | HTTP-эндпоинты, HTMX-рендер | `app/routes/{pages,chat,upload,actions,admin}.py` |
| **Services** | Бизнес-логика | `app/services/*.py` |
| **Config** | Настройки (bootstrap + runtime) | `app/core/config.py`, `app/services/runtime_config.py` |
| **Prompts** | Версионированные промпты | `prompts/v1/system.md`, `app/services/prompt_loader.py` |
| **Registries** | Единый источник истины действий/графиков | `app/services/registries.py` |
| **Templates** | Jinja2 + HTMX | `templates/` |
| **Storage** | Загрузки, артефакты, runtime-config | `storage/` (volume) |

---

## 3. Конфигурация: три источника истины, без дублирования

Приложение строго разделяет три класса параметров, у каждого — единственный
источник истины (SSOT). Перекрытия и дублирование умолчаний между слоями
отсутствуют намеренно.

### Секреты и bootstrap — `.env` (`Settings`, рестарт)

`app/core/config.py` — Pydantic `BaseSettings`. Здесь живут **только** параметры,
которыми реально управляет окружение процесса:

- **Секреты:** `OPENAI_API_KEY`, `ADMIN_TOKEN` — только в `.env`, никогда в config.json.
- **Bootstrap:** `APP_HOST`, `APP_PORT`, `LOG_LEVEL`, пути к каталогам
  (`UPLOAD_DIR`, `OUTPUT_DIR`, `STORAGE_DIR`, `TEMPLATES_DIR`, `STATIC_DIR`,
  `PROMPTS_DIR`), `RUNTIME_CONFIG_PATH`.

Все они требуют рестарта процесса. Операторских параметров в `.env` НЕТ.

### Операторские параметры — `storage/config.json` (`RuntimeConfig`, без рестарта)

`app/services/runtime_config.py` — единый SOT операторских параметров.
JSON-файл + mtime-кеш + `threading.Lock`:

- **Первоначальная инициализация из хардкода:** при первом старте
  `ensure_initialized()` сеет `storage/config.json` значениями из хардкоженного
  словаря `DEFAULTS` (только `SEEDED_KEYS`). Это намеренный хардкод, а не `.env`:
  одна точка правки умолчаний, `.env` не дублирует операторские параметры.
- Чтение `get(key)`: если ключ в файле — берётся оттуда, иначе fallback к `DEFAULTS`.
- `has(key)`: отличает «явно задан в файле» от «fallback» — критично для
  портабельности (см. ниже).
- Запись `set(key, value)` (через `/admin`): атомарная запись, инвалидация кеша.
- `reset(key)`: удаление ключа — возврат к `DEFAULTS` (для opt-in = «не задавать»).
- mtime-кеш: правка файла (через `/admin` **или** файловым менеджером)
  применяется на следующем запросе без рестарта.

`RUNTIME_KEYS` (порядок = порядок в `/admin`):

| Ключ | Тип | Seeded | Назначение |
|------|-----|--------|------------|
| `assistant_specialization` | str | да | Роль в системном промпте |
| `openai_model` | str | да | Модель |
| `openai_base_url` | str | да | Endpoint провайдера |
| `structured_output` | bool | да | Строгий контракт ответа |
| `openai_max_history_messages` | int | да | Сообщений истории в запросе |
| `max_file_size` | str | да | Лимит файла (напр. `10MB`) |
| `provider_name` | str\|null | **нет** (opt-in) | Имя провайдера в контенте (null = нейтрально) |
| `openai_temperature` | float | **нет** (opt-in) | Температура; отправляется только если задана |
| `openai_seed` | int\|null | **нет** (opt-in) | Seed; отправляется только если задан |

> **Почему opt-in ключи не сеются.** `ensure_initialized` сеет только
> `SEEDED_KEYS`; `provider_name`/`openai_temperature`/`openai_seed` остаются
> отсутствующими, пока оператор их не задаст. Поэтому `has("openai_temperature")`
> после чистого старта — `False`, и температура **не отправляется** в запрос.
> Это портабельность: модели вроде `gpt-5-mini` принимают только умолчательную
> температуру и отвергают любое иное значение. Оператор, явно задавший
> температуру в `/admin`, получает `has()=True` — она отправляется.

### Системный промпт — файл `prompts/v1/system.md` (`PromptLoader`, без рестарта)

Единый SOT текста промпта — сам файл (не config.json). Чтение с mtime-кешем;
оператор правит его через `/admin` (POST `/admin/prompt` пишет в файл) или
файловым менеджером — применяется на следующем запросе. В production каталог
`prompts/` монтируется volume (`./prompts:/app/prompts`), чтобы правки переживали
пересборку. Переменные шаблона `{{specialization}}` / `{{provider_attribution}}`
интерполируются значениями из `RuntimeConfig`.

> Секреты (`OPENAI_API_KEY`, `ADMIN_TOKEN`) **никогда** не входят в config.json
> и не пишутся в файл промпта — только в `.env`.

---

## 4. Реестры — единый источник истины

`app/services/registries.py`:

```python
ACTION_TYPES = ("preview", "analyze", "generate_chart", "generate_report", "save_summary")
CHART_TYPES  = ("histogram", "bar", "line", "pie")
```

Из реестров выводятся:

- валидация действий и типов графиков в `ChatService`/`AIService`/`ChartService`;
- enum'ы в JSON-схеме structured output (`_build_response_schema`);
- `available_actions` — подсказка модели (`_build_available_actions`);
- fallback-детекция типа графика в `_detect_chart_type`;
- help-сообщение в чате.

Следствие: модель **не может** вернуть действие или график, который приложение не умеет исполнять. Добавление нового графика — одна строка в реестре + реализация в `chart_service`.

---

## 5. AI-слой (AIService)

`app/services/ai_service.py`:

- **Chat Completions** (`client.chat.completions.create`) — не Responses API.
- **Портабельный клиент**: `OpenAI(api_key, base_url=runtime.openai_base_url)`; клиент пересоздаётся при смене `base_url` в runtime.
- **Промпт из файла**: `PromptLoader.load_system_prompt(variables=…)` с интерполяцией `{{specialization}}`, `{{provider_attribution}}`.
- **Structured output**: `response_format: {type: "json_schema", json_schema: …}` strict, схема из реестров. Включается только если `runtime.structured_output == true`.
- **Fallback-парсер**: при отключённом structured output или невалидном JSON — устойчивый разбор с валидацией против реестров.
- **Мультимодал**: изображение передаётся как `image_url` (data URL).

Все runtime-значения (модель, base_url, structured_output, история, специализация, провайдер) читаются из `RuntimeConfig` на каждом запросе — поэтому правки через `/admin` применяются без рестарта.

---

## 6. Промпты

`prompts/v1/system.md` — системный промпт с плейсхолдерами:

| Пласхолдер | Значение |
|------------|----------|
| `{{specialization}}` | `runtime.assistant_specialization` |
| `{{provider_attribution}}` | ` от {provider_name}` либо пусто (нейтрально) |

`PromptLoader` кеширует по mtime — правка файла применяется в runtime. Версионирование через каталог (`v1/`) позволяет переключать версии без правки кода.

> Промпт нейтрален по провайдеру: явное упоминание OpenAI отсутствует. При `provider_name=null` контент не содержит имени провайдера — корректно для любого провайдера (GigaChat, YandexGPT и т.п.).

---

## 7. Оркестрация диалога (ChatService)

`app/services/chat_service.py`:

1. Получить/создать разговор.
2. Если есть загрузка — сохранить файл, сделать активным.
3. Собрать контекст активного файла.
4. `AIService.plan_response(…)` → `AIPlan(assistant_message, actions)`.
5. `_apply_actions` исполняет действия (анализ, график, отчёт, сводка).
6. Сохранить разговор в JSON.
7. При ошибке модели — fallback к локальной обработке (`_handle_local_prompt`).

Файл должен быть загружен **в чат** (`/chat/{id}/message` с `data_file`), чтобы стать активным. Standalone `/upload` создаёт preview, но не привязывает файл к разговору.

---

## 8. Графики (ChartService)

`app/services/chart_service.py` — matplotlib, типы из `CHART_TYPES`:

- `histogram`, `bar`, `line` — исходная реализация.
- `pie` (новый) — для таблиц: сумма числовой колонки по категориям (топ-10, доли %); для изображений: доли средних по каналам.

Валидация: `if chart_type not in CHART_TYPES_SET: raise`. Артефакты — PNG в `storage/outputs/`.

---

## 9. Админка оператора (`/admin`)

`app/routes/admin.py` + `templates/admin.html`:

- Доступ: HTTP Basic (пользователь `admin`, пароль = `ADMIN_TOKEN`). Если `ADMIN_TOKEN` не задан — `/admin` отключён (403).
- GET `/admin` — карточки операторских параметров с текущими значениями.
- POST `/admin/update` — `key` + `value` → `RuntimeConfig.set()`, возвращает HTMX-паршал статуса + обновлённое отображение.
- POST `/admin/reset` — сброс к умолчанию.
- Каждый параметр: подпись, подсказка, текущее значение, поле ввода, кнопки «Сохранить»/«Сбросить».

Применятеся на следующем запросе без рестарта — доказано в работающем контейнере.

---

## 10. Развёртывание

Два режима (см. [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md)):

| Режим | Compose | Когда | Правки кода | Правки операторских параметров |
|-------|---------|-------|-------------|-------------------------------|
| **Production** | `docker-compose.yml` | эксплойт | пересборка | `/admin` или `storage/config.json` (без рестарта) |
| **Dev/operator** | `+ docker-compose.override.yml` | разработка/оператор | mount + `--reload` (без пересборки) | `/admin` или файл (без рестарта) |

`storage/` — volume (переживает пересборку); содержит `config.json` (runtime-config), `uploads/`, `outputs/`, `chats/`.

---

## 11. Безопасность

См. [`SECURITY_NOTES.md`](SECURITY_NOTES.md): секреты только в `.env`, `.env` исключён из образа (проверено), `/admin` за HTTP Basic, публичная документация самодостаточна.