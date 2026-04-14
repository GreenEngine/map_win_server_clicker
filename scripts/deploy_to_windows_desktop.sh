#!/usr/bin/env bash
# Копирование windows-mcp-server на диск Windows по SSH (rsync поверх ssh).
#
# Требуется: на Windows включён OpenSSH Server, доступ по ключу/паролю.
#
#   export WINDOWS_SSH="Admin@192.168.x.x"
#   export REMOTE_DESKTOP_DIR="C:/Users/Admin/Desktop/windows-mcp-server"
#   ./scripts/deploy_to_windows_desktop.sh
#
# Исключаются .venv и мусор — на ВМ при необходимости: setup_local.ps1
# После копирования перезапустите MCP.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${WINDOWS_SSH:?Задайте WINDOWS_SSH, например: export WINDOWS_SSH=Admin@192.168.1.50}"
REMOTE="${REMOTE_DESKTOP_DIR:-C:/Users/Admin/Desktop/windows-mcp-server}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "Нужен rsync. Установка: brew install rsync" >&2
  exit 1
fi

echo "Источник: $ROOT"
echo "Куда:    ${WINDOWS_SSH}:${REMOTE}"

rsync -avz --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.tmp' \
  --exclude '.pip-cache' \
  --exclude 'python-embed' \
  --exclude '.git' \
  -e ssh \
  "./" "${WINDOWS_SSH}:${REMOTE}/"

echo "Готово. На Windows: перезапустите MCP (server.py или run_local.ps1)."
