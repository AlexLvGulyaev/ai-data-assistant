# 🔌 Data Assistant · HTTP API Contract

**Проект:** ai-data-assistant
**Дата:** 2026-08-12
**Статус:** Контракт существующих HTTP-эндпоинтов as-is.

---

## 🎯 1. Назначение и область

Этот документ фиксирует **фактический** HTTP-интерфейс приложения, как он
реализован в `app/routes/`. Назначение — быть справочником для сопровождения,
интеграции и аудита: какие методы/пути существуют, что принимают, что отдают,
какие коды возвращают.

### Единственная точка входа — Web UI

Приложение — веб-приложение (FastAPI + Jinja2 + HTMX). **Единственная точка входа
для пользователя — браузер** по HTTP(S). Документ фиксирует именно этот
интерфейс. В приложении **нет** отдельного JSON REST API, CLI, Telegram-бота или
вебхука — и они не планируются. Endpoints ниже — это маршруты веб-приложения,
большинство из которых отдаёт HTML/HTMX-паршлы, а не JSON.

### Два класса ответов

Большинство маршрутов использует `render_page()` (`app/routes/pages.py`):

- если запрос несёт заголовок `HX-Request: true` (HTMX) → отдаётся **паршл**
  (HTML-фрагмент) для подмены части страницы (HTMX `swap`);
- иначе → отдаётся **полная HTML-страница**.

Контракт ответа — **HTML**, не JSON. Потребитель — браузер (HTMX-клиент).

### Готовый JSON-эндпоинт

Только один маршрут отдаёт JSON по умолчанию — `GET /health` (liveness probe).

---

## 📐 2. Соглашения

- Все пути — без префикса: роутеры подключаются в `app/main.py` через
  `app.include_router(...)` без `prefix`. Пути ниже — итоговые.
- Статические ассеты — `GET /static/*` (CSS/JS); `GET /storage/*` — смонтированный
  каталог хранилища (графики/артефакты), отдаётся `StaticFiles`.
- `:id` в путях — это `conversation_id` или `file_id` (строка, генерируется
  сервисом; для человека — opaque идентификатор).
- Формы — `multipart/form-data` (загрузка файлов) или `application/x-www-form-urlencoded`.

---

## 🗺️ 3. Карта эндпоинтов

### Страницы и навигация (`app/routes/pages.py`)

| Метод | Путь | Принимает | Ответ (браузер) | Статусы |
|-------|------|-----------|-----------------|---------|
| GET | `/` | — | `303` редирект на `/chat/{conversation_id}` (создаётся новый разговор) | 303 |
| GET | `/health` | — | JSON `{"status":"ok","app":"Data Assistant"}` | 200 |
| GET | `/chat/{conversation_id}` | — | Полная страница чата (HTML) или паршл `partials/chat_shell.html` (HTMX) | 200, 404 (чат не найден) |
| GET | `/preview/{file_id}` | — | Страница превью файла или паршл `partials/preview_content.html` | 200 |
| GET | `/results/{file_id}` | — | Страница результатов (анализ + графики) или паршл; если графиков нет — строятся дефолтные | 200 |

### Чат (`app/routes/chat.py`)

| Метод | Путь | Принимает (Form) | Ответ | Статусы |
|-------|------|------------------|-------|---------|
| POST | `/chat/{conversation_id}/message` | `message_text: str` (default `""`), `data_file: UploadFile \| None` | `partials/chat_shell.html` (HTMX) или полная `chat.html` | 200, 404 |
| POST | `/chat/{conversation_id}/activate/{file_id}` | — | то же | 200, 404 |

> Файл **прикрепляется к разговору** только при отправке через `/chat/{id}/message`
> с полем `data_file`. Standalone `/upload` (ниже) не привязывает файл к разговору.

### Загрузка (`app/routes/upload.py`)

| Метод | Путь | Принимает (Form) | Ответ | Статусы |
|-------|------|------------------|-------|---------|
| POST | `/upload` | `data_file: UploadFile` (обязательно) | HTMX → паршл `partials/preview_content.html` + заголовок `HX-Push-Url: /preview/{file_id}`; не-HTMX → `303` редирект на `/preview/{file_id}` | 200 / 303; 400 при ошибке (Unsupported/TooLarge/Empty/Read) |

### Действия по файлу (`app/routes/actions.py`)

| Метод | Путь | Принимает (Form) | Ответ (HTML-паршл `partials/result_panel.html`) | Статусы |
|-------|------|------------------|--------------------------------------------------|---------|
| POST | `/actions/analyze/{file_id}` | — | панель с обновлённым анализом | 200 |
| POST | `/actions/chart/{file_id}` | `chart_type: str`, `x_column: str?`, `y_column: str?` | панель с новым графиком (PNG в артефактах) | 200; ошибка читения → панель с сообщением |
| POST | `/actions/report/{file_id}` | — | панель с DOCX-отчётом в артефактах | 200 |

### Скачивание артефактов (`app/routes/actions.py`)

| Метод | Путь | Принимает | Ответ | Статусы |
|-------|------|-----------|-------|---------|
| GET | `/download/{artifact_name}` | — | `FileResponse` с корректным `media_type`: `image/png` (`.png`), `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (`.docx`), `application/pdf` (`.pdf`), иначе `application/octet-stream` | 200; 404 (нет файла / путь вне `output_dir`) |

> `artifact_name` — имя файла в `storage/outputs/`. Проверяется, что путь не
> выходит за пределы `output_dir` (защита от path traversal).

### Админка оператора (`app/routes/admin.py`)

Доступ — HTTP Basic, пользователь `admin`, пароль = `ADMIN_TOKEN` (bootstrap, `.env`).
Если `ADMIN_TOKEN` не задан — `/admin` отключён (403).

| Метод | Путь | Принимает | Ответ (HTML) | Статусы |
|-------|------|-----------|--------------|---------|
| GET | `/admin`, `/admin/` | — (Basic) | Панель операторских параметров (`admin.html` или паршл `partials/admin_content.html` для HTMX) | 200; 401 (неверный Basic); 403 (токен не задан) |
| POST | `/admin/update` | `key: str`, `value: str` | Паршл `partials/admin_status.html` с подтверждением/ошибкой | 200; 401/403 |
| POST | `/admin/reset` | `key: str` | Паршл `partials/admin_status.html` (сброс к умолчанию) | 200; 401/403 |
| POST | `/admin/provider` | `preset: str` | Паршл секции «Провайдер» с активным чипом и обновлёнными полями | 200; 401/403 |
| POST | `/admin/test` | — | Паршл `partials/admin_status.html` с результатом пинга провайдера (модель, латентность, ошибка) | 200; 401/403 |
| POST | `/admin/prompt` | `prompt: str` | Паршл `partials/admin_status.html` — промпт сохранён в файл `prompts/v1/system.md` | 200; 401/403 |

HTMX-цель подмены статуса — `#admin-status`. После `update`/`reset` inline-JS
обновляет отображение текущего значения параметра в карточке.

---

## 🤖 4. Контракт ответа модели (structured output)

Когда `structured_output` включён (runtime-параметр, по умолчанию `true`),
запрос к модели отправляется с `response_format = {type: "json_schema",
json_schema: {...}}` (strict). Схема генерируется из реестров
`ACTION_TYPES`/`CHART_TYPES` (`app/services/registries.py`,
`AIService._build_response_schema`) — единый источник истины: модель не может
вернуть действие или тип графика, отсутствующий в реестрах.

### Схема `data_assistant_plan` (strict)

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

### Enum'ы (источник — реестры)

- `ACTION_TYPES = (preview, analyze, generate_chart, generate_report, save_summary)`
- `CHART_TYPES = (histogram, bar, line, pie)`

### Когда structured output выключен

Для провайдеров без поддержки `json_schema` (`structured_output=false` через
`/admin`) запрос уходит без `response_format`; ответ парсится устойчивым
парсером `AIService._parse_plan` (с удалением markdown-обёртки ` ```json ` и
валидацией действий/графиков по тем же реестрам). Контракт потребителя
(возвращаемый `AIPlan`) не меняется.

### Мультимодал

Если активный файл — изображение, в `chat.completions` отправляется блок
`{type: "image_url", image_url: {url: <data URL>}}` рядом с текстовым блоком
(Chat Completions API).

---

## ⚙️ 5. Runtime-контракт оператора

Операторские параметры живут в `storage/config.json` (путь —
`RUNTIME_CONFIG_PATH`, по умолчанию). Чтение — с mtime-кешем: правка файла
(через `/admin` или файловый менеджер) применяется **на следующем запросе без
рестарта**. Отсутствующие ключи берутся из стартовых настроек (fallback).

### `RUNTIME_KEYS`

| Ключ | Тип | Seeded | Назначение |
|------|-----|--------|------------|
| `assistant_specialization` | str | да | Роль в системном промпте (`{{specialization}}`) |
| `provider` | str | да | Пресет провайдера (`openai`/`gigachat`/`yandex`/`custom`) |
| `openai_model` | str | да | Имя модели (generic; для Yandex — URI с `<folder_id>`) |
| `openai_base_url` | str | да | OpenAI-совместимый endpoint (generic) |
| `structured_output` | bool | да | Строгий `json_schema` (true) или fallback-парсер (false) |
| `openai_max_history_messages` | int | да | Сообщений истории в запросе |
| `max_file_size` | str | да | Лимит файла (напр. `10MB`) |
| `provider_name` | str\|null | **нет** (opt-in) | Имя провайдера в контенте (null = нейтрально) |
| `openai_temperature` | float | **нет** (opt-in) | Температура; отправляется только если `has()=True` |
| `openai_seed` | int\|null | **нет** (opt-in) | Seed; отправляется только если `has()=True` |
| `yandex_folder_id` | str\|null | **нет** (opt-in) | Folder Yandex Cloud (только для пресета `yandex`) |

> Opt-in ключи (`provider_name`, `openai_temperature`, `openai_seed`,
> `yandex_folder_id`) не сеются при первом старте — `has()` возвращает `False`,
> и параметр не отправляется в запрос. Это портабельность: модели вроде
> `gpt-5-mini` отвергают явную температуру. Оператор, задавший значение в
> `/admin`, получает `has()=True` — оно уходит в запрос.

**Секреты (`OPENAI_API_KEY`, `ADMIN_TOKEN`) в runtime-конфиг НЕ входят** — они
остаются bootstrap-параметрами `.env` (см. [`SECURITY_NOTES.md`](SECURITY_NOTES.md)).

Формат файла — JSON-объект ключ:значение. Запись через `/admin/update` атомарна
(блокировка + инвалидация кеша); `/admin/reset` удаляет ключ (возврат к умолчанию).

---

## 🧩 6. Модели данных (память, не эндпоинты)

Для сопровождения — ключевые структуры, которыми оперируют сервисы
(контракт приложения «под капотом»):

- **`StoredFile`** (`file_service`) — загруженный файл: `file_id`, `original_name`,
  `path`, `kind` (`table`/`image`/`unknown`), `size`, метаданные (для таблиц —
  колонки/типы/shape). Источник для preview, анализа, графиков, отчётов.
- **Разговор** (`chat_service`, JSON в `storage/chats/`) — `conversation_id`,
  история сообщений, `active_file_id`, привязанные файлы. Контекст диалога.
- **`AIPlan`** (`ai_service`) — результат модели: `assistant_message: str` +
  `actions: list[dict]`. Валидируется по реестрам (см. §4).
- **Артефакты** (`storage/outputs/`) — PNG-графики и DOCX-отчёты, отдаются через
  `GET /download/{artifact_name}`.

---

## 📋 7. Статус-коды — сводка

| Код | Когда |
|-----|-------|
| 200 | Успешный HTML/JSON/файл |
| 303 | Редирект (создание чата, не-HTMX загрузка) |
| 400 | Ошибка загрузки файла (тип/размер/пустой/чтение) |
| 401 | `/admin`: неверный Basic |
| 403 | `/admin`: `ADMIN_TOKEN` не задан |
| 404 | Чат/файл/артефакт не найден |
| 405 | Метод не разрешён для пути (напр. HEAD для GET-only `/health`) |

---

## 🚫 8. Что НЕ входит в контракт

Явно (чтобы избежать ложных ожиданий):

- **Нет** отдельного JSON REST API для автоматизации. Все «операционные»
  действия (анализ, графики, отчёты) — HTML-формами через `/actions/*` и чат.
- **Нет** вебхука, CLI, Telegram-бота.
- **Нет** пагинации/листинга файлов по API — список артефактов отдаётся в
  HTML-контексте страницы (`/preview`, `/results`, чат).
- `/static/*` и `/storage/*` — статические монтирования, не прикладной API.

---

## 📚 9. Связанные документы

- [🏗️ `ARCHITECTURE.md`](ARCHITECTURE.md) — как маршруты связаны с сервисами.
- [📝 `PROMPT_ARCHITECTURE.md`](PROMPT_ARCHITECTURE.md) — структура промпта и контракт ответа.
- [🎛️ `OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — управление runtime-параметрами.
- [🚀 `DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание (включая публичный эндпоинт).
- [🔐 `SECURITY_NOTES.md`](SECURITY_NOTES.md) — секреты, `/admin`, path traversal.