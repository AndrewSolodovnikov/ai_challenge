from flask import Flask, request, jsonify
import anthropic
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import openai
import time
import sqlite3
from pathlib import Path

load_dotenv()
app = Flask(__name__)

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

openai.api_key = os.getenv("HF_TOKEN")
openai.api_base = "https://router.huggingface.co/v1"

conversations = {}
DB_PATH = "memory.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS conversations
                 (
                     session_id
                     TEXT
                     PRIMARY
                     KEY,
                     title
                     TEXT
                     DEFAULT
                     'Untitled',
                     created_at
                     TIMESTAMP,
                     updated_at
                     TIMESTAMP,
                     model
                     TEXT,
                     system_prompt
                     TEXT,
                     message_count
                     INTEGER
                     DEFAULT
                     0,
                     total_tokens
                     INTEGER
                     DEFAULT
                     0,
                     total_time
                     REAL
                     DEFAULT
                     0
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS messages
    (
        id
        INTEGER
        PRIMARY
        KEY
        AUTOINCREMENT,
        session_id
        TEXT,
        role
        TEXT,
        content
        TEXT,
        tokens
        INTEGER
        DEFAULT
        0,
        response_time
        REAL
        DEFAULT
        0,
        created_at
        TIMESTAMP,
        FOREIGN
        KEY
                 (
        session_id
                 ) REFERENCES conversations
                 (
                     session_id
                 )
        )''')

    c.execute('''CREATE TABLE IF NOT EXISTS summaries
    (
        id
        INTEGER
        PRIMARY
        KEY
        AUTOINCREMENT,
        session_id
        TEXT,
        summary_text
        TEXT,
        messages_count
        INTEGER,
        created_at
        TIMESTAMP,
        FOREIGN
        KEY
                 (
        session_id
                 ) REFERENCES conversations
                 (
                     session_id
                 )
        )''')

    conn.commit()
    conn.close()
    print("[LOG] Database initialized")


init_db()


def load_conversation_from_db(session_id):
    """Загрузить диалог из БД"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT role, content
                 FROM messages
                 WHERE session_id = ?
                 ORDER BY created_at ASC''', (session_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return None

    messages = []
    for role, content in rows:
        messages.append({"role": role, "content": content})

    print(f"[LOG] Loaded {len(messages)} messages for session {session_id}")
    return messages


def save_conversation(session_id, model, system_prompt):
    """Сохранить новый диалог"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''INSERT
    OR IGNORE INTO conversations (session_id, created_at, updated_at, model, system_prompt, title)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (session_id, now, now, model, system_prompt, f"Chat {datetime.now().strftime('%d.%m %H:%M')}"))
    conn.commit()
    conn.close()
    print(f"[LOG] Conversation {session_id} saved to DB")


def save_message(session_id, role, content, tokens=0, response_time=0):
    """Сохранить сообщение в БД"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()

    c.execute('''INSERT INTO messages (session_id, role, content, tokens, response_time, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)''', (session_id, role, content[:1000], tokens, response_time, now))

    c.execute('''SELECT message_count, total_tokens, total_time
                 FROM conversations
                 WHERE session_id = ?''', (session_id,))
    result = c.fetchone()
    if result:
        msg_count, total_tokens, total_time = result
        c.execute('''UPDATE conversations
                     SET message_count = ?,
                         total_tokens  = ?,
                         total_time    = ?,
                         updated_at    = ?
                     WHERE session_id = ?''',
                  (msg_count + 1, total_tokens + tokens, total_time + response_time, now, session_id))

    conn.commit()
    conn.close()


def delete_conversation(session_id):
    """Удалить диалог из БД"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''DELETE
                 FROM messages
                 WHERE session_id = ?''', (session_id,))
    c.execute('''DELETE
                 FROM summaries
                 WHERE session_id = ?''', (session_id,))
    c.execute('''DELETE
                 FROM conversations
                 WHERE session_id = ?''', (session_id,))

    conn.commit()
    conn.close()

    if session_id in conversations:
        del conversations[session_id]

    print(f"[LOG] Conversation {session_id} deleted")


def update_conversation_title(session_id, title):
    """Обновить название диалога"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''UPDATE conversations
                 SET title      = ?,
                     updated_at = ?
                 WHERE session_id = ?''', (title, now, session_id))
    conn.commit()
    conn.close()
    print(f"[LOG] Conversation {session_id} renamed to '{title}'")


def get_all_conversations():
    """Получить список всех диалогов"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT session_id, title, created_at, updated_at, model, system_prompt
                 FROM conversations
                 ORDER BY updated_at DESC''')
    results = c.fetchall()
    conn.close()
    return [dict(row) for row in results]


SYSTEM_PROMPTS = {
    "default": "You are a helpful AI assistant. Answer questions clearly and concisely. Be friendly and professional. Provide accurate information",
    "running_coach": "You are an expert running coach for amateur runners. Be encouraging and give specific, actionable advice.",
    "fast_food_chef": "You are an expert fast food chef. Be enthusiastic about food and give practical recipes.",
    "programmer": "You are an expert Python developer. Provide working code examples and explain concepts.",
    "teacher": "You are a patient teacher. Explain complex concepts using simple words and real-world analogies.",
    "creative": "You are a creative assistant. Think outside the box and provide innovative ideas.",
    "philosopher": "You are a wise philosopher. Ask probing questions and present multiple perspectives.",
    "mathematician": "You are a brilliant mathematician. Explain concepts with mathematical rigor and clarity.",
    "linguist": "You are an expert linguist. Explain grammar and provide etymology.",
}


def create_summary(messages):
    """Create a summary of conversation messages"""
    try:
        summary_prompt = "Please provide a concise summary of the following conversation:\n\n"

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            summary_prompt += f"{role.upper()}: {content}\n\n"

        summary_prompt += "\nBrief summary (2-3 sentences):"

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            temperature=0,
            messages=[{"role": "user", "content": summary_prompt}]
        )

        for block in response.content:
            if hasattr(block, 'text'):
                return f"[SUMMARY] {block.text}"
        return "[SUMMARY] Conversation history"
    except Exception as e:
        print(f"[ERROR] Summary creation failed: {e}")
        return "[SUMMARY] Previous conversation context"


def compact_conversation(messages, compact_threshold):
    """Compact conversation history by summarizing old messages"""
    if len(messages) <= compact_threshold:
        return messages, False

    messages_to_summarize = len(messages) - compact_threshold
    old_messages = messages[:messages_to_summarize]
    recent_messages = messages[messages_to_summarize:]

    print(f"[LOG] Compacting: {len(old_messages)} messages -> summary")

    summary = create_summary(old_messages)

    return [{"role": "user", "content": summary}] + recent_messages, True


def agent_loop_claude(messages, system_prompt="default", temperature=0.6):
    system = SYSTEM_PROMPTS.get(system_prompt, SYSTEM_PROMPTS["default"])
    start_time = time.time()
    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            temperature=temperature,
            system=system,
            messages=messages
        )
        elapsed_time = time.time() - start_time

        input_tokens = response.usage.input_tokens if hasattr(response, 'usage') else 0
        output_tokens = response.usage.output_tokens if hasattr(response, 'usage') else 0

        for block in response.content:
            if hasattr(block, 'text'):
                return block.text, elapsed_time, input_tokens, output_tokens
        return "OK", elapsed_time, input_tokens, output_tokens
    except Exception as e:
        elapsed_time = time.time() - start_time
        return f"Error: {str(e)}", elapsed_time, 0, 0


def agent_loop_huggingface(messages, model_id, system_prompt="default", temperature=0.6):
    system = SYSTEM_PROMPTS.get(system_prompt, SYSTEM_PROMPTS["default"])
    hf_messages = [{"role": "system", "content": system}]
    for msg in messages:
        if isinstance(msg.get("content"), str):
            hf_messages.append({"role": msg["role"], "content": msg["content"]})

    start_time = time.time()
    try:
        print(f"[LOG] Calling HF model: {model_id}")
        response = openai.ChatCompletion.create(
            model=model_id,
            messages=hf_messages,
            max_tokens=1024,
            temperature=temperature,
        )
        elapsed_time = time.time() - start_time

        input_tokens = response.get('usage', {}).get('prompt_tokens', 0) if 'usage' in response else 0
        output_tokens = response.get('usage', {}).get('completion_tokens', 0) if 'usage' in response else 0

        return response.choices[0].message['content'], elapsed_time, input_tokens, output_tokens
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"[ERROR] HuggingFace API error: {str(e)}")
        return f"Error: {str(e)}", elapsed_time, 0, 0


def format_response(response_text, output_format, elapsed_time=0, input_tokens=0, output_tokens=0, show_stats=False):
    if show_stats:
        total_tokens = input_tokens + output_tokens
        stats = f"\n\n⏱️ Time: {elapsed_time:.2f}s | 📥 In: {input_tokens} | 📤 Out: {output_tokens} | 📊 Total: {total_tokens}"
        response_text = response_text + stats

    if output_format == "json":
        try:
            if response_text.strip().startswith('{') or response_text.strip().startswith('['):
                return response_text
            data = {
                "status": "success",
                "response": response_text,
                "timestamp": datetime.now().isoformat(),
                "format": "json",
                "response_time": elapsed_time,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens
            }
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    else:
        return response_text


@app.route('/')
def index():
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Multi-Model AI Agent</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px}.container{width:100%;max-width:900px;background:white;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);display:flex;flex-direction:row;height:700px;overflow:hidden}.sidebar{width:250px;background:#f8f9fa;border-right:1px solid #ddd;overflow-y:auto;padding:15px}.sidebar h3{font-size:14px;font-weight:600;color:#333;margin-bottom:10px;margin-top:15px}.sidebar-item{padding:10px;background:white;border:1px solid #ddd;border-radius:6px;margin-bottom:8px;cursor:pointer;font-size:13px;word-break:break-all;transition:all 0.2s;display:flex;justify-content:space-between;align-items:flex-start;gap:8px}.sidebar-item-content{flex:1;min-width:0}.sidebar-item-title{font-weight:600;word-break:break-word;white-space:normal}.sidebar-item-date{font-size:11px;color:#999;margin-top:4px}.sidebar-item:hover{background:#e8e9ff;border-color:#667eea}.sidebar-item.active{background:#667eea;color:white;border-color:#667eea}.sidebar-item.active .sidebar-item-date{color:rgba(255,255,255,0.7)}.sidebar-buttons{display:flex;gap:4px;flex-wrap:wrap}.edit-btn{background:none;border:none;color:#667eea;cursor:pointer;font-size:16px;padding:0;width:24px;height:24px;display:flex;align-items:center;justify-content:center;border-radius:4px}.delete-btn{background:none;border:none;color:#ff4444;cursor:pointer;font-size:16px;padding:0;width:24px;height:24px;display:flex;align-items:center;justify-content:center;border-radius:4px}.edit-btn:hover{background:#e0e0ff}.delete-btn:hover{background:#ffcccc}.sidebar-item.active .edit-btn{color:#fff}.sidebar-item.active .edit-btn:hover{background:rgba(0,0,0,0.2)}.sidebar-item.active .delete-btn{color:#fff}.sidebar-item.active .delete-btn:hover{background:rgba(0,0,0,0.2)}.main{flex:1;display:flex;flex-direction:column;overflow:hidden}.header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:20px;display:flex;justify-content:space-between;align-items:center}.header h1{font-size:24px}.header-controls{display:flex;gap:10px}.model-select{padding:8px 12px;border:1px solid rgba(255,255,255,0.4);border-radius:5px;background:rgba(255,255,255,0.2);color:white;cursor:pointer;font-size:13px;min-width:160px}.model-select option{background:#667eea;color:white}.settings-btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.4);color:white;padding:8px 12px;border-radius:5px;cursor:pointer;font-size:14px}.settings-btn:hover{background:rgba(255,255,255,0.3)}.modal{display:none;position:fixed;z-index:1000;left:0;top:0;width:100%;height:100%;background:rgba(0,0,0,0.4)}.modal.active{display:block}.modal-content{background:white;margin:5% auto;padding:30px;border-radius:10px;width:90%;max-width:550px;box-shadow:0 10px 40px rgba(0,0,0,0.3);max-height:80vh;overflow-y:auto}.modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.modal-header h2{font-size:20px;color:#333}.close-btn{background:none;border:none;font-size:24px;cursor:pointer;color:#999}.close-btn:hover{color:#333}.modal-group{margin-bottom:25px}.modal-group label{display:block;margin-bottom:10px;color:#333;font-weight:600;font-size:14px}.modal-group select,.modal-group input[type="number"],.modal-group input[type="text"]{width:100%;padding:12px;border:1px solid #ddd;border-radius:6px}.temperature-controls{display:flex;gap:8px;margin-bottom:10px}.temp-btn{flex:1;padding:10px;border:2px solid #ddd;border-radius:6px;background:white;cursor:pointer;font-size:13px;color:#888}.temp-btn.active{background:#667eea;color:white;border-color:#667eea}.checkbox-group{display:flex;align-items:center;gap:12px;padding:12px;background:#f5f5f5;border-radius:6px;margin-bottom:8px}.checkbox-group input{cursor:pointer}.checkbox-group label{cursor:pointer;margin:0;flex:1;color:#333;font-size:14px}.modal-buttons{display:flex;gap:10px;justify-content:flex-end;margin-top:25px}.modal-buttons button{padding:10px 20px;border:none;border-radius:5px;cursor:pointer;font-weight:bold;font-size:14px}.btn-save{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white}.btn-cancel{background:#e0e0e0;color:#333}.messages{flex:1;overflow-y:auto;padding:20px;background:#f5f5f5}.message{margin:12px 0;padding:12px;border-radius:8px;word-wrap:break-word;white-space:pre-wrap;line-height:1.5}.user{background:#667eea;color:white;text-align:right;margin-left:50px}.bot{background:#e0e0e0;color:#333;margin-right:50px;font-family:'Courier New',monospace;font-size:12px}.notification{background:#fff3cd;color:#856404;margin-right:50px;font-style:italic}.input-area{padding:20px;border-top:1px solid #ddd;display:flex;gap:10px;background:white}input{flex:1;padding:12px;border:1px solid #ddd;border-radius:6px;font-size:14px}button{padding:12px 24px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:6px;cursor:pointer;font-weight:bold}</style></head><body><div class="container"><div class="sidebar"><h3>💬 Диалоги</h3><div id="conversationsList"></div></div><div class="main"><div class="header"><div><h1>🤖 Multi-Model AI Agent</h1></div><div class="header-controls"><select class="model-select" id="modelSelect"><option value="claude-sonnet-4.5">Claude Sonnet 4.5</option><option value="Qwen/Qwen2.5-7B-Instruct">Qwen 2.5 7B</option><option value="meta-llama/Llama-3.2-3B-Instruct">Llama 3.2 3B</option></select><button class="settings-btn" onclick="openSettings()">⚙️</button></div></div><div id="settingsModal" class="modal"><div class="modal-content"><div class="modal-header"><h2>Settings</h2><button class="close-btn" onclick="closeSettings()">×</button></div><div class="modal-group"><label>System Prompt:</label><select id="prompt"><optgroup label="General"><option value="default">Default</option><option value="creative">Creative</option></optgroup><optgroup label="Experts"><option value="philosopher">Philosopher</option><option value="mathematician">Mathematician</option><option value="linguist">Linguist</option><option value="programmer">Programmer</option><option value="teacher">Teacher</option></optgroup></select></div><div class="modal-group"><label>Temperature:</label><div class="temperature-controls"><button class="temp-btn active" onclick="setTemperature(0)">0</button><button class="temp-btn" onclick="setTemperature(0.35)">0.35</button><button class="temp-btn" onclick="setTemperature(0.6)">0.6</button></div></div><div class="modal-group"><div class="checkbox-group"><input type="checkbox" id="enableCompact" checked><label for="enableCompact">Enable compression</label></div><div class="checkbox-group"><input type="checkbox" id="showstats"><label for="showstats">Show stats</label></div></div><div class="modal-buttons"><button class="btn-cancel" onclick="closeSettings()">Close</button><button class="btn-save" onclick="saveSettings()">Save</button></div></div></div><div id="editModal" class="modal"><div class="modal-content"><div class="modal-header"><h2>Edit Title</h2><button class="close-btn" onclick="closeEditModal()">×</button></div><div class="modal-group"><label>New title:</label><input type="text" id="editTitle" placeholder="Enter new title"></div><div class="modal-buttons"><button class="btn-cancel" onclick="closeEditModal()">Cancel</button><button class="btn-save" onclick="saveTitle()">Save</button></div></div></div><div class="messages" id="messages"></div><div class="input-area"><input type="text" id="input" placeholder="Ask..."><button onclick="send()">Send</button></div></div></div><script>let sid='session_'+Date.now();let editingSid='';let waiting=false;let settings={system:'default',temperature:0,enableCompact:true,compactThreshold:20,showstats:false};async function loadConversations(){const r=await fetch('/api/stats');const data=await r.json();const list=document.getElementById('conversationsList');list.innerHTML='<button onclick="newConversation()" style="width:100%;padding:10px;background:#667eea;color:white;border:none;border-radius:6px;cursor:pointer;margin-bottom:10px">+ New</button>';data.conversations.forEach(c=>{const div=document.createElement('div');div.className='sidebar-item';const date=new Date(c.updated_at).toLocaleString();const content=document.createElement('div');content.className='sidebar-item-content';content.innerHTML=`<div class="sidebar-item-title">${c.title}</div><div class="sidebar-item-date">${date}</div>`;content.onclick=()=>loadConversation(c.session_id);const editBtn=document.createElement('button');editBtn.className='edit-btn';editBtn.innerHTML='✏️';editBtn.onclick=(e)=>{e.stopPropagation();openEditModal(c.session_id,c.title)};const deleteBtn=document.createElement('button');deleteBtn.className='delete-btn';deleteBtn.innerHTML='🗑️';deleteBtn.onclick=(e)=>{e.stopPropagation();deleteConversation(c.session_id)};const btnContainer=document.createElement('div');btnContainer.className='sidebar-buttons';btnContainer.appendChild(editBtn);btnContainer.appendChild(deleteBtn);div.appendChild(content);div.appendChild(btnContainer);list.appendChild(div)})}function openEditModal(sessionId,title){editingSid=sessionId;document.getElementById('editTitle').value=title;document.getElementById('editModal').classList.add('active');document.getElementById('editTitle').focus()}function closeEditModal(){document.getElementById('editModal').classList.remove('active')}async function saveTitle(){const newTitle=document.getElementById('editTitle').value.trim();if(!newTitle)return;await fetch(`/api/conversation/${editingSid}/title`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:newTitle})});closeEditModal();loadConversations()}async function deleteConversation(sessionId){if(!confirm('Delete this conversation?'))return;await fetch(`/api/conversation/${sessionId}`,{method:'DELETE'});loadConversations();newConversation()}function newConversation(){sid='session_'+Date.now();document.getElementById('messages').innerHTML='';loadConversations()}async function loadConversation(sessionId){sid=sessionId;const r=await fetch(`/api/conversation/${sessionId}`);const data=await r.json();const messagesDiv=document.getElementById('messages');messagesDiv.innerHTML='';data.messages.forEach(m=>{const div=document.createElement('div');div.className='message '+(m.role==='user'?'user':'bot');div.textContent=m.content;messagesDiv.appendChild(div)});messagesDiv.scrollTop=messagesDiv.scrollHeight;document.querySelectorAll('.sidebar-item').forEach(el=>el.classList.remove('active'));event.target.closest('.sidebar-item').classList.add('active')}function setTemperature(t){settings.temperature=t;document.querySelectorAll('.temp-btn').forEach(b=>b.classList.remove('active'));event.target.classList.add('active')}function openSettings(){document.getElementById('settingsModal').classList.add('active')}function closeSettings(){document.getElementById('settingsModal').classList.remove('active')}function saveSettings(){settings.system=document.getElementById('prompt').value;settings.enableCompact=document.getElementById('enableCompact').checked;settings.showstats=document.getElementById('showstats').checked;closeSettings()}async function send(){let input=document.getElementById('input');let msg=input.value.trim();if(!msg||waiting)return;addMsg(msg,true);input.value='';waiting=true;const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid,message:msg,model:document.getElementById('modelSelect').value,system_prompt:settings.system,temperature:settings.temperature,show_stats:settings.showstats,enable_compact:settings.enableCompact,compact_threshold:settings.compactThreshold})});const data=await r.json();waiting=false;if(data.success){if(data.compact_notification)addMsg(data.compact_notification,false);addMsg(data.response,false);loadConversations()}else addMsg('Error: '+data.error,false)}function addMsg(text,isUser){const div=document.createElement('div');div.className='message '+(isUser?'user':text.includes('🔄')?'notification':'bot');div.textContent=text;document.getElementById('messages').appendChild(div);document.getElementById('messages').scrollTop=document.getElementById('messages').scrollHeight}document.getElementById('input').addEventListener('keypress',e=>{if(e.key==='Enter')send()});loadConversations();setInterval(loadConversations,5000)</script></body></html>"""


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message', '')
        model = data.get('model', 'claude-sonnet-4.5')
        system_prompt = data.get('system_prompt', 'default')
        temperature = float(data.get('temperature', 0.6))
        show_stats = data.get('show_stats', False)
        enable_compact = data.get('enable_compact', True)
        compact_threshold = int(data.get('compact_threshold', 20))

        if not msg:
            return jsonify({'success': False, 'error': 'Empty message'})

        if sid not in conversations:
            loaded = load_conversation_from_db(sid)
            if loaded:
                conversations[sid] = loaded
            else:
                conversations[sid] = []
                save_conversation(sid, model, system_prompt)

        conversations[sid].append({"role": "user", "content": msg})
        save_message(sid, "user", msg)

        compact_notification = None

        if enable_compact and len(conversations[sid]) > compact_threshold:
            conversations[sid], was_compacted = compact_conversation(conversations[sid], compact_threshold)
            if was_compacted:
                compact_notification = "🔄 History compressed"

        if model == "claude-sonnet-4.5":
            response, elapsed_time, input_tokens, output_tokens = agent_loop_claude(conversations[sid], system_prompt,
                                                                                    temperature)
        else:
            response, elapsed_time, input_tokens, output_tokens = agent_loop_huggingface(conversations[sid], model,
                                                                                         system_prompt, temperature)

        conversations[sid].append({"role": "assistant", "content": response})
        save_message(sid, "assistant", response, input_tokens + output_tokens, elapsed_time)

        formatted_response = format_response(response, "text", elapsed_time, input_tokens, output_tokens, show_stats)

        return jsonify({
            'success': True,
            'response': formatted_response,
            'compact_notification': compact_notification
        })
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        convs = get_all_conversations()
        return jsonify({
            'success': True,
            'total_conversations': len(convs),
            'conversations': convs
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/conversation/<session_id>', methods=['GET'])
def get_conversation(session_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''SELECT role, content, created_at
                     FROM messages
                     WHERE session_id = ?
                     ORDER BY created_at ASC''', (session_id,))
        rows = c.fetchall()
        conn.close()

        messages = [{"role": row[0], "content": row[1], "created_at": row[2]} for row in rows]

        return jsonify({
            'success': True,
            'session_id': session_id,
            'messages': messages
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/conversation/<session_id>', methods=['DELETE'])
def delete_conversation_api(session_id):
    try:
        delete_conversation(session_id)
        return jsonify({'success': True, 'message': 'Conversation deleted'})
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/conversation/<session_id>/title', methods=['PUT'])
def update_title_api(session_id):
    try:
        data = request.json
        title = data.get('title', '')
        if not title:
            return jsonify({'success': False, 'error': 'Title is empty'})
        update_conversation_title(session_id, title)
        return jsonify({'success': True, 'message': 'Title updated'})
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("[INFO] Multi-Model AI Agent running on http://0.0.0.0:8000")
    print("[INFO] SQLite memory enabled")
    app.run(host='0.0.0.0', port=8000, debug=False)