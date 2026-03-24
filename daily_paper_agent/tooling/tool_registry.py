from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass
class RegisteredTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def as_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.as_schema() for tool in self._tools.values()]

    def execute(self, name: str, args: dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"unknown tool: {name}")
        return tool.handler(args)

    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())

