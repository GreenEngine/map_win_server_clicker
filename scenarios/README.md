# JSON-сценарии LEP / nanoCAD (MCP)

Декларативный список вызовов инструментов Windows MCP. **Два режима:** (1) агент **lep-plugin-tester** в Cursor по промпту из [`scripts/run_lep_scenario.py`](../scripts/run_lep_scenario.py); (2) **автономно на Windows** — [`scripts/execute_lep_scenario_local.py`](../scripts/execute_lep_scenario_local.py) выполняет `steps` напрямую через `src/server` (без HTTP и без Cursor).

## Схема (version: 1)

| Поле | Обязательно | Описание |
|------|---------------|----------|
| `id` | да | Короткий идентификатор латиницей (префикс имён файлов). |
| `title` | да | Человекочитаемое название. |
| `version` | да | Число схемы; сейчас только **1**. |
| `skip_nanocad_lep_prepare` | нет | Если `true`, в промпте не требовать шаг `nanocad_lep_prepare` (CAD уже поднят). |
| `stop_on_first_error` | нет | По умолчанию **true**: при `ok: false` у шага сценарий останавливается. **`false`** — выполняются все шаги; итог **`lep_run_scenario`**: `data.all_steps_ok`, `ERR_SCENARIO_PARTIAL`, если были ошибки. |
| `requires` | нет | Объект: `golden_dwg` (bool) — напоминание про `LEP_GOLDEN_DWG`; `note` (string). |
| `steps` | да | Массив шагов по порядку. |

### Шаг (`steps[]`)

| Поле | Обязательно | Описание |
|------|---------------|----------|
| `n` | нет | Номер шага для отчёта; если нет — порядок в массиве. |
| `invoke` | да | Имя инструмента MCP (как в `server.py`). |
| `args` | нет | Объект аргументов инструмента (имена как у MCP). |
| `expect` | нет | Текст: что должно быть видно на скрине после шага (агент сверяет с base64). |
| `capture_label` | нет | Короткий латинский slug для **`filename_suffix`** / `out_path` при парах `capture_*`. |

Поддерживаемые `invoke` перечислены в `ALLOWED_INVOKES` внутри `run_lep_scenario.py` (синхронизируйте при добавлении инструментов на сервер).

## Имена файлов скриншотов

- Предпочтительно задавать **`filename_suffix`** в `args` для `capture_window` / `capture_monitor`, если не передаёте полный **`out_path`**: сервер сохранит PNG в каталог **`MCP_CAPTURE_DIR`** (или системный temp) с именем, содержащим слаг (окно / вкладка / шаг).
- Либо явный **`out_path`** на машине Windows, где крутится MCP (пути с `/` или `\\`).
- В отчёте агент указывает `data.path` и человекочитаемый контекст (`capture_label` / вкладка).

## Связь с UIA id

Стабильные `automation_id` вкладок и кнопок: [`../../ALL/Docs/QA_UiaIds.md`](../../ALL/Docs/QA_UiaIds.md).

## Приёмка «полная работоспособность» (product-delivery + MCP)

Файл **[`lep_mcp_full_operability_smoke.json`](lep_mcp_full_operability_smoke.json)** — минимальная цепочка: **`health`** → **`agent_session`** → **`lep_qa_catalog`** → **`nanocad_lep_prepare`** → пара **`capture_*`** (палитра на скрине) → **`uia_list_subtree`** → вкладки **Трасса** и **Генератор чертежей** с парами снимков после каждого клика.

- Один вызов на ВМ: MCP **`lep_run_scenario("lep_mcp_full_operability_smoke.json")`** (или имя без `.json`).
- Проверка только JSON: `python scripts/execute_lep_scenario_local.py --scenario scenarios/lep_mcp_full_operability_smoke.json --validate-only` (из каталога `windows-mcp-server`, `PYTHONPATH=.`).

Критерии A–F в **`.cursor/skills/product-delivery/SKILL.md`** (раздел «Критерий полная работоспособность»).

## Расширенный UI-прогон палитры (все вкладки)

Файл **[`lep_plugin_full_palette_uia.json`](lep_plugin_full_palette_uia.json)** — обход **всех** главных вкладок по `automation_id` из **`ALL/Docs/QA_UiaIds.md`**, подвкладки **Трасса**, пары **`capture_*`** после каждого клика; **`stop_on_first_error: false`** для полного журнала. Вызов: **`lep_run_scenario("lep_plugin_full_palette_uia.json")`** (долгий прогон, десятки шагов).

## Старая матрица 10×

[`../../reports/qa_full_plugin_10runs_matrix.json`](../../reports/qa_full_plugin_10runs_matrix.json) и [`../scripts/run_lep_qa_matrix.py`](../scripts/run_lep_qa_matrix.py) остаются для чеклистов без строгого `invoke`+`args`. Новые фичи оформляйте в **`scenarios/*.json`**.
