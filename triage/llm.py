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


class LLMConfigurationError(RuntimeError):
    """Bad key, unknown model, wrong base URL: retrying or falling back per ticket would only hide it."""


class ChatClient(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn: ...


class OpenAIChatClient:
    def __init__(self, model: str, temperature: float | None = 0.0, timeout: float = 60.0, max_retries: int = 3):
        import openai  # imported lazily so tests don't need the SDK configured

        self._errors = openai
        try:
            # Reads OPENAI_API_KEY and OPENAI_BASE_URL (any OpenAI-compatible provider) from the environment.
            self._client = openai.OpenAI(timeout=timeout, max_retries=max_retries)
        except openai.OpenAIError as exc:
            raise LLMConfigurationError(f"OpenAI client could not start: {exc}. Check OPENAI_API_KEY in .env") from exc
        self._model = model
        self._temperature = temperature

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        kwargs = {"model": self._model, "messages": messages, "tools": tools, "tool_choice": "required"}
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        try:
            message = self._client.chat.completions.create(**kwargs).choices[0].message
        except (self._errors.AuthenticationError, self._errors.PermissionDeniedError) as exc:
            raise LLMConfigurationError(f"API key rejected ({exc.status_code}). Check OPENAI_API_KEY in .env") from exc
        except self._errors.NotFoundError as exc:
            raise LLMConfigurationError(
                f"Model '{self._model}' or endpoint not found. Check TRIAGE_MODEL / OPENAI_BASE_URL") from exc
        return AssistantTurn(
            content=message.content,
            tool_calls=[ToolCall(c.id, c.function.name, c.function.arguments) for c in message.tool_calls or []],
        )
