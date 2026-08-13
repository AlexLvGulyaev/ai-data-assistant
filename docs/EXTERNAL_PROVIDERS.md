# 🤖 Data Assistant · External Providers (OpenAI-compatible)

**Проект:** ai-data-assistant
**Дата:** 2026-08-12
**Статус:** исследовательская справка (Source of Truth — официальные доки провайдеров).

Назначение: зафиксировать реальные параметры OpenAI-совместимых провайдеров
для реестра пресетов в `/admin`. По правилу APL (внешняя интеграция —
официальная документация = SOT) значения взяты из доков провайдеров, не из
памяти модели.

---

## 📋 Краткая сводка

| Провайдер | base_url | Дефолтная модель | Auth для OpenAI SDK | structured_output | Drop-in? |
|-----------|----------|------------------|--------------------|--------------------|----------|
| **OpenAI** | `https://api.openai.com/v1` | `gpt-5-mini` | raw `api_key` (Bearer) — напрямую | да (json_schema strict, верифицировано) | **да** |
| **GigaChat** (Сбер) | `https://gigachat.devices.sberbank.ru/api/v1` | `GigaChat-Max` | **нет** — OAuth-обмен authorization key → access token (адаптер `gigachat_adapter.py` запрашивает per-request, refresh скрыт) | нет (не задокументировано) | **нет** (но есть рабочий адаптер в проекте) |
| **YandexGPT** (Yandex Foundation Models) | `https://llm.api.cloud.yandex.net/v1` | `gpt://<folder_id>/yandexgpt/latest` | API key как Bearer **+** header `x-folder-id` (и опц. `x-data-logging-enabled: false`) | нет (не подтверждено) | **частично** (в проекте не верифицирован) |

**Главный вывод:** чистым drop-in (только `base_url` + `model` + `api_key`)
является только OpenAI. GigaChat требует код-адаптера (OAuth-обмен токена + SSL),
но в проекте уже есть рабочий адаптер (`app/services/gigachat_adapter.py`).
YandexGPT требует `folder_id` + header `x-folder-id` (default_headers в OpenAI
SDK) и в проекте не верифицирован. Пресет «провайдер» как чистая конфигурация
(без кода) корректно работает только для OpenAI; GigaChat/Yandex — через
адаптеры.

---

## 🟢 1. OpenAI (эталон, верифицирован в проде)

- **base_url:** `https://api.openai.com/v1`
- **Модель:** `gpt-5-mini` (используется в проекте; верифицировано реальными
  запросами).
- **Auth:** `OPENAI_API_KEY` передаётся как Bearer напрямую в `OpenAI(api_key=…,
  base_url=…)`. Никаких дополнительных шагов.
- **structured_output:** поддерживается `response_format: {type: "json_schema",
  strict: true}`. Верифицировано: `AIService` использует json_schema из реестров
  `ACTION_TYPES`/`CHART_TYPES`.
- **Ограничения модели `gpt-5-mini`** (верифицировано в проде):
  - не принимает `max_tokens` («Unsupported parameter»);
  - принимает только умолчательную `temperature` (любое иное значение →
    «Only the default (1) value is supported») — поэтому температура у нас
    opt-in (отправляется только если оператор задал явно).
- **provider_name:** «OpenAI».

## 🤖 2. GigaChat (Сбер) — НЕ drop-in, требуется адаптер

- **base_url:** `https://gigachat.devices.sberbank.ru/api/v1` (рабочий endpoint,
  battle-tested в проекте). Документация совместимости называет также
  `https://api.giga.chat/v1` — в проекте не верифицировался.
- **Модель:** `GigaChat-Max` (используется в проекте). На странице совместимости фигурирует
  `GigaChat`; `GigaChat-Max`/`GigaChat-Pro` — в прод-конфиге лабы.
- **Auth:** **нельзя** использовать authorization key как статический `api_key`.
  Нужен обмен authorization key → access token: POST на
  `https://ngw.devices.sberbank.ru:9443/api/v2/oauth` с
  `Authorization: Basic <auth_key>`, scope `GIGACHAT_API_PERS`; полученный
  access token — как `Authorization: Bearer <token>` в `/chat/completions`.
  Access token живёт ~30 минут, **но это не ручная проблема оператора**:
  адаптер (`gigachat_adapter.py`) запрашивает свежий token перед каждым запросом
  (`_get_access_token` в `generate_sync`, без кеша) — refresh под капотом.
- **TLS:** эндпоинты GigaChat используют сертификат Минцифры РФ. Проект
  решает отключением проверки (`ssl.CERT_NONE`) — dev-уровень; для prod нужен
  Russian Trusted Root CA bundle.
- **structured_output:** не задокументировано → `structured_output=false`.
- **Реализация в проекте:** `app/services/gigachat_adapter.py` —
  прямой HTTP (urllib), per-request token exchange, SSL off. Можно
  переиспользовать/адаптировать под наш `AIService` (или держать отдельным
  adapter-классом). Это НЕ OpenAI SDK — отдельный код-путь.
- **provider_name:** «GigaChat».
- **Источники:** [Sber developers — GigaChat OpenAI-compatible mode](https://developers.sber.ru/docs/ru/gigachat/guides/compatible-openai.md),
  реализация `app/services/gigachat_adapter.py`.

## ☁️ 3. YandexGPT (Yandex Foundation Models) — частичный drop-in

- **base_url:** `https://llm.api.cloud.yandex.net/v1` (OpenAI-совместимый путь
  `/v1/chat/completions`).
- **Модель:** задаётся URI вида `gpt://<folder_id>/yandexgpt/latest` — то есть
  **имя модели содержит `folder_id`** оператора. Доступные модели:
  `yandexgpt/latest` (Pro 5), `yandexgpt/rc` (5.1 RC), `yandexgpt-lite`,
  `qwen3-235b-a22b-fp8/latest`, `gpt-oss-120b/latest`, `gpt-oss-20b/latest`,
  `gemma-3-27b-it/latest`.
- **Auth:** API key как Bearer (передаётся как `api_key` в OpenAI SDK) —
  работает. **Дополнительно** требуется header `x-folder-id: <folder_id>` (либо
  folder_id вшит в model URI). Опционально `x-data-logging-enabled: false`
  (запрет логирования промптов на стороне Yandex). → нужен механизм
  `default_headers` в `OpenAI(...)`, которого у `AIService` сейчас нет.
- **structured_output:** не подтверждено → `structured_output=false`.
- **provider_name:** «YandexGPT».
- **Источники:** [Yandex AI Studio — OpenAI compatibility](https://aistudio.yandex.ru/docs/ru/ai-studio/concepts/openai-compatibility),
  [langchain-yandex chat_models.ts](https://github.com/langchain-ai/langchainjs-community/blob/main/libs/langchain-yandex/src/chat_models.ts),
  [Yandex AI Studio Integration Guide](https://codegraph.ru/docs/en/integrations/YANDEX_AI_STUDIO.html)

> Примечание: страница `aistudio.yandex.ru` отдала капчу при автоматическом
> запросе; параметры YandexGPT сверены по англ. доке и реализации langchain-yandex.
> Перед боевым подключением YandexGPT — перепроверить base_url/header по
> официальной странице в браузере.

---

## 🔧 Следствие для реестра пресетов (реализовано — вариант B)

Реестр пресетов провайдеров (`PROVIDER_PRESETS` в `registries.py`) хранит для
каждого пресета: `label`, `provider_name`, `base_url`, `default_model`,
`structured_output` (да/нет) и `auth_mode` (`openai_key` | `gigachat_oauth` |
`yandex_folder`), опц. `token_url`/`scope` для GigaChat.

Реализованы **полные адаптеры** (вариант B):

- **OpenAI** (`auth_mode=openai_key`) — пресет + `OPENAI_API_KEY` как Bearer.
  Работает сразу, structured_output поддерживается.
- **GigaChat** (`auth_mode=gigachat_oauth`) — пресет заполняет endpoint/модель,
  запрос идёт через `app/services/gigachat_adapter.py` (порт адаптера:
  OAuth-обмен authorization key → access token **per-request**, refresh скрыт).
  Секрет `GIGACHAT_AUTH_KEY` в `.env` (отдельный от `OPENAI_API_KEY`).
  structured_output выключен (не поддерживается) — ответ разбирается устойчивым
  парсером free-text. TLS: `ssl.CERT_NONE` либо `GIGACHAT_CA_BUNDLE` для prod.
- **YandexGPT** (`auth_mode=yandex_folder`) — пресет заполняет endpoint/модель
  (модель — URI с `<folder_id>`); запрос через OpenAI SDK с
  `default_headers={"x-folder-id", "x-data-logging-enabled: false"}`; folder_id —
  runtime-ключ `yandex_folder_id` (подставляется в URI и заголовок). API-ключ
  Yandex — в `OPENAI_API_KEY` (как Bearer). structured_output выключен.
- **Свой** (`auth_mode=openai_key`) — пустые endpoint/модель, оператор заполняет
  вручную; `OPENAI_API_KEY` как Bearer; structured_output по умолчанию Вкл.

### 🧪 Статус верификации (2026-08-13)

- **OpenAI** — end-to-end верифицирован реальным запросом к `gpt-5-mini`
  (structured_output, план с pie-графиком), `test_connection` OK.
- **GigaChat** — end-to-end верифицирован реальным `GIGACHAT_AUTH_KEY`
  (authorization key Сбер, из локального `.env`):
  `enabled=True`, `test_connection` OK (OAuth-обмен + ping, латентность ~550 мс,
  ответ «pong»), `plan_response` к `GigaChat-Max` вернул план с pie-графиком
  (free-text парсер, structured_output выключен). Без ключа — честная
  конфиг-ошибка, не падение. TLS: `ssl.CERT_NONE` (dev/демо); для prod —
  `GIGACHAT_CA_BUNDLE`.
- **YandexGPT** — код-путь верифицирован: подстановка `<folder_id>` в URI,
  `default_headers` (`x-folder-id`, `x-data-logging-enabled: false`) формируются,
  routing на `llm.api.cloud.yandex.net` подтверждён ответом Yandex (401 на
  OpenAI-ключе — ожидаемо, нужен API-ключ Yandex). End-to-end — при наличии
  API-ключа Yandex + folder_id. Параметры сверены по официальной документации
  (страница `aistudio.yandex.ru` отдала капчу при автоматическом запросе —
  сверка по англ. доке и реализации langchain-yandex).