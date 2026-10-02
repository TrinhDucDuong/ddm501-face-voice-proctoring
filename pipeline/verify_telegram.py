"""Check project-owned Telegram credentials without displaying their values."""
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitoring.telegram import request_telegram  # noqa: E402


def main():
    config = {**dotenv_values('.env'), **os.environ}
    token, chat = config.get('TELEGRAM_BOT_TOKEN'), config.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        raise SystemExit('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env')
    status, me = request_telegram(token, 'getMe')
    if status != 200 or not me.get('ok'):
        raise SystemExit('Telegram credential verification failed')
    status, result = request_telegram(token, 'sendMessage', {'chat_id':chat,
        'text':'DDM501 Face Voice Proctoring — Telegram notification verified.\nMonitoring: '
               + config.get('PUBLIC_GRAFANA_URL','http://localhost:13000/d/biometric-overview')})
    evidence = {'bot_username':me['result']['username'],'delivered':status == 200 and result.get('ok',False)}
    Path('reports').mkdir(exist_ok=True)
    Path('reports/telegram-verification.json').write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence))
    if not evidence['delivered']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
