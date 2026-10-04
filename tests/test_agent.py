"""Agent loop tests with a scripted fake LLM - no network, no API key."""

import json

import pytest
from pydantic import ValidationError

from tests.factories import make_result
from triage.agent import SUBMIT_TOOL_NAME
from triage.config import PROJECT_ROOT, Settings
from triage.factory import build_agent
from triage.llm import AssistantTurn, LLMConfigurationError, ToolCall
from triage.models import Action, IssueType, Team, TriageResult


class ScriptedClient:
    def __init__(self, turns):
        self._turns = list(turns)
        self.requests = []

    def complete(self, messages, tools):
        self.requests.append(list(messages))
        return self._turns.pop(0)


def call(name, idx, **args):
    return AssistantTurn(None, [ToolCall(f"call_{idx}", name, json.dumps(args))])


def submit(idx, result):
    return AssistantTurn(None, [ToolCall(f"call_{idx}", SUBMIT_TOOL_NAME, result.model_dump_json())])


def agent_with(turns, max_steps=6):
    client = ScriptedClient(turns)
    agent, _ = build_agent(Settings(data_dir=PROJECT_ROOT / "data", max_steps=max_steps), client=client)
    return agent, client


def test_happy_path_runs_tools_then_submits(tickets):
    agent, client = agent_with([
        call("get_customer_history", 1, customer_id="C-003"),
        call("search_knowledge_base", 2, query="macOS dark mode system default"),
        submit(3, make_result(kb_article_ids=["KB-008"])),
    ])
    outcome = agent.triage(tickets["T-003"])
    assert [c.name for c in outcome.trace] == ["get_customer_history", "search_knowledge_base", SUBMIT_TOOL_NAME]
    assert outcome.result.action == Action.AUTO_RESPOND and not outcome.fallback_used
    # tool output was sent back to the model
    assert any(m["role"] == "tool" and "KB-008" in m["content"] for m in client.requests[2])


def test_invalid_submission_is_fed_back_and_retried(tickets):
    bad = AssistantTurn(None, [ToolCall("c1", SUBMIT_TOOL_NAME, json.dumps({"urgency": "urgent"}))])
    agent, client = agent_with([bad, submit(2, make_result(kb_article_ids=["KB-008"]))])
    outcome = agent.triage(tickets["T-003"])
    assert not outcome.fallback_used
    assert "Invalid triage" in client.requests[1][-1]["content"]


def test_guardrails_override_unsafe_llm_decision(tickets):
    unsafe = make_result(primary_issue=IssueType.BILLING, issue_types=[IssueType.BILLING], kb_article_ids=["KB-002"])
    agent, _ = agent_with([submit(1, unsafe)])
    outcome = agent.triage(tickets["T-001"])
    assert outcome.llm_result.action == Action.AUTO_RESPOND
    assert outcome.result.action == Action.ESCALATE_TO_HUMAN and outcome.result.route_to == Team.BILLING


def test_falls_back_to_human_when_model_never_submits(tickets):
    turns = [call("search_knowledge_base", i, query="error 500") for i in range(3)]
    agent, _ = agent_with(turns, max_steps=3)
    outcome = agent.triage(tickets["T-002"])
    assert outcome.fallback_used and outcome.result.action == Action.ESCALATE_TO_HUMAN


def test_falls_back_when_llm_api_errors(tickets):
    class Broken:
        def complete(self, *_):
            raise TimeoutError("timeout")

    agent, _ = build_agent(Settings(data_dir=PROJECT_ROOT / "data"), client=Broken())
    outcome = agent.triage(tickets["T-003"])
    assert outcome.fallback_used and "timeout" in outcome.result.internal_note


def test_submit_schema_requires_route_for_handoff():
    with pytest.raises(ValidationError):
        TriageResult(**{**make_result().model_dump(), "action": "escalate_to_human", "route_to": None})


def test_configuration_errors_stop_the_run_instead_of_falling_back(tickets):
    class BadKey:
        def complete(self, *_):
            raise LLMConfigurationError("API key rejected (401)")

    agent, _ = build_agent(Settings(data_dir=PROJECT_ROOT / "data"), client=BadKey())
    with pytest.raises(LLMConfigurationError):
        agent.triage(tickets["T-001"])


def test_cli_reports_configuration_error_with_exit_code(monkeypatch, capsys):
    from triage import cli

    def broken_build(*_a, **_k):
        raise LLMConfigurationError("API key rejected (401)")

    monkeypatch.setattr(cli, "build_agent", broken_build)
    assert cli.main(["--ticket", "T-001"]) == 2
    assert "Configuration error" in capsys.readouterr().err
