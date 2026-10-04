"""Terminal entry point: python -m triage [--ticket T-001] [--file ticket.json] [--json] [--trace]"""

import argparse
import json
import sys

from triage.agent import TriageOutcome
from triage.config import Settings
from triage.factory import build_agent
from triage.llm import LLMConfigurationError
from triage.models import Ticket


def format_outcome(o: TriageOutcome, show_trace: bool) -> str:
    r = o.result
    lines = [
        "=" * 72,
        f"Ticket {o.ticket_id}" + ("   [FALLBACK]" if o.fallback_used else ""),
        "=" * 72,
        f"Urgency    : {r.urgency.value.upper()}  - {r.urgency_reason}",
        f"Issue      : {r.primary_issue.value} (all: {', '.join(i.value for i in r.issue_types)}) | area: {r.product_area}",
        f"Sentiment  : {r.sentiment.value} | language: {r.language} | confidence: {r.confidence:.2f}",
        f"Action     : {r.action.value}" + (f" -> {r.route_to.value}" if r.route_to else "") + f"  - {r.action_reason}",
        f"Follow-ups : {', '.join(t.value for t in r.follow_up_teams) or '-'}",
        f"KB used    : {', '.join(r.kb_article_ids) or '-'}",
        f"Guardrails : {', '.join(o.guardrails_fired) or '-'}",
        f"Summary    : {r.summary}",
        "Key facts  :", *[f"  - {f}" for f in r.key_facts],
        "Reply to customer:", f"  {r.customer_reply}",
        "Internal note:", f"  {r.internal_note}",
    ]
    if show_trace:
        lines.append("Tool trace:")
        lines += [f"  {i}. {c.name}({json.dumps(c.arguments, ensure_ascii=False)[:120]})" for i, c in enumerate(o.trace, 1)]
    return "\n".join(lines)


def to_json(o: TriageOutcome) -> dict:
    return {
        "ticket_id": o.ticket_id,
        "result": o.result.model_dump(mode="json"),
        "guardrails_fired": o.guardrails_fired,
        "fallback_used": o.fallback_used,
        "tools_called": [c.name for c in o.trace],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Triage support tickets with an LLM agent.")
    parser.add_argument("--ticket", help="Sample ticket id (e.g. T-002). Default: all samples.")
    parser.add_argument("--file", help="Path to a JSON file with one ticket or a list of tickets.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--trace", action="store_true", help="Show tool calls.")
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except LLMConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    agent, store = build_agent(Settings.from_env())

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            raw = json.load(f)
        tickets = [Ticket(**t) for t in (raw if isinstance(raw, list) else [raw])]
    else:
        tickets = [t for t in store.sample_tickets if args.ticket in (None, t.id)]
    if not tickets:
        print(f"No ticket found for {args.ticket!r}", file=sys.stderr)
        return 1

    outcomes = [agent.triage(t) for t in tickets]
    if args.json:
        print(json.dumps([to_json(o) for o in outcomes], ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(format_outcome(o, args.trace) for o in outcomes))
    return 0
