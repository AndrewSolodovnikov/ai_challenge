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


def agent_loop(messages):
    for iteration in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
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
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

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

        .header h1 {
            font-size: 24px;
            margin-bottom: 10px;
        }

        .controls {
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
        }

        .control-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .control-group label {
            font-size: 14px;
            white-space: nowrap;
        }

        select {
            padding: 8px 12px;
            border: none;
            border-radius: 5px;
            background: rgba(255, 255, 255, 0.2);
            color: white;
            cursor: pointer;
            font-size: 14px;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }

        select option {
            background: #667eea;
            color: white;
        }

        select:hover {
            background: rgba(255, 255, 255, 0.3);
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
            font-family: 'Courier New', monospace;
            font-size: 13px;
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
        }

        .bot.json {
            background: #f0f0f0;
            border-left: 4px solid #667eea;
            color: #1e40af;
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

        button:hover {
            transform: translateY(-2px);
        }

        button:active {
            transform: translateY(0);
        }

        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        @media (max-width: 600px) {
            .container {
                height: 100vh;
            }
            .controls {
                flex-direction: column;
                align-items: flex-start;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Claude 4.5 Agent</h1>
            <div class="controls">
                <div class="control-group">
                    <label for="format">Output format:</label>
                    <select id="format">
                        <option value="text">Plain Text</option>
                        <option value="json">JSON</option>
                    </select>
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

        function getSelectedFormat() {
            return document.getElementById('format').value;
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

            let format = getSelectedFormat();

            fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: sid,
                    message: msg,
                    output_format: format
                })
            })
            .then(r => r.json())
            .then(data => {
                let loading = document.getElementById('loading');
                if (loading) loading.remove();
                document.getElementById('btn').disabled = false;
                waiting = false;

                if (data.success) {
                    addMsg(data.response, false, format);
                } else {
                    addMsg('Error: ' + data.error, false, 'text');
                }
            })
            .catch(e => {
                let loading = document.getElementById('loading');
                if (loading) loading.remove();
                document.getElementById('btn').disabled = false;
                waiting = false;
                addMsg('Error: ' + e.message, false, 'text');
            });
        }

        function addMsg(text, isUser, format) {
            let div = document.createElement('div');
            format = format || 'text';

            if (isUser) {
                div.className = 'message user';
            } else {
                div.className = 'message bot' + (format === 'json' ? ' json' : '');
            }

            div.textContent = text;
            document.getElementById('messages').appendChild(div);
            document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
        }

        document.getElementById('input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') send();
        });

        // Update format selection indicator
        document.getElementById('format').addEventListener('change', function(e) {
            console.log('Format changed to:', e.target.value);
        });
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
        output_format = data.get('output_format', 'text')

        print(f"[LOG] Format: {output_format}, Message: {msg}")

        if not msg:
            return jsonify({'success': False, 'error': 'Empty message'})

        if sid not in conversations:
            conversations[sid] = []

        conversations[sid].append({"role": "user", "content": msg})
        response = agent_loop(conversations[sid])
        conversations[sid].append({"role": "assistant", "content": response})

        # Format response based on selected format
        formatted_response = format_response(response, output_format)

        return jsonify({'success': True, 'response': formatted_response})
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model': 'claude-sonnet-4-5'})


if __name__ == '__main__':
    print("[INFO] Claude Agent running on http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000, debug=False)
