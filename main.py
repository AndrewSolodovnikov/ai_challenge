from flask import Flask, request, jsonify
import anthropic
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import openai

load_dotenv()
app = Flask(__name__)

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

openai.api_key = os.getenv("HF_TOKEN")
openai.api_base = "https://router.huggingface.co/v1"

conversations = {}

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

def agent_loop_claude(messages, system_prompt="default", temperature=0.6):
    system = SYSTEM_PROMPTS.get(system_prompt, SYSTEM_PROMPTS["default"])
    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            temperature=temperature,
            system=system,
            messages=messages
        )
        for block in response.content:
            if hasattr(block, 'text'):
                return block.text
        return "OK"
    except Exception as e:
        return f"Error: {str(e)}"

def agent_loop_huggingface(messages, model_id, system_prompt="default", temperature=0.6):
    system = SYSTEM_PROMPTS.get(system_prompt, SYSTEM_PROMPTS["default"])
    hf_messages = [{"role": "system", "content": system}]
    for msg in messages:
        if isinstance(msg.get("content"), str):
            hf_messages.append({"role": msg["role"], "content": msg["content"]})
    try:
        print(f"[LOG] Calling HF model: {model_id}")
        response = openai.ChatCompletion.create(
            model=model_id,
            messages=hf_messages,
            max_tokens=1024,
            temperature=temperature,
        )
        return response.choices[0].message['content']
    except Exception as e:
        print(f"[ERROR] HuggingFace API error: {str(e)}")
        return f"Error: {str(e)}"

def format_response(response_text, output_format):
    if output_format == "json":
        try:
            if response_text.strip().startswith('{') or response_text.strip().startswith('['):
                return response_text
            data = {"status": "success", "response": response_text, "timestamp": datetime.now().isoformat(), "format": "json"}
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    else:
        return response_text

@app.route('/')
def index():
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Multi-Model AI Agent</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px}.container{width:100%;max-width:800px;background:white;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);display:flex;flex-direction:column;height:700px;overflow:hidden}.header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:20px;border-radius:12px 12px 0 0}.header-top{display:flex;justify-content:space-between;align-items:center}.header h1{font-size:24px}.header-controls{display:flex;gap:10px;align-items:center}.model-select{padding:8px 12px;border:1px solid rgba(255,255,255,0.4);border-radius:5px;background:rgba(255,255,255,0.2);color:white;cursor:pointer;font-size:13px;font-weight:500;min-width:180px}.model-select option{background:#667eea;color:white}.settings-btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.4);color:white;padding:8px 12px;border-radius:5px;cursor:pointer;font-size:14px}.settings-btn:hover{background:rgba(255,255,255,0.3)}.modal{display:none;position:fixed;z-index:1000;left:0;top:0;width:100%;height:100%;background:rgba(0,0,0,0.4)}.modal.active{display:block}.modal-content{background:white;margin:5% auto;padding:30px;border-radius:10px;width:90%;max-width:550px;box-shadow:0 10px 40px rgba(0,0,0,0.3);max-height:80vh;overflow-y:auto}.modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.modal-header h2{font-size:20px;color:#333}.close-btn{background:none;border:none;font-size:24px;cursor:pointer;color:#999}.close-btn:hover{color:#333}.modal-group{margin-bottom:25px}.modal-group label{display:block;margin-bottom:10px;color:#333;font-weight:600;font-size:14px}.modal-group select{width:100%;padding:12px;border:1px solid #ddd;border-radius:6px;background:white;color:#333;cursor:pointer;font-size:14px}.modal-group select:focus{outline:none;border-color:#667eea;box-shadow:0 0 0 3px rgba(102,126,234,0.1)}.temperature-controls{display:flex;gap:8px;margin-bottom:10px}.temp-btn{flex:1;padding:10px;border:2px solid #ddd;border-radius:6px;background:white;cursor:pointer;font-size:13px;font-weight:500;color:#888}.temp-btn:hover{border-color:#667eea;background:#f0f0f0}.temp-btn.active{background:#667eea;color:white;border-color:#667eea}.checkbox-group{display:flex;align-items:center;gap:12px;padding:12px;background:#f5f5f5;border-radius:6px}.checkbox-group input{cursor:pointer}.checkbox-group label{cursor:pointer;margin:0;flex:1;color:#333;font-size:14px}.modal-buttons{display:flex;gap:10px;justify-content:flex-end;margin-top:25px}.modal-buttons button{padding:10px 20px;border:none;border-radius:5px;cursor:pointer;font-weight:bold;font-size:14px}.btn-save{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white}.btn-cancel{background:#e0e0e0;color:#333}.messages{flex:1;overflow-y:auto;padding:20px;background:#f5f5f5}.message{margin:12px 0;padding:12px;border-radius:8px;word-wrap:break-word;white-space:pre-wrap;line-height:1.5}.user{background:#667eea;color:white;text-align:right;margin-left:50px}.bot{background:#e0e0e0;color:#333;margin-right:50px;font-family:'Courier New',monospace;font-size:12px}.loading{text-align:center;color:#999;font-style:italic}.input-area{padding:20px;border-top:1px solid #ddd;display:flex;gap:10px;background:white}input{flex:1;padding:12px;border:1px solid #ddd;border-radius:6px;font-size:14px}input:focus{outline:none;border-color:#667eea;box-shadow:0 0 0 3px rgba(102,126,234,0.1)}button{padding:12px 24px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;border-radius:6px;cursor:pointer;font-weight:bold}button:hover{transform:translateY(-2px)}button:disabled{opacity:0.6}</style></head><body><div class="container"><div class="header"><div class="header-top"><h1>🤖 Multi-Model AI Agent</h1><div class="header-controls"><select class="model-select" id="modelSelect"><option value="claude-sonnet-4.5">Claude Sonnet 4.5</option><option value="Qwen/Qwen2.5-7B-Instruct">Qwen 2.5 7B</option><option value="meta-llama/Llama-3.2-3B-Instruct">Llama 3.2 3B</option></select><button class="settings-btn" onclick="openSettings()">⚙️ Settings</button></div></div></div><div id="settingsModal" class="modal"><div class="modal-content"><div class="modal-header"><h2>Settings</h2><button class="close-btn" onclick="closeSettings()">×</button></div><div class="modal-group"><label>System Prompt:</label><select id="prompt"><optgroup label="General"><option value="default">Default Assistant</option><option value="creative">Creative</option></optgroup><optgroup label="Experts"><option value="philosopher">Philosopher</option><option value="mathematician">Mathematician</option><option value="linguist">Linguist</option><option value="programmer">Programmer</option><option value="teacher">Teacher</option></optgroup><optgroup label="Specialists"><option value="running_coach">Running Coach</option><option value="fast_food_chef">Fast Food Chef</option></optgroup></select></div><div class="modal-group"><label>Output Format:</label><select id="format"><option value="text">Plain Text</option><option value="json">JSON</option></select></div><div class="modal-group"><label>Temperature:</label><div class="temperature-controls"><button class="temp-btn active" onclick="setTemperature(0)">0</button><button class="temp-btn" onclick="setTemperature(0.35)">0.35</button><button class="temp-btn" onclick="setTemperature(0.6)">0.6</button></div><div id="tempValue">Current: 0</div></div><div class="modal-group"><div class="checkbox-group"><input type="checkbox" id="followup" checked><label for="followup">Ask follow-up questions</label></div></div><div class="modal-buttons"><button class="btn-cancel" onclick="closeSettings()">Close</button><button class="btn-save" onclick="saveSettings()">Save</button></div></div></div><div class="messages" id="messages"></div><div class="input-area"><input type="text" id="input" placeholder="Ask your question..."><button id="btn" onclick="send()">Send</button></div></div><script>let sid='session_'+Date.now();let waiting=false;let settings={system:'default',format:'text',temperature:0,followup:true};function setTemperature(temp){settings.temperature=temp;document.querySelectorAll('.temp-btn').forEach(btn=>btn.classList.remove('active'));event.target.classList.add('active');document.getElementById('tempValue').textContent='Current: '+temp}function openSettings(){document.getElementById('settingsModal').classList.add('active')}function closeSettings(){document.getElementById('settingsModal').classList.remove('active')}function saveSettings(){settings.system=document.getElementById('prompt').value;settings.format=document.getElementById('format').value;settings.followup=document.getElementById('followup').checked;closeSettings()}function send(){let input=document.getElementById('input');let msg=input.value.trim();if(!msg||waiting)return;addMsg(msg,true);input.value='';waiting=true;document.getElementById('btn').disabled=true;let div=document.createElement('div');div.className='message loading';div.id='loading';div.textContent='Processing...';document.getElementById('messages').appendChild(div);document.getElementById('messages').scrollTop=document.getElementById('messages').scrollHeight;const model=document.getElementById('modelSelect').value;fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid,message:msg,model:model,system_prompt:settings.system,output_format:settings.format,temperature:settings.temperature})}).then(r=>r.json()).then(data=>{let loading=document.getElementById('loading');if(loading)loading.remove();document.getElementById('btn').disabled=false;waiting=false;if(data.success){addMsg(data.response,false)}else{addMsg('Error: '+data.error,false)}}).catch(e=>{let loading=document.getElementById('loading');if(loading)loading.remove();document.getElementById('btn').disabled=false;waiting=false;addMsg('Error: '+e.message,false)})}function addMsg(text,isUser){let div=document.createElement('div');div.className='message '+(isUser?'user':'bot');div.textContent=text;document.getElementById('messages').appendChild(div);document.getElementById('messages').scrollTop=document.getElementById('messages').scrollHeight}document.getElementById('input').addEventListener('keypress',function(e){if(e.key==='Enter')send()});window.onclick=function(event){let modal=document.getElementById('settingsModal');if(event.target==modal){closeSettings()}}</script></body></html>"""

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message', '')
        model = data.get('model', 'claude-sonnet-4.5')
        system_prompt = data.get('system_prompt', 'default')
        output_format = data.get('output_format', 'text')
        temperature = float(data.get('temperature', 0.6))

        print(f"[LOG] Model: {model}, System: {system_prompt}, Temp: {temperature}")

        if not msg:
            return jsonify({'success': False, 'error': 'Empty message'})

        if sid not in conversations:
            conversations[sid] = []

        conversations[sid].append({"role": "user", "content": msg})

        if model == "claude-sonnet-4.5":
            print("[LOG] Using Claude Sonnet 4.5")
            response = agent_loop_claude(conversations[sid], system_prompt, temperature)
        else:
            print(f"[LOG] Using HuggingFace model: {model}")
            response = agent_loop_huggingface(conversations[sid], model, system_prompt, temperature)

        conversations[sid].append({"role": "assistant", "content": response})
        formatted_response = format_response(response, output_format)

        return jsonify({'success': True, 'response': formatted_response})
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("[INFO] Multi-Model AI Agent running on http://0.0.0.0:8000")
    print("[INFO] Models: Claude Sonnet 4.5, Qwen 2.5 7B, Llama 3.2 3B")
    app.run(host='0.0.0.0', port=8000, debug=False)