# 🗃️ Data Assistant — каталог медиаматериалов

**Проект:** ai-data-assistant
**Дата:** 2026-08-13
**Статус:** as-built (скриншоты — human-in-the-loop, оператор снимает по подписям)

---

## 🎯 1. Назначение

Единый каталог всех изображений проекта. Каждому скриншоту присвоен
**IMG-ID**, по которому на него ссылаются остальные документы
([`SCREENSHOTS.md`](../SCREENSHOTS.md), [`E2E_SCENARIOS.md`](../E2E_SCENARIOS.md),
`README.md`). Скриншоты делает оператор в браузере по живому демо
`https://data-assistant.alex-n8n.site` — по подписям из этого каталога.

---

## 📐 2. Схема нейминга

```
ADA_<context>_<description>.png
```

| Часть | Значение |
|-------|----------|
| `ADA` | Префикс кейса (AI Data Assistant). |
| `<context>` | Контур интерфейса: `home`, `preview`, `chat`, `admin`. |
| `<description>` | Краткое описание содержимого (snake_case). |

**Категории контекста:**

| Контекст | Что фиксирует |
|----------|----------------|
| `home` | Главная страница, зона загрузки. |
| `preview` | Страница preview файла (CSV/изображение). |
| `chat` | Чат-контур: результаты действий, диалог, артефакты. |
| `admin` | Операторская консоль `/admin`. |

---

## 🗂️ 3. Каталог изображений

### Пользовательский контур (чат)

| IMG-ID | Файл | Контур | Что показано |
|--------|------|--------|--------------|
| IMG-01 | `ADA_home_upload.png` | home | Главная: зона загрузки файла. |
| IMG-02 | `ADA_preview_csv.png` | preview | Preview CSV: строки, мета, numeric-колонки. |
| IMG-03 | `ADA_chat_analyze.png` | chat | Карточка анализа: stats-strip, инсайты, статистики. |
| IMG-04 | `ADA_chat_pie.png` | chat | Круговая диаграмма + карточка артефакта. |
| IMG-05 | `ADA_chat_bar.png` | chat | Столбчатая диаграмма. |
| IMG-06 | `ADA_chat_line.png` | chat | Линейный график. |
| IMG-07 | `ADA_chat_histogram.png` | chat | Гистограмма распределения. |
| IMG-08 | `ADA_chat_report.png` | chat | Карточка DOCX-отчёта с кнопкой скачивания. |
| IMG-09 | `ADA_chat_summary.png` | chat | Карточка markdown-сводки. |
| IMG-10 | `ADA_preview_image.png` | preview | Preview изображения: размеры, режим, формат. |
| IMG-11 | `ADA_chat_image_chart.png` | chat | Гистограмма яркости пикселей. |
| IMG-12 | `ADA_chat_multi_files.png` | chat | Раздел «Файлы в чате»: переключение контекста. |
| IMG-13 | `ADA_chat_free_dialog.png` | chat | Свободный запрос: модель выбрала действие. |
| IMG-14 | `ADA_chat_prompt_applied.png` | chat | Ответ с применённым новым промптом. |

### Операторский контур (админка `/admin`)

| IMG-ID | Файл | Контур | Что показано |
|--------|------|--------|--------------|
| IMG-15 | `ADA_admin_overview.png` | admin | Общий вид `/admin`: промпт + Runtime-конфиг + Реестры. |
| IMG-16 | `ADA_admin_prompt_edit.png` | admin | Редактор системного промпта. |
| IMG-17 | `ADA_admin_model_swap.png` | admin | Смена модели + «Тест провайдера». |
| IMG-18 | `ADA_admin_provider_presets.png` | admin | Чипы пресетов провайдера + автозаполнение. |
| IMG-19 | `ADA_admin_temp_seed.png` | admin | Поля «Температура» и «Seed». |
| IMG-20 | `ADA_admin_specialization.png` | admin | Поле «Специализация». |
| IMG-21 | `ADA_admin_registries.png` | admin | Реестры агента (read-only). |
| IMG-22 | `ADA_admin_usage.png` | admin | Дашборд статистики использования. |
| IMG-23 | `ADA_admin_structured_output.png` | admin | Переключатель structured_output. |

---

## 📊 4. Матрица использования

Где какой скриншот упоминается.

| IMG-ID | Файл | SCREENSHOTS | E2E_SCENARIOS | README |
|--------|------|:-----------:|:-------------:|:------:|
| IMG-01 | `ADA_home_upload.png` | ✅ | §2 | ✅ |
| IMG-02 | `ADA_preview_csv.png` | ✅ | §2 | — |
| IMG-03 | `ADA_chat_analyze.png` | ✅ | §3 | ✅ |
| IMG-04 | `ADA_chat_pie.png` | ✅ | §4 | — |
| IMG-05 | `ADA_chat_bar.png` | ✅ | §5 | — |
| IMG-06 | `ADA_chat_line.png` | ✅ | §6 | — |
| IMG-07 | `ADA_chat_histogram.png` | ✅ | §7 | — |
| IMG-08 | `ADA_chat_report.png` | ✅ | §8 | ✅ |
| IMG-09 | `ADA_chat_summary.png` | ✅ | §9 | — |
| IMG-10 | `ADA_preview_image.png` | ✅ | §10 | — |
| IMG-11 | `ADA_chat_image_chart.png` | ✅ | §10 | — |
| IMG-12 | `ADA_chat_multi_files.png` | ✅ | §11 | — |
| IMG-13 | `ADA_chat_free_dialog.png` | ✅ | §12 | ✅ |
| IMG-14 | `ADA_chat_prompt_applied.png` | ✅ | §14 | — |
| IMG-15 | `ADA_admin_overview.png` | ✅ | §13 | ✅ |
| IMG-16 | `ADA_admin_prompt_edit.png` | ✅ | §14 | — |
| IMG-17 | `ADA_admin_model_swap.png` | ✅ | §15 | — |
| IMG-18 | `ADA_admin_provider_presets.png` | ✅ | §16 | — |
| IMG-19 | `ADA_admin_temp_seed.png` | ✅ | §17 | — |
| IMG-20 | `ADA_admin_specialization.png` | ✅ | §18 | — |
| IMG-21 | `ADA_admin_registries.png` | ✅ | §19 | — |
| IMG-22 | `ADA_admin_usage.png` | ✅ | §20 | — |
| IMG-23 | `ADA_admin_structured_output.png` | ✅ | §21 | — |

---

## 📝 5. Замечания по съёмке

- **Разрешение:** 1440×900 (стандартный ноутбук) или 1920×1080; указать в
  подписи, если снято в мобильном viewport.
- **Демо-данные:** использовать `examples/sample_sales.csv` и
  `examples/sample_chart_data.csv` (входят в репозиторий).
- **Админка:** Basic-авторизация `admin` / `ADMIN_TOKEN`. Перед съёмкой —
  выполнить сценарий до шага, дающего нужное состояние (например, для
  IMG-14 сначала сменить промпт в `/admin`, затем отправить чат-запрос).
- **Свободный диалог (IMG-13) и применённый промпт (IMG-14):** требуют
  реального вызова LLM (тратят токены). Снимать после проверки связи
  «Тестом провайдера».
- **Реестры (IMG-21):** read-only — снимаются как есть, без правки.

---

## 📚 Связанные документы

- [🖼️ `../SCREENSHOTS.md`](../SCREENSHOTS.md) — галерея с подписями.
- [🎬 `../E2E_SCENARIOS.md`](../E2E_SCENARIOS.md) — сквозные сценарии.
- [🏠 `../../README.md`](../../README.md) — главная страница проекта.