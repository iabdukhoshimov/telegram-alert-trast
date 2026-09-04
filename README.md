# telegram-alert-trast

Alertmanager → Telegram webhook bot. Receives Alertmanager webhooks, formats alerts, sends to Telegram.

Part of [trast-monitoring](https://github.com/iabdukhoshimov/trast-monitoring).

## How it works

```
Alertmanager  ──webhook──►  bot (port 5001)  ──sendMessage──►  Telegram
```

Example message:
```
🔴 FIRING: InstanceDown

Severity:  critical
Instance:  app1.example.com
Job:       node_exporter
Xulosa:    app1.example.com serveri ishlamayapti
Details:   node_exporter app1.example.com serverida 2 daqiqadan beri javob bermayapti.
Started:   2026-09-04 09:15 UTC
```

Resolved alerts show ✅ and `Resolved:` timestamp.

## Install

```bash
bash install_bot.sh
```

This installs to `/opt/telegram-alertbot/` as a systemd service under `alertbot` user.

## Configure

```bash
sudo nano /opt/telegram-alertbot/.env
```

```env
BOT_TOKEN=1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
CHAT_IDS=-1001234567890,987654321
LISTEN_HOST=127.0.0.1
LISTEN_PORT=5001
```

- `BOT_TOKEN` — from [@BotFather](https://t.me/BotFather) via `/newbot`
- `CHAT_IDS` — comma-separated; group chat IDs are negative numbers
- Multiple chat IDs → alert sent to all of them

### How to get group chat ID

1. Create Telegram group and add your bot
2. Send any message in the group
3. Open: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
4. Find `"chat":{"id": -100xxxxxxxxx}` — that negative number is the chat ID

## Start / stop

```bash
sudo systemctl start telegram_alertbot
sudo systemctl stop telegram_alertbot
sudo systemctl status telegram_alertbot

# View logs
sudo journalctl -u telegram_alertbot -f
```

## Health check

```bash
curl http://127.0.0.1:5001/health
# {"ok": true, "chats": 1}
```

## Test alert

```bash
curl -X POST http://127.0.0.1:5001/alert \
  -H 'Content-Type: application/json' \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning",
        "instance": "test-server",
        "job": "node_exporter"
      },
      "annotations": {
        "summary": "Bu test ogohlantirishidir",
        "description": "Hamma narsa yaxshi ishlayapti."
      },
      "startsAt": "2026-09-04T09:00:00Z"
    }]
  }'
```

## Alertmanager config

In `alertmanager.yml` set:

```yaml
receivers:
  - name: telegram
    webhook_configs:
      - url: "http://127.0.0.1:5001/alert"
        send_resolved: true
```

## Severity icons

| Severity | Icon |
|----------|------|
| critical | 🔴 |
| warning | 🟡 |
| info | 🔵 |
| none | ⚪ |
| resolved | ✅ |
