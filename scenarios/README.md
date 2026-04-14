# JSON-сценарии LEP / nanoCAD (MCP)

Декларативный список вызовов инструментов Windows MCP для агента **lep-plugin-tester**. Сами вызовы выполняет агент в Cursor по сгенерированному промпту ([`scripts/run_lep_scenario.py`](../scripts/run_lep_scenario.py)).

## Схема (version: 1)

| Поле | Обязательно | Описание |
|------|---------------|----------|
| `id` | да | Короткий идентификатор латиницей (префикс имён файлов). |
| `title` | да | Человекочитаемое название. |
| `version` | да | Число схемы; сейчас только **1**. |
| `skip_nanocad_lep_prepare` | нет | Если `true`, в промпте не требовать шаг `nanocad_lep_prepare` (CAD уже поднят). |
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

## Старая матрица 10×

[`../../reports/qa_full_plugin_10runs_matrix.json`](../../reports/qa_full_plugin_10runs_matrix.json) и [`../scripts/run_lep_qa_matrix.py`](../scripts/run_lep_qa_matrix.py) остаются для чеклистов без строгого `invoke`+`args`. Новые фичи оформляйте в **`scenarios/*.json`**.
