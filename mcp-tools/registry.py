"""MCP Tool Registry - центральный реестр всех MCP инструментов"""


class MCPRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, func, description, input_schema):
        """Регистрация нового инструмента"""
        self.tools[name] = {
            "func": func,
            "description": description,
            "input_schema": input_schema
        }

    def get_tool_definitions(self):
        """Получить список инструментов для Claude API"""
        return [
            {
                "name": name,
                "description": tool["description"],
                "input_schema": tool["input_schema"]
            }
            for name, tool in self.tools.items()
        ]

    def execute_tool(self, name, arguments):
        """Выполнить инструмент по имени"""
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found"}

        try:
            return self.tools[name]["func"](**arguments)
        except Exception as e:
            return {"error": str(e)}


# Глобальный экземпляр
mcp_registry = MCPRegistry()
