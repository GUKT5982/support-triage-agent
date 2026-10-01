"""Deterministic business rules applied AFTER the LLM decision.

The LLM proposes; these rules enforce non-negotiable policy (money at risk, enterprise outages,
grounding). Each rule may only make a decision safer: raise urgency or hand the ticket to a human.
"""

from dataclasses import dataclass, field
from typing import Protocol

from triage.models import Action, Customer, IssueType, Sentiment, Team, Ticket, TriageResult, Urgency

DISPUTE_KEYWORDS = ("disput", "chargeback", "charge back", "report to my bank", "ยกเลิกบัตร", "แจ้งธนาคาร")
MONEY_KEYWORDS = ("charge", "charged", "refund", "double", "twice", "three", "หักเงิน", "คืนเงิน", "ตัดเงิน")
ENTERPRISE_PLANS = ("enterprise",)


@dataclass(frozen=True)
class GuardrailContext:
    ticket: Ticket
    customer: Customer | None
    known_kb_ids: frozenset[str] = field(default_factory=frozenset)

    def text_contains(self, keywords: tuple[str, ...]) -> bool:
        text = self.ticket.full_text.lower()
        return any(k in text for k in keywords)


class Rule(Protocol):
    name: str

    def apply(self, result: TriageResult, ctx: GuardrailContext) -> TriageResult | None:
        """Return a modified result if the rule fires, otherwise None."""


def _hand_off(result: TriageResult, team: Team, urgency_floor: Urgency, reason: str) -> TriageResult:
    return result.model_copy(update={
        "action": Action.ESCALATE_TO_HUMAN,
        "route_to": team,
        "urgency": result.urgency.at_least(urgency_floor),
        "internal_note": f"{result.internal_note}\n[guardrail] {reason}".strip(),
    })


class MoneyAtRiskRule:
    """Billing issues with real charges are never auto-answered; dispute threats are critical."""
    name = "money_at_risk"

    def apply(self, result, ctx):
        if IssueType.BILLING not in result.issue_types:
            return None
        pending = sum(1 for e in (ctx.customer.billing_events if ctx.customer else []) if e.get("status") == "pending")
        if not (pending >= 2 or ctx.text_contains(MONEY_KEYWORDS)):
            return None
        floor = Urgency.CRITICAL if ctx.text_contains(DISPUTE_KEYWORDS) else Urgency.HIGH
        return _hand_off(result, Team.BILLING, floor, f"Money at risk ({pending} pending charges); only Billing may void or refund.")


class EnterpriseOutageRule:
    """Service outage for an enterprise customer always pages incident response."""
    name = "enterprise_outage"

    def apply(self, result, ctx):
        if IssueType.OUTAGE not in result.issue_types or ctx.customer is None:
            return None
        if ctx.customer.plan.lower() not in ENTERPRISE_PLANS:
            return None
        return _hand_off(result, Team.INCIDENT_RESPONSE, Urgency.CRITICAL,
                         f"Enterprise outage ({ctx.customer.seats} seats, region {ctx.customer.data_region}).")


class UnknownKbArticleRule:
    """Drop KB ids the model invented."""
    name = "unknown_kb_article"

    def apply(self, result, ctx):
        valid = [i for i in result.kb_article_ids if i in ctx.known_kb_ids]
        if valid == result.kb_article_ids:
            return None
        return result.model_copy(update={"kb_article_ids": valid})


class UngroundedAutoResponseRule:
    """An automatic reply must cite at least one KB article."""
    name = "ungrounded_auto_response"

    def apply(self, result, ctx):
        if result.action != Action.AUTO_RESPOND or result.kb_article_ids:
            return None
        return result.model_copy(update={"action": Action.ROUTE_TO_SPECIALIST, "route_to": Team.TECHNICAL_SUPPORT})


class LowConfidenceRule:
    """Below the threshold a human reviews instead of auto-replying."""
    name = "low_confidence"

    def __init__(self, threshold: float):
        self.threshold = threshold

    def apply(self, result, ctx):
        if result.action != Action.AUTO_RESPOND or result.confidence >= self.threshold:
            return None
        return result.model_copy(update={"action": Action.ROUTE_TO_SPECIALIST, "route_to": Team.TECHNICAL_SUPPORT})


class AngryCustomerFloorRule:
    """An angry customer is never 'low' urgency."""
    name = "angry_customer_floor"

    def apply(self, result, ctx):
        if result.sentiment != Sentiment.ANGRY or result.urgency.rank > Urgency.LOW.rank:
            return None
        return result.model_copy(update={"urgency": Urgency.MEDIUM})


class GuardrailEngine:
    def __init__(self, rules: list[Rule]):
        self._rules = rules

    def enforce(self, result: TriageResult, ctx: GuardrailContext) -> tuple[TriageResult, list[str]]:
        fired: list[str] = []
        for rule in self._rules:
            updated = rule.apply(result, ctx)
            if updated is not None:
                result = updated
                fired.append(rule.name)
        return result, fired


def default_rules(confidence_threshold: float) -> list[Rule]:
    """Order matters: clean the data first, then the safety escalations."""
    return [
        UnknownKbArticleRule(),
        UngroundedAutoResponseRule(),
        LowConfidenceRule(confidence_threshold),
        AngryCustomerFloorRule(),
        MoneyAtRiskRule(),
        EnterpriseOutageRule(),
    ]
