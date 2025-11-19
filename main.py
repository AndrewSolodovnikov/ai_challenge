from flask import Flask, request, jsonify, render_template_string
import anthropic
import os
import json
from dotenv import load_dotenv
from database import (
    save_message,
    get_conversation_history,
    get_all_conversations,
)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

from mcp_tools.registry import mcp_registry
from mcp_tools.gdrive_tools import register_gdrive_tools
from scheduler import set_gdrive_service, get_scheduler

load_dotenv()
app = Flask(__name__)

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
gdrive_service = None
scheduler = None


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
.new-chat-btn { width: 100%; padding: 10px; background: #667eea; border: none; border-radius: 6px; color: white; cursor: pointer; font-weight: bold; }
.new-chat-btn:hover { background: #764ba2; }
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
.tools { background: #f0f0f0; padding: 12px 30px; border-bottom: 1px solid #ddd; overflow-x: auto; }
.tool-badge { display: inline-block; background: white; padding: 6px 10px; border-radius: 4px; margin-right: 8px; font-size: 11px; border: 1px solid #ddd; color: #667eea; }
.chat { flex: 1; padding: 20px 30px; overflow-y: auto; background: #fafafa; }
.msg { margin-bottom: 15px; padding: 12px; border-radius: 8px; max-width: 80%; word-wrap: break-word; line-height: 1.6; }
.user { background: #667eea; color: white; margin-left: auto; text-align: right; }
.assistant { background: white; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
.tool-call { background: #fff3cd; color: #856404; font-size: 12px; border-left: 3px solid #ffc107; }
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
</style></head><body>

<div class="sidebar">
<div class="sidebar-header">
<h2>💬 Conversations</h2>
<button class="new-chat-btn" onclick="newChat()">+ New Chat</button>
</div>
<div class="status">
✅ Scheduler Running<br>
📁 Every 30 seconds
</div>
<div class="conversations" id="convList">Loading...</div>
</div>

<div class="main">
<div class="header">
<h1>🤖 Claude + MCP Agent</h1>
<div class="subtitle">Google Drive Monitor + Telegram Notifications</div>
</div>

<div class="tools">
<strong>📋 MCP Tools:</strong>
<div id="toolsList">Loading...</div>
</div>

<div class="chat" id="chat"></div>

<div class="input-area">
<input type="text" id="input" placeholder="Ask Claude...">
<button id="btn" onclick="send()">Send</button>
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
    document.getElementById('toolsList').innerHTML = data.tools.map(t => 
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

        document.getElementById('chat').removeChild(loading);

        if (data.success) {
            if (data.tools && data.tools.length > 0) {
                for (let tool of data.tools) {
                    addMsg('🔧 Used: ' + tool.name, 'tool-call');
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


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message', '')

        if not msg:
            return jsonify({'success': False, 'error': 'Empty message'})

        history = get_conversation_history(sid)
        history.append({"role": "user", "content": msg})
        save_message(sid, "user", msg)

        tools = mcp_registry.get_tool_definitions()

        response = anthropic_client.messages.create(
            model="claude-opus-4-1",
            max_tokens=2048,
            tools=tools,
            messages=history
        )

        tool_calls = []
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                result = mcp_registry.execute_tool(block.name, block.input)
                tool_calls.append({"name": block.name})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result)
                })

        if tool_results:
            history.append({"role": "assistant", "content": response.content})
            history.append({"role": "user", "content": tool_results})

            final_response = anthropic_client.messages.create(
                model="claude-opus-4-1",
                max_tokens=2048,
                messages=history
            )

            assistant_msg = ""
            for block in final_response.content:
                if hasattr(block, 'text'):
                    assistant_msg = block.text
        else:
            assistant_msg = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    assistant_msg = block.text

        save_message(sid, "assistant", assistant_msg, tool_calls if tool_calls else None)

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
    print(f"[INFO] Claude + MCP Agent running on http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)