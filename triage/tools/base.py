"""Tool abstraction: a Pydantic params model is the single source of truth for schema + validation."""

import json
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError


def inline_refs(schema: dict) -> dict:
    """Resolve $defs/$ref so the schema is self-contained (friendlier for function calling)."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    Params: ClassVar[type[BaseModel]]

    @abstractmethod
    def run(self, params: BaseModel) -> dict:
        """Execute the tool with validated params and return a JSON-serialisable result."""

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": inline_refs(self.Params.model_json_schema()),
            },
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def openai_schemas(self) -> list[dict]:
        return [t.openai_schema() for t in self._tools.values()]

    def execute(self, name: str, raw_arguments: str) -> dict:
        """Run a tool. Errors are returned as data so the model can recover instead of crashing the loop."""
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool '{name}'. Available: {sorted(self._tools)}"}
        try:
            params = tool.Params.model_validate(json.loads(raw_arguments or "{}"))
        except (json.JSONDecodeError, ValidationError) as exc:
            return {"error": f"Invalid arguments for {name}: {exc}"}
        try:
            return tool.run(params)
        except Exception as exc:  # a broken backend must not kill triage
            return {"error": f"{name} failed: {exc}"}
