# 🔐 Data Assistant · SECURITY_NOTES

**Проект:** ai-data-assistant
**Дата:** 2026-08-12

---

## 🔑 1. Секреты

| Секрет | Где хранится | Доступ |
|--------|--------------|--------|
| `OPENAI_API_KEY` | `.env` (только на хосте) | инъектируется через `env_file` при запуске контейнера |
| `GIGACHAT_AUTH_KEY` | `.env` | то же — authorization key Сбер (только для пресета GigaChat) |
| `ADMIN_TOKEN` | `.env` | то же |

- `.env` **не коммитируется** (см. `.gitignore`).
- `.env` **не попадает в образ** (см. `.dockerignore`, раздел `.env`). Проверено: `grep -rl '<реальный ключ>' /app` в образе возвращает 0 файлов.
- В документации используются плейсхолдеры `YOUR_API_KEY`, `YOUR_GIGACHAT_AUTH_KEY`, `YOUR_ADMIN_TOKEN`.
- `.env.example` содержит только плейсхолдеры и комментируется — безопасен для коммита.

---

## 🛡️ 2. Админка (`/admin`)

- Доступ — HTTP Basic, пользователь `admin`, пароль = `ADMIN_TOKEN`.
- Если `ADMIN_TOKEN` не задан — `/admin` отключён (403).
- Неверные учётные данные → 401 с `WWW-Authenticate: Basic`.
- Runtime-config (`storage/config.json`) содержит **только операторские параметры**; секреты в него не пишутся.

---

## 📦 3. Данные

- Загрузки и артефакты хранятся в `storage/` (volume), не в образе.
- `storage/` исключён из git (`.gitignore`).
- Тестовые данные (`examples/sample_sales.csv`) — синтетические.
- Логи не содержат значений секретов (только имена параметров и статусы).

---

## 🔌 4. Провайдеры: GigaChat и Yandex

### 🔑 4.1. GigaChat (Сбер)

- **`GIGACHAT_AUTH_KEY`** — authorization key Сбер, секрет в `.env` (см. §1). Используется как Basic-auth для OAuth-обмена на endpoint `/oauth`; **не** передаётся как статический Bearer в Chat Completions.
- **OAuth access token.** Адаптер (`app/services/gigachat_adapter.py`) запрашивает свежий access token **перед каждым запросом** (`_get_access_token`), без кеша и без сохранения на диск. Token живёт ~30 мин и держится в памяти только на время запроса. Access token и auth key **не логируются** — в лог попадают только режим TLS и сообщения об ошибках обмена.
- **TLS.** Эндпоинты GigaChat используют сертификат Минцифры РФ. По умолчанию проверка TLS **отключена** (`ssl.CERT_NONE`) — приемлемо для dev/демо, но оставляет запросы уязвимыми к MITM в ненадёжных сетях. Для production задайте `GIGACHAT_CA_BUNDLE` (путь к Russian Trusted Root CA) — тогда проверка включается (`ssl.create_default_context(cafile=…)`). `GIGACHAT_CA_BUNDLE` — путь, не секрет.
- **Код-путь.** GigaChat идёт отдельным адаптером (urllib, прямой HTTP), не через OpenAI SDK — сознательное отклонение от drop-in, продиктованное OAuth-обменом.

### 🌐 4.2. YandexGPT

- **`yandex_folder_id`** — идентификатор каталога Yandex Cloud, хранится в `storage/config.json` как runtime-параметр (НЕ секрет). Подставляется в URI модели и в заголовок `x-folder-id`.
- **API-ключ Yandex** — передаётся как Bearer в переменной `OPENAI_API_KEY` (см. §1); отдельной env-переменной нет.
- **Приватность промптов.** Для YandexGPT добавляется заголовок `x-data-logging-enabled: false` — запрет логирования промптов и ответов на стороне Yandex. Заголовок выставляется в `default_headers` OpenAI SDK при `provider=yandex` и заданном `folder_id`; если ваша политика требует полного запрета обучения на ваших данных — убедитесь, что пресет Yandex активен и `folder_id` задан.

---

## 🚧 5. Публичная/внутренняя граница

Публичный репозиторий самодостаточен: README + `docs/` + код + `.env.example` + Docker-файлы + `examples/`. Внутренние рабочие материалы и история разработки исключены из публичного репозитория через `.gitignore` и не являются частью поставки.

---

## ⚠️ 6. Известные ограничения (MVP)

- Чат открыт (без аутентификации пользователей) — только `/admin` защищён. Для production-эксплойта с публичным доступом требуется добавить аутентификацию пользователей.
- `storage/` — локальный volume; для горизонтального масштабирования нужен shared/persistent storage.
- HTTP (без TLS) — для production за reverse-proxy с TLS.