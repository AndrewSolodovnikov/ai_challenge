import requests
import os

def send_telegram_alert(title, text):
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] ❌ Token or chat_id not set")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': f"<b>{title}</b>\n{text}",
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        resp = requests.post(url, data=payload, timeout=100)
        if resp.status_code == 200:
            print("[Telegram] ✅ Alert sent!")
            return True
        else:
            print(f"[Telegram] ❌ Alert error: {resp.status_code}, {resp.text}")
            return False
    except Exception as e:
        print(f"[Telegram] ❌ send_telegram_alert error: {e}")
        return False

def send_telegram_file(filename, content, caption=None):
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] ❌ Token or chat_id not set")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    files = {
        'document': (filename, content.encode('utf-8'), 'text/plain')
    }
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'caption': caption or filename,
        'parse_mode': 'HTML'
    }

    try:
        resp = requests.post(url, files=files, data=data, timeout=100)
        if resp.status_code == 200:
            print("[Telegram] ✅ File sent!")
            return True
        else:
            print(f"[Telegram] ❌ File not sent: {resp.status_code}, {resp.text}")
            return False
    except Exception as e:
        print(f"[Telegram] ❌ send_telegram_file error: {e}")
        return False