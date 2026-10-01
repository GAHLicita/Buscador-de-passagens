#!/usr/bin/env bash
# Instala o buscador e agenda a busca diária às 07:17 (Linux ou Mac).
# Uso: bash instalar.sh
set -euo pipefail
cd "$(dirname "$0")"
PASTA="$(pwd)"

if ! command -v python3 >/dev/null; then
  echo "Python 3 não encontrado. No Ubuntu/Debian/Mint rode: sudo apt install python3 python3-venv"
  exit 1
fi
if [ ! -x .venv/bin/python ] && ! python3 -c "import ensurepip" 2>/dev/null; then
  echo "Falta o módulo venv do Python. No Ubuntu/Debian/Mint rode:"
  echo "  sudo apt install python3-venv"
  echo "e depois rode este instalador de novo."
  exit 1
fi

echo "==> Criando ambiente Python e instalando dependências"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q

echo "==> Instalando o navegador automatizado (Chromium)"
.venv/bin/python -m playwright install chromium
if ! .venv/bin/python -c "
from playwright.sync_api import sync_playwright
p = sync_playwright().start(); p.chromium.launch().close(); p.stop()" >/dev/null 2>&1; then
  echo "    O Chromium não abriu: faltam bibliotecas do sistema. Rode:"
  echo "      sudo $PASTA/.venv/bin/python -m playwright install-deps chromium"
  echo "    (o buscador funciona sem isso se a API da Smiles responder direto)"
fi

[ -f .env ] || cp .env.exemplo .env

COMANDO="cd \"$PASTA\" && PYTHONIOENCODING=utf-8 .venv/bin/python buscador.py >> busca.log 2>&1"

remover_cron_antigo() {
  if command -v crontab >/dev/null && crontab -l 2>/dev/null | grep -q '# buscador-smiles'; then
    crontab -l | grep -v '# buscador-smiles' | crontab -
  fi
}

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

elif systemctl --user show-environment >/dev/null 2>&1; then
  # No Linux preferimos um timer do systemd: com Persistent=true, se o PC estiver
  # desligado às 07:17, a busca roda assim que você ligar e entrar na sua conta.
  UNIDADES="$HOME/.config/systemd/user"
  mkdir -p "$UNIDADES"
  cat > "$UNIDADES/buscador-smiles.service" <<UNIT
[Unit]
Description=Busca diária de passagens em milhas Smiles

[Service]
Type=oneshot
WorkingDirectory=$PASTA
Environment=PYTHONIOENCODING=utf-8
# Espera a internet ficar disponível (até 5 min) depois de ligar o PC.
ExecStartPre=/bin/bash -c 'for i in {1..30}; do getent hosts www.smiles.com.br >/dev/null && exit 0; sleep 10; done; exit 0'
ExecStart=/bin/bash -c '.venv/bin/python buscador.py >> busca.log 2>&1'
TimeoutStartSec=3h
UNIT
  cat > "$UNIDADES/buscador-smiles.timer" <<UNIT
[Unit]
Description=Busca diária de passagens Smiles às 07:17

[Timer]
OnCalendar=*-*-* 07:17:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable --now buscador-smiles.timer
  remover_cron_antigo
  echo "==> Busca agendada com o systemd (todo dia às 07:17)"
  systemctl --user list-timers buscador-smiles.timer --no-pager || true

elif command -v crontab >/dev/null; then
  ( crontab -l 2>/dev/null | grep -v '# buscador-smiles' || true
    echo "17 7 * * * $COMANDO # buscador-smiles" ) | crontab -
  echo "==> Busca agendada no cron (todo dia às 07:17)"

else
  echo "==> Não encontrei systemd nem cron para agendar. Instale o cron (sudo apt install cron)"
  echo "    e rode de novo, ou agende manualmente:  17 7 * * * $COMANDO"
fi

cat <<FIM

Pronto! Agora:
 1. Abra o arquivo .env desta pasta e preencha SMTP_USUARIO e SMTP_SENHA.
 2. Teste o e-mail:   .venv/bin/python buscador.py --testar-notificacao
 3. Busque agora:     .venv/bin/python buscador.py
FIM
