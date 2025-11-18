from flask import Flask, request, jsonify
import anthropic
import os
import json
from dotenv import load_dotenv
import io

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

load_dotenv()
app = Flask(__name__)

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
conversations = {}
gdrive_service = None


def init_gdrive():
    global gdrive_service
    if not GOOGLE_AVAILABLE:
        return False
    try:
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/drive']
        )
        gdrive_service = build('drive', 'v3', credentials=creds)
        print("[Google Drive] ✅ Initialized")
        return True
    except Exception as e:
        print(f"[Google Drive] ❌ Error: {e}")
        return False


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
    """Прочитать содержимое файла из Google Drive"""
    if not gdrive_service:
        return {"error": "Google Drive not initialized"}

    try:
        # Получить информацию о файле
        file_info = gdrive_service.files().get(
            fileId=file_id,
            fields='name, mimeType, size'
        ).execute()

        file_name = file_info.get('name', 'unknown')
        mime_type = file_info.get('mimeType', '')
        file_size = int(file_info.get('size', 0))

        # Ограничение на размер файла (5MB)
        if file_size > 5 * 1024 * 1024:
            return {
                "error": "File too large",
                "size_mb": round(file_size / (1024 ** 2), 2),
                "message": "File size exceeds 5MB limit. Please download manually."
            }

        # Текстовые форматы которые можно читать
        readable_types = [
            'text/plain',
            'text/csv',
            'text/html',
            'text/xml',
            'application/json',
            'application/x-python',
            'application/javascript',
            'application/sql',
            'text/markdown',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
        ]

        # Для Google Docs/Sheets/Slides - экспортируем
        if mime_type == 'application/vnd.google-apps.document':
            # Экспортируем как текст
            request_obj = gdrive_service.files().export(
                fileId=file_id,
                mimeType='text/plain'
            )
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            # Экспортируем как CSV
            request_obj = gdrive_service.files().export(
                fileId=file_id,
                mimeType='text/csv'
            )
        elif any(mime_type.startswith(t.split('/')[0]) for t in readable_types):
            # Прямая загрузка текстовых файлов
            request_obj = gdrive_service.files().get_media(fileId=file_id)
        else:
            return {
                "error": "Unsupported file type",
                "file_name": file_name,
                "mime_type": mime_type,
                "message": f"Cannot read files of type: {mime_type}"
            }

        # Загружаем содержимое
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request_obj)
        done = False

        while not done:
            status, done = downloader.next_chunk()

        file_stream.seek(0)
        content = file_stream.read().decode('utf-8', errors='ignore')

        # Ограничиваем длину контента
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


@app.route('/')
def index():
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Claude + Google Drive Agent</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 10px 40px rgba(0,0,0,0.3); display: flex; flex-direction: column; height: 92vh; }
h1 { color: #667eea; margin-bottom: 10px; }
.subtitle { color: #999; font-size: 13px; margin-bottom: 20px; }
.tools { background: #f0f0f0; padding: 12px 15px; border-radius: 6px; margin-bottom: 15px; }
.tools strong { font-size: 12px; }
.tool-badge { display: inline-block; background: white; padding: 6px 10px; border-radius: 4px; margin-right: 8px; margin-top: 8px; font-size: 11px; border: 1px solid #ddd; color: #667eea; }
.chat { flex: 1; background: #f5f5f5; border-radius: 8px; padding: 15px; margin-bottom: 15px; overflow-y: auto; border: 1px solid #ddd; }
.msg { margin: 10px 0; padding: 12px; border-radius: 6px; word-wrap: break-word; line-height: 1.6; }
.user { background: #667eea; color: white; margin-left: 50px; text-align: right; }
.assistant { background: #e0e0e0; color: #333; margin-right: 50px; }
.tool-call { background: #fff3cd; color: #856404; margin-right: 50px; font-size: 12px; border-left: 3px solid #ffc107; padding-left: 15px; }
.loading { background: #e3f2fd; color: #1976d2; margin-right: 50px; animation: pulse 1s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.input-area { display: flex; gap: 10px; }
input { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
input:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.1); }
button { padding: 12px 24px; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
button:hover { background: #764ba2; }
button:disabled { background: #ccc; }

/* Markdown styles */
.markdown h1 { font-size: 24px; margin: 16px 0 8px 0; color: #333; font-weight: bold; }
.markdown h2 { font-size: 20px; margin: 14px 0 6px 0; color: #333; font-weight: bold; }
.markdown h3 { font-size: 16px; margin: 12px 0 4px 0; color: #333; font-weight: bold; }
.markdown strong { font-weight: bold; }
.markdown em { font-style: italic; }
.markdown code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 13px; }
.markdown pre { background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; margin: 8px 0; max-height: 300px; }
.markdown pre code { background: none; padding: 0; }
.markdown ul, .markdown ol { margin: 8px 0; padding-left: 20px; }
.markdown li { margin: 4px 0; }
.markdown blockquote { border-left: 3px solid #667eea; padding-left: 12px; color: #666; margin: 8px 0; }
.markdown a { color: #667eea; text-decoration: none; }
.markdown a:hover { text-decoration: underline; }
</style></head><body>
<div class="container">
<h1>🤖 Claude + Google Drive Agent</h1>
<div class="subtitle">Powered by Claude Opus 4.1 + Google Drive API</div>

<div class="tools">
<strong>📋 Available Tools:</strong>
<div>
<span class="tool-badge">🔍 search_files</span>
<span class="tool-badge">📁 list_folders</span>
<span class="tool-badge">💾 get_drive_info</span>
<span class="tool-badge">📄 get_recent_files</span>
<span class="tool-badge">📖 read_file_content</span>
</div>
</div>

<div class="chat" id="chat"></div>

<div class="input-area">
<input type="text" id="input" placeholder="Ask Claude about your Google Drive (e.g., 'Read content of file XXX', 'Find and read PDF')...">
<button id="btn" onclick="send()">Send</button>
</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
let sid = 'session_' + Date.now();
let busy = false;

async function send() {
    const inp = document.getElementById('input');
    const msg = inp.value.trim();
    if (!msg || busy) return;

    addMsg(msg, 'user');
    inp.value = '';
    busy = true;
    document.getElementById('btn').disabled = true;

    const loading = addMsg('⏳ Claude is thinking...', 'loading');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({session_id: sid, message: msg})
        });
        const data = await res.json();

        const chat = document.getElementById('chat');
        chat.removeChild(loading);

        if (data.success) {
            if (data.tools && data.tools.length > 0) {
                for (let tool of data.tools) {
                    addMsg('🔧 Used: ' + tool.name, 'tool-call');
                }
            }
            if (data.response) {
                addMarkdownMsg(data.response, 'assistant');
            }
        } else {
            addMsg('❌ Error: ' + data.error, 'assistant');
        }
    } catch (e) {
        addMsg('❌ Error: ' + e.message, 'assistant');
    }
    busy = false;
    document.getElementById('btn').disabled = false;
    inp.focus();
}

function addMsg(text, role) {
    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

function addMarkdownMsg(text, role) {
    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = 'msg ' + role + ' markdown';
    div.innerHTML = marked.parse(text);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

document.getElementById('input').addEventListener('keypress', e => {
    if (e.key === 'Enter' && !busy) send();
});
</script>
</body></html>"""


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message', '')

        if not msg:
            return jsonify({'success': False, 'error': 'Empty message'})

        if sid not in conversations:
            conversations[sid] = []

        conversations[sid].append({"role": "user", "content": msg})

        tools = [
            {
                "name": "get_drive_info",
                "description": "Get Google Drive storage info",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "search_files",
                "description": "Search files in Google Drive by name",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"]
                }
            },
            {
                "name": "get_recent_files",
                "description": "Get recent files from Google Drive",
                "input_schema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}}
                }
            },
            {
                "name": "list_folders",
                "description": "List folders in Google Drive",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "read_file_content",
                "description": "Read content from a file in Google Drive. Supports: text files, CSV, JSON, Python, JavaScript, SQL, Google Docs (as text), Google Sheets (as CSV). Max 5MB files, content limited to 10k chars.",
                "input_schema": {
                    "type": "object",
                    "properties": {"file_id": {"type": "string", "description": "File ID to read"}},
                    "required": ["file_id"]
                }
            }
        ]

        response = anthropic_client.messages.create(
            model="claude-opus-4-1",
            max_tokens=2048,
            tools=tools,
            messages=conversations[sid]
        )

        tool_calls = []
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                if tool_name == "get_drive_info":
                    result = get_drive_info()
                elif tool_name == "search_files":
                    result = search_files(tool_input.get("query", ""))
                elif tool_name == "get_recent_files":
                    result = get_recent_files(tool_input.get("limit", 10))
                elif tool_name == "list_folders":
                    result = list_folders()
                elif tool_name == "read_file_content":
                    result = read_file_content(tool_input.get("file_id", ""))
                else:
                    result = {"error": f"Unknown tool"}

                tool_calls.append({"name": tool_name})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result)
                })

        if tool_results:
            conversations[sid].append({"role": "assistant", "content": response.content})
            conversations[sid].append({"role": "user", "content": tool_results})

            final_response = anthropic_client.messages.create(
                model="claude-opus-4-1",
                max_tokens=2048,
                messages=conversations[sid]
            )

            assistant_msg = ""
            for block in final_response.content:
                if hasattr(block, 'text'):
                    assistant_msg = block.text

            conversations[sid].append({"role": "assistant", "content": assistant_msg})
        else:
            assistant_msg = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    assistant_msg = block.text

            conversations[sid].append({"role": "assistant", "content": assistant_msg})

        return jsonify({
            'success': True,
            'response': assistant_msg,
            'tools': tool_calls
        })
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    init_gdrive()
    print("[INFO] Claude + Google Drive Agent running on http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000, debug=False)
