"""Run the agent on labelled tickets N times and report per-check pass rates.

Usage: python -m evals.run_eval [--runs 3]
Needs OPENAI_API_KEY. Running several times measures consistency, not just correctness.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from triage.agent import TriageOutcome
from triage.config import Settings
from triage.factory import build_agent
from triage.guardrails import PROMISE_PATTERNS
from triage.llm import LLMConfigurationError

EXPECTED = json.loads((Path(__file__).parent / "expected.json").read_text(encoding="utf-8"))


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def check(outcome: TriageOutcome, exp: dict) -> dict[str, bool]:
    r = outcome.result
    checks = {
        "urgency": r.urgency.value in exp["urgency"],
        "action": r.action.value in _as_list(exp["action"]),
        "issue_types": set(exp["must_include_issue_types"]) <= {i.value for i in r.issue_types},
        "sentiment": r.sentiment.value in exp["sentiment"],
        "language": r.language.lower().startswith(exp["language"]),
        "no_fallback": not outcome.fallback_used,
    }
    if "must_not_include_issue_types" in exp:
        checks["no_wrong_issue_types"] = not set(exp["must_not_include_issue_types"]) & {i.value for i in r.issue_types}
    if "route_to" in exp:
        checks["route_to"] = r.route_to is not None and r.route_to.value == exp["route_to"]
    if "must_call_tools" in exp:
        checks["tools"] = set(exp["must_call_tools"]) <= {c.name for c in outcome.trace}
    if "must_follow_up" in exp:
        checks["follow_ups"] = set(exp["must_follow_up"]) <= {t.value for t in r.follow_up_teams}
    if exp.get("no_promises"):
        checks["no_promises"] = not PROMISE_PATTERNS.search(r.customer_reply)
    if "must_cite_kb" in exp:
        checks["kb_grounding"] = set(exp["must_cite_kb"]) <= set(r.kb_article_ids)
    # How often the raw LLM was already right (guardrails didn't have to save it).
    if outcome.llm_result is not None:
        checks["llm_action_before_guardrails"] = outcome.llm_result.action.value in _as_list(exp["action"])
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    agent, store = build_agent(Settings.from_env())
    tickets = [t for t in store.sample_tickets if t.id in EXPECTED]
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for ticket in tickets:
        for _ in range(args.runs):
            results = check(agent.triage(ticket), EXPECTED[ticket.id])
            failed = [k for k, ok in results.items() if not ok]
            print(f"{ticket.id}: {'PASS' if not failed else 'FAIL ' + ', '.join(failed)}")
            for name, ok in results.items():
                totals[name][0] += ok
                totals[name][1] += 1

    print("\nPass rate per check:")
    for name, (passed, n) in sorted(totals.items()):
        print(f"  {name:<30} {passed}/{n}  ({passed / n:.0%})")


if __name__ == "__main__":
    try:
        main()
    except LLMConfigurationError as exc:
        raise SystemExit(f"Configuration error: {exc}")
