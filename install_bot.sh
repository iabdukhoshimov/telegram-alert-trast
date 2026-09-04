#!/usr/bin/env bash
# ==============================================================================
# install_bot.sh
# Installs the Telegram alertbot on the monitoring server.
# Run AFTER install_monitoring.sh.
# Rocky Linux / RHEL / AlmaLinux
# ==============================================================================
set -euo pipefail

INSTALL_DIR="/opt/telegram-alertbot"
SERVICE_USER="alertbot"
BOT_SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root: sudo bash $0"

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║   Telegram Alertbot Installer                    ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Python 3 ──────────────────────────────────────────────────────────────────
log "Checking Python 3..."
if ! command -v python3 &>/dev/null; then
  dnf install -y python3 python3-pip python3-venv
fi
python3 --version

# ── Service user ──────────────────────────────────────────────────────────────
log "Creating user ${SERVICE_USER}..."
id "$SERVICE_USER" &>/dev/null || \
  useradd --system --no-create-home --shell /sbin/nologin "$SERVICE_USER"

# ── Install directory ─────────────────────────────────────────────────────────
log "Installing to ${INSTALL_DIR}..."
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$INSTALL_DIR"
install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0640 \
  "${BOT_SRC_DIR}/bot.py" \
  "${BOT_SRC_DIR}/requirements.txt" \
  "$INSTALL_DIR/"

# ── .env ──────────────────────────────────────────────────────────────────────
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0600 \
    "${BOT_SRC_DIR}/.env.example" \
    "${INSTALL_DIR}/.env"
  warn ".env created from example — edit ${INSTALL_DIR}/.env before starting!"
  warn "  Set BOT_TOKEN and CHAT_IDS then re-run this script or: systemctl start telegram_alertbot"
else
  log ".env already exists, keeping it"
fi

# ── Virtualenv + deps ─────────────────────────────────────────────────────────
log "Setting up Python virtualenv..."
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/venv"

# ── Systemd service ───────────────────────────────────────────────────────────
log "Installing systemd service..."
install -o root -g root -m 0644 \
  "${BOT_SRC_DIR}/telegram_alertbot.service" \
  /etc/systemd/system/telegram_alertbot.service

systemctl daemon-reload
systemctl enable telegram_alertbot

# Only start if .env has real values (check for any example/placeholder token)
_bot_token_value=$(grep -Po '(?<=BOT_TOKEN=)\S+' "${INSTALL_DIR}/.env" 2>/dev/null || true)
if [[ -z "$_bot_token_value" || "$_bot_token_value" == *"xxxx"* || "$_bot_token_value" == *"YOUR_"* ]]; then
  warn "BOT_TOKEN looks like placeholder — NOT starting service"
  warn "Edit ${INSTALL_DIR}/.env then run: systemctl start telegram_alertbot"
else
  systemctl restart telegram_alertbot
  sleep 2
  if systemctl is-active --quiet telegram_alertbot; then
    log "telegram_alertbot is running"
  else
    warn "Service failed to start — check: journalctl -u telegram_alertbot -n 50"
  fi
fi

echo ""
echo -e "${GREEN}Bot installed!${NC}"
echo ""
echo "  Config:  ${INSTALL_DIR}/.env"
echo "  Logs:    journalctl -u telegram_alertbot -f"
echo "  Status:  systemctl status telegram_alertbot"
echo ""
echo "  Alertmanager webhook URL: http://127.0.0.1:5001/alert"
echo "  Health check:             http://127.0.0.1:5001/health"
