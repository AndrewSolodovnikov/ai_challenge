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
from scheduler import set_gdrive_service, get_scheduler, update_scheduler_interval

load_dotenv()
app = Flask(__name__)

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
gdrive_service = None
scheduler = None

SYSTEM_PROMPT = """You are a helpful Google Drive assistant with access to 9 MCP tools.

When users ask about files or folders:
1. Use search_files_in_folder to find files in specific folders
2. Use read_file_content to read file contents
3. Use read_and_summarize to get AI summaries
4. Chain tools together to provide complete information
5. EXECUTE TOOLS and return actual data, not assumptions

Be thorough and provide complete answers."""


def init_gdrive():
    global gdrive_service, scheduler

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

        register_gdrive_tools(mcp_registry, gdrive_service)
        register_pipeline_tools(mcp_registry, gdrive_service)
        print(f"[MCP] ✅ Registered {len(mcp_registry.tools)} tools")

        set_gdrive_service(gdrive_service)
        scheduler = get_scheduler()

        return True
    except Exception as e:
        print(f"[Google Drive] ❌ Error: {e}")
        return False


@app.route('/')
def index():
    return render_template_string('''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Claude + MCP Agent</title>
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
.status { padding: 10px; background: #27ae60; color: white; font-size: 12px; text-align: center; }

.main { flex: 1; display: flex; flex-direction: column; }
.header { padding: 20px 30px; background: white; border-bottom: 1px solid #ddd; }
.header h1 { color: #667eea; font-size: 24px; }
.subtitle { color: #999; font-size: 13px; margin-top: 5px; }
.tools { background: #f0f0f0; padding: 12px 30px; border-bottom: 1px solid #ddd; overflow-x: auto; max-height: 60px; overflow-y: hidden; }
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
.markdown pre { background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; }
.markdown ul { margin: 8px 0; padding-left: 20px; }
.markdown li { margin: 4px 0; }

.modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
.modal.active { display: flex; align-items: center; justify-content: center; }
.modal-content { background: white; border-radius: 12px; padding: 30px; width: 500px; max-width: 90%; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.modal-header h2 { color: #2c3e50; }
.close-btn { background: none; border: none; font-size: 24px; cursor: pointer; color: #999; }
.close-btn:hover { color: #333; }
.setting-group { margin-bottom: 20px; }
.setting-label { display: block; font-weight: bold; margin-bottom: 8px; color: #2c3e50; }
.setting-description { font-size: 12px; color: #999; margin-bottom: 8px; }
.checkbox-wrapper { display: flex; align-items: center; gap: 10px; }
.checkbox-wrapper input[type="checkbox"] { width: 20px; height: 20px; cursor: pointer; }
.number-input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
.save-settings-btn { width: 100%; padding: 12px; background: #27ae60; color: white; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; }
.save-settings-btn:hover { background: #229954; }
</style></head><body>

<div class="sidebar">
<div class="sidebar-header">
<h2>💬 Conversations</h2>
<button class="new-chat-btn" onclick="newChat()">+ New Chat</button>
<button class="settings-btn" onclick="openSettings()">⚙️ Settings</button>
</div>
<div class="status">
✅ System Active<br>
📁 Pipeline Ready<br>
🤖 9 MCP Tools
</div>
<div class="conversations" id="convList">Loading...</div>
</div>

<div class="main">
<div class="header">
<h1>🤖 Claude + MCP Agent</h1>
<div class="subtitle">Google Drive Monitor + MCP Pipeline + Telegram</div>
</div>

<div class="tools">
<strong>📋 MCP Tools:</strong>
<div id="toolsList" style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;">Loading...</div>
</div>

<div class="chat" id="chat"></div>

<div class="input-area">
<input type="text" id="input" placeholder="Ask Claude or run MCP pipeline...">
<button id="btn" onclick="send()">Send</button>
</div>
</div>

<div class="modal" id="settingsModal">
<div class="modal-content">
<div class="modal-header">
<h2>⚙️ Settings</h2>
<button class="close-btn" onclick="closeSettings()">&times;</button>
</div>

<div class="setting-group">
<label class="setting-label">📱 Telegram Notifications</label>
<div class="setting-description">Enable or disable Telegram notifications for new files</div>
<div class="checkbox-wrapper">
<input type="checkbox" id="telegramEnabled" checked>
<label for="telegramEnabled">Send Telegram notifications</label>
</div>
</div>

<div class="setting-group">
<label class="setting-label">⏱️ Monitoring Interval</label>
<div class="setting-description">How often to check for new files (in seconds)</div>
<input type="number" id="monitorInterval" class="number-input" value="30" min="10" max="300" step="5">
</div>

<button class="save-settings-btn" onclick="saveSettings()">💾 Save Settings</button>
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
        list.innerHTML = '<div style="padding:20px;text-align:center;color:#bdc3c7;">No conversations</div>';
        return;
    }

    list.innerHTML = data.conversations.map(c => `
        <div class="conv-item ${c.session_id === sid ? 'active' : ''}" onclick="loadConversation('${c.session_id}')">
            <div class="conv-title">${c.title}</div>
            <div class="conv-meta">${c.message_count} messages</div>
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
        if (msg.role === 'user') {
            addMsg(msg.content, 'user');
        } else if (msg.role === 'assistant') {
            addMarkdownMsg(msg.content, 'assistant');
        }
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
    toolsList.innerHTML = data.tools.map(t => 
        `<span class="tool-badge">🔧 ${t.name}</span>`
    ).join('');
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

    const loading = addMsg('⏳ Claude is thinking...', 'loading');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({session_id: sid, message: msg})
        });
        const data = await res.json();

        const chat = document.getElementById('chat');
        if (chat.contains(loading)) {
            chat.removeChild(loading);
        }

        if (data.success) {
            if (data.tool_count && data.tool_count > 0) {
                addMsg(`🔧 Executed ${data.tool_count} tool(s)`, 'tool-call');
                if (data.tools && data.tools.length > 0) {
                    for (let tool of data.tools) {
                        addMsg(`  • <b>${tool.name}</b>`, 'tool-call');
                    }
                }
            }

            if (data.response) {
                addMarkdownMsg(data.response, 'assistant');
            }

            loadConversations();
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

async function openSettings() {
    document.getElementById('settingsModal').classList.add('active');

    const res = await fetch('/api/settings');
    const data = await res.json();

    document.getElementById('telegramEnabled').checked = data.telegram_enabled !== false;
    document.getElementById('monitorInterval').value = data.monitor_interval || 30;
}

function closeSettings() {
    document.getElementById('settingsModal').classList.remove('active');
}

async function saveSettings() {
    const telegramEnabled = document.getElementById('telegramEnabled').checked;
    const monitorInterval = parseInt(document.getElementById('monitorInterval').value);

    const res = await fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            telegram_enabled: telegramEnabled,
            monitor_interval: monitorInterval
        })
    });

    const data = await res.json();

    if (data.success) {
        alert('✅ Settings saved successfully!');
        closeSettings();
    } else {
        alert('❌ Error saving settings: ' + data.error);
    }
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

    return jsonify({
        "telegram_enabled": telegram_enabled,
        "monitor_interval": monitor_interval
    })


@app.route('/api/settings', methods=['POST'])
def save_settings():
    try:
        data = request.json
        telegram_enabled = data.get('telegram_enabled', True)
        monitor_interval = data.get('monitor_interval', 30)

        set_setting(1, 'telegram_enabled', 'true' if telegram_enabled else 'false')
        set_setting(1, 'monitor_interval', str(monitor_interval))

        update_scheduler_interval(monitor_interval)

        print(f"[Settings] ✅ Updated: telegram={telegram_enabled}, interval={monitor_interval}s")

        return jsonify({"success": True})
    except Exception as e:
        print(f"[Settings] ❌ Error: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message', '')

        print(f"\n{'=' * 100}")
        print(f"[CHAT] 🟦 USER: {msg}")
        print(f"{'=' * 100}")

        if not msg:
            return jsonify({'success': False, 'error': 'Empty message'})

        history = get_conversation_history(sid)
        print(f"[CHAT] 📜 History: {len(history)} msgs")

        history.append({"role": "user", "content": msg})
        save_message(sid, "user", msg)

        tools = mcp_registry.get_tool_definitions()

        all_tool_calls = []
        final_text = ""
        request_num = 1
        iteration = 0

        while True:
            iteration += 1
            print(f"\n[CHAT] 🔄 ITERATION {iteration}")
            print(f"[CHAT] 📤 REQUEST #{request_num} | History: {len(history)} msgs")

            response = anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=history
            )

            print(f"[CHAT] 📥 RESPONSE #{request_num}: {len(response.content)} blocks")
            request_num += 1

            tool_calls_this_round = []
            tool_results = []
            assistant_content = []

            for idx, block in enumerate(response.content):
                if block.type == "tool_use":
                    tool_name = block.name
                    print(f"[CHAT]   🔧 {tool_name}")

                    try:
                        result = mcp_registry.execute_tool(tool_name, block.input)
                        print(f"[CHAT]     ✅")

                        tool_calls_this_round.append({"name": tool_name})
                        all_tool_calls.append({"name": tool_name})
                        assistant_content.append(block)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result)
                        })

                    except Exception as e:
                        print(f"[CHAT]     ❌ {str(e)[:50]}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps({"error": str(e)})
                        })

                elif block.type == "text":
                    final_text = block.text
                    assistant_content.append(block)

            print(f"[CHAT] 📊 Round {iteration}: tools={len(tool_calls_this_round)} | text={len(final_text)}")

            if not tool_results:
                print(f"[CHAT] ✅ FINAL ANSWER RECEIVED")
                break

            print(f"[CHAT] 🔀 Continuing: adding assistant + tool_results to history")
            history.append({"role": "assistant", "content": assistant_content})
            history.append({"role": "user", "content": tool_results})

        print(f"\n[CHAT] 💾 Saving to DB: {len(final_text)} chars | {len(all_tool_calls)} total tools")
        save_message(sid, "assistant", final_text, all_tool_calls if all_tool_calls else None)

        print(f"[CHAT] ✅ COMPLETE - {iteration} iterations")
        print(f"{'=' * 100}\n")

        return jsonify({
            'success': True,
            'response': final_text,
            'tools': [{"name": tc["name"]} for tc in all_tool_calls],
            'tool_count': len(all_tool_calls)
        })

    except Exception as e:
        print(f"\n[CHAT] ❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        print(f"{'=' * 100}\n")
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    init_gdrive()
    print(f"[INFO] Claude + MCP Agent running on http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)