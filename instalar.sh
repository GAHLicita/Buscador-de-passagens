#!/usr/bin/env bash
# Instala o buscador e agenda a busca diária às 07:17 (Mac ou Linux).
# Uso: bash instalar.sh
set -euo pipefail
cd "$(dirname "$0")"
PASTA="$(pwd)"

if ! command -v python3 >/dev/null; then
  echo "Python 3 não encontrado. Instale em https://www.python.org/downloads/ e rode de novo."
  exit 1
fi

echo "==> Criando ambiente Python e instalando dependências"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q

echo "==> Instalando o navegador automatizado (Chromium)"
.venv/bin/python -m playwright install chromium

[ -f .env ] || cp .env.exemplo .env

COMANDO="cd \"$PASTA\" && PYTHONIOENCODING=utf-8 .venv/bin/python buscador.py >> busca.log 2>&1"

if [ "$(uname)" = "Darwin" ]; then
  # No Mac usamos o launchd: se o Mac estiver dormindo às 07:17, roda ao acordar.
  PLIST="$HOME/Library/LaunchAgents/br.buscador-smiles.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>br.buscador-smiles</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>-c</string><string>$COMANDO</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>17</integer></dict>
</dict>
</plist>
PLIST
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "==> Busca agendada no launchd (todo dia às 07:17)"
elif ! command -v crontab >/dev/null; then
  echo "==> 'crontab' não encontrado. Instale o cron (ex.: sudo apt install cron) e rode de novo,"
  echo "    ou agende manualmente:  17 7 * * * $COMANDO"
else
  ( crontab -l 2>/dev/null | grep -v '# buscador-smiles' || true
    echo "17 7 * * * $COMANDO # buscador-smiles" ) | crontab -
  echo "==> Busca agendada no cron (todo dia às 07:17)"
fi

cat <<FIM

Pronto! Agora:
 1. Abra o arquivo .env desta pasta e preencha SMTP_USUARIO e SMTP_SENHA.
 2. Teste o e-mail:   .venv/bin/python buscador.py --testar-notificacao
 3. Busque agora:     .venv/bin/python buscador.py
FIM
