"""Google Drive MCP Tools"""
import io
from googleapiclient.http import MediaIoBaseDownload


def register_gdrive_tools(registry, gdrive_service):
    """Регистрация всех Google Drive инструментов"""

    def get_drive_info():
        if not gdrive_service:
            return {"error": "Google Drive not initialized"}
        try:
            about = gdrive_service.about().get(fields='storageQuota,user').execute()
            quota = about.get('storageQuota', {})
            user = about.get('user', {})

            total = int(quota.get('limit', 0))
            used = int(quota.get('usage', 0))
            free = total - used
            percent = (used / total * 100) if total > 0 else 0

            return {
                "user": user.get('displayName', 'Unknown'),
                "total_gb": round(total / (1024 ** 3), 2),
                "used_gb": round(used / (1024 ** 3), 2),
                "free_gb": round(free / (1024 ** 3), 2),
                "percent_used": round(percent, 2)
            }
        except Exception as e:
            return {"error": str(e)}

    def search_files(query):
        if not gdrive_service:
            return []
        try:
            results = gdrive_service.files().list(
                q=f"name contains '{query}' and trashed=false",
                pageSize=10,
                fields="files(id, name, mimeType, size, modifiedTime)",
                orderBy="modifiedTime desc"
            ).execute()

            files = []
            for f in results.get('files', []):
                size_mb = int(f.get('size', 0)) / (1024 ** 2) if f.get('size') else 0
                files.append({
                    "id": f.get('id'),
                    "name": f.get('name'),
                    "type": f.get('mimeType'),
                    "size_mb": round(size_mb, 2),
                    "modified": f.get('modifiedTime')
                })
            return files
        except Exception as e:
            return [{"error": str(e)}]

    def get_recent_files(limit=10):
        if not gdrive_service:
            return []
        try:
            results = gdrive_service.files().list(
                pageSize=limit,
                fields="files(id, name, mimeType, size, modifiedTime)",
                orderBy="modifiedTime desc"
            ).execute()

            files = []
            for f in results.get('files', []):
                size_mb = int(f.get('size', 0)) / (1024 ** 2) if f.get('size') else 0
                files.append({
                    "id": f.get('id'),
                    "name": f.get('name'),
                    "type": f.get('mimeType'),
                    "size_mb": round(size_mb, 2),
                    "modified": f.get('modifiedTime')
                })
            return files
        except Exception as e:
            return [{"error": str(e)}]

    def list_folders():
        if not gdrive_service:
            return []
        try:
            results = gdrive_service.files().list(
                q="mimeType='application/vnd.google-apps.folder' and trashed=false",
                pageSize=20,
                fields="files(id, name, modifiedTime)",
                orderBy="modifiedTime desc"
            ).execute()

            folders = []
            for f in results.get('files', []):
                folders.append({
                    "id": f.get('id'),
                    "name": f.get('name')
                })
            return folders
        except Exception as e:
            return [{"error": str(e)}]

    def read_file_content(file_id):
        if not gdrive_service:
            return {"error": "Google Drive not initialized"}

        try:
            file_info = gdrive_service.files().get(
                fileId=file_id,
                fields='name, mimeType, size'
            ).execute()

            file_name = file_info.get('name', 'unknown')
            mime_type = file_info.get('mimeType', '')
            file_size = int(file_info.get('size', 0))

            if file_size > 5 * 1024 * 1024:
                return {
                    "error": "File too large",
                    "size_mb": round(file_size / (1024 ** 2), 2),
                    "message": "File size exceeds 5MB limit."
                }

            if mime_type == 'application/vnd.google-apps.document':
                request_obj = gdrive_service.files().export(fileId=file_id, mimeType='text/plain')
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                request_obj = gdrive_service.files().export(fileId=file_id, mimeType='text/csv')
            else:
                request_obj = gdrive_service.files().get_media(fileId=file_id)

            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request_obj)
            done = False

            while not done:
                status, done = downloader.next_chunk()

            file_stream.seek(0)
            content = file_stream.read().decode('utf-8', errors='ignore')

            max_chars = 10000
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n\n... (файл обрезан, показано первых {max_chars} символов)"

            return {
                "file_name": file_name,
                "mime_type": mime_type,
                "size_mb": round(file_size / (1024 ** 2), 2),
                "content": content,
                "char_count": len(content)
            }
        except Exception as e:
            return {"error": str(e), "file_id": file_id}

    # Регистрация всех инструментов
    registry.register(
        "get_drive_info",
        get_drive_info,
        "Get Google Drive storage usage info",
        {"type": "object", "properties": {}}
    )

    registry.register(
        "search_files",
        search_files,
        "Search files in Google Drive by name",
        {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"]
        }
    )

    registry.register(
        "get_recent_files",
        get_recent_files,
        "Get recent files from Google Drive",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}}
        }
    )

    registry.register(
        "list_folders",
        list_folders,
        "List all folders in Google Drive",
        {"type": "object", "properties": {}}
    )

    registry.register(
        "read_file_content",
        read_file_content,
        "Read content from a text file in Google Drive (max 5MB, 10k chars)",
        {
            "type": "object",
            "properties": {"file_id": {"type": "string", "description": "File ID"}},
            "required": ["file_id"]
        }
    )
