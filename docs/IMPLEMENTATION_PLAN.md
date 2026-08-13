# 📋 Data Assistant · IMPLEMENTATION_PLAN

**Проект:** ai-data-assistant
**Дата:** 2026-08-12

Технический план реализации архитектурных улучшений A–G + варианта 3 (runtime-config + `/admin`).

---

## 🏗️ 1. Архитектура решения

Переработка проекта по двум направлениям:

1. **Архитектурные улучшения A–G** — провайдер-портабельность, версионированные промпты, реестры, structured output, Pydantic Settings, Chat Completions.
2. **Вариант 3 (гибрид)** — runtime-config provider + промпты/схема как файлы + `/admin` HTMX-админка + source mounting с `--reload`. Цель: оператор меняет поведение через привычный UI без пересборки/рестарта.

Подробности — в [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 🧩 2. Состав компонентов

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Settings | `app/core/config.py` | Pydantic BaseSettings, bootstrap + умолчания |
| RuntimeConfig | `app/services/runtime_config.py` | JSON + mtime-кеш операторских параметров |
| PromptLoader | `app/services/prompt_loader.py` | Версионированные промпты, mtime-кеш |
| Registries | `app/services/registries.py` | ACTION_TYPES, CHART_TYPES — единый источник истины |
| AIService | `app/services/ai_service.py` | Chat Completions + structured output + runtime |
| ChatService | `app/services/chat_service.py` | Оркестрация диалога и действий |
| ChartService | `app/services/chart_service.py` | Графики (вкл. pie) |
| ReportService | `app/services/report_service.py` | DOCX-отчёты |
| FileService | `app/services/file_service.py` | Загрузка, хранение, чтение, runtime-лимит |
| Admin router | `app/routes/admin.py` | `/admin` HTMX-панель, HTTP Basic |
| System prompt | `prompts/v1/system.md` | Промпт с плейсхолдерами |
| Admin templates | `templates/admin.html`, `templates/partials/admin_*.html` | UI админки |

---

## 🗂️ 3. Модель данных

- **Settings** — поля см. `ARCHITECTURE.md` §3 (bootstrap) + `ADMIN_TOKEN`.
- **RuntimeConfig** — `RUNTIME_KEYS` (7 операторских параметров), JSON `storage/config.json`.
- **StoredFile** — метаданные файла (`file_id`, `original_name`, `size_bytes`, `kind`, …), JSON в `storage/uploads/`.
- **Conversation** — `conversation_id`, `messages[]`, `files[]`, `active_file_id`; JSON в `storage/chats/`.
- **AIPlan** — `assistant_message: str`, `actions: list[dict]`.
- **AI response schema** — генерируется из реестров: `assistant_message` + `actions[]` с `type` (enum `ACTION_TYPES`), `chart_type` (enum `CHART_TYPES` + null), `x_column`, `y_column`.

---

## 🔌 4. Интеграции

- **Провайдер модели** — OpenAI-совместимый Chat Completions API через `OPENAI_BASE_URL`. Портабельно.
- **Structured output** — `response_format: {type: "json_schema", strict: true}`; отключается через `STRUCTURED_OUTPUT`.
- **Мультимодал** — `image_url` (data URL) для изображений.
- **Файловая система** — `storage/` как volume.

---

## 📅 5. План реализации (по шагам)

| Шаг | Что | Статус |
|----|------|--------|
| A | Промпт в `prompts/v1/system.md` + `PromptLoader` + специализация | ✅ |
| B | `OPENAI_BASE_URL` + пересоздание клиента | ✅ |
| C | Pydantic BaseSettings (замена dataclass) | ✅ |
| D | Реестр `CHART_TYPES` + pie | ✅ |
| E | Реестр `ACTION_TYPES` | ✅ |
| F | Structured output json_schema из реестров | ✅ |
| G | Responses → Chat Completions | ✅ |
| V3.1 | `RuntimeConfig` (JSON + mtime-кеш) | ✅ |
| V3.2 | Wiring runtime в `AIService` | ✅ |
| V3.3 | Wiring runtime в `FileService` (max_file_size) | ✅ |
| V3.4 | `/admin` HTMX-админка + HTTP Basic + `ADMIN_TOKEN` | ✅ |
| V3.5 | `reset(key)` + UI сброса | ✅ |
| Conf | `.env`, `.env.example`, `.dockerignore`, `.gitignore` | ✅ |
| Compose | `docker-compose.yml` (production) + `docker-compose.override.yml` (dev) | ✅ |
| Health | `/health` endpoint | ✅ |
| Fix | MIME-типы скачиваний (DOCX/PNG/PDF) | ✅ |
| Fix | Лог `structured_output` из runtime (не bootstrap) | ✅ |
| Test | Docker build + end-to-end тесты | ✅ |
| Validation | Deployment Validation в чистом окружении | ✅ |
| Docs | README, PROJECT_STATE, ARCHITECTURE, DEPLOYMENT_GUIDE, OPERATOR_GUIDE, SECURITY_NOTES, VALIDATION_REPORT | ✅ |

---

## ✅ 6. Критерии готовности

- [x] Приложение импортируется и стартует.
- [x] Все 4 типа графиков (histogram/bar/line/pie) рендерятся на `sample_sales.csv`.
- [x] AI plan через Chat Completions + structured output возвращает корректные действия.
- [x] AI выбирает pie для «круговая диаграмма».
- [x] DOCX-отчёт генерируется и скачивается с правильным MIME.
- [x] `/admin`: auth (401/200), update, reset, persist в `config.json`.
- [x] Runtime-смена параметра применяется в **работающем** контейнере без рестарта (PID неизменен, лог подтверждает).
- [x] `.env` не попадает в образ (security).
- [x] `docker compose -f docker-compose.yml config` и override валидны.
- [x] Deployment Validation пройдена в чистом окружении.
- [x] Публичная документация самодостаточна.