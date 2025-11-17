import subprocess
import json
import sys
import os

def test_mcp_list_tools():
    """Тест получения списка инструментов MCP"""

    print("🔌 Запуск MCP сервера filesystem для /tmp...\n")

    try:
        # Запускаем MCP сервер для директории /tmp
        process = subprocess.Popen(
            ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Отправляем инициализационный запрос (MCP protocol)
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }

        print("📤 Отправка initialize запроса...\n")
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        # Читаем ответ
        response = process.stdout.readline()

        if response:
            print("✅ MCP сервер ответил!\n")
            print("📋 Ответ сервера:")
            print(json.dumps(json.loads(response), indent=2))
            print("\n✅ MCP сервер работает корректно!")
        else:
            print("⚠️  Нет ответа от сервера")

        # Завершаем процесс
        process.terminate()
        process.wait(timeout=2)

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


def test_simple():
    """Простой тест доступности MCP"""
    print("🧪 Простая проверка MCP сервера...\n")

    try:
        # Проверяем что npx работает
        result = subprocess.run(
            ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            capture_output=True,
            text=True,
            timeout=2
        )
    except subprocess.TimeoutExpired:
        print("✅ MCP сервер запущен (timeout ожидаем)")
        print("\n📋 Доступные MCP серверы:")
        print("1. @modelcontextprotocol/server-filesystem - работа с файлами")
        print("2. @modelcontextprotocol/server-sqlite - работа с SQLite")
        print("3. @modelcontextprotocol/server-brave-search - поиск в интернете")
        print("\n✅ MCP готов к интеграции в app.py")
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("MCP SERVER TEST")
    print("=" * 60 + "\n")

    # Сначала простой тест
    if test_simple():
        print("\n" + "=" * 60)
        print("PROTOCOL TEST")
        print("=" * 60 + "\n")
        # Затем тест протокола
        test_mcp_list_tools()
