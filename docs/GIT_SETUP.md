# Git: только этот сервер (windows-mcp-server)

Репозиторий **один** — каталог **`windows-mcp-server`**, в нём лежит **`.git`**.

Инструмент **`server_update`** с **`full`** / **`git_pull`** делает **`git pull`** в этом каталоге (если настроен **`origin`**) и **`pip install`** в той же папке.

## Первый push (Mac / разработка)

В каталоге сервера уже настроен **`origin`** по SSH:

`git@github.com:GreenEngine/lep-windows-mcp-server.git`

**Вариант 1** — скрипт (создаёт репозиторий через API, если задан **`GITHUB_TOKEN`** с правом **`repo`**, или репозиторий уже есть):

```bash
cd /path/to/windows-mcp-server
./scripts/github_first_push.sh
```

**Вариант 2** — вручную: на GitHub создайте **пустой** репозиторий **`GreenEngine/lep-windows-mcp-server`** (без README), затем:

```bash
cd /path/to/windows-mcp-server
git push -u origin main
```

**Вариант 3** — один раз войти в GitHub CLI и создать репозиторий из папки:

```bash
gh auth login
gh repo create GreenEngine/lep-windows-mcp-server --public --source=. --remote=origin --push
```

(если **`origin`** уже есть, сначала `git remote remove origin` или укажите другое имя remote.)

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
