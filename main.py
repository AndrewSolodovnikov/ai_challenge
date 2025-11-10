from flask import Flask, request, jsonify
import anthropic
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
conversations = {}

# Разные system prompts
SYSTEM_PROMPTS = {
    "default": """You are a helpful AI assistant. 
- Answer questions clearly and concisely
- Be friendly and professional
- Provide accurate information""",

    "running_coach": """You are an expert running coach for amateur runners focusing on middle distances (800m to 5km).
Your expertise includes:
- Training plans tailored to individual fitness levels
- Interval training and tempo runs
- Injury prevention and recovery
- Nutrition for runners
- Mental preparation for races

Be encouraging, supportive, and give specific, actionable advice.""",

    "fast_food_chef": """You are an expert fast food chef with years of experience creating quick, delicious meals.
Your expertise includes:
- Quick recipes (20 minutes or less)
- Using common ingredients
- Street food and comfort food
- Budget-friendly cooking
- Flavor combinations

Be enthusiastic about food and give practical, easy-to-follow recipes.""",

    "programmer": """You are an expert Python developer.
- Provide working code examples
- Explain complex concepts
- Use markdown formatting with code blocks
- Suggest best practices and design patterns
- Be precise and technical
- Discuss performance optimization""",

    "teacher": """You are a patient teacher.
- Explain complex concepts using simple words
- Use real-world analogies and examples
- Check understanding with questions
- Always encourage the student
- Break down topics step by step
- Adapt explanations to student level""",

    "creative": """You are a creative assistant.
- Think outside the box
- Provide innovative ideas
- Use storytelling and examples
- Be imaginative and engaging
- Encourage brainstorming
- Offer multiple perspectives""",

    "philosopher": """You are a wise philosopher with deep knowledge of philosophy, ethics, and human nature.
Your expertise includes:
- Existentialism, epistemology, metaphysics
- Ethics and moral philosophy
- Philosophy of mind and consciousness
- Ancient and modern philosophical traditions
- Critical thinking and logical reasoning

Your approach:
- Ask probing questions to help people think deeper
- Present multiple philosophical perspectives
- Use Socratic method when appropriate
- Connect abstract concepts to real life
- Be thoughtful, nuanced, and humble about complexities
- Acknowledge different philosophical traditions""",

    "mathematician": """You are a brilliant mathematician with expertise across all mathematical domains.
Your expertise includes:
- Algebra, geometry, calculus, linear algebra
- Number theory and discrete mathematics
- Statistics and probability
- Mathematical modeling and problem-solving
- Advanced mathematics and theoretical foundations

Your approach:
- Explain concepts with mathematical rigor and clarity
- Use step-by-step solutions with clear derivations
- Provide multiple solution methods when applicable
- Use visual descriptions for geometric concepts
- Connect mathematics to real-world applications
- Explain the "why" behind mathematical principles
- Use appropriate mathematical notation and symbols""",

    "linguist": """You are an expert linguist with deep knowledge of language, grammar, and communication.
Your expertise includes:
- Linguistics, grammar, syntax, and semantics
- Etymology and word origins
- Multiple languages and language families
- Phonetics and phonology
- Language evolution and history
- Communication and rhetorics

Your approach:
- Explain grammatical concepts with clear examples
- Provide etymological context for words
- Compare language structures across different languages
- Use linguistic terminology appropriately
- Help people understand nuances in language
- Teach language learning strategies
- Discuss how language shapes thinking""",
}

tools = [
    {
        "name": "get_time",
        "description": "Get current time",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "calculate",
        "description": "Calculate math expression",
        "input_schema": {
            "type": "object",
            "properties": {"expr": {"type": "string"}},
            "required": ["expr"]
        }
    }
]


def run_tool(name, inputs):
    if name == "get_time":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif name == "calculate":
        try:
            return str(eval(inputs.get("expr", "")))
        except Exception as e:
            return str(e)
    return "Unknown tool"


def agent_loop(messages, system_prompt="default", ask_followup=False, temperature=0.6):
    system = SYSTEM_PROMPTS.get(system_prompt, SYSTEM_PROMPTS["default"])

    # Если включено "ask follow-up questions", добавляем инструкцию в system
    if ask_followup:
        system += """

[IMPORTANT INSTRUCTIONS FOR ASK_FOLLOWUP MODE]:
1. When user's request needs clarification, ask ONE question at a time
2. Wait for the user's answer before asking the next question
3. Ask 3-5 clarifying questions in total, one per response
4. Format each question clearly and on a new line
5. After collecting all information, provide a comprehensive, personalized answer
6. Do NOT ask all questions at once - ask them sequentially"""

    for iteration in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            temperature=temperature,
            system=system,
            tools=tools,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, 'text'):
                    return block.text
            return "OK"

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})

    return "Max iterations"


def format_response(response_text, output_format):
    """Format response based on selected format"""
    if output_format == "json":
        try:
            # Try to parse as JSON first
            if response_text.strip().startswith('{') or response_text.strip().startswith('['):
                return response_text

            # Otherwise wrap in JSON structure
            data = {
                "status": "success",
                "response": response_text,
                "timestamp": datetime.now().isoformat(),
                "format": "json"
            }
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    else:
        # Return as plain text
        return response_text


@app.route('/')
def index():
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Claude Agent</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .container {
            width: 100%;
            max-width: 800px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            display: flex;
            flex-direction: column;
            height: 700px;
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px 12px 0 0;
        }

        .header-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }

        .header h1 {
            font-size: 24px;
        }

        .settings-btn {
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.4);
            color: white;
            padding: 8px 12px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.2s;
        }

        .settings-btn:hover {
            background: rgba(255, 255, 255, 0.3);
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.4);
        }

        .modal.active {
            display: block;
        }

        .modal-content {
            background: white;
            margin: 5% auto;
            padding: 30px;
            border-radius: 10px;
            width: 90%;
            max-width: 550px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
            max-height: 80vh;
            overflow-y: auto;
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .modal-header h2 {
            font-size: 20px;
            color: #333;
        }

        .close-btn {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #999;
        }

        .close-btn:hover {
            color: #333;
        }

        .modal-group {
            margin-bottom: 25px;
        }

        .modal-group label {
            display: block;
            margin-bottom: 10px;
            color: #333;
            font-weight: 600;
            font-size: 14px;
        }

        .modal-group select {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            background: white;
            color: #333;
            cursor: pointer;
            font-size: 14px;
        }

        .modal-group select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .temperature-controls {
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
        }

        .temp-btn {
            flex: 1;
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 6px;
            background: white;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            transition: all 0.2s;
            color: #888;
        }

        .temp-btn:hover {
            border-color: #667eea;
            background: #f0f0f0;
        }

        .temp-btn.active {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }

        .temperature-description {
            font-size: 12px;
            color: #999;
            margin-top: 8px;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
            line-height: 1.4;
        }

        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            background: #f5f5f5;
            border-radius: 6px;
            margin-bottom: 12px;
        }

        .checkbox-group input[type="checkbox"] {
            cursor: pointer;
            width: 18px;
            height: 18px;
        }

        .checkbox-group label {
            cursor: pointer;
            margin: 0;
            flex: 1;
            color: #333;
            font-size: 14px;
            font-weight: normal;
        }

        .modal-buttons {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
            margin-top: 25px;
        }

        .modal-buttons button {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            font-size: 14px;
        }

        .btn-save {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-save:hover {
            transform: translateY(-2px);
        }

        .btn-cancel {
            background: #e0e0e0;
            color: #333;
        }

        .btn-cancel:hover {
            background: #d0d0d0;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f5f5f5;
        }

        .message {
            margin: 12px 0;
            padding: 12px;
            border-radius: 8px;
            word-wrap: break-word;
            white-space: pre-wrap;
            line-height: 1.5;
        }

        .user {
            background: #667eea;
            color: white;
            text-align: right;
            margin-left: 50px;
            font-family: Arial, sans-serif;
        }

        .bot {
            background: #e0e0e0;
            color: #333;
            margin-right: 50px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
        }

        .loading {
            text-align: center;
            color: #999;
            font-style: italic;
        }

        .input-area {
            padding: 20px;
            border-top: 1px solid #ddd;
            display: flex;
            gap: 10px;
            background: white;
        }

        input {
            flex: 1;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
        }

        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        button {
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            transition: transform 0.2s;
        }

        button:hover { transform: translateY(-2px); }
        button:active { transform: translateY(0); }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-top">
                <h1>🤖 Claude 4.5 Agent</h1>
                <button class="settings-btn" onclick="openSettings()">⚙️ Settings</button>
            </div>
        </div>

        <!-- Settings Modal -->
        <div id="settingsModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Settings</h2>
                    <button class="close-btn" onclick="closeSettings()">×</button>
                </div>

                <div class="modal-group">
                    <label for="prompt">System Prompt:</label>
                    <select id="prompt">
                        <optgroup label="General">
                            <option value="default">Default Assistant</option>
                            <option value="creative">Creative</option>
                        </optgroup>
                        <optgroup label="Experts">
                            <option value="philosopher">Philosopher</option>
                            <option value="mathematician">Mathematician</option>
                            <option value="linguist">Linguist</option>
                            <option value="programmer">Programmer</option>
                            <option value="teacher">Teacher</option>
                        </optgroup>
                        <optgroup label="Specialists">
                            <option value="running_coach">Running Coach</option>
                            <option value="fast_food_chef">Fast Food Chef</option>
                        </optgroup>
                    </select>
                </div>

                <div class="modal-group">
                    <label for="format">Output Format:</label>
                    <select id="format">
                        <option value="text">Plain Text</option>
                        <option value="json">JSON</option>
                    </select>
                </div>

                <div class="modal-group">
                    <label>Temperature (Creativity Level):</label>
                    <div class="temperature-controls">
                        <button class="temp-btn active" onclick="setTemperature(0)">0 Deterministic</button>
                        <button class="temp-btn" onclick="setTemperature(0.35)">0.35 Balanced</button>
                        <button class="temp-btn" onclick="setTemperature(0.6)">0.6 Creative</button>
                    </div>
                    <div id="tempValue" style="font-size: 13px; color: #666; margin-bottom: 8px;">Current: 0 (Deterministic)</div>
                    <div class="temperature-description" id="tempDescription">
                        0 = Deterministic: Same answer every time. Good for technical tasks, calculations.
                    </div>
                </div>

                <div class="modal-group">
                    <label>Options:</label>
                    <div class="checkbox-group">
                        <input type="checkbox" id="followup" checked>
                        <label for="followup">Ask follow-up questions (one by one)</label>
                    </div>
                </div>

                <div class="modal-buttons">
                    <button class="btn-cancel" onclick="closeSettings()">Close</button>
                    <button class="btn-save" onclick="saveSettings()">Save</button>
                </div>
            </div>
        </div>

        <div class="messages" id="messages"></div>

        <div class="input-area">
            <input type="text" id="input" placeholder="Ask your question...">
            <button id="btn" onclick="send()">Send</button>
        </div>
    </div>

    <script>
        let sid = 'session_' + Date.now();
        let waiting = false;
        let settings = {
            system: 'default',
            format: 'text',
            temperature: 0,
            followup: true
        };

        const temperatureDescriptions = {
            0: "0 = Deterministic: Same answer every time. Good for technical tasks, calculations, factual information.",
            0.35: "0.35 = Balanced: Good balance between accuracy and creativity. Recommended for most tasks.",
            0.6: "0.6 = Creative: More varied and creative responses. Good for brainstorming, writing, ideas."
        };

        function setTemperature(temp) {
            settings.temperature = temp;
            document.querySelectorAll('.temp-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            document.getElementById('tempValue').textContent = `Current: ${temp}`;
            document.getElementById('tempDescription').textContent = temperatureDescriptions[temp];
        }

        function openSettings() {
            document.getElementById('settingsModal').classList.add('active');
            document.getElementById('prompt').value = settings.system;
            document.getElementById('format').value = settings.format;
            document.getElementById('followup').checked = settings.followup;

            // Update temperature buttons
            document.querySelectorAll('.temp-btn').forEach(btn => btn.classList.remove('active'));
            const tempBtn = document.querySelector(`[onclick="setTemperature(${settings.temperature})"]`);
            if (tempBtn) tempBtn.classList.add('active');
            document.getElementById('tempValue').textContent = `Current: ${settings.temperature}`;
            document.getElementById('tempDescription').textContent = temperatureDescriptions[settings.temperature];
        }

        function closeSettings() {
            document.getElementById('settingsModal').classList.remove('active');
        }

        function saveSettings() {
            settings.system = document.getElementById('prompt').value;
            settings.format = document.getElementById('format').value;
            settings.followup = document.getElementById('followup').checked;
            closeSettings();
            console.log('Settings saved:', settings);
        }

        function send() {
            let input = document.getElementById('input');
            let msg = input.value.trim();
            if (!msg || waiting) return;

            addMsg(msg, true);
            input.value = '';
            waiting = true;
            document.getElementById('btn').disabled = true;

            let div = document.createElement('div');
            div.className = 'message loading';
            div.id = 'loading';
            div.textContent = 'Processing...';
            document.getElementById('messages').appendChild(div);
            document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;

            fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: sid,
                    message: msg,
                    system_prompt: settings.system,
                    output_format: settings.format,
                    temperature: settings.temperature,
                    ask_followup: settings.followup
                })
            })
            .then(r => r.json())
            .then(data => {
                let loading = document.getElementById('loading');
                if (loading) loading.remove();
                document.getElementById('btn').disabled = false;
                waiting = false;

                if (data.success) {
                    addMsg(data.response, false);
                } else {
                    addMsg('Error: ' + data.error, false);
                }
            })
            .catch(e => {
                let loading = document.getElementById('loading');
                if (loading) loading.remove();
                document.getElementById('btn').disabled = false;
                waiting = false;
                addMsg('Error: ' + e.message, false);
            });
        }

        function addMsg(text, isUser) {
            let div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            div.textContent = text;
            document.getElementById('messages').appendChild(div);
            document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
        }

        document.getElementById('input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') send();
        });

        // Закрытие модального окна при клике вне его
        window.onclick = function(event) {
            let modal = document.getElementById('settingsModal');
            if (event.target == modal) {
                closeSettings();
            }
        }
    </script>
</body>
</html>"""
    return html


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message', '')
        system_prompt = data.get('system_prompt', 'default')
        output_format = data.get('output_format', 'text')
        temperature = float(data.get('temperature', 0.6))
        ask_followup = data.get('ask_followup', True)

        print(
            f"[LOG] System: {system_prompt}, Format: {output_format}, Temp: {temperature}, Follow-up: {ask_followup}, Message: {msg}")

        if not msg:
            return jsonify({'success': False, 'error': 'Empty message'})

        if sid not in conversations:
            conversations[sid] = []

        conversations[sid].append({"role": "user", "content": msg})
        response = agent_loop(conversations[sid], system_prompt, ask_followup, temperature)
        conversations[sid].append({"role": "assistant", "content": response})

        # Format response
        formatted_response = format_response(response, output_format)

        return jsonify({'success': True, 'response': formatted_response})
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    print("[INFO] Claude Agent with Temperature Control running on http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000, debug=False)
