# 🚀 Data Assistant · DEPLOYMENT_GUIDE

**Проект:** ai-data-assistant
**Дата:** 2026-08-12
**Статус:** Source of Truth процесса развёртывания.

---

## 🎯 1. Назначение

Единый Source of Truth для воспроизведения работоспособного экземпляра Data Assistant в чистом окружении. Если после выполнения руководства система не работает — руководство устарело.

Руководство рассчитано на пользователя, знакомого с Docker и Linux. Управление операторскими параметрами через `/admin` описано в [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) и здесь не повторяется.

> ⚠️ Все токены и ключи в документе — плейсхолдеры. Никогда не используйте значения из примеров в production.

---

## 📚 2. Связанные документы

- [`README.md`](../README.md) — главная страница, быстрый старт.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура.
- [`docs/API_CONTRACT.md`](API_CONTRACT.md) — контракт HTTP-эндпоинтов (Web UI as-is).
- [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — управление параметрами оператором.
- [`docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — секреты, безопасность.
- [`docs/DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) — отчёт валидации.

---

## 📦 3. Варианты развёртывания

| Вариант | Compose | Когда использовать | Требования |
|---------|---------|--------------------|------------|
| **Production** | `docker-compose.yml` | Эксплойт | Docker, Docker Compose v2 |
| **Production + публичный домен** | `docker-compose.yml` + обратный прокси | Портфолио-демо на VPS 24/7 (HTTPS) | Docker, существующий Traefik |
| **Dev/operator** | `docker-compose.yml` + `docker-compose.override.yml` | Разработка, операторские правки кода без пересборки | Docker, Docker Compose v2 |
| **Локальный запуск** | без Docker | Разработка без контейнеров | Python 3.11 |

---

## ✅ 4. Требования

- Установленный Docker и Docker Compose (плагин `docker compose`, не `docker-compose` v1).
- Ключ API провайдера модели (`OPENAI_API_KEY`) — для OpenAI: `sk-…`; для
  YandexGPT сюда подставляется API-ключ Yandex (Bearer).
- Опционально `GIGACHAT_AUTH_KEY` — authorization key Сбер, только если будете
  использовать пресет GigaChat (подробнее — `OPERATOR_GUIDE.md` §4).
- Токен админки (`ADMIN_TOKEN`) — для доступа к `/admin`.
- Модель и endpoint провайдера задаются оператором в runtime (`/admin` или
  `storage/config.json`); по умолчанию сеются пресет `openai`, `gpt-5-mini` и
  OpenAI endpoint.

---

## 🔧 5. Переменные окружения

Создайте `.env` из `.env.example`:

```bash
cp .env.example .env
```

Заполните обязательные поля:

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `OPENAI_API_KEY` | да | Ключ API провайдера: Bearer для OpenAI/YandexGPT/«Свой» (для Yandex — API-ключ Yandex) (секрет) |
| `GIGACHAT_AUTH_KEY` | только для GigaChat | Authorization key Сбер (секрет) |
| `GIGACHAT_CA_BUNDLE` | нет | Путь к CA-bundle для TLS GigaChat (без него — `ssl.CERT_NONE`) |
| `ADMIN_TOKEN` | для `/admin` | Токен доступа к админке (HTTP Basic, пользователь `admin`) |
| `APP_PASSWORD` | нет | Общий пароль чата на весь UI (чат, загрузки, `/storage`, артефакты). Пусто/не задан — открытый демо-режим; задан — все запросы, кроме `/health`, `/static` и `/login`, редиректят на `/login`. `/admin` остаётся за HTTP Basic (второй фактор) |
| `APP_PORT` | нет (умолч. `8000`) | Порт хоста (только dev-режим с публикацией порта) |
| `APP_HOST` | нет (умолч. `0.0.0.0`) | Хост |
| `LOG_LEVEL` | нет (умолч. `INFO`) | Уровень логирования |

Полный список с комментариями — в [`.env.example`](../.env.example).

> **В `.env` живут только секреты и bootstrap** (хост/порт, логирование, пути к
> каталогам, `RUNTIME_CONFIG_PATH`). Операторские параметры (модель, endpoint,
> специализация, температура, лимиты файла и др.) единственным источником
> истины имеют `storage/config.json` — начальные значения сеются из хардкоженных
> умолчаний при первом старте, дальше оператор правит их через `/admin` или
> файлом **без рестарта** (см. [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md)). В `.env`
> операторских параметров НЕТ — это намеренно (одна точка правки).

---

## 🚀 6. Развёртывание Production

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

## 🌐 6.1. Развёртывание на публичный домен (обратный прокси)

Production-конфигурация `docker-compose.yml` готова к выставлению через
обратный прокси: хост-порт **не публикуется** (`expose: ["8000"]` вместо
`ports`), контейнер подключается к внешней сети прокси, и прокси достаёт его
по имени контейнера. Ниже — схема на примере Traefik v3 (file-provider).
Значения сети, resolver'а, entrypoint'а и пути к файлу конфигурации — **ваши**;
`data-assistant.alex-n8n.site` — пример домена (замените на ваш). На этой схеме
верифицирован публичный эндпоинт демо.

### Предусловия

- На хосте уже работает Traefik v3 с file-provider (`--providers.file.filename`),
  entrypoint `websecure` (443), ACME-resolver (Let's Encrypt, HTTP-01 challenge
  на entrypoint `web`). Имя контейнера Traefik, resolver и entrypoint — ваши
  значения (пример: контейнер `traefik`, resolver `myresolver`, entrypoint
  `websecure`).
- Контейнер Traefik и контейнер Data Assistant должны находиться в **одной
  Docker-сети**, чтобы прокси мог достучаться до контейнера по имени.
  В примере используется внешняя сеть `n8n_default` (замените на имя вашей сети
  прокси).
- DNS: A-запись домена → IP хоста с Traefik (например,
  `<your-domain> A <IP>`).

### Шаг 1. Подключение контейнера к сети прокси

`docker-compose.yml` уже содержит (имя сети `n8n_default` — пример; замените
на имя вашей сети прокси):

```yaml
services:
  web:
    # ...
    expose:
      - "8000"          # без публикации на хост — наружу смотрит прокси
    networks:
      - default
      - n8n_default     # внешняя сеть прокси (ваша)
networks:
  n8n_default:
    external: true
```

> Если сети `n8n_default` на хосте нет, создайте её (`docker network create
> n8n_default`) или укажите имя вашей сети прокси (и в compose, и в конфиге
> Traefik). Имя сети и имя контейнера (`container_name: data-assistant`)
> используются в конфиге прокси.

### Шаг 2. Регистрация маршрута в Traefik (file-provider)

Routing для file-provider описывается в файле, который смонтирован в Traefik
(ваш `--providers.file.filename`; пример пути — `/etc/traefik/dynamic.yml`).
Добавьте две секции — роутер и сервис (**additive**, не трогая остальные
записи):

```yaml
http:
  routers:
    # ... существующие роутеры ...
    data-assistant:
      rule: "Host(`data-assistant.alex-n8n.site`)"   # ваш домен
      entryPoints:
        - websecure                                   # ваш entrypoint
      tls:
        certResolver: myresolver                      # ваш resolver
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
> вашем Traefik (пример: `myresolver` и `websecure`). Имя контейнера в
> `url` (`data-assistant`) должно совпадать с `container_name` в compose.

### Шаг 3. Применение конфигурации прокси

Если Traefik запущен **без** file-provider `watch` (файл читается только при
старте — типично для file-provider), конфигурация вступает в силу после
перезапуска Traefik:

```bash
docker restart <traefik-container>   # кратковременно (2–5 c) «гасит» все публичные сервисы
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

## 🛠️ 7. Развёртывание Dev/Operator

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

## 🐍 8. Локальный запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # заполните OPENAI_API_KEY и ADMIN_TOKEN
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Каталог `storage/` (`uploads/`, `outputs/`, `chats/`) создаётся автоматически при старте.

---

## 🧪 9. Проверка работоспособности (Verification)

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
| Аутентификация чата | задать `APP_PASSWORD` → рестарт → `curl -o /dev/null -w "%{http_code}" http://localhost:8000/` | `303` с `Location: /login?next=/` |
| Вход по паролю | `curl -c /tmp/ada-cookie -o /dev/null -w "%{http_code}" -d "password=<APP_PASSWORD>&next=/" http://localhost:8000/login` | `303`, cookie `ada_session` установлена; далее `/` открывается без логина |
| Неверный пароль | `curl -o /dev/null -w "%{http_code}" -d "password=wrong" http://localhost:8000/login` | `401` + страница входа с «Неверный пароль» |
| Health без входа | `curl http://localhost:8000/health` | `200` всегда (exempt для Docker healthcheck) |
| Второй фактор админки | `curl -o /dev/null -w "%{http_code}" -b cookie.txt http://localhost:8000/admin` | `401` — cookie чата не открывает `/admin`, нужен HTTP Basic |

### Публичный деплой (через обратный прокси)

| Проверка | Команда | Ожидаемый результат |
|----------|---------|---------------------|
| Публичный health (HTTPS) | `curl https://data-assistant.alex-n8n.site/health` | `{"status":"ok","app":"Data Assistant"}`, валидный сертификат Let's Encrypt |
| Главная (HTTPS) | `curl -o /dev/null -w "%{http_code}" https://data-assistant.alex-n8n.site/` | `303` → `Location: /login?next=/` (при заданном `APP_PASSWORD`; без пароля — `200` после редиректа на `/chat/{id}`) |
| Сертификат | `openssl s_client -servername data-assistant.alex-n8n.site -connect data-assistant.alex-n8n.site:443 </dev/null \| openssl x509 -noout -issuer` | `issuer=...Let's Encrypt...` |

---

## 🎛️ 10. Управление

- **Остановить:** `docker compose down` (dev) или `docker compose -f docker-compose.yml down` (production).
- **Логи:** `docker compose logs -f web`.
- **Пересборка (production):** при изменении кода — `docker compose -f docker-compose.yml up -d --build`.
- **Обновление зависимостей:** изменить `requirements.txt` → пересборка в любом режиме.

### Runtime-параметры без рестарта

Операторские параметры (модель, endpoint, специализация, температура, лимиты файла и др.) меняются через `/admin` (см. [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md)) или прямым редактированием `storage/config.json` — применяются на следующем запросе. **Пересборка и рестарт не требуются.** `storage/config.json` — единственный источник истины этих параметров; начальные значения сеются из хардкоженных умолчаний при первом старте.

### Реестры агента (runtime, `/admin`)

Разрешённые действия и типы графиков редактируются в `/admin` → «Реестры агента» (лейблы/подсказки/чипы действий, рецепты graph-типов, добавление нового типа графика поверх трёх табличных kind'ов без кода, сброс к кодовым дефолтам). Единый источник истины — `storage/registries.json`; применение — на следующем запросе. См. [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) и `app/services/registry_runtime.py`.

### Bootstrap-параметры (требуют рестарт)

`OPENAI_API_KEY`, `GIGACHAT_AUTH_KEY`, `GIGACHAT_CA_BUNDLE`, `ADMIN_TOKEN`, `APP_HOST`, `APP_PORT`, `LOG_LEVEL`, пути к каталогам, `PROMPTS_DIR`, `RUNTIME_CONFIG_PATH` — меняются в `.env` с последующим `docker compose up -d` (production) или рестартом. Операторских параметров в `.env` нет.

---

## 🗂️ 11. Каталоги и тома

| Путь | Назначение | В образе | Volume |
|------|------------|----------|--------|
| `storage/uploads/` | Загруженные файлы + метаданные | нет (создаётся при старте) | `./storage:/app/storage` |
| `storage/outputs/` | Графики (PNG), отчёты (DOCX) | нет | volume |
| `storage/chats/` | Разговоры (JSON) | нет | volume |
| `storage/config.json` | Runtime-конфиг оператора (единственный SOT параметров) | нет | volume |
| `storage/registries.json` | Runtime-реестры агента (типы графиков с рецептами, лейблы действий) | нет (сеется при первом старте) | volume |
| `prompts/` | Версионированные промпты (единый SOT системного промпта) | да (в образе) + mount | `./prompts:/app/prompts` |
| `.env` | Секреты и bootstrap | **нет** (`.dockerignore`) | `env_file` (runtime injection) |

> `.env` не попадает в образ (см. `.dockerignore`). Секреты инъектируются через `env_file` при запуске контейнера.
>
> **`storage/` — bind-mount (`./storage:/app/storage`)**: чаты, загрузки, артефакты,
> runtime-конфиг и реестры переживают рестарт и пересборку контейнера — данные
> лежат на хосте, а не в слое образа. Подтверждено Deployment Validation
> (пересоздание контейнера, счётчики файлов до/после). Бэкап — целиком каталог
> `storage/` (и, при желании, `prompts/`): `tar czf ada-storage-$(date +%F).tgz storage/`.
>
> `prompts/` монтируется в production поверх образа: правка системного промпта
> через `/admin` (POST `/admin/prompt` пишет в `prompts/v1/system.md`) переживает
> рестарт/пересборку. Каталог `prompts/` лежит в репозитории — `git pull` может
> перезаписать операторские правки промпта; коммитьте их обратно или
> резервируйте файл перед обновлением.

---

## 🩹 12. Устранение неисправностей

| Симптом | Причина | Решение |
|---------|---------|---------|
| Порт занят | другой процесс на 8000 | `APP_PORT=80xx docker compose …` |
| `/admin` → 403 | `ADMIN_TOKEN` не задан | задайте `ADMIN_TOKEN` в `.env`, рестарт |
| `/admin` → 401 | неверный пароль | пароль = `ADMIN_TOKEN`, пользователь `admin` |
| Чат → «Требуется вход»/редирект на `/login` | задан `APP_PASSWORD`, cookie сессии нет/протухла (30 дней) | войдите на `/login`; сброс пароля в `.env` инвалидирует все сессии (требуется рестарт) |
| `/login` не открывается | `APP_PASSWORD` пуст — auth выключен | это штатное поведение открытого демо; задайте `APP_PASSWORD`, если нужен вход |
| Модель не отвечает | неверный ключ/endpoint/провайдер | проверьте `OPENAI_API_KEY` (или `GIGACHAT_AUTH_KEY` для GigaChat) и пресет провайдера в `/admin` → «Тест провайдера» |
| Модель возвращает мусор | провайдер без structured output | `/admin` → `STRUCTURED_OUTPUT=false` |
| Файл не прикреплён к чату | загрузка через standalone `/upload` | загружайте файл **в чат** (`/chat/{id}/message` с `data_file`) |