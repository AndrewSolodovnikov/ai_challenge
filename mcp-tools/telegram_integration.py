"""Telegram Integration - инструменты для прямой отправки в Telegram"""
import os
from mcp_tools.notifications import send_telegram_file, send_telegram_alert


def register_telegram_tools(registry):
    """Регистрировать инструменты для отправки в Telegram"""

    def send_file_to_telegram(filename, content, caption=None):
        """Отправить файл в Telegram"""
        print(f"[TelegramTools] 📤 Sending file: {filename}")
        ok = send_telegram_file(filename, content, caption)
        return {
            "success": ok,
            "message": f"File sent to Telegram: {filename}" if ok else "Failed to send file",
            "size": len(content) if ok else 0
        }

    def send_alert_to_telegram(title, message):
        """Отправить alert в Telegram"""
        print(f"[TelegramTools] 🔔 Sending alert: {title}")
        ok = send_telegram_alert(title, message)
        return {
            "success": ok,
            "message": "Alert sent to Telegram" if ok else "Failed to send alert"
        }

    # Регистрировать инструменты
    registry.register(
        "send_file_to_telegram",
        send_file_to_telegram,
        "Send a file to Telegram chat",
        {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename for the document"},
                "content": {"type": "string", "description": "File content to send"},
                "caption": {"type": "string", "description": "Optional caption/title"}
            },
            "required": ["filename", "content"]
        }
    )

    registry.register(
        "send_alert_to_telegram",
        send_alert_to_telegram,
        "Send an alert message to Telegram",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Alert title"},
                "message": {"type": "string", "description": "Alert message text"}
            },
            "required": ["title", "message"]
        }
    )

    print("[TelegramTools] ✅ Registered 2 tools")