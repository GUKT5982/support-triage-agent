"""Thin LLM adapter so the agent loop does not depend on a vendor SDK (and can be tested offline)."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as produced by the model


@dataclass(frozen=True)
class AssistantTurn:
    content: str | None
    tool_calls: list[ToolCall]

    def as_message(self) -> dict:
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ],
        }


class ChatClient(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn: ...


class OpenAIChatClient:
    def __init__(self, model: str, temperature: float | None = 0.0, timeout: float = 60.0, max_retries: int = 3):
        from openai import OpenAI  # imported lazily so tests don't need the SDK configured

        self._client = OpenAI(timeout=timeout, max_retries=max_retries)
        self._model = model
        self._temperature = temperature

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        kwargs = {"model": self._model, "messages": messages, "tools": tools, "tool_choice": "required"}
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        message = self._client.chat.completions.create(**kwargs).choices[0].message
        return AssistantTurn(
            content=message.content,
            tool_calls=[ToolCall(c.id, c.function.name, c.function.arguments) for c in message.tool_calls or []],
        )
