# Git: только этот сервер (windows-mcp-server)

Репозиторий **один** — каталог **`windows-mcp-server`**, в нём лежит **`.git`**.

Инструмент **`server_update`** с **`full`** / **`git_pull`** делает **`git pull`** в этом каталоге (если настроен **`origin`**) и **`pip install`** в той же папке.

## Сначала создать репозиторий на GitHub (публичный)

Пока репозитория **нет**, **`git push` по SSH не пройдёт** (`Repository not found`). Нужен **пустой публичный** репозиторий **`GreenEngine/lep-windows-mcp-server`**.

### Через сайт (проще всего)

1. Открой: **[github.com/new](https://github.com/new)**  
2. **Repository name:** `lep-windows-mcp-server`  
3. Видимость: **Public**  
4. **НЕ** включай «Add a README» (репозиторий должен быть пустым).  
5. **Create repository**

После этого в каталоге с кодом:

```bash
cd /path/to/windows-mcp-server
git push -u origin main
```

### Через API (нужен Personal Access Token)

Создай токен: **GitHub → Settings → Developer settings → Personal access tokens** — классический токен с правом **`repo`**.

```bash
export GITHUB_TOKEN=ghp_ВАШ_ТОКЕН
curl -sS -X POST \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user/repos \
  -d '{"name":"lep-windows-mcp-server","private":false,"description":"LEP Windows MCP server"}'
```

Ответ **201** — репозиторий создан; затем **`git push -u origin main`**.

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
