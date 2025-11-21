import os
import json
from datetime import datetime
import anthropic
from mcp_tools.notifications import send_telegram_file


def register_pipeline_tools(registry, gdrive_service):
    def search_files_in_folder(folder_id, query="", file_types=None):
        if not gdrive_service:
            return {"error": "Google Drive not initialized"}
        try:
            q_parts = [f"'{folder_id}' in parents", "trashed=false"]
            if query:
                q_parts.append(f"name contains '{query}'")
            if file_types:
                type_conditions = " or ".join([f"mimeType='{t}'" for t in file_types])
                q_parts.append(f"({type_conditions})")
            q = " and ".join(q_parts)
            results = gdrive_service.files().list(
                q=q,
                pageSize=20,
                fields="files(id, name, mimeType, size, modifiedTime, createdTime)",
                orderBy="createdTime desc",
                supportsAllDrives=True
            ).execute()
            files = []
            for f in results.get('files', []):
                if f.get('mimeType') == 'application/vnd.google-apps.folder':
                    continue
                size_mb = int(f.get('size', 0)) / (1024 ** 2) if f.get('size') else 0
                files.append({
                    "id": f.get('id'),
                    "name": f.get('name'),
                    "type": f.get('mimeType'),
                    "size_mb": round(size_mb, 2),
                    "modified": f.get('modifiedTime'),
                    "created": f.get('createdTime')
                })
            return {
                "success": True,
                "count": len(files),
                "files": files
            }
        except Exception as e:
            print(f"[Pipeline] ❌ search_files_in_folder error: {e}")
            return {"error": str(e)}

    def read_and_summarize(file_id, max_lines=50):
        if not gdrive_service:
            return {"error": "Google Drive not initialized"}
        try:
            from googleapiclient.http import MediaIoBaseDownload
            import io
            file_info = gdrive_service.files().get(
                fileId=file_id,
                fields='name, mimeType, size',
                supportsAllDrives=True
            ).execute()
            file_name = file_info.get('name', 'unknown')
            mime_type = file_info.get('mimeType', '')
            file_size = int(file_info.get('size', 0))
            if file_size > 3 * 1024 * 1024:
                return {
                    "error": "File too large",
                    "size_mb": round(file_size / (1024 ** 2), 2),
                    "file_name": file_name
                }
            if mime_type.startswith('application/vnd.google-apps'):
                return {
                    "error": "Cannot process Google Docs files",
                    "file_name": file_name,
                    "mime_type": mime_type
                }
            request = gdrive_service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            file_stream.seek(0)
            content = file_stream.read().decode('utf-8', errors='ignore')
            if len(content) > 3000:
                content = content[:3000] + "\n\n[... truncated]"
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return {"error": "ANTHROPIC_API_KEY not set"}
            client = anthropic.Anthropic(api_key=api_key)
            model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
            prompt = f"""Сделай краткое резюме этого файла (2-3 предложения на русском):

Имя файла: {file_name}
Тип: {mime_type}

Содержимое:
{content}

Резюме должно быть конкретным и информативным."""
            response = client.messages.create(
                model=model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            summary = response.content[0].text if response.content else "No summary"
            return {
                "success": True,
                "file_name": file_name,
                "file_id": file_id,
                "mime_type": mime_type,
                "size_mb": round(file_size / (1024 ** 2), 2),
                "content_length": len(content),
                "summary": summary
            }
        except Exception as e:
            print(f"[Pipeline] ❌ read_and_summarize error: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def save_result_to_telegram(filename, content):
        print(f"[Pipeline] 🚀 Sending file to Telegram: {filename}")
        ok = send_telegram_file(filename, content)
        if ok:
            print(f"[Pipeline] ✅ Sent to Telegram!")
            return {"success": True, "destination": "telegram"}
        else:
            print(f"[Pipeline] ❌ Telegram error")
            return {"error": "Failed to send via Telegram"}

    def run_pipeline(source_folder_id, output_folder_id=None, query="", max_files=5):
        print(f"\n[Pipeline] 🚀 STARTING PIPELINE")
        print(f"[Pipeline]    Source: {source_folder_id}")
        print(f"[Pipeline]    Query: {query or '(all files)'}")
        print(f"[Pipeline]    Max files: {max_files}")
        search_result = search_files_in_folder(source_folder_id, query)
        if not search_result.get("success"):
            print(f"[Pipeline] ❌ Search failed: {search_result}")
            return {"error": "Search failed", "details": search_result}
        files = search_result.get("files", [])[:max_files]
        if not files:
            print(f"[Pipeline] ⚠️  No files found")
            return {"error": "No files found", "query": query}
        print(f"[Pipeline] ✅ Found {len(files)} files")
        print(f"\n[Pipeline] 📄 STEP 2: Summarizing files...")
        summaries = []
        for i, f in enumerate(files, 1):
            print(f"[Pipeline]    {i}/{len(files)}: {f['name']}")
            summary_result = read_and_summarize(f['id'])
            if summary_result.get("success"):
                summaries.append({
                    "file_name": f['name'],
                    "summary": summary_result.get("summary"),
                    "size_mb": summary_result.get("size_mb")
                })
                print(f"[Pipeline]      ✅ Summarized")
            else:
                summaries.append({
                    "file_name": f['name'],
                    "error": summary_result.get("error")
                })
                print(f"[Pipeline]      ⚠️  Skipped: {summary_result.get('error')}")
        print(f"[Pipeline] ✅ Processed {len(summaries)} files")
        print(f"\n[Pipeline] 📝 STEP 3: Creating report...")
        output_filename = f"Pipeline_Results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        report_content = f"""MCP PIPELINE REPORT
{'=' * 60}

Дата выполнения: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Папка источника: {source_folder_id}
Поисковый запрос: {query or '(не указан)'}
Обработано файлов: {len(summaries)}

{'=' * 60}

РЕЗУЛЬТАТЫ:
"""
        for i, s in enumerate(summaries, 1):
            report_content += f"\n{i}. {s['file_name']}\n"
            report_content += f"   Размер: {s.get('size_mb', 'N/A')} MB\n"
            if 'summary' in s:
                report_content += f"   Резюме: {s['summary']}\n"
            else:
                report_content += f"   Пропущен: {s.get('error', 'Unknown error')}\n"
        print(f"\n[Pipeline] 📤 STEP 4: Sending report to Telegram...")
        telegram_result = save_result_to_telegram(output_filename, report_content)
        if telegram_result.get("success"):
            print(f"[Pipeline] ✅ PIPELINE COMPLETE! (sent to Telegram)")
            return {
                "success": True,
                "files_processed": len(summaries),
                "destination": "telegram",
                "output_file": output_filename,
                "summaries": summaries
            }
        else:
            print(f"[Pipeline] ❌ Save failed: {telegram_result}")
            return {"error": "Failed to send results to Telegram", "details": telegram_result}

    registry.register(
        "search_files_in_folder",
        search_files_in_folder,
        "Search files in a specific Google Drive folder with optional query and file type filters",
        {
            "type": "object",
            "properties": {
                "folder_id": {"type": "string", "description": "Google Drive folder ID"},
                "query": {"type": "string", "description": "Search query (optional)"},
                "file_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "MIME types to filter (optional)"
                }
            },
            "required": ["folder_id"]
        }
    )
    registry.register(
        "read_and_summarize",
        read_and_summarize,
        "Read file content and generate AI summary using Claude",
        {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "Google Drive file ID"},
                "max_lines": {"type": "integer", "default": 50, "description": "Max lines to read"}
            },
            "required": ["file_id"]
        }
    )
    registry.register(
        "run_pipeline",
        run_pipeline,
        "Run full MCP pipeline: search files -> summarize with Claude -> send results to Telegram",
        {
            "type": "object",
            "properties": {
                "source_folder_id": {"type": "string", "description": "Source folder ID to search files"},
                "output_folder_id": {"type": "string", "description": "Output folder ID (ignored, for compatibility)"},
                "query": {"type": "string", "description": "Search query (optional)"},
                "max_files": {"type": "integer", "default": 5, "description": "Max files to process"}
            },
            "required": ["source_folder_id"]
        }
    )
