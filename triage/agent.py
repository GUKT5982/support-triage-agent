"""Agent loop: tool-calling until the model submits a schema-valid TriageResult, then guardrails."""

import json
from dataclasses import dataclass, field

from pydantic import ValidationError

from triage.data_store import MockDataStore
from triage.guardrails import GuardrailContext, GuardrailEngine
from triage.llm import ChatClient
from triage.models import Action, IssueType, Sentiment, Team, Ticket, TriageResult, Urgency
from triage.tools.base import ToolRegistry, inline_refs

SUBMIT_TOOL_NAME = "submit_triage"


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict
    result: dict


@dataclass
class TriageOutcome:
    ticket_id: str
    result: TriageResult
    llm_result: TriageResult | None  # what the model proposed, before guardrails
    guardrails_fired: list[str]
    trace: list[ToolCallRecord] = field(default_factory=list)
    fallback_used: bool = False


def submit_tool_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": SUBMIT_TOOL_NAME,
            "description": "Submit the final triage decision. Call exactly once, after investigating.",
            "parameters": inline_refs(TriageResult.model_json_schema()),
        },
    }


def render_ticket(ticket: Ticket) -> str:
    lines = [f"Ticket {ticket.id} | customer_id: {ticket.customer_id} | channel: {ticket.channel}", "<ticket_messages>"]
    lines += [f"[{i}] ({m.sent_at}) {m.text}" for i, m in enumerate(ticket.messages, 1)]
    lines.append("</ticket_messages>")
    return "\n".join(lines)


def fallback_result(reason: str) -> TriageResult:
    """Safe default when the model fails: a human looks at it."""
    return TriageResult(
        urgency=Urgency.HIGH, urgency_reason="Automatic triage failed; defaulting to human review.",
        product_area="unknown", primary_issue=IssueType.OTHER, issue_types=[IssueType.OTHER],
        sentiment=Sentiment.NEUTRAL, language="en", summary="Automatic triage could not complete.",
        key_facts=[], action=Action.ESCALATE_TO_HUMAN, route_to=Team.CUSTOMER_SUCCESS,
        action_reason=reason, customer_reply="", internal_note=f"[fallback] {reason}", confidence=0.0,
    )


class TriageAgent:
    def __init__(self, client: ChatClient, tools: ToolRegistry, guardrails: GuardrailEngine,
                 store: MockDataStore, system_prompt: str, max_steps: int = 6):
        self._client = client
        self._tools = tools
        self._guardrails = guardrails
        self._store = store
        self._system_prompt = system_prompt
        self._max_steps = max_steps

    def triage(self, ticket: Ticket) -> TriageOutcome:
        trace: list[ToolCallRecord] = []
        llm_result, failure = self._run_loop(ticket, trace)
        proposed = llm_result or fallback_result(failure)

        ctx = GuardrailContext(ticket, self._store.get_customer(ticket.customer_id), self._store.kb_ids)
        final, fired = self._guardrails.enforce(proposed, ctx)
        return TriageOutcome(ticket.id, final, llm_result, fired, trace, fallback_used=llm_result is None)

    def _run_loop(self, ticket: Ticket, trace: list[ToolCallRecord]) -> tuple[TriageResult | None, str]:
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": render_ticket(ticket)},
        ]
        tool_schemas = [*self._tools.openai_schemas(), submit_tool_schema()]

        for _ in range(self._max_steps):
            try:
                turn = self._client.complete(messages, tool_schemas)
            except Exception as exc:  # network / API errors after SDK retries
                return None, f"LLM call failed: {exc}"
            if not turn.tool_calls:
                messages.append({"role": "assistant", "content": turn.content or ""})
                messages.append({"role": "user", "content": f"Respond with a tool call. Finish with {SUBMIT_TOOL_NAME}."})
                continue

            messages.append(turn.as_message())
            submitted: TriageResult | None = None
            for call in turn.tool_calls:  # every tool_call id needs a tool message
                if call.name == SUBMIT_TOOL_NAME:
                    output, submitted = self._validate_submission(call.arguments)
                else:
                    output = self._tools.execute(call.name, call.arguments)
                trace.append(ToolCallRecord(call.name, _safe_json(call.arguments), output))
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(output, ensure_ascii=False)})
            if submitted is not None:
                return submitted, ""

        return None, f"No valid {SUBMIT_TOOL_NAME} within {self._max_steps} steps"

    @staticmethod
    def _validate_submission(raw: str) -> tuple[dict, TriageResult | None]:
        try:
            result = TriageResult.model_validate_json(raw)
            return {"status": "accepted"}, result
        except ValidationError as exc:
            # Feed the error back so the model can fix its own output on the next step.
            return {"error": f"Invalid triage: {exc}. Fix the fields and call {SUBMIT_TOOL_NAME} again."}, None


def _safe_json(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw}
