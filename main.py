from flask import Flask, request, jsonify
import anthropic
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
conversations = {}

tools = [
    {
        "name": "get_time",
        "description": "Получить текущее время",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "calculate",
        "description": "Вычислить математическое выражение",
        "input_schema": {
            "type": "object",
            "properties": {"expr": {"type": "string", "description": "Математическое выражение (например: 2+2)"}},
            "required": ["expr"]
        }
    }
]


def run_tool(name, inputs):
    if name == "get_time":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif name == "calculate":
        try:
            expr = inputs.get("expr", "")
            result = eval(expr)
            return f"Результат: {result}"
        except Exception as e:
            return f"Ошибка вычисления: {str(e)}"
    else:
        return f"Неизвестный инструмент: {name}"


def agent_loop(messages):
    print(f"[DEBUG] Начало цикла агента. Сообщений в истории: {len(messages)}")

    for iteration in range(10):
        print(f"[DEBUG] Итерация {iteration + 1}/10")

        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2048,
                tools=tools,
                messages=messages
            )

            print(f"[DEBUG] stop_reason: {response.stop_reason}")

            if response.stop_reason == "end_turn":
                print("[DEBUG] Claude завершил работу (end_turn)")
                for block in response.content:
                    if hasattr(block, 'text'):
                        return block.text
                return "Ответ получен"

            if response.stop_reason == "tool_use":
                print("[DEBUG] Claude хочет использовать инструмент")

                messages.append({
                    "role": "assistant",
                    "content": response.content
                })

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"[DEBUG] Вызов инструмента: {block.name}")
                        result = run_tool(block.name, block.input)
                        print(f"[DEBUG] Результат: {result}")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })

                messages.append({
                    "role": "user",
                    "content": tool_results
                })
            else:
                break

        except Exception as e:
            print(f"[ERROR] Ошибка: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"Ошибка: {str(e)}"

    return "Достигнут максимум итераций"


@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Claude 4.5 Agent</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.jsdelivr.net/npm/markdown-it@14/dist/markdown-it.min.js"></script>
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
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
            }

            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 12px 12px 0 0;
                text-align: center;
            }

            .header h1 { font-size: 24px; margin-bottom: 5px; }
            .status { font-size: 12px; opacity: 0.8; }

            .messages {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                background: #f9f9f9;
            }

            .message {
                margin-bottom: 15px;
                padding: 12px 16px;
                border-radius: 8px;
                animation: slideIn 0.3s ease-in-out;
                word-wrap: break-word;
            }

            @keyframes slideIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .user-message {
                background: #667eea;
                color: white;
                margin-left: 50px;
                text-align: right;
            }

            .assistant-message {
                background: #e9ecef;
                color: #333;
                margin-right: 50px;
            }

            .assistant-message code {
                background: #f5f5f5;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
                font-size: 13px;
            }

            .assistant-message pre {
                background: #2d2d2d;
                color: #f8f8f2;
                padding: 12px;
                border-radius: 6px;
                overflow-x: auto;
                margin: 8px 0;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.4;
            }

            .assistant-message pre code {
                background: none;
                padding: 0;
                color: inherit;
            }

            .assistant-message h1 { font-size: 20px; margin: 15px 0 10px 0; color: #333; }
            .assistant-message h2 { font-size: 18px; margin: 12px 0 8px 0; color: #444; border-bottom: 2px solid #667eea; padding-bottom: 5px; }
            .assistant-message h3 { font-size: 16px; margin: 10px 0 6px 0; color: #555; }

            .assistant-message ul, .assistant-message ol { margin: 8px 0 8px 20px; }
            .assistant-message li { margin-bottom: 4px; line-height: 1.6; }

            .assistant-message blockquote { border-left: 4px solid #667eea; padding-left: 12px; margin: 8px 0; color: #666; font-style: italic; }

            .assistant-message table { border-collapse: collapse; margin: 10px 0; width: 100%; }
            .assistant-message table td, .assistant-message table th { border: 1px solid #ddd; padding: 8px; }
            .assistant-message table th { background: #667eea; color: white; }
            .assistant-message table tr:nth-child(even) { background: #f5f5f5; }

            .loading {
                text-align: center;
                color: #999;
                font-style: italic;
                padding: 20px;
            }

            .input-area {
                padding: 20px;
                border-top: 1px solid #ddd;
                display: flex;
                gap: 10px;
                background: white;
                border-radius: 0 0 12px 12px;
            }

            input {
                flex: 1;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 14px;
                outline: none;
            }

            input:focus {
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
                <h1>🤖 Claude 4.5 Agent</h1>
                <div class="status">С поддержкой кода и формул</div>
            </div>
            <div class="messages" id="messages"></div>
            <div class="input-area">
                <input type="text" id="input" placeholder="Введите ваш вопрос..." autocomplete="off">
                <button onclick="sendMessage()">Отправить</button>
            </div>
        </div>

        <script>
            let sessionId = 'session_' + Date.now();
            let isWaiting = false;

            const md = window.markdownit({
                html: true,
                linkify: true,
                typographer: true
            });

            function addMessage(text, isUser) {
                const messagesDiv = document.getElementById('messages');
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message ' + (isUser ? 'user-message' : 'assistant-message');

                if (isUser) {
                    messageDiv.textContent = text;
                } else {
                    messageDiv.innerHTML = md.render(text);
                }

                messagesDiv.appendChild(messageDiv);

                if (!isUser && window.MathJax) {
                    MathJax.typesetPromise([messageDiv]).catch(err => console.log('MathJax Error:', err));
                }

                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }

            function sendMessage() {
                console.log('sendMessage called');

                if (isWaiting) {
                    console.log('Still waiting for response');
                    return;
                }

                const input = document.getElementById('input');
                const message = input.value.trim();

                console.log('Message:', message);

                if (!message) return;

                addMessage(message, true);
                input.value = '';

                const button = document.querySelector('button');
                button.disabled = true;
                isWaiting = true;

                const messagesDiv = document.getElementById('messages');
                const loadingDiv = document.createElement('div');
                loadingDiv.className = 'message loading';
                loadingDiv.textContent = '⏳ Обработка...';
                loadingDiv.id = 'loading';
                messagesDiv.appendChild(loadingDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;

                console.log('Sending request to /api/chat');

                fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: sessionId,
                        message: message
                    })
                })
                .then(response => {
                    console.log('Response status:', response.status);
                    return response.json();
                })
                .then(data => {
                    console.log('Response data:', data);

                    const loading = document.getElementById('loading');
                    if (loading) loading.remove();

                    button.disabled = false;
                    isWaiting = false;

                    if (data.success) {
                        addMessage(data.response, false);
                    } else {
                        addMessage('❌ Ошибка: ' + data.error, false);
                    }
                })
                .catch(error => {
                    console.error('Fetch error:', error);

                    const loading = document.getElementById('loading');
                    if (loading) loading.remove();

                    button.disabled = false;
                    isWaiting = false;

                    addMessage('❌ Ошибка: ' + error.message, false);
                });
            }

            document.getElementById('input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !isWaiting) {
                    sendMessage();
                }
            });

            console.log('Page loaded. sendMessage function:', typeof sendMessage);
        </script>
    </body>
    </html>
    '''


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        session_id = data.get('session_id', 'default')
        user_message = data.get('message', '')

        print(f"\n[LOG] Новый запрос: {user_message}")

        if not user_message:
            return jsonify({'success': False, 'error': 'Пустое сообщение'})

        if session_id not in conversations:
            conversations[session_id] = []

        conversations[session_id].append({"role": "user", "content": user_message})
        response = agent_loop(conversations[session_id])
        conversations[session_id].append({"role": "assistant", "content": response})

        return jsonify({'success': True, 'response': response})

    except Exception as e:
        print(f"[ERROR] Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    print("[INFO] Запуск Claude 4.5 Agent")
    app.run(host='0.0.0.0', port=8000, debug=False)
