#!/usr/bin/env bash
# Первый push на GitHub: создать репозиторий (API) и git push по SSH.
# Нужен токен с правом repo ИЛИ уже созданный пустой репозиторий на github.com.
#
# Вариант A — токен (classic: repo, или fine-grained: Contents RW):
#   export GITHUB_TOKEN=ghp_xxxx
#   ./scripts/github_first_push.sh
#
# Вариант B — репозиторий уже создан вручную на GitHub (пустой, без README):
#   ./scripts/github_first_push.sh
#
# Вариант C — только авторизация gh (один раз):
#   gh auth login
#   gh repo create GreenEngine/lep-windows-mcp-server --public --source=. --remote=origin --push

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OWNER="${GITHUB_OWNER:-GreenEngine}"
REPO="${GITHUB_REPO:-lep-windows-mcp-server}"
TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"

if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "git@github.com:${OWNER}/${REPO}.git"
fi

if [[ -n "${TOKEN}" ]]; then
  echo "Создание репозитория ${OWNER}/${REPO} через API..."
  code=$(curl -sS -o /tmp/gh_create.json -w "%{http_code}" -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/user/repos" \
    -d "{\"name\":\"${REPO}\",\"private\":false,\"description\":\"LEP Windows MCP server\"}" || true)
  if [[ "${code}" == "201" ]]; then
    echo "Репозиторий создан."
  elif [[ "${code}" == "422" ]]; then
    echo "Репозиторий уже существует (422), продолжаем push."
  else
    echo "Ответ API: HTTP ${code}, см. /tmp/gh_create.json"
    cat /tmp/gh_create.json 2>/dev/null || true
  fi
fi

echo "git push -u origin main ..."
git push -u origin main
echo "Готово: https://github.com/${OWNER}/${REPO}"
