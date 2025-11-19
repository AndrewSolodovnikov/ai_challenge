"""Notifications module - Telegram, Email, etc."""
import os
import requests
from datetime import datetime


def send_telegram_message(message, chat_id=None):
    """Отправить сообщение в Telegram"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token:
        print("[Telegram] ⚠️  Bot token not configured")
        return False

    if not chat_id:
        print("[Telegram] ⚠️  Chat ID not configured")
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data)

        if response.status_code == 200:
            print(f"[Telegram] ✅ Message sent at {datetime.now().strftime('%H:%M:%S')}")
            return True
        else:
            print(f"[Telegram] ❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"[Telegram] ❌ Error: {e}")
        return False


def send_telegram_alert(title, details):
    """Отправить красивый alert в Telegram"""
    message = f"""
<b>🔔 {title}</b>

{details}

<i>📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</i>
"""
    return send_telegram_message(message)
