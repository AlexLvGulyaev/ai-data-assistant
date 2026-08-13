# 📊 Data Assistant · PROJECT_STATE

**Проект:** ai-data-assistant
**Дата создания:** 2026-08-12
**Последнее обновление:** 2026-08-12
**Статус:** MVP готов — архитектурные улучшения A–G + вариант 3 (runtime-config + `/admin`) реализованы, протестированы в Docker end-to-end, Deployment Validation пройдена в чистом окружении.

---

## 📝 1. Project Summary

AI Data Assistant — веб-приложение (FastAPI + Jinja2 + HTMX) для анализа данных в чате. Пользователь загружает CSV/Excel/JSON или изображение и общается с AI-ассистентом, который планирует действия (анализ, график, отчёт, сводка) и исполняет их локально. Графики (histogram/bar/line/pie) и DOCX-отчёты сохраняются как артефакты и доступны из чата.

Проект переработан по стандарту APL: провайдер-портабельность, версионированные промпты, реестры как единый источник истины, structured output, Pydantic Settings, и — ключевое — runtime-конфиг операторских параметров с веб-админкой, позволяющий менять поведение без пересборки и рестарта контейнера.

**Ключевые параметры:**

| Параметр | Значение |
|----------|----------|
| Стек | Python 3.11, FastAPI, Jinja2, HTMX |
| LLM | OpenAI-совместимый Chat Completions API (портабельный через `OPENAI_BASE_URL`) |
| Контракт ответа | Structured output `json_schema` (strict) + fallback-парсер |
| Графики | matplotlib (histogram/bar/line/pie) |
| Отчёты | python-docx |
| Конфиг | Pydantic Settings (bootstrap) + JSON runtime-config (оператор) |
| Контейнеризация | Docker Compose (production + dev/operator) |

---

## 🚦 2. Current Status

**Стадия:** MVP готов, протестирован end-to-end в Docker (production-режим). Deployment Validation пройдена в чистом окружении — все шаги DEPLOYMENT_GUIDE воспроизведены, система работоспособна.

### ✅ Завершённые задачи

- [x] **A. Промпт в версионированный файл + специализация** — `prompts/v1/system.md` с плейсхолдерами `{{specialization}}`, `{{provider_attribution}}`; `PromptLoader` с mtime-кешем (правка применяется в runtime).
- [x] **B. Портабельность провайдера** — `OPENAI_BASE_URL`, клиент пересоздаётся при смене endpoint в runtime.
- [x] **C. Pydantic BaseSettings** — заменён frozen-dataclass + `os.getenv`; bootstrap-параметры отделены от операторских.
- [x] **D. Реестр CHART_TYPES + pie** — `CHART_TYPES = (histogram, bar, line, pie)` как единый источник истины; pie реализован для табличных и графических данных.
- [x] **E. Реестр ACTION_TYPES** — валидация, enum в AI-схеме, `available_actions`, fallback-детекция — всё из одного реестра.
- [x] **F. Structured output json_schema** — схема генерируется из реестров; строгий контракт; fallback-парсер для провайдеров без поддержки.
- [x] **G. Responses → Chat Completions** — `client.chat.completions.create`; мультимодал через `image_url`.
- [x] **Вариант 3. Runtime-config + `/admin`** — JSON-файл + mtime-кеш; HTMX-админка с HTTP Basic; операторские параметры применяются на следующем запросе без рестарта. Подтверждено в работающем контейнере (PID неизменен, логи отражают смену `structured_output`).
- [x] **Два режима docker-compose** — production (сборка) и dev/operator (mount + `--reload`).
- [x] **Безопасность** — `.env` исключён из образа (проверено), `.dockerignore`/`.gitignore` по стандарту APL, правильные MIME-типы скачиваний.
- [x] **`/health`** — endpoint для Docker healthcheck и мониторинга.
- [x] **Полный комплект документации APL** + Deployment Validation Report.

---

## 📈 3. Market Validation

Учебный проект. Коммерческая валидация не проводилась. Архитектура (провайдер-портабельность, runtime-конфиг оператора, реестры) переиспользуема в продуктовых кейсах анализа данных.

---

## 💰 4. Commercial Assessment

| Фактор | Оценка |
|--------|--------|
| Переиспользуемость архитектуры | Высокая — runtime-config/`/admin` и реестры применимы к любому AI-чату |
| Портабельность провайдера | Высокая — не привязан к OpenAI, поддерживает российского провайдера |
| Риски | API-затраты модели; для production нужен persistent storage и аутентификация пользователей |

---

## 🛠️ 5. Key Technology Areas

| Компетенция | Статус |
|-------------|--------|
| FastAPI + HTMX | Освоена |
| OpenAI Chat Completions + structured output | Освоена |
| Pydantic Settings (bootstrap vs runtime) | Освоена |
| Runtime-config provider (JSON + mtime-кеш) | Освоена |
| Реестры как единый источник истины | Освоена |
| Docker Compose (двухрежимный) | Освоена |
| matplotlib (вкл. pie) | Освоена |

---

## ✅ 6. Decision

Проект завершён как портфельный актив. Архитектурные улучшения A–G и вариант 3 реализованы в полном объёме («по-максимуму»). Дальнейшее развитие — опционально (декларативный движок графиков — вариант 4 — отложен).

---

## 🧭 7. Next Steps

- [ ] (опционально) Вариант 4 — декларативный движок графиков (chart spec как данные).
- [ ] (роадмап) Реестры агента (`ACTION_TYPES`, `CHART_TYPES` + лейблы/подсказки) вынести из хардкода (`app/services/registries.py`) в редактируемые runtime-параметры админки. Сейчас реестры code-defined (добавление типа графика требует записи в `CHART_TYPES` + реализации рендера в `ChartService`); в админке они показаны read-only секцией «Реестры агента» как движение в нужном направлении. Полный вынос требует: (1) хранения реестра в `storage/config.json`, (2) generic-рендера графиков по декларативному spec (Вариант 4), (3) загрузки enum structured output и `available_actions` из runtime-реестра в `AIService`, (4) UI редактирования в `/admin`.
- [ ] (опционально) Аутентификация пользователей чата (сейчас `/admin` защищён, чат — открыт).
- [ ] (опционально) Persistent volume для `storage/` в production.

---

## 📜 8. Status History

| Дата | Статус | Комментарий |
|------|--------|-------------|
| 2026-08-12 | Решение об архитектуре | Согласованы улучшения A–G + вариант 3 (runtime-config + `/admin`) |
| 2026-08-12 | Реализация | A–G + вариант 3 реализованы, скомпилированы, проверены локально |
| 2026-08-12 | Docker + тесты | Production-сборка, end-to-end тесты пройдены (upload → analyze → charts incl. pie → DOCX → download; `/admin` без рестарта) |
| 2026-08-12 | Deployment Validation | Пройдена в чистом окружении (см. DEPLOYMENT_VALIDATION_REPORT.md) |
| 2026-08-12 | MVP готов | Документация APL опубликована |