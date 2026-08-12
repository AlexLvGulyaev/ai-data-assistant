# Prompts

Версионированные промпты. Каталог `prompts/` — источник истины для системного
промпта; загружается `app/services/prompt_loader.py` с mtime-кешем, поэтому
правка файла применяется в runtime без рестарта процесса.

## Структура

```
prompts/
└── v1/
    └── system.md            — системный промпт (шаблон с плейсхолдерами)
```

> JSON-схема ответа модели (structured output) **не хранится** файлом — она
> генерируется из реестров `ACTION_TYPES`/`CHART_TYPES` в
> `app/services/ai_service.py` (`_build_response_schema`). Это сохраняет единый
> источник истины: модель не может вернуть действие/график, отсутствующий в
> реестрах. См. `app/services/registries.py` и `docs/ARCHITECTURE.md` §4.

## Плейсхолдеры `system.md`

| Плейсхолдер              | Источник значения          | Пример                          |
|--------------------------|----------------------------|---------------------------------|
| `{{specialization}}`     | `ASSISTANT_SPECIALIZATION` / runtime-config | «финансовый аналитик» |
| `{{provider_attribution}}` | `PROVIDER_NAME` / runtime-config | « от GigaChat» либо `` (нейтрально) |

`{{provider_attribution}}` рассчитывается как ` от {provider_name}`, если
`provider_name` задан, иначе пустая строка — промпт остаётся нейтральным и
корректным для любого провайдера (OpenAI, GigaChat, YandexGPT, Gemini и т.п.).

## Версионирование

Новая версия промпта — новый каталог (`v2/`). Это позволяет сравнивать версии и
откатываться без правки кода. Активная версия задаётся в `PromptLoader`
(`DEFAULT_VERSION`), при необходимости выносится в runtime-config.