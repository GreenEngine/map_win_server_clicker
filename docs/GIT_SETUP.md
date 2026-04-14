# Git и обновление MCP

Публичный репозиторий: **[GreenEngine/map_win_server_clicker](https://github.com/GreenEngine/map_win_server_clicker)**  
(ветка по умолчанию на GitHub: **`master`**; локально можно работать в **`main`** и пушить в **`master`**.)

Корень git совпадает с каталогом сервера (`src/`, `scripts/` в корне клона). **`MCP_REPO_ROOT`** обычно **не нужен**.

## Клон на Windows (сервер)

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/GreenEngine/map_win_server_clicker.git
cd map_win_server_clicker
powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
```

SSH-клон: `git clone git@github.com:GreenEngine/map_win_server_clicker.git`

## Самообновление с GitHub

1. Сервер должен быть установлен **из `git clone`**, не только скопированными файлами — в каталоге должен быть **`.git`** и **`origin`**.

2. Включено **`MCP_ALLOW_SELF_UPDATE=1`** (по умолчанию в `server.py`, если не задано иначе).

3. Из Cursor вызови инструмент **`server_update`** с режимом **`full`**:
   - выполнится **`git pull --ff-only`** в корне репозитория;
   - затем **`pip install -r requirements.txt`**;
   - после смены **`.py`** **перезапусти** процесс MCP вручную (или планировщиком).

4. Опционально — **Планировщик заданий** на Windows: раз в день `git -C "C:\...\map_win_server_clicker" pull` и перезапуск `python` с `server.py` (если нужен pull без агента).

## Разработка на Mac

```bash
git clone git@github.com:GreenEngine/map_win_server_clicker.git
cd map_win_server_clicker
# правки → commit → push
git push origin main:master
```

## Обновление только зависимостей

Инструмент **`server_update`** с режимом **`pip`** — без `git pull`.
