#!/usr/bin/env python3
"""
Alertmanager → Telegram webhook bot.

Alertmanager sends webhook → this bot formats it → sends to Telegram.

Config (set in .env or export as env vars):
  BOT_TOKEN    — Telegram bot token from @BotFather  (required)
  CHAT_IDS     — comma-separated list of chat IDs    (required)
                 group chat IDs are negative numbers: -1001234567890
  LISTEN_HOST  — bind address  (default: 127.0.0.1)
  LISTEN_PORT  — listen port   (default: 5001)

Alertmanager webhook_configs url: http://127.0.0.1:5001/alert
"""

import logging
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

_raw_token    = os.environ.get("BOT_TOKEN", "").strip()
_raw_chat_ids = os.environ.get("CHAT_IDS", "").strip()

if not _raw_token:
    raise RuntimeError("BOT_TOKEN env var is required but not set")
if not _raw_chat_ids:
    raise RuntimeError("CHAT_IDS env var is required but not set")

BOT_TOKEN   = _raw_token
CHAT_IDS    = [c.strip() for c in _raw_chat_ids.split(",") if c.strip()]
LISTEN_HOST = os.getenv("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "5001"))

if not CHAT_IDS:
    raise RuntimeError("CHAT_IDS is set but contains no valid IDs")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_ts(ts: str) -> str:
    """ISO-8601 timestamp → 'YYYY-MM-DD HH:MM UTC'. Returns '' on failure."""
    if not ts or ts.startswith("0001"):
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return ""


SEVERITY_ICON = {
    "critical": "🔴",
    "warning":  "🟡",
    "info":     "🔵",
    "none":     "⚪",
}

# Telegram message size limit
_MAX_MSG_LEN = 4096


def format_alert(alert: dict) -> str:
    """Format a single Alertmanager alert into an HTML Telegram message."""
    status    = alert.get("status", "unknown")
    labels    = alert.get("labels", {})
    ann       = alert.get("annotations", {})

    alertname = labels.get("alertname", "Unknown")
    severity  = labels.get("severity", "unknown")
    instance  = labels.get("instance", "n/a")
    job       = labels.get("job", "")
    summary   = ann.get("summary", "")
    desc      = ann.get("description", "")

    if status == "firing":
        status_icon = SEVERITY_ICON.get(severity, "🔴")
        status_text = "FIRING"
        ts_label    = "Started"
        ts_value    = _parse_ts(alert.get("startsAt", ""))
    else:
        status_icon = "✅"
        status_text = "RESOLVED"
        ts_label    = "Resolved"
        ts_value    = _parse_ts(alert.get("endsAt", ""))

    lines = [
        f"{status_icon} <b>{status_text}: {alertname}</b>",
        "",
        f"<b>Severity:</b>  {severity}",
        f"<b>Instance:</b>  {instance}",
    ]

    if job:
        lines.append(f"<b>Job:</b>       {job}")
    if summary:
        lines.append(f"<b>Xulosa:</b>    {summary}")    # Summary in Uzbek
    if desc:
        lines.append(f"<b>Details:</b>   {desc}")
    if ts_value:
        lines.append(f"<b>{ts_label}:</b>  {ts_value}")

    text = "\n".join(lines)
    if len(text) > _MAX_MSG_LEN:
        text = text[: _MAX_MSG_LEN - 20] + "\n<i>…truncated</i>"
    return text


def send_message(chat_id: str, text: str, retries: int = 3) -> None:
    """Send message to Telegram with exponential back-off retry."""
    delay = 2
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                TELEGRAM_URL,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                log.warning("Telegram send attempt %d/%d failed, retrying in %ds", attempt, retries, delay)
                time.sleep(delay)
                delay *= 2
    raise last_exc  # type: ignore[misc]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/alert")
def receive_alert():
    """Alertmanager webhook endpoint."""
    raw = request.get_data()
    payload = request.get_json(force=True, silent=True)
    if payload is None:
        log.warning("Received unparseable body (%d bytes): %r", len(raw), raw[:200])
        return jsonify({"error": "invalid JSON"}), 400

    alerts = payload.get("alerts", [])
    if not alerts:
        return jsonify({"ok": True, "sent": 0})

    sent   = 0
    failed = 0

    for alert in alerts:
        alertname = alert.get("labels", {}).get("alertname", "?")
        status    = alert.get("status", "?")
        text      = format_alert(alert)

        for chat_id in CHAT_IDS:
            try:
                send_message(chat_id, text)
                sent += 1
                # Log chat_id as last 4 chars only — avoids leaking full group ID in logs
                log.info("alert=%s status=%s → chat=…%s", alertname, status, chat_id[-4:])
            except requests.HTTPError as exc:
                failed += 1
                log.error(
                    "Telegram API error alert=%s: HTTP %s — %s",
                    alertname,
                    exc.response.status_code,
                    exc.response.text[:200],
                )
            except requests.RequestException as exc:
                failed += 1
                log.error("Network error alert=%s: %s", alertname, exc)

    status_code = 200 if failed == 0 else 207
    return jsonify({"ok": failed == 0, "sent": sent, "failed": failed}), status_code


@app.get("/health")
def health():
    """Liveness probe."""
    return jsonify({"ok": True, "chats": len(CHAT_IDS)})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info(
        "telegram-alertbot starting | host=%s port=%s chat_count=%d",
        LISTEN_HOST, LISTEN_PORT, len(CHAT_IDS),  # count only — not IDs
    )
    app.run(host=LISTEN_HOST, port=LISTEN_PORT)
