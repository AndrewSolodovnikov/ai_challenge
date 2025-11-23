from flask import Flask, request, jsonify, render_template_string
import anthropic
import os
import json
from dotenv import load_dotenv
from database import (
    save_message,
    get_conversation_history,
    get_all_conversations,
    get_setting,
    set_setting
)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

from mcp_tools.registry import mcp_registry
from mcp_tools.gdrive_tools import register_gdrive_tools
from mcp_tools.pipeline import register_pipeline_tools
from mcp_tools.local_files import register_local_files_tools
from mcp_tools.web_api import register_web_api_tools
from mcp_tools.database_server import register_database_tools
from mcp_tools.code_executor import register_code_executor_tools
from mcp_tools.telegram_integration import register_telegram_tools
from mcp_tools.notifications import send_telegram_file, send_telegram_alert
from mcp_tools.orchestrator import create_orchestrator, ExecutionContext
from scheduler import set_gdrive_service, get_scheduler, update_scheduler_interval

load_dotenv()

# ============ DEBUG: проверить загрузку переменных окружения ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

print("\n" + "=" * 80)
print("[STARTUP] 🔍 ENVIRONMENT VARIABLES CHECK")
print("=" * 80)
print(f"[STARTUP] TELEGRAM_TOKEN: {'✅ LOADED' if TELEGRAM_TOKEN else '❌ NOT FOUND'}")
if TELEGRAM_TOKEN:
    print(f"           Token starts with: {TELEGRAM_TOKEN[:20]}...")
print(f"[STARTUP] TELEGRAM_CHAT_ID: {'✅ LOADED' if TELEGRAM_CHAT_ID else '❌ NOT FOUND'}")
if TELEGRAM_CHAT_ID:
    print(f"           Chat ID: {TELEGRAM_CHAT_ID}")
print(f"[STARTUP] ANTHROPIC_API_KEY: {'✅ LOADED' if ANTHROPIC_KEY else '❌ NOT FOUND'}")
print("=" * 80 + "\n")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("[WARNING] ⚠️  Telegram credentials not fully configured!")
    print("[WARNING]     Some features may not work properly")

# ========================================================================

app = Flask(__name__)

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
gdrive_service = None
scheduler = None
orchestrator = None
mcp_router = None

# ============ ОБНОВЛЕННЫЙ SYSTEM_PROMPT С TELEGRAM ИНТЕГРАЦИЕЙ ============
SYSTEM_PROMPT = """You are an intelligent task orchestrator with access to 6 MCP servers and 29+ tools.

⚠️ TELEGRAM INTEGRATION RULES:
If user asks to send to Telegram, use these tools:
- send_file_to_telegram(filename, content, caption): Send file to Telegram
- send_alert_to_telegram(title, message): Send alert message to Telegram

WORKFLOW EXAMPLE:
User: "Find olympiad 1980 info and send to Telegram"
1. Use http_get or search_files_in_folder to find data
2. Process/summarize the information  
3. Call: send_file_to_telegram("olympiad_1980.txt", [info], "📚 Olympiad 1980")
4. Report success to user

Available servers and tools:

📁 GOOGLE DRIVE SERVER (3 tools):
- search_files_in_folder(folder_id, query, file_types): Search files
- read_and_summarize(file_id): Read and summarize file
- run_pipeline(source_folder_id, query, max_files): Full pipeline

📄 LOCAL FILES SERVER (5 tools):
- list_files(directory, pattern, max_files)
- read_file(filepath, max_size_mb)
- write_file(filepath, content, create_dirs)
- search_files_by_content(directory, search_text)
- get_file_stats(filepath)

🌐 WEB API SERVER (5 tools):
- http_get(url, headers, params): Make GET request
- http_post(url, data, json_data, headers): Make POST request
- parse_json_response(json_string): Parse JSON
- validate_url(url): Validate URL
- get_request_info(url): Get endpoint info

💾 DATABASE SERVER (8 tools):
- db_select(query, params): SELECT query
- db_insert(query, params): INSERT query
- db_update(query, params): UPDATE query
- db_delete(query, params): DELETE query
- db_create_table(table_name, columns): Create table
- db_list_tables(): List tables
- db_get_schema(table_name): Get table schema
- db_get_data(table_name, limit): Get table data

🐍 CODE EXECUTOR SERVER (5 tools):
- execute_python(code, timeout): Execute Python code
- calculate_expression(expression): Calculate math
- parse_json(json_string): Parse JSON
- generate_json(data_dict): Generate JSON
- transform_data(data, transform_code): Transform data

📤 TELEGRAM SERVER (2 tools):
- send_file_to_telegram(filename, content, caption): Send file
- send_alert_to_telegram(title, message): Send alert

IMPORTANT:
1. Always use Telegram tools when user asks to send something
2. Chain tools efficiently
3. Report when task is complete"""


def init_gdrive():
    global gdrive_service, scheduler, orchestrator, mcp_router

    if not GOOGLE_AVAILABLE:
        print("[Google Drive] ⚠️  Libraries not available")
        return False

    try:
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/drive']
        )
        gdrive_service = build('drive', 'v3', credentials=creds)
        print("[Google Drive] ✅ Initialized")

        # Регистрировать все MCP серверы (7 серверов)
        register_gdrive_tools(mcp_registry, gdrive_service)
        register_pipeline_tools(mcp_registry, gdrive_service)
        register_local_files_tools(mcp_registry)
        register_web_api_tools(mcp_registry)
        register_database_tools(mcp_registry)
        register_code_executor_tools(mcp_registry)
        register_telegram_tools(mcp_registry)

        print(f"[MCP] ✅ Registered {len(mcp_registry.tools)} tools from 7 servers")

        # Создать оркестратор
        orchestrator, mcp_router = create_orchestrator(
            llm_client=anthropic_client,
            gdrive_registry=mcp_registry,
            telegram_registry=mcp_registry
        )
        print(f"[Orchestrator] ✅ Created with 7 MCP servers")

        set_gdrive_service(gdrive_service)
        scheduler = get_scheduler()

        return True
    except Exception as e:
        print(f"[Google Drive] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


@app.route('/')
def index():
    return render_template_string('''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Claude + MCP Agent v4 - Telegram Integrated</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; display: flex; height: 100vh; background: #f5f7fa; }
.sidebar { width: 280px; background: #2c3e50; color: white; display: flex; flex-direction: column; }
.sidebar-header { padding: 20px; background: #34495e; }
.sidebar-header h2 { font-size: 18px; margin-bottom: 10px; }
.new-chat-btn { width: 100%; padding: 10px; background: #667eea; border: none; border-radius: 6px; color: white; cursor: pointer; font-weight: bold; margin-bottom: 8px; }
.new-chat-btn:hover { background: #764ba2; }
.settings-btn { width: 100%; padding: 10px; background: #34495e; border: 1px solid #667eea; border-radius: 6px; color: white; cursor: pointer; font-size: 13px; }
.settings-btn:hover { background: #3d5a7a; }
.conversations { flex: 1; overflow-y: auto; padding: 10px; }
.conv-item { padding: 12px; margin-bottom: 8px; background: #34495e; border-radius: 6px; cursor: pointer; }
.conv-item:hover { background: #3d5a7a; }
.conv-item.active { background: #667eea; }
.conv-title { font-size: 14px; font-weight: 500; margin-bottom: 4px; }
.conv-meta { font-size: 11px; color: #bdc3c7; }
.status { padding: 10px; background: #27ae60; color: white; font-size: 12px; text-align: center; line-height: 1.5; }
.main { flex: 1; display: flex; flex-direction: column; }
.header { padding: 20px 30px; background: white; border-bottom: 1px solid #ddd; }
.header h1 { color: #667eea; font-size: 24px; }
.subtitle { color: #999; font-size: 13px; margin-top: 5px; }
.tools { background: #f0f0f0; padding: 12px 30px; border-bottom: 1px solid #ddd; overflow-x: auto; max-height: 100px; overflow-y: hidden; }
.tool-badge { display: inline-block; background: white; padding: 6px 10px; border-radius: 4px; margin-right: 8px; font-size: 11px; border: 1px solid #ddd; color: #667eea; white-space: nowrap; }
.chat { flex: 1; padding: 20px 30px; overflow-y: auto; background: #fafafa; }
.msg { margin-bottom: 15px; padding: 12px; border-radius: 8px; max-width: 85%; word-wrap: break-word; line-height: 1.6; }
.user { background: #667eea; color: white; margin-left: auto; text-align: right; }
.assistant { background: white; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
.tool-call { background: #fff3cd; color: #856404; font-size: 12px; border-left: 3px solid #ffc107; margin-left: 20px; }
.loading { background: #e3f2fd; color: #1976d2; margin-right: 50px; animation: pulse 1s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.input-area { padding: 20px 30px; background: white; border-top: 1px solid #ddd; display: flex; gap: 10px; }
input { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
button { padding: 12px 24px; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
button:hover { background: #764ba2; }
button:disabled { background: #ccc; }
.markdown h2 { font-size: 18px; margin: 12px 0 8px 0; font-weight: bold; }
.markdown code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
.markdown pre { background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; font-size: 12px; }
</style></head><body>
<div class="sidebar">
<div class="sidebar-header">
<h2>💬 Conversations</h2>
<button class="new-chat-btn" onclick="newChat()">+ New Chat</button>
<button class="settings-btn" onclick="openSettings()">⚙️ Settings</button>
</div>
<div class="status">
✅ System Active<br>
📁 7 MCP Servers<br>
🎯 29+ Tools<br>
📤 Telegram ✅
</div>
<div class="conversations" id="convList">Loading...</div>
</div>
<div class="main">
<div class="header">
<h1>🤖 Claude + MCP Agent v4</h1>
<div class="subtitle">7 Servers • 29+ Tools • Telegram Integrated</div>
</div>
<div class="tools">
<strong>📋 Available Tools:</strong>
<div id="toolsList" style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;">Loading...</div>
</div>
<div class="chat" id="chat"></div>
<div class="input-area">
<input type="text" id="input" placeholder="Ask Claude (mention Telegram if you want to send results)...">
<button id="btn" onclick="send()">Send</button>
</div>
</div>
<div class="modal" id="settingsModal" style="display:none; position:fixed; z-index:1000; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.5); align-items:center; justify-content:center;">
<div style="background:white; border-radius:12px; padding:30px; width:500px; max-width:90%;">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
<h2 style="color:#2c3e50;">⚙️ Settings</h2>
<button onclick="closeSettings()" style="background:none; border:none; font-size:24px; cursor:pointer;">×</button>
</div>
<div style="margin-bottom:20px;">
<label style="display:block; font-weight:bold; margin-bottom:8px;">📱 Telegram</label>
<input type="checkbox" id="telegramEnabled" checked style="width:20px; height:20px; cursor:pointer;">
<label for="telegramEnabled">Enabled</label>
</div>
<button onclick="saveSettings()" style="width:100%; padding:12px; background:#27ae60; color:white; border:none; border-radius:6px; font-weight:bold; cursor:pointer;">💾 Save</button>
</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
let sid = null;
let busy = false;
async function loadConversations() {
    const res = await fetch('/api/conversations');
    const data = await res.json();
    const list = document.getElementById('convList');
    if (data.conversations.length === 0) {
        list.innerHTML = '<div style="padding:20px;text-align:center;color:#bdc3c7;">No chats yet</div>';
        return;
    }
    list.innerHTML = data.conversations.map(c => `
        <div class="conv-item ${c.session_id === sid ? 'active' : ''}" onclick="loadConversation('${c.session_id}')">
            <div class="conv-title">${c.title}</div>
            <div class="conv-meta">${c.message_count} msgs</div>
        </div>
    `).join('');
}
async function loadConversation(sessionId) {
    sid = sessionId;
    const res = await fetch(`/api/conversation/${sessionId}`);
    const data = await res.json();
    const chat = document.getElementById('chat');
    chat.innerHTML = '';
    for (let msg of data.messages) {
        if (msg.role === 'user') addMsg(msg.content, 'user');
        else addMarkdownMsg(msg.content, 'assistant');
    }
    loadConversations();
}
function newChat() {
    sid = 'session_' + Date.now();
    document.getElementById('chat').innerHTML = '';
    loadConversations();
}
fetch('/api/tools').then(r => r.json()).then(data => {
    const toolsList = document.getElementById('toolsList');
    toolsList.innerHTML = data.tools.map(t => `<span class="tool-badge">🔧 ${t.name}</span>`).join('');
});
async function send() {
    if (!sid) newChat();
    const inp = document.getElementById('input');
    const msg = inp.value.trim();
    if (!msg || busy) return;
    addMsg(msg, 'user');
    inp.value = '';
    busy = true;
    document.getElementById('btn').disabled = true;
    const loading = addMsg('⏳ Processing...', 'loading');
    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({session_id: sid, message: msg})
        });
        const data = await res.json();
        const chat = document.getElementById('chat');
        if (chat.contains(loading)) chat.removeChild(loading);
        if (data.success) {
            if (data.tool_count > 0) {
                addMsg(`🔧 Used ${data.tool_count} tool(s)`, 'tool-call');
            }
            if (data.response) addMarkdownMsg(data.response, 'assistant');
            loadConversations();
        } else {
            addMsg('❌ ' + data.error, 'assistant');
        }
    } catch (e) {
        addMsg('❌ ' + e.message, 'assistant');
    }
    busy = false;
    document.getElementById('btn').disabled = false;
    inp.focus();
}
function addMsg(text, role) {
    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.innerHTML = text;
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
function openSettings() {
    document.getElementById('settingsModal').style.display = 'flex';
}
function closeSettings() {
    document.getElementById('settingsModal').style.display = 'none';
}
function saveSettings() {
    alert('✅ Settings saved!');
    closeSettings();
}
newChat();
loadConversations();
</script>
</body></html>''')


@app.route('/api/tools')
def get_tools():
    tools = mcp_registry.get_tool_definitions()
    return jsonify({"success": True, "tools": tools})


@app.route('/api/conversations')
def get_conversations():
    conversations = get_all_conversations()
    return jsonify({"conversations": conversations})


@app.route('/api/conversation/<session_id>')
def get_conversation(session_id):
    messages = get_conversation_history(session_id)
    return jsonify({"messages": messages})


@app.route('/api/settings', methods=['GET'])
def get_settings():
    telegram_enabled = get_setting(1, 'telegram_enabled', 'true') == 'true'
    monitor_interval = int(get_setting(1, 'monitor_interval', '30'))
    return jsonify({"telegram_enabled": telegram_enabled, "monitor_interval": monitor_interval})


@app.route('/api/settings', methods=['POST'])
def save_settings():
    try:
        data = request.json
        telegram_enabled = data.get('telegram_enabled', True)
        monitor_interval = data.get('monitor_interval', 30)
        set_setting(1, 'telegram_enabled', 'true' if telegram_enabled else 'false')
        set_setting(1, 'monitor_interval', str(monitor_interval))
        update_scheduler_interval(monitor_interval)
        print(f"[Settings] ✅ Updated")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message', '')
        print(f"\n{'=' * 100}")
        print(f"[CHAT] 🟦 USER: {msg}")
        if not msg:
            return jsonify({'success': False, 'error': 'Empty message'})
        history = get_conversation_history(sid)
        history.append({"role": "user", "content": msg})
        save_message(sid, "user", msg)
        tools = mcp_registry.get_tool_definitions()
        all_tool_calls = []
        final_text = ""
        iteration = 0
        while True:
            iteration += 1
            print(f"[CHAT] 🔄 ITERATION {iteration}")
            response = anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=history
            )
            tool_calls_this_round = []
            tool_results = []
            assistant_content = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    try:
                        result = mcp_registry.execute_tool(tool_name, block.input)
                        tool_calls_this_round.append({"name": tool_name})
                        all_tool_calls.append({"name": tool_name})
                        assistant_content.append(block)
                        tool_results.append(
                            {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
                        print(f"[CHAT] ✅ Tool executed: {tool_name}")
                    except Exception as e:
                        print(f"[CHAT] ❌ Tool error: {tool_name}: {e}")
                        tool_results.append(
                            {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps({"error": str(e)})})
                elif block.type == "text":
                    final_text = block.text
                    assistant_content.append(block)
            if not tool_results:
                break
            history.append({"role": "assistant", "content": assistant_content})
            history.append({"role": "user", "content": tool_results})
        save_message(sid, "assistant", final_text, all_tool_calls if all_tool_calls else None)
        print(f"[CHAT] ✅ COMPLETE - {iteration} iterations, {len(all_tool_calls)} tools used")
        print(f"{'=' * 100}\n")
        return jsonify({
            'success': True,
            'response': final_text,
            'tools': [{"name": tc["name"]} for tc in all_tool_calls],
            'tool_count': len(all_tool_calls)
        })
    except Exception as e:
        print(f"[CHAT] ❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/workflow', methods=['POST'])
def workflow():
    try:
        data = request.json
        request_text = data.get('request', '')
        if not request_text or not orchestrator:
            return jsonify({'error': 'Invalid request'})
        context = orchestrator.execute_workflow(request_text)
        return jsonify({
            'success': True,
            'session_id': context.session_id,
            'steps': len(context.history),
            'state': context.state
        })
    except Exception as e:
        return jsonify({'error': str(e)})


# ============ TELEGRAM ENDPOINTS ============
@app.route('/api/send-to-telegram', methods=['POST'])
def send_to_telegram():
    try:
        data = request.json
        filename = data.get('filename', 'report.txt')
        content = data.get('content', '')
        caption = data.get('caption', None)

        print(f"\n[TELEGRAM_ENDPOINT] 📤 Sending file: {filename}")

        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return jsonify({'success': False, 'error': 'Telegram not configured'}), 400

        ok = send_telegram_file(filename, content, caption)

        if ok:
            print(f"[TELEGRAM_ENDPOINT] ✅ File sent!")
            return jsonify({'success': True, 'message': f'File sent: {filename}', 'size': len(content)})
        else:
            return jsonify({'success': False, 'error': 'Failed to send'}), 400
    except Exception as e:
        print(f"[TELEGRAM_ENDPOINT] ❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send-telegram-alert', methods=['POST'])
def send_alert_endpoint():
    try:
        data = request.json
        title = data.get('title', 'Alert')
        text = data.get('text', '')

        print(f"\n[TELEGRAM_ENDPOINT] 🔔 Sending alert: {title}")

        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return jsonify({'success': False, 'error': 'Telegram not configured'}), 400

        ok = send_telegram_alert(title, text)

        if ok:
            print(f"[TELEGRAM_ENDPOINT] ✅ Alert sent!")
            return jsonify({'success': True, 'message': 'Alert sent'})
        else:
            return jsonify({'success': False, 'error': 'Failed to send'}), 400
    except Exception as e:
        print(f"[TELEGRAM_ENDPOINT] ❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'telegram_configured': bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        'anthropic_configured': bool(ANTHROPIC_KEY),
        'gdrive_initialized': gdrive_service is not None,
        'orchestrator_ready': orchestrator is not None,
        'tools_count': len(mcp_registry.tools)
    })


if __name__ == '__main__':
    init_gdrive()
    print(f"\n{'=' * 80}")
    print(f"[INFO] 🚀 Claude + MCP Agent v4 running on http://0.0.0.0:8000")
    print(f"[INFO] 📊 7 MCP Servers • 29+ Tools • Telegram Integrated")
    print(f"[INFO] 📡 Endpoints available:")
    print(f"       • /api/chat - Chat with auto-Telegram sending")
    print(f"       • /api/workflow - Multi-step orchestrator")
    print(f"       • /api/send-to-telegram - Direct file send")
    print(f"       • /api/send-telegram-alert - Direct alert send")
    print(f"       • /api/health - System health")
    print(f"{'=' * 80}\n")
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)