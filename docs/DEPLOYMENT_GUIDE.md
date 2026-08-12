# Data Assistant · DEPLOYMENT_GUIDE

**Проект:** ai-data-assistant
**Дата:** 2026-08-12
**Статус:** Source of Truth процесса развёртывания.

---

## 1. Назначение

Единый Source of Truth для воспроизведения работоспособного экземпляра Data Assistant в чистом окружении. Если после выполнения руководства система не работает — руководство устарело.

Руководство рассчитано на пользователя, знакомого с Docker и Linux. Управление операторскими параметрами через `/admin` описано в [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) и здесь не повторяется.

> ⚠️ Все токены и ключи в документе — плейсхолдеры. Никогда не используйте значения из примеров в production.

---

## 2. Связанные документы

- [`README.md`](../README.md) — главная страница, быстрый старт.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура.
- [`docs/API_CONTRACT.md`](API_CONTRACT.md) — контракт HTTP-эндпоинтов (Web UI as-is).
- [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — управление параметрами оператором.
- [`docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — секреты, безопасность.
- [`docs/DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) — отчёт валидации.

---

## 3. Варианты развёртывания

| Вариант | Compose | Когда использовать | Требования |
|---------|---------|--------------------|------------|
| **Production** | `docker-compose.yml` | Эксплойт | Docker, Docker Compose v2 |
| **Production + публичный домен** | `docker-compose.yml` + обратный прокси | Портфолио-демо на VPS 24/7 (HTTPS) | Docker, существующий Traefik |
| **Dev/operator** | `docker-compose.yml` + `docker-compose.override.yml` | Разработка, операторские правки кода без пересборки | Docker, Docker Compose v2 |
| **Локальный запуск** | без Docker | Разработка без контейнеров | Python 3.11 |

---

## 4. Требования

- Установленный Docker и Docker Compose (плагин `docker compose`, не `docker-compose` v1).
- Ключ API провайдера модели (`OPENAI_API_KEY`) — для OpenAI: `sk-…`.
- (Опционально) `OPENAI_BASE_URL` — для не-OpenAI провайдера.
- Токен админки (`ADMIN_TOKEN`) — для доступа к `/admin`.

---

## 5. Переменные окружения

Создайте `.env` из `.env.example`:

```bash
cp .env.example .env
```

Заполните обязательные поля:

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `OPENAI_API_KEY` | да | Ключ API провайдера |
| `ADMIN_TOKEN` | для `/admin` | Токен доступа к админке (HTTP Basic, пользователь `admin`) |
| `OPENAI_MODEL` | нет (умолч. `gpt-5-mini`) | Модель; меняется в runtime через `/admin` |
| `OPENAI_BASE_URL` | нет (умолч. OpenAI) | Endpoint провайдера; меняется в runtime |
| `ASSISTANT_SPECIALIZATION` | нет | Специализация в промпте; меняется в runtime |
| `STRUCTURED_OUTPUT` | нет (умолч. `true`) | Строгий контракт ответа; меняется в runtime |
| `MAX_FILE_SIZE` | нет (умолч. `10MB`) | Лимит файла; меняется в runtime |
| `OPENAI_MAX_HISTORY_MESSAGES` | нет (умолч. `8`) | Сообщений истории; меняется в runtime |
| `PROVIDER_NAME` | нет | Имя провайдера в контенте (пусто = нейтрально); runtime |
| `APP_PORT` | нет (умолч. `8000`) | Порт хоста |
| `APP_HOST` | нет (умолч. `0.0.0.0`) | Хост |

Полный список с комментариями — в [`.env.example`](../.env.example).

> Параметры с пометкой «меняется в runtime» имеют в `.env` только значение по умолчанию; их можно менять через `/admin` без рестарта (см. [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md)).

---

## 6. Развёртывание Production

```bash
# 1. Подготовьте .env
cp .env.example .env
#    заполните OPENAI_API_KEY и ADMIN_TOKEN

# 2. Сборка и запуск
docker compose -f docker-compose.yml up -d --build

# 3. Проверка работоспособности
curl http://localhost:8000/health
# ожидается: {"status":"ok","app":"Data Assistant"}

# 4. Откройте http://localhost:8000
```

Если порт 8000 занят, задайте `APP_PORT`:

```bash
APP_PORT=8010 docker compose -f docker-compose.yml up -d --build
# тогда приложение доступно на http://localhost:8010
```

> В режиме «Production + публичный домен» (см. §6.1) хост-порт **не
> публикуется** — наружу сервис смотрит через обратный прокси. В этом случае
> `APP_PORT` не нужен: прокси достаёт контейнер по имени в Docker-сети.

---

## 6.1. Развёртывание на публичный домен (обратный прокси)

Production-конфигурация `docker-compose.yml` готова к выставлению через
обратный прокси: хост-порт **не публикуется** (`expose: ["8000"]` вместо
`ports`), контейнер подключается к внешней сети прокси, и прокси достаёт его
по имени контейнера. Ниже — конкретная схема для стенда лаборатории
(общий Traefik v3, file-provider), на которой верифицирован публичный эндпоинт
`https://data-assistant.alex-n8n.site`.

### Предусловия

- На хосте уже работает Traefik v3 с file-provider (`--providers.file.filename`),
  entrypoint `websecure` (443), ACME-resolver (Let's Encrypt, HTTP-01 challenge
  на entrypoint `web`). У стенда это `n8n-traefik-1`, resolver `myresolver`.
- Контейнер Traefik и контейнер Data Assistant должны находиться в **одной
  Docker-сети**, чтобы прокси мог достучаться до контейнера по имени.
  Используется внешняя сеть `n8n_default`.
- DNS: A-запись домена → IP хоста с Traefik (например,
  `data-assistant.alex-n8n.site A <IP>`).

### Шаг 1. Подключение контейнера к сети прокси

`docker-compose.yml` уже содержит:

```yaml
services:
  web:
    # ...
    expose:
      - "8000"          # без публикации на хост — наружу смотрит прокси
    networks:
      - default
      - n8n_default     # внешняя сеть Traefik
networks:
  n8n_default:
    external: true
```

> Если сети `n8n_default` на хосте нет, создайте её (`docker network create
> n8n_default`) или укажите имя вашей сети прокси. Имя сети и имя контейнера
> (`container_name: data-assistant`) используются в конфиге прокси.

### Шаг 2. Регистрация маршрута в Traefik (file-provider)

Routing для file-provider описывается в файле, который смонтирован в Traefik
(на стенде — `/opt/n8n/dynamic.yml`). Добавьте две секции — роутер и сервис
(**additive**, не трогая остальные записи):

```yaml
http:
  routers:
    # ... существующие роутеры ...
    data-assistant:
      rule: "Host(`data-assistant.alex-n8n.site`)"
      entryPoints:
        - websecure
      tls:
        certResolver: myresolver
      service: data-assistant
      priority: 1

  services:
    # ... существующие сервисы ...
    data-assistant:
      loadBalancer:
        servers:
          - url: "http://data-assistant:8000"   # <container_name>:<expose-порт>
```

> Имя resolver'а и entrypoint'а должны совпадать с теми, что настроены в
> вашем Traefik. На стенде это `myresolver` и `websecure`. Имя контейнера в
> `url` (`data-assistant`) должно совпадать с `container_name` в compose.

### Шаг 3. Применение конфигурации прокси

Если Traefik запущен **без** file-provider `watch` (файл читается только при
старте — как на стенде), конфигурация вступает в силу после перезапуска
Traefik:

```bash
docker restart n8n-traefik-1   # кратковременно (2–5 c) «гасит» все публичные сервисы
```

> Существующие сертификаты хранятся в `acme.json` и не перевыпускаются при
> перезапуске. ACME запустится только для нового домена (`data-assistant.…`).
> Если `--providers.file.watch=true` включён — перезапуск не нужен, конфиг
> применяется автоматически.

### Шаг 4. Запуск и проверка

```bash
# 1. Поднять контейнер (если ещё не запущен)
docker compose -f docker-compose.yml up -d --build

# 2. Проверить здоровье локально (внутри сети/контейнера)
curl http://localhost:8000/health          # если порт опубликован, иначе:
docker exec data-assistant python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"

# 3. Проверить публичный эндпоинт (HTTPS, сертификат Let's Encrypt)
curl https://data-assistant.alex-n8n.site/health
# ожидается: {"status":"ok","app":"Data Assistant"}

# 4. Открыть в браузере https://data-assistant.alex-n8n.site → страница чата
```

Первый HTTPS-запрос инициирует ACME-выпуск сертификата (Let's Encrypt,
HTTP-01). До выпуска Traefik может отдать самоподписанный сертификат по
умолчанию — это нормально, через ~10–30 c сертификат выпускается.

### Устранение неисправностей публичного деплоя

| Симптом | Причина | Решение |
|---------|---------|---------|
| Самоподписанный сертификат не сменяется | Traefik не перечитал `dynamic.yml` | перезапустите Traefik (если `watch` выключен) |
| `404` по HTTPS | роутер не зарегистрирован / опечатка в `Host(...)` | проверьте секцию в `dynamic.yml`, перезапустите Traefik |
| `502`/`503` | прокси не достаёт контейнер | проверьте, что контейнер и Traefik в одной сети (`n8n_default`) и `container_name` совпадает с `url` в `dynamic.yml` |
| ACME-ошибка `NXDOMAIN` / DNS | A-запись не создана/не размножилась | создайте A-запись, дождитесь распространения DNS |
| ACME-ошибка challenge на :80 | entrypoint `web` (80) недоступен извне | убедитесь, что порт 80 опубликован и открыт; HTTP-01 challenge идёт через :80 |

---

## 7. Развёртывание Dev/Operator

Режим монтирует исходники, промпты, шаблоны и статику внутрь контейнера и запускает `uvicorn --reload` — правки кода и промптов применяются без пересборки образа.

```bash
# 1. Подготовьте .env (см. раздел 5)

# 2. Первый запуск — сборка образа (нужна только для зависимостей)
docker compose up --build -d

# 3. Последующие правки кода/промптов/шаблонов — БЕЗ пересборки:
#    uvicorn сам перезагрузит процесс при изменении файлов в ./app и ./prompts.

# 4. Проверка
curl http://localhost:8000/health
```

> Пересборка в dev-режиме нужна только при изменении `requirements.txt` (состав зависимостей).

---

## 8. Локальный запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # заполните OPENAI_API_KEY и ADMIN_TOKEN
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Каталог `storage/` (`uploads/`, `outputs/`, `chats/`) создаётся автоматически при старте.

---

## 9. Проверка работоспособности (Verification)

После развёртывания проверьте:

| Проверка | Команда | Ожидаемый результат |
|----------|---------|---------------------|
| Health | `curl http://localhost:8000/health` | `{"status":"ok","app":"Data Assistant"}` |
| Главная | открыть `http://localhost:8000` | редирект на `/chat/{id}`, страница чата |
| Загрузка + анализ | загрузить `examples/sample_sales.csv` в чат | preview таблицы, колонки |
| График | «построй круговую диаграмму выручки по категориям» | PNG-pie в артефактах |
| Отчёт | кнопка/запрос отчёта | DOCX в артефактах, скачивается |
| Админка | `http://localhost:8000/admin` (Basic: `admin`/`ADMIN_TOKEN`) | панель операторских параметров |
| Runtime-смена | изменить параметр в `/admin` → новый запрос | новое значение применено без рестарта |

### Публичный деплой (через обратный прокси)

| Проверка | Команда | Ожидаемый результат |
|----------|---------|---------------------|
| Публичный health (HTTPS) | `curl https://data-assistant.alex-n8n.site/health` | `{"status":"ok","app":"Data Assistant"}`, валидный сертификат Let's Encrypt |
| Главная (HTTPS) | `curl -L -o /dev/null -w "%{http_code}" https://data-assistant.alex-n8n.site/` | `200` (после редиректа на `/chat/{id}`) |
| Сертификат | `openssl s_client -servername data-assistant.alex-n8n.site -connect data-assistant.alex-n8n.site:443 </dev/null \| openssl x509 -noout -issuer` | `issuer=...Let's Encrypt...` |

---

## 10. Управление

- **Остановить:** `docker compose down` (dev) или `docker compose -f docker-compose.yml down` (production).
- **Логи:** `docker compose logs -f web`.
- **Пересборка (production):** при изменении кода — `docker compose -f docker-compose.yml up -d --build`.
- **Обновление зависимостей:** изменить `requirements.txt` → пересборка в любом режиме.

### Runtime-параметры без рестарта

Операторские параметры меняются через `/admin` (см. [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md)) или прямым редактированием `storage/config.json` — применяются на следующем запросе. **Пересборка и рестарт не требуются.**

### Bootstrap-параметры (требуют рестарт)

`OPENAI_API_KEY`, `ADMIN_TOKEN`, `APP_HOST`, `APP_PORT`, пути к каталогам, `RUNTIME_CONFIG_PATH` — меняются в `.env` с последующим `docker compose up -d` (production) или рестартом.

---

## 11. Каталоги и тома

| Путь | Назначение | В образе | Volume |
|------|------------|----------|--------|
| `storage/uploads/` | Загруженные файлы + метаданные | нет (создаётся при старте) | `./storage:/app/storage` |
| `storage/outputs/` | Графики (PNG), отчёты (DOCX) | нет | volume |
| `storage/chats/` | Разговоры (JSON) | нет | volume |
| `storage/config.json` | Runtime-конфиг оператора | нет | volume |
| `prompts/` | Версионированные промпты | да (production) / mount (dev) | — |
| `.env` | Секреты и bootstrap | **нет** (`.dockerignore`) | `env_file` (runtime injection) |

> `.env` не попадает в образ (см. `.dockerignore`). Секреты инъектируются через `env_file` при запуске контейнера.

---

## 12. Устранение неисправностей

| Симптом | Причина | Решение |
|---------|---------|---------|
| Порт занят | другой процесс на 8000 | `APP_PORT=80xx docker compose …` |
| `/admin` → 403 | `ADMIN_TOKEN` не задан | задайте `ADMIN_TOKEN` в `.env`, рестарт |
| `/admin` → 401 | неверный пароль | пароль = `ADMIN_TOKEN`, пользователь `admin` |
| Модель не отвечает | неверный ключ/endpoint | проверьте `OPENAI_API_KEY`, `OPENAI_BASE_URL` (можно через `/admin`) |
| Модель возвращает мусор | провайдер без structured output | `/admin` → `STRUCTURED_OUTPUT=false` |
| Файл не прикреплён к чату | загрузка через standalone `/upload` | загружайте файл **в чат** (`/chat/{id}/message` с `data_file`) |