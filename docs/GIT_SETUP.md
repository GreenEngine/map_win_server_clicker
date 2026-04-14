# Git: только этот сервер (windows-mcp-server)

Репозиторий **один** — каталог **`windows-mcp-server`**, в нём лежит **`.git`**.

Инструмент **`server_update`** с **`full`** / **`git_pull`** делает **`git pull`** в этом каталоге (если настроен **`origin`**) и **`pip install`** в той же папке.

## Первый push (Mac / разработка)

```bash
cd /path/to/LEP/windows-mcp-server
git remote add origin https://github.com/<АККАУНТ>/<РЕПО-mcp>.git
git push -u origin main
```

Создайте **пустой** репозиторий на GitHub/GitLab, затем команды выше.

## Клон на Windows (сервер)

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/<АККАУНТ>/<РЕПО-mcp>.git windows-mcp-server
cd windows-mcp-server
powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
```

**`MCP_REPO_ROOT`** задавать **не нужно**: корень git совпадает с каталогом сервера (`update.py` ищет **`.git`** в **`windows-mcp-server`** первым).

## Обновление с агента (Cursor)

После изменений на GitHub: **`server_update`** → **`full`** → перезапуск процесса **`server.py`**.
