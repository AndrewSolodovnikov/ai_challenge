from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import os
import json
import anthropic
import io
from datetime import datetime

gdrive_service = None
previous_files = {}
scheduler_instance = None

def set_gdrive_service(service):
    global gdrive_service
    gdrive_service = service
    print("[Scheduler] ✅ Google Drive service set")

def is_telegram_enabled():
    from database import get_setting
    enabled = get_setting(1, 'telegram_enabled', 'true')
    return enabled == 'true'

def send_telegram_alert(title, details):
    if not is_telegram_enabled():
        print("[Telegram] ⏸️  Notifications disabled in settings")
        return False

    from mcp_tools.notifications import send_telegram_alert as send_alert
    return send_alert(title, details)

def read_file_content(file_id, mime_type, file_name):
    if not gdrive_service:
        return None

    try:
        if mime_type == 'application/vnd.google-apps.document':
            request = gdrive_service.files().export(fileId=file_id, mimeType='text/plain')
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            request = gdrive_service.files().export(fileId=file_id, mimeType='text/csv')
        elif 'text' in mime_type or mime_type in ['application/json', 'application/javascript', 'application/xml']:
            request = gdrive_service.files().get_media(fileId=file_id)
        else:
            return None

        file_stream = io.BytesIO()
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(file_stream, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_stream.seek(0)
        content = file_stream.read().decode('utf-8', errors='ignore')

        max_chars = 5000
        if len(content) > max_chars:
            truncate_msg = f"\n\n[...truncated, total {len(content)} chars]"
            content = content[:max_chars] + truncate_msg

        print(f"[Scheduler] 📖 Read {len(content)} chars from {file_name}")
        return content

    except Exception as e:
        print(f"[Scheduler] ⚠️  Cannot read {file_name}: {e}")
        return None

def analyze_new_files_with_claude(new_files):
    if not new_files:
        return None

    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        client = anthropic.Anthropic(api_key=api_key)
        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

        files_data = []
        for f in new_files[:3]:
            file_info = f"Файл: {f['name']}\n"
            file_info += f"Тип: {f['type']}\n"
            file_info += f"Размер: {f.get('size_mb', 0)} MB\n"

            if f.get('content'):
                file_info += f"Содержимое:\n{f['content']}"
            else:
                file_info += "(содержимое недоступно)"

            files_data.append(file_info)

        all_files = "\n\n--- ФАЙЛ ---\n\n".join(files_data)

        prompt = f"""Ты - умный ассистент для анализа файлов. Проанализируй новые файлы добавленные в Google Drive.

{all_files}

Предоставь краткое резюме на русском языке (3-5 предложений):
1. Что это за файлы и их назначение
2. Ключевая информация из содержимого
3. Есть ли что-то важное или требующее внимания

Будь конкретен и полезен."""

        response = client.messages.create(
            model=model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        summary = response.content[0].text if response.content else None
        print(f"[Scheduler] 🤖 Claude analysis complete")
        return summary

    except Exception as e:
        print(f"[Scheduler] ❌ Claude analysis error: {e}")
        return None

def get_folder_files(folder_id):
    if not gdrive_service:
        return []

    try:
        query = f"'{folder_id}' in parents and trashed=false"
        results = gdrive_service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, mimeType, size, modifiedTime, createdTime)",
            orderBy="createdTime desc",
            supportsAllDrives=True
        ).execute()

        files = []
        for f in results.get('files', []):
            size_mb = int(f.get('size', 0)) / (1024**2) if f.get('size') else 0
            files.append({
                "id": f.get('id'),
                "name": f.get('name'),
                "type": f.get('mimeType'),
                "size_mb": round(size_mb, 2),
                "modified": f.get('modifiedTime'),
                "created": f.get('createdTime')
            })

        return files
    except Exception as e:
        print(f"[Scheduler] ❌ Error getting files: {e}")
        return []

def detect_new_files(folder_id, current_files):
    global previous_files

    if folder_id not in previous_files:
        previous_files[folder_id] = {f['id']: f for f in current_files}
        return []

    prev_ids = set(previous_files[folder_id].keys())
    curr_ids = {f['id'] for f in current_files}

    new_ids = curr_ids - prev_ids
    new_files = [f for f in current_files if f['id'] in new_ids]

    previous_files[folder_id] = {f['id']: f for f in current_files}

    return new_files

def folder_monitoring_task():
    folder_id = os.getenv("GDRIVE_FOLDER_ID")
    output_folder_id = os.getenv("GDRIVE_OUTPUT_FOLDER_ID")

    if not folder_id:
        print("[Scheduler] ⚠️  GDRIVE_FOLDER_ID not configured")
        return

    print(f"[Scheduler] 🔍 Checking folder: {folder_id}")

    current_files = get_folder_files(folder_id)

    if output_folder_id:
        current_files = [f for f in current_files if f['id'] != output_folder_id]

    if not current_files:
        send_telegram_alert("📁 Google Drive Monitor", "⚠️ Папка пуста или недоступна")
        return

    folders = sum(1 for f in current_files if 'folder' in f['type'])
    regular_files = len(current_files) - folders

    new_files = detect_new_files(folder_id, current_files)

    print(f"[Scheduler] 📊 Stats: {len(current_files)} total, {len(new_files)} new")

    if new_files:
        message_parts = []
        message_parts.append("📊 <b>Статистика:</b>")
        message_parts.append(f"  • Всего: <b>{len(current_files)}</b> ({folders} папок, {regular_files} файлов)")
        message_parts.append(f"  • 🆕 Новых: <b>{len(new_files)}</b>")
        message_parts.append("")
        message_parts.append("📄 <b>Новые файлы:</b>")

        for f in new_files[:5]:
            file_type = "📁" if 'folder' in f['type'] else "📄"
            message_parts.append(f"  {file_type} <code>{f['name']}</code> ({f['size_mb']} MB)")

            if f['size_mb'] < 5 and 'folder' not in f['type']:
                content = read_file_content(f['id'], f['type'], f['name'])
                if content:
                    f['content'] = content
                    preview = content[:150].replace('\n', ' ')
                    message_parts.append(f"    <i>{preview}...</i>")

        print("[Scheduler] 🤖 Analyzing with Claude...")
        claude_summary = analyze_new_files_with_claude(new_files)

        if claude_summary:
            message_parts.append("")
            message_parts.append("🤖 <b>Анализ Claude:</b>")
            message_parts.append(f"<i>{claude_summary}</i>")

        message = "\n".join(message_parts)
        send_telegram_alert("🆕 Новые файлы в Google Drive!", message)
        print("[Scheduler] ✅ Notification sent with analysis")

    else:
        message = f"""📊 <b>Статистика:</b>
  • Всего: <b>{len(current_files)}</b> ({folders} папок, {regular_files} файлов)

✅ Новых файлов нет"""

        send_telegram_alert("📁 Google Drive Monitor", message)
        print("[Scheduler] ✅ No new files")

def start_scheduler():
    from database import get_setting

    interval = int(get_setting(1, 'monitor_interval', '30'))

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        folder_monitoring_task,
        IntervalTrigger(seconds=interval),
        id='gdrive_monitor',
        name='Google Drive Folder Monitor',
        replace_existing=True
    )

    scheduler.start()
    print(f"[Scheduler] ✅ Started (monitoring every {interval} seconds)")

    return scheduler

def update_scheduler_interval(new_interval):
    global scheduler_instance

    if scheduler_instance:
        try:
            scheduler_instance.reschedule_job(
                'gdrive_monitor',
                trigger=IntervalTrigger(seconds=new_interval)
            )
            print(f"[Scheduler] ✅ Interval updated to {new_interval} seconds")
        except Exception as e:
            print(f"[Scheduler] ❌ Error updating interval: {e}")
    else:
        print(f"[Scheduler] ⚠️  Scheduler not initialized yet")

def get_scheduler():
    global scheduler_instance
    if scheduler_instance is None:
        scheduler_instance = start_scheduler()
    return scheduler_instance