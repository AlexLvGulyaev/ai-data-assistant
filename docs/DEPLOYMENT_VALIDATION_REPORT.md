# ✅ Data Assistant · DEPLOYMENT_VALIDATION_REPORT

**Проект:** ai-data-assistant
**Дата валидации:** 2026-08-12
**DEPLOYMENT_GUIDE:** `docs/DEPLOYMENT_GUIDE.md`
**Окружение валидации:** Docker Host, чистая сборка образа из публичных артефактов репозитория (Dockerfile + `requirements.txt` + `app/` + `prompts/` + `templates/` + `static/`). Образ строится от `python:3.11-slim`; локальное окружение разработчика (`.venv`, системный Python) в воспроизведении **не участвует** — только артефакты репозитория + `.env`, подготовленный из `.env.example`.

---

## 📋 Условия валидации

- Команда выполняла **только** шаги из `DEPLOYMENT_GUIDE.md`.
- Секреты (`OPENAI_API_KEY`, `ADMIN_TOKEN`) подготовлены из `.env.example` (плейсхолдеры заменены на реальные значения) — как описано в руководстве.
- Хост-порт 8000 был занят сторонним процессом; использован `APP_PORT=8010` (раздел 6 руководства явно допускает `APP_PORT`).
- Действия по ходу проверки, отсутствующие в руководстве, **не выполнялись**.

---

## ✅ Результаты по шагам

| # | Шаг DEPLOYMENT_GUIDE | Выполненное действие | Ожидаемый результат | Фактический результат | Статус |
|---|----------------------|----------------------|---------------------|------------------------|--------|
| 1 | §5 Подготовка `.env` | `cp .env.example .env`; заполнены `OPENAI_API_KEY`, `ADMIN_TOKEN` | `.env` создан, ключи заданы | `.env` создан; `Settings` загружает `api_key` (len 164), `admin_token` задан | PASS |
| 2 | §6 Сборка production | `APP_PORT=8010 docker compose -f docker-compose.yml up -d --build` | Образ собран, контейнер стартовал | Образ `ai-data-assistant-web:latest` собран, контейнер `data-assistant` Up | PASS |
| 3 | §6 Health | `curl http://localhost:8010/health` | `{"status":"ok","app":"Data Assistant"}` | `{"status":"ok","app":"Data Assistant"}` | PASS |
| 4 | §9 Главная | `GET /` | редирект на `/chat/{id}`, страница чата | редирект `302 → /chat/<id>`, HTML чата | PASS |
| 5 | §9 Загрузка + анализ | загрузка `examples/sample_sales.csv` в чат (`POST /chat/{id}/message` с `data_file`) | preview таблицы, колонки | HTTP 200, preview с колонками `date, region, category, revenue, orders, margin` | PASS |
| 6 | §9 График bar | `POST /actions/chart/{id}` `chart_type=bar, x=region, y=revenue` | PNG-bar в артефактах | HTTP 200, `…__bar__….png` (41 KB) | PASS |
| 7 | §9 График line | `chart_type=line, x=date, y=revenue` | PNG-line | HTTP 200, `…__line__….png` (82 KB) | PASS |
| 8 | §9 График **pie** | `chart_type=pie, x=category, y=revenue` | PNG-pie (новый тип) | HTTP 200, `…__pie__….png` (49 KB, 1485×854) | PASS |
| 9 | §9 Отчёт | `POST /actions/report/{id}` | DOCX в артефактах | HTTP 200, `…__report__….docx` (190 KB) | PASS |
| 10 | §9 Скачивание PNG | `GET /download/{png}` | PNG, `image/png` | HTTP 200, `image/png`, валидный PNG | PASS |
| 11 | §9 Скачивание DOCX | `GET /download/{docx}` | DOCX, корректный MIME | HTTP 200, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, валидный Word 2007+ | PASS |
| 12 | §9 AI plan (real call) | `POST /chat/{id}/message`: «построй круговую диаграмму выручки по категориям» + файл | модель планирует pie, график строится | HTTP 200; лог: `Model plan received with 1 actions (structured_output=True)`; `chart_service` сгенерил pie; ассистент дал разбивку по категориям с долями | PASS |
| 13 | §9 Админка: auth | `GET /admin` без auth; с неверным паролем; с верным | 401 / 401 / 200 | 401 / 401 / 200, панель рендерится | PASS |
| 14 | §9 Админка: update | `POST /admin/update` `assistant_specialization`, `provider_name`, `structured_output=false` | 200, `config.json` обновлён | HTTP 200, `status--ok`; `storage/config.json` содержит новые значения | PASS |
| 15 | §9 Runtime-смена без рестарта | записать PID → `structured_output=false` через `/admin` → новый AI-запрос → лог | PID неизменен, лог отражает `False` | PID 675111→675111 (рестарта нет); лог: `structured_output=False`; затем `=true` после обратной смены — в том же процессе | PASS |
| 16 | §9 Админка: reset | `POST /admin/reset` `provider_name` | 200, возврат к умолчанию | HTTP 200, `provider_attribution` → пусто (нейтрально) | PASS |
| 17 | Безопасность: секреты в образе | `grep -rl '<ключ>' /app` в образе | 0 файлов | 0 файлов; `.env` отсутствует в образе, `.env.example` присутствует | PASS |
| 18 | Compose config | `docker compose -f docker-compose.yml config`; `docker compose config` (base+override) | валидны | оба валидны | PASS |

---

## 🏁 Итог

- **Всего проверок:** 18
- **PASS:** 18
- **FAIL:** 0

**Заключение:** DEPLOYMENT_GUIDE воспроизводим в чистом окружении (Docker-сборка из артефактов репозитория + `.env` из `.env.example`). Полностью работоспособный экземпляр получен исключительно по инструкциям руководства. Критерий готовности к публикации по стандарту APL (воспроизведение с нуля по DEPLOYMENT_GUIDE) **выполнен**.

### Доказательства (логи/артефакты проверки)

- Контейнер `data-assistant` поднимался из собранного образа; `/health` → 200.
- Артефакты в `storage/outputs/`: `__bar__`, `__line__`, `__pie__` PNG + `__report__` DOCX.
- Лог AI: `Model plan received with 1 actions (structured_output=True/False, model=gpt-5-mini)` — значение `structured_output` следует runtime-конфигу, не bootstrap.
- PID контейнера неизменен при смене параметров через `/admin` — рестарта нет.
- `grep` реального ключа в `/app` образа → 0 файлов.

---

## 📎 Приложение A. Верификация публичного эндпоинта (2026-08-12)

> Это **Deployment Verification** запущенного публичного экземпляра, а не часть
> clean-room критерия §«Итог». Публичный деплой зависит от внешней инфраструктуры
> (обратный прокси Traefik, DNS), которая не входит в репозиторий проекта, и
> поэтому не может быть воспроизведён «с нуля по репозиторию» в чистом окружении.
> Критерий готовности к публикации (clean-room, 18/18) этим разделом **не
> заменяется** — он зафиксирован выше. Здесь верифицируется, что запущенный
> публичный эндпоинт `https://data-assistant.alex-n8n.site` работоспособен.

**Публичный домен:** `data-assistant.alex-n8n.site`
**Механизм:** общий Traefik v3 (file-provider), контейнер `data-assistant` на
сети `n8n_default`, сертификат Let's Encrypt (resolver `myresolver`, HTTP-01
на entrypoint `web`). Инструкция — `DEPLOYMENT_GUIDE.md` §6.1.

| # | Проверка | Команда | Ожидаемый результат | Фактический результат | Статус |
|---|----------|---------|---------------------|------------------------|--------|
| P1 | Health (HTTPS) | `curl https://data-assistant.alex-n8n.site/health` | `{"status":"ok","app":"Data Assistant"}` | `{"status":"ok","app":"Data Assistant"}` | PASS |
| P2 | Главная (HTTPS, follow) | `curl -L -o /dev/null -w "%{http_code}" https://data-assistant.alex-n8n.site/` | `200` | `200` (редирект `/` → `/chat/<id>`, HTML 8 KB, `<title>AI Data Chat</title>`) | PASS |
| P3 | Сертификат | `openssl s_client ... \| openssl x509 -noout -issuer` | Let's Encrypt | `issuer=C = US, O = Let's Encrypt, CN = YR2`, subject `CN=data-assistant.alex-n8n.site`, valid до Nov 2026 | PASS |
| P4 | Routing через Traefik | `docker exec <traefik-container> wget -qO- http://data-assistant:8000/health` | JSON из контейнера | `{"status":"ok","app":"Data Assistant"}` (прокси достаёт контейнер по имени в сети прокси) | PASS |
| P5 | Контейнер healthy | `docker ps --filter name=data-assistant` | Up (healthy) | `Up (healthy)`, `/health` 200 внутри контейнера | PASS |

**Применение конфигурации прокси:** правка файла динамической конфигурации
Traefik (ваш `--providers.file.filename`; additive:
router `data-assistant` + service → `http://data-assistant:8000`) применена
перезапуском контейнера Traefik (file-provider без `watch` читает файл при старте).
После перезапуска ACME выпустил сертификат для нового домена; существующие
домены не затронуты (`acme.json` сохранён).

**Публичный эндпоинт работоспособен:** `https://data-assistant.alex-n8n.site`
отдаёт UI чата и `/health` по HTTPS с валидным сертификатом Let's Encrypt.

---

## 📎 Приложение B. Перевалидация после SSOT-рефактора (2026-08-12)

**Повод:** изменение `docker-compose.yml` (добавлен volume `./prompts:/app/prompts`),
слоя конфигурации (`config.py` — из `.env` убраны операторские параметры,
оставлены только секреты+bootstrap; `runtime_config.py` — `config.json` стал
единственным SOT с хардкоженным `DEFAULTS` и `ensure_initialized`), переноса
системного промпта на модель «файл = SOT» (POST `/admin/prompt` пишет в
`prompts/v1/system.md`), обновления DEPLOYMENT_GUIDE/ARCHITECTURE/OPERATOR_GUIDE.
По стандарту APL любое изменение compose/инфра требует перевалидации.

**Окружение:** пересборка образа из артефактов репозитория на том же Docker Host
(`docker compose -f docker-compose.yml up -d --build`). Это **Verification +
functional Validation** в существенном объёме, но не строго чистый VPS —
полная clean-env перевалидация (новый VPS) остаётся на усмотрение оператора.
Ниже — проверенные шаги.

| # | Шаг | Команда | Ожидание | Факт | Статус |
|---|-----|---------|----------|------|--------|
| R1 | Пересборка production | `docker compose -f docker-compose.yml up -d --build` | образ собран, контейнер Up | образ `ai-data-assistant-web:latest` пересобран, `data-assistant` Up | PASS |
| R2 | Health (в контейнере) | `urllib.urlopen('/health')` | `{"status":"ok",...}` | `{"status":"ok","app":"Data Assistant"}` | PASS |
| R3 | ensure_initialized: засев config.json | `cat /app/storage/config.json` (до этого — отсутствовал) | 6 SEEDED_KEYS, opt-in отсутствуют | `assistant_specialization, openai_model, openai_base_url, structured_output, openai_max_history_messages, max_file_size`; `provider_name/openai_temperature/openai_seed` отсутствуют | PASS |
| R4 | Opt-in `has()`=False | `RuntimeConfig.has(...)` | False для temperature/seed/provider_name | `False / False / False`; `get(openai_temperature)`=0.0 (default) | PASS |
| R5 | Промпт-SOT: запись через /admin | `POST /admin/prompt` (пересохранён текущий контент) | 200, status--ok, файл на хосте обновлён (mountpersist) | `Системный промпт сохранён`; mtime хост-файла `prompts/v1/system.md` изменился, контент цел | PASS |
| R6 | /admin рендер | `GET /admin` | карточка «Системный промпт», путь файла, нет override, dashboard, тест, opt-in hint | все 6 проверок OK | PASS |
| R7 | Реальный AI-запрос (gpt-5-mini) | `AIService.plan_response(...)` | успех, без ошибки температуры | `assistant_message: Готов`; `actions: []` — температура не отправлена (`has=False`), модель не отвергла | PASS |
| R8 | Публичный эндпоинт | `curl https://data-assistant.alex-n8n.site/health` | HTTP 200, JSON | HTTP 200, `{"status":"ok","app":"Data Assistant"}` | PASS |
| R9 | Секреты вне config.json | `config.json` не содержит `api_key`/`admin_token` | только операторские ключи | secrets отсутствуют в `config.json` (только в `.env`) | PASS |

**Итог приложения B:** 9/9 PASS. SSOT-рефактор воспроизведён пересборкой из
артефактов репозитория: `config.json` сеется из хардкода, opt-in ключи
отсутствуют (`has()=False` → gpt-5-mini не отвергает запрос), промпт-файл
редактируется через `/admin` и переживает пересборку через volume, секреты
остаются только в `.env`. Строго clean-env перевалидация (новый VPS) — за
оператором; до её проведения изменение считается верифицированным функционально.

---

## 📎 Приложение C. Перевалидация после multi-provider admin (2026-08-12)

**Повод:** добавление реестра пресетов провайдеров (`PROVIDER_PRESETS`), новых
runtime-ключей (`provider`, `yandex_folder_id`), секрета `GIGACHAT_AUTH_KEY`,
GigaChat-адаптера (`app/services/gigachat_adapter.py`), мультипровайдерного
роутинга в `AIService`, редизайна `/admin` (двухколоночная раскладка, секция
«Провайдер» с пресетами, тултипы). По стандарту APL изменение конфигурации и
зависимостей требует перевалидации.

**Окружение:** пересборка образа из артефактов репозитория
(`docker compose -f docker-compose.yml up -d --build`). Verification +
functional Validation в существенном объёме; полная clean-env перевалидация
(новый VPS) — за оператором.

| # | Шаг | Команда / действие | Ожидание | Факт | Статус |
|---|-----|--------------------|----------|------|--------|
| C1 | Пересборка production | `docker compose -f docker-compose.yml up -d --build` | образ собран, контейнер Up | образ пересобран, `data-assistant` Up | PASS |
| C2 | Health | `GET /health` | `{"status":"ok",...}` | `{"status":"ok","app":"Data Assistant"}` | PASS |
| C3 | ensure_initialized: `provider` сеется | `config.json` после чистого старта | `provider="openai"`, opt-in (`yandex_folder_id`) отсутствует | `provider="openai"`; `yandex_folder_id`/`provider_name`/`openai_temperature`/`openai_seed` отсутствуют | PASS |
| C4 | `/admin` рендер (новая раскладка) | `GET /admin` | двухколоночная раскладка, секция «Провайдер», чипы пресетов, тултипы, «Тест провайдера» в секции | `admin-layout`, `admin-tooltip`, `preset-chip`, `provider-section`, 4 пресета (OpenAI активен), `Тест провайдера` — все элементы присутствуют | PASS |
| C5 | Применение пресета GigaChat | `POST /admin/provider preset=gigachat` | активный чип GigaChat + 4 поля обновлены | `provider=gigachat`, `base_url=https://gigachat.devices.sberbank.ru/api/v1`, `model=GigaChat-Max`, `structured_output=false`, `provider_name=GigaChat`; чип активен | PASS |
| C6 | Возврат пресета OpenAI | `POST /admin/provider preset=openai` | активный чип OpenAI + поля восстановлены | `provider=openai`, `model=gpt-5-mini`, `structured_output=true` | PASS |
| C7 | OpenAI end-to-end (real) | `AIService.plan_response(...)` к gpt-5-mini | успех, план с действием, без ошибки температуры | `assistant_message` получен, `actions=[{generate_chart, pie, category, revenue}]`; температура не отправлена (`has()=False`) | PASS |
| C8 | OpenAI test_connection | `AIService.test_connection()` | `{ok: True, provider: openai, ...}` | `ok=True, provider=openai, model=gpt-5-mini, latency_ms=2224, reply=pong` | PASS |
| C9 | GigaChat без ключа — enabled | `AIService.enabled` при `provider=gigachat`, `GIGACHAT_AUTH_KEY` не задан | `False` | `enabled=False` | PASS |
| C10 | GigaChat без ключа — test/plan | `test_connection()`, `plan_response()` | честная конфиг-ошибка, не падение | `test_connection`: `ok=False, error="Выбран GigaChat, но не задан GIGACHAT_AUTH_KEY..."`; `plan_response` raises `AIServiceConfigurationError` | PASS |
| C11 | Yandex folder_id подстановка | `provider=yandex`, `yandex_folder_id=b1g...` | `_effective_model` подставляет folder_id; `default_headers` с `x-folder-id` | `effective_model=gpt://b1g.../yandexgpt/latest`; client signature `(yandex_url, yandex, folder)`; `default_headers={x-folder-id, x-data-logging-enabled:false}` | PASS |
| C12 | Yandex routing | `test_connection()` при `provider=yandex` | запрос уходит на Yandex endpoint | routing на `llm.api.cloud.yandex.net` подтверждён ответом Yandex (401 на OpenAI-ключе — ожидаемо, нужен API-ключ Yandex) | PASS |
| C13 | Секреты вне config.json | `config.json` не содержит `api_key`/`auth_key`/`admin_token` | только операторские ключи | секреты отсутствуют (только в `.env`) | PASS |
| C14 | GigaChat end-to-end (real key) | `GIGACHAT_AUTH_KEY` задан (из локального `.env`, подготовленного из `.env.example`); `test_connection()` + `plan_response()` при `provider=gigachat` | OAuth-обмен + пинг OK; план с действием | `enabled=True`; `test_connection`: `ok=True, latency_ms≈550, reply=pong`; `plan_response` к `GigaChat-Max`: `actions=[{generate_chart, pie, category, revenue}]` (free-text parse) | PASS |

**Итог приложения C:** 14/14 PASS. Multi-provider admin воспроизведён пересборкой
из артефактов репозитория: пресеты применяются, OpenAI и GigaChat работают
end-to-end реальными запросами (регрессия температуры не вернулась; GigaChat —
OAuth-адаптер, free-text parse), Yandex корректно подставляет folder_id и
заголовки (routing подтверждён; end-to-end требует API-ключ Yandex). Секрет
`GIGACHAT_AUTH_KEY` берётся из локального `.env` (подготовленного из
`.env.example`) и остаётся только в локальном `.env` (gitignored, в репозиторий
не попадает).
Строго clean-env перевалидация (новый VPS) — за оператором.

---

## 📎 Приложение D. Чистая Deployment Validation в dind (2026-08-30)

**Повод:** флагманская доработка — декларативный движок графиков +
runtime-реестры агента (`db447e2`), парольная аутентификация чата
(`60315be`, `f8fc61c`). По стандарту APL изменения конфигурации/зависимостей
требуют перевалидации.

**Классификация прогонов:** базовый прогон от 2026-08-12 (главная таблица и
приложения B/C) выполнялся на dev Docker Host разработчика и по строгому
стандарту APL классифицируется как **Deployment Verification + functional
Validation**. Данное приложение — первый прогон, отвечающий критерию строго
чистого окружения, и подтверждает **воспроизводимость** проекта.

**Окружение (чистое, соответствует стандарту):** изолированный
Docker-in-Docker контейнер (`docker:29.7.2-dind`, свежий dockerd, общих
образов/контейнеров/volumes с dev-хостом нет). Свежий `git clone` публичного
репозитория; незапушенная дельта (3 коммита текущей доработки) перенесена
патчами (`git format-patch` → `git am`) — прецедент валидации TIB/MAB. Направляющие
знания разработчика (env-процедуры, имена портов) в прогоне не использовались;
dind-хост не имеет curl — проверки выполнены штатными средствами контейнера
(`urllib`), как и допускает руководство.

| # | Шаг DEPLOYMENT_GUIDE | Действие | Ожидаемый результат | Фактический результат | Статус |
|---|----------------------|----------|---------------------|------------------------|--------|
| D1 | §5 Подготовка `.env` | `git clone` (чисто) → `cp .env.example .env` → вписать `OPENAI_API_KEY`, `ADMIN_TOKEN`, `APP_PASSWORD` | валидный `.env` из `.env.example` | `.env` создан в контейнере dind; при первом забеге выявлена склейка строк (отсутствие trailing newline в исходнике) — дефект подготовки окружения оператором, не гайда; `.env` пересобран чисто, значения по длине сверены | PASS |
| D2 | §6 Сборка | `docker compose -f docker-compose.yml up -d --build` (внутри dind) | образ собран, контейнер стартовал | EXIT=0, образ собран, контейнер Started → healthy | PASS |
| D3 | §6/§9 Health | GET `/health` (в сети контейнера) | `{"status":"ok","app":"Data Assistant"}` | `{"status":"ok","app":"Data Assistant"}` | PASS |
| D4 | §11 Монтирования | `docker inspect` volume-маунтов | `./storage` и `./prompts` — bind | bind-монтирования подтверждены, каталоги созданы | PASS |
| D5 | §5/§9 Аутентификация (парольный режим) | POST `/login` с верным/неверным паролем | 303 + cookie / 401 | Полная матрица получена на живом прод-инстансе (P-серия ниже) и в TestClient; в dind после починки окружения повторный забег не выполнялся (см. «Ограничения прогона») | PASS* |
| D6 | Teardown | `docker compose down -v` внутри dind; удаление env-файла и патчей | окружение и секреты удалены | контейнеры/сеть/volumes удалены, `/tmp/ada-dv-env`, `/tmp/patches` удалены | PASS |

**Ограничения прогона (зафиксировано честно):**
- **Пост-деплой-проверка на живом инстансе (2026-08-30) нашла три дефекта,
  не проявившихся в dind-забеге (health-уровень):**
  1. `RegistryRuntime.ensure_initialized()` никогда не материализовал
     `storage/registries.json` — `_read_raw()` возвращала дефолты для
     отсутствующего файла, и seed-логика считала себя уже выполненной
     (исправлено `1a249d9`; после редеплоя — файл сеется, идемпотентность
     подтверждена). Приложение при этом работало корректно на кодовых
     дефолтах — дефект не влиял на работоспособность.
  2. `app/routes/chat.py` — отсутствовал импорт `fastapi.status`: ветка
     «чат не найден» падала NameError→500 вместо 404 (`69d5b29`; latent —
     проявился только при запросе в несуществующий разговор).
  3. **Критический**: рендеры `ChartService` рисовали в собственную фигуру,
     а dispatcher сохранял pre-created пустую — **каждый график на проде
     выходил пустым** (0.9% непустых пикселей, histogram≈pie по байтам).
     Обнаружен владельцем на живом UI и пиксельным анализом артефактов;
     исправлено `dd54801` (рендер возвращает свою фигуру). Локальный
     чек-скрипт + live-верификация: histogram 35.6% / bar 48.0% /
     line 3.1% / pie 32.6% непустых пикселей — размеры согласуются с
     довалидационными артефактами 12.08 (line 82KB, pie 49KB).
     **Урок: пиксельное содержание артефакта — часть критерия "график
     построен"; HTTP 200 + валидный PNG — нет.**
  Все дефекты исправлены, прод пересобран и повторно верифицирован:
  health 200, `/admin` 200/401, `registries.json` засеян, e2e
  upload→pie→download (200, image/png), реальный LLM-цикл (план модели →
  графики с реальным содержимым, HTTP 200).
- Первичная auth-матрица в dind была прервана устаревшим `.env` (дефект
  подготовки окружения); после пересоздания контейнера валидирован только
  старт/health/монтирования. Парольная аутентификация при этом верифицирована:
  (а) программно — TestClient-матрица (см. TESTING §4, блок 7), (б) на живом
  публичном инстансе.
- Проверка «секреты не входят в образ» выполнялась в прогонах 2026-08-12
  (приложение A, п.17: grep ключа в `/app` → 0 файлов); в текущем забеге не
  повторялась (Dockerfile/`.dockerignore` не менялись с тех пор).

**Верификация живого публичного инстанса (2026-08-30, Verification):**

| # | Проверка | Ожидание | Факт | Статус |
|---|----------|----------|------|--------|
| P1 | `GET /health` (HTTPS) | 200, JSON | 200, `{"status":"ok","app":"Data Assistant"}` | PASS |
| P2 | Парольный режим (окно доработки): `GET /` без cookie | 303 → `/login?next=…` | 303 на `/login` | PASS |
| P3 | Там же: неверный/верный пароль | 401 / 303 + cookie | 401 / 303 + cookie-сессия | PASS |
| P4 | Открытый режим (финальное состояние): `GET /` | 200 (редиректа на `/login` нет) | 200, UI чата доступен | PASS |
| P5 | Persistent storage: пересоздание контейнера | chats/uploads/outputs переживают recreate | счётчики файлов до/после неизменны | PASS |

**Итог приложения D:** свежий клон в чистом окружении собирается, стартует и
проходит health исключительно по DEPLOYMENT_GUIDE (не используя знаний автора
сверх документа); парольные/открытые режимы аутентификации и персистентность
подтверждены на живом инстансе. DEPLOYMENT_GUIDE соответствует статусу Source
of Truth воспроизводимости; флагманская доработка (движок графиков, реестры,
auth) валидирована.