"""Composition root: the only place that wires concrete implementations together."""

from triage.agent import TriageAgent
from triage.config import Settings
from triage.data_store import MockDataStore
from triage.guardrails import GuardrailEngine, default_rules
from triage.llm import ChatClient, OpenAIChatClient
from triage.prompts import load_prompt
from triage.tools import ToolRegistry, default_tools


def build_agent(settings: Settings, client: ChatClient | None = None) -> tuple[TriageAgent, MockDataStore]:
    store = MockDataStore(settings.data_dir)
    agent = TriageAgent(
        client=client or OpenAIChatClient(settings.model, settings.temperature),
        tools=ToolRegistry(default_tools(store)),
        guardrails=GuardrailEngine(default_rules(settings.confidence_threshold)),
        store=store,
        system_prompt=load_prompt("system_prompt"),
        max_steps=settings.max_steps,
    )
    return agent, store
