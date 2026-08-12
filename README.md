# Data Assistant

AI-чат для анализа данных на FastAPI + Jinja2 + HTMX. Загружаете CSV/Excel/JSON или изображение, общаетесь с ассистентом на естественном языке — он строит графики, считает метрики, собирает DOCX-отчёты и хранит артефакты. Работает с любым OpenAI-совместимым провайдером (OpenAI, GigaChat, YandexGPT и др.).

Подробная архитектура — в [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Инструкция по развёртыванию — в [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md). Управление параметрами оператором — в [`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md). Контракт HTTP-эндпоинтов — в [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

> **Публичное демо (портфолио):** <https://data-assistant.alex-n8n.site> —
> запущенный экземпляр за обратным прокси (HTTPS, Let's Encrypt). См.
> [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) §6.1.

---

## Возможности

- **Чат с моделью** — ассистент читает контекст файла и сам решает, какое действие выполнить (анализ, график, отчёт, сводка).
- **Загрузка файлов** — CSV, Excel (`.xlsx`/`.xls`), JSON, изображения (PNG/JPG/JPEG/BMP/GIF/WEBP).
- **Графики** — `histogram`, `bar`, `line`, `pie` в PNG. Тип и колонки подбирает модель либо оператор.
- **DOCX-отчёты** — отчёт по файлу с графиками и метриками, скачивается из чата.
- **Провайдер-портабельность** — пресеты OpenAI / GigaChat (Сбер) / YandexGPT / «Свой» в `/admin`: одним кликом заполняются endpoint, модель, имя и structured_output. GigaChat работает через OAuth-адаптер (refresh токена под капотом), YandexGPT — через folder_id + заголовок `x-folder-id`. Смена провайдера — без рестарта.
- **Runtime-конфиг оператора** — специализацию, модель, лимиты и другие параметры меняет оператор через веб-админку `/admin` **без пересборки и рестарта контейнера**. Тултипы на параметрах с подробными комментариями.
- **Structured output** — строгий контракт ответа модели через `json_schema` (отключается для провайдеров без поддержки).

---

## Быстрый старт (Docker)

```bash
# 1. Подготовьте .env
cp .env.example .env
#    заполните OPENAI_API_KEY и ADMIN_TOKEN
#    (GIGACHAT_AUTH_KEY — только если будете использовать пресет GigaChat)

# 2. Запустите (production-режим — сборка образа)
docker compose -f docker-compose.yml up -d --build

# 3. Откройте http://localhost:8000
```

Для разработки/оператора (монтирование исходников + live reload, без пересборки при правках кода):

```bash
docker compose up          # авто-применяет docker-compose.override.yml
```

Полный процесс развёртывания, переменные окружения и оба режима — в [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md).

---

## Локальный запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # заполните OPENAI_API_KEY и ADMIN_TOKEN
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Переменные окружения

В `.env` живут **только секреты и bootstrap** (хост/порт, логирование, пути).
Операторские параметры (модель, endpoint, специализация, температура, лимиты
файла и др.) единственным источником истины имеют `storage/config.json`
(начальные значения сеются из хардкоженных умолчаний при первом старте) —
меняются через `/admin` без рестарта. Полный список — в [`.env.example`](.env.example)
и [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md#переменные-окружения).

| Переменная | Назначение | Режим изменения |
|------------|------------|-----------------|
| `OPENAI_API_KEY` | Ключ API провайдера: Bearer для OpenAI/YandexGPT/«Свой» (для Yandex — API-ключ Yandex) (секрет) | `.env` (рестарт) |
| `GIGACHAT_AUTH_KEY` | Authorization key Сбер — только для пресета GigaChat (секрет) | `.env` (рестарт) |
| `GIGACHAT_CA_BUNDLE` | Опц. путь к CA-bundle для TLS GigaChat (сертификат Минцифры) | `.env` (рестарт) |
| `ADMIN_TOKEN` | Доступ к `/admin` (секрет) | `.env` (рестарт) |
| `APP_HOST` / `APP_PORT` | Хост/порт | `.env` (рестарт) |
| `LOG_LEVEL` | Уровень логирования | `.env` (рестарт) |
| Пути (`UPLOAD_DIR`, `PROMPTS_DIR`, `RUNTIME_CONFIG_PATH`, …) | Каталоги и файлы | `.env` (рестарт) |
| Провайдер (пресет), модель, endpoint, температура, специализация, лимиты, Yandex folder_id, … | Операторские параметры | `storage/config.json` → `/admin` (без рестарта) |

---

## Структура проекта

```
.
├── app/
│   ├── core/config.py            # Pydantic Settings, bootstrap-параметры
│   ├── routes/                   # pages, chat, upload, actions, admin
│   ├── services/
│   │   ├── ai_service.py         # Chat Completions + structured output
│   │   ├── chat_service.py       # Оркестрация диалога и действий
│   │   ├── chart_service.py      # Графики (histogram/bar/line/pie)
│   │   ├── report_service.py     # DOCX-отчёты
│   │   ├── file_service.py       # Загрузка, хранение, чтение данных
│   │   ├── analysis_service.py   # Метрики по таблице
│   │   ├── export_service.py     # Экспорт артефактов
│   │   ├── prompt_loader.py      # Версионированные промпты (mtime-кеш)
│   │   ├── registries.py         # ACTION_TYPES / CHART_TYPES — единый источник истины
│   │   └── runtime_config.py     # Runtime-конфиг операторских параметров
│   └── main.py
├── prompts/v1/system.md          # Системный промпт с плейсхолдерами
├── templates/                    # Jinja2: страницы + HTMX-паршлы + admin
├── static/                       # CSS/JS
├── examples/                     # sample_sales.csv, sample_chart_data.csv
├── docs/                         # Документация
├── Dockerfile
├── docker-compose.yml            # production (сборка)
├── docker-compose.override.yml   # dev/operator (mount + --reload)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Пример данных

Используйте `examples/sample_sales.csv` (колонки `date, region, category, revenue, orders, margin`).

Примеры запросов в чат:
- «построй круговую диаграмму выручки по категориям»
- «сделай столбчатую диаграмму заказов по регионам»
- «линейный график выручки по датам»
- «собери отчёт по файлу»

---

## Документация

- [`docs/BUSINESS_VALUE.md`](docs/BUSINESS_VALUE.md) — бизнес-ценность: позиционирование, количественные оценки, целевые заказчики, риски.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архитектура, слои, реестры, runtime-конфиг.
- [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — контракт HTTP-эндпоинтов (Web UI as-is).
- [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) — воспроизводимое развёртывание (Source of Truth).
- [`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md) — управление параметрами через `/admin`.
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — план реализации.
- [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — паспорт состояния проекта.
- [`docs/SECURITY_NOTES.md`](docs/SECURITY_NOTES.md) — секреты, границы, безопасность.
- [`docs/DEPLOYMENT_VALIDATION_REPORT.md`](docs/DEPLOYMENT_VALIDATION_REPORT.md) — отчёт валидации в чистом окружении.

---

## Лицензия

Учебный проект. Используйте и адаптируйте свободно.