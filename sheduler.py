"""Background scheduler for periodic tasks"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import os
import json
import anthropic
import io
from datetime import datetime
from mcp_tools.notifications import send_telegram_alert

gdrive_service = None
previous_files = {}


def set_gdrive_service(service):
    """Установить сервис Google Drive"""
    global gdrive_service
    gdrive_service = service
    print("[Scheduler] ✅ Google Drive service set")


def read_file_content(file_id, mime_type, file_name):
    """Прочитать содержимое файла"""
    if not gdrive_service:
        return None

    try:
        # Для Google Docs - экспортируем как текст
        if mime_type == 'application/vnd.google-apps.document':
            request = gdrive_service.files().export(fileId=file_id, mimeType='text/plain')
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            request = gdrive_service.files().export(fileId=file_id, mimeType='text/csv')
        # Для текстовых файлов
        elif 'text' in mime_type or mime_type in [
            'application/json',
            'application/javascript',
            'application/xml'
        ]:
            request = gdrive_service.files().get_media(fileId=file_id)
        else:
            return None

        # Загрузить содержимое
        file_stream = io.BytesIO()
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(file_stream, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_stream.seek(0)
        content = file_stream.read().decode('utf-8', errors='ignore')

        # Ограничить до 5000 символов
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
    """Анализ новых файлов с помощью Claude"""
    if not new_files:
        return None

    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        client = anthropic.Anthropic(api_key=api_key)

        # Подготовить данные о файлах
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

        # Объединить все файлы
        all_files = "\n\n--- ФАЙЛ ---\n\n".join(files_data)

        prompt = f"""Ты - умный ассистент для анализа файлов. Проанализируй новые файлы добавленные в Google Drive.

{all_files}

Предоставь краткое резюме на русском языке (3-5 предложений):
1. Что это за файлы и их назначение
2. Ключевая информация из содержимого
3. Есть ли что-то важное или требующее внимания

Будь конкретен и полезен."""

        response = client.messages.create(
            model="claude-opus-4-1",
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
    """Получить список файлов в папке"""
    if not gdrive_service:
        return []

    try:
        query = f"'{folder_id}' in parents and trashed=false"
        results = gdrive_service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, mimeType, size, modifiedTime, createdTime)",
            orderBy="createdTime desc"
        ).execute()

        files = []
        for f in results.get('files', []):
            size_mb = int(f.get('size', 0)) / (1024 ** 2) if f.get('size') else 0
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
    """Определить новые файлы"""
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
    """Фоновая задача для мониторинга папки"""
    folder_id = os.getenv("GDRIVE_FOLDER_ID")

    if not folder_id:
        print("[Scheduler] ⚠️  GDRIVE_FOLDER_ID not configured")
        return

    print(f"[Scheduler] 🔍 Checking folder: {folder_id}")

    current_files = get_folder_files(folder_id)

    if not current_files:
        send_telegram_alert("📁 Google Drive Monitor", "⚠️ Папка пуста или недоступна")
        return

    folders = sum(1 for f in current_files if 'folder' in f['type'])
    regular_files = len(current_files) - folders

    new_files = detect_new_files(folder_id, current_files)

    print(f"[Scheduler] 📊 Stats: {len(current_files)} total, {len(new_files)} new")

    if new_files:
        # Есть новые файлы
        message_parts = []
        message_parts.append("📊 <b>Статистика:</b>")
        message_parts.append(f"  • Всего: <b>{len(current_files)}</b> ({folders} папок, {regular_files} файлов)")
        message_parts.append(f"  • 🆕 Новых: <b>{len(new_files)}</b>")
        message_parts.append("")
        message_parts.append("📄 <b>Новые файлы:</b>")

        for f in new_files[:5]:
            file_type = "📁" if 'folder' in f['type'] else "📄"
            message_parts.append(f"  {file_type} <code>{f['name']}</code> ({f['size_mb']} MB)")

            # Читать содержимое
            if f['size_mb'] < 5 and 'folder' not in f['type']:
                content = read_file_content(f['id'], f['type'], f['name'])
                if content:
                    f['content'] = content
                    preview = content[:150].replace('\n', ' ')
                    message_parts.append(f"    <i>{preview}...</i>")

        # Анализ Claude
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
        # Нет новых файлов
        message = f"""📊 <b>Статистика:</b>
  • Всего: <b>{len(current_files)}</b> ({folders} папок, {regular_files} файлов)

✅ Новых файлов нет"""

        send_telegram_alert("📁 Google Drive Monitor", message)
        print("[Scheduler] ✅ No new files")


def start_scheduler():
    """Запустить планировщик"""
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        folder_monitoring_task,
        IntervalTrigger(seconds=30),
        id='gdrive_monitor',
        name='Google Drive Folder Monitor',
        replace_existing=True
    )

    scheduler.start()
    print("[Scheduler] ✅ Started (monitoring every 30 seconds)")

    return scheduler


scheduler_instance = None


def get_scheduler():
    global scheduler_instance
    if scheduler_instance is None:
        scheduler_instance = start_scheduler()
    return scheduler_instance
