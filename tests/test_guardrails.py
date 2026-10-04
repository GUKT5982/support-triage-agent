from tests.factories import make_result
from triage.guardrails import GuardrailContext, GuardrailEngine, default_rules
from triage.models import Action, IssueType, Sentiment, Team, Urgency

engine = GuardrailEngine(default_rules(confidence_threshold=0.7))


def ctx(store, ticket):
    return GuardrailContext(ticket, store.get_customer(ticket.customer_id), store.kb_ids)


def test_billing_with_dispute_threat_becomes_critical_escalation(store, tickets):
    proposed = make_result(primary_issue=IssueType.BILLING, issue_types=[IssueType.BILLING], urgency=Urgency.HIGH)
    result, fired = engine.enforce(proposed, ctx(store, tickets["T-001"]))
    assert "money_at_risk" in fired
    assert (result.action, result.route_to, result.urgency) == (Action.ESCALATE_TO_HUMAN, Team.BILLING, Urgency.CRITICAL)


def test_enterprise_outage_pages_incident_response(store, tickets):
    proposed = make_result(primary_issue=IssueType.OUTAGE, issue_types=[IssueType.OUTAGE],
                           urgency=Urgency.HIGH, action=Action.ROUTE_TO_SPECIALIST)
    result, fired = engine.enforce(proposed, ctx(store, tickets["T-002"]))
    assert "enterprise_outage" in fired
    assert (result.route_to, result.urgency) == (Team.INCIDENT_RESPONSE, Urgency.CRITICAL)


def test_correct_low_risk_decision_is_untouched(store, tickets):
    proposed = make_result(kb_article_ids=["KB-008"], issue_types=[IssueType.BUG, IssueType.FEATURE_REQUEST],
                           primary_issue=IssueType.BUG, sentiment=Sentiment.POSITIVE,
                           follow_up_teams=[Team.ENGINEERING, Team.PRODUCT])
    result, fired = engine.enforce(proposed, ctx(store, tickets["T-003"]))
    assert fired == [] and result == proposed


def test_hallucinated_kb_ids_are_removed_and_reply_goes_to_human(store, tickets):
    result, fired = engine.enforce(make_result(kb_article_ids=["KB-404"]), ctx(store, tickets["T-003"]))
    assert result.kb_article_ids == []
    assert fired == ["unknown_kb_article", "ungrounded_auto_response"]
    assert result.action == Action.ROUTE_TO_SPECIALIST


def test_low_confidence_blocks_auto_response(store, tickets):
    result, fired = engine.enforce(make_result(confidence=0.4), ctx(store, tickets["T-003"]))
    assert "low_confidence" in fired and result.action == Action.ROUTE_TO_SPECIALIST


def test_angry_customer_is_never_low(store, tickets):
    result, _ = engine.enforce(make_result(sentiment=Sentiment.ANGRY), ctx(store, tickets["T-003"]))
    assert result.urgency == Urgency.MEDIUM


def test_guardrails_never_lower_urgency(store, tickets):
    proposed = make_result(primary_issue=IssueType.OUTAGE, issue_types=[IssueType.OUTAGE], urgency=Urgency.CRITICAL,
                           action=Action.ESCALATE_TO_HUMAN, route_to=Team.INCIDENT_RESPONSE)
    result, _ = engine.enforce(proposed, ctx(store, tickets["T-002"]))
    assert result.urgency == Urgency.CRITICAL


def test_auto_reply_still_sends_bug_and_feature_request_to_owners(store, tickets):
    proposed = make_result(kb_article_ids=["KB-008"], issue_types=[IssueType.BUG, IssueType.FEATURE_REQUEST],
                           primary_issue=IssueType.BUG)
    result, fired = engine.enforce(proposed, ctx(store, tickets["T-003"]))
    assert fired == ["follow_up_owners"]
    assert result.action == Action.AUTO_RESPOND
    assert result.follow_up_teams == [Team.ENGINEERING, Team.PRODUCT]


def test_hand_off_reply_with_refund_promise_is_replaced(store, tickets):
    proposed = make_result(primary_issue=IssueType.BILLING, issue_types=[IssueType.BILLING],
                           customer_reply="Billing will refund you and grant temporary Pro access.")
    result, fired = engine.enforce(proposed, ctx(store, tickets["T-001"]))
    assert fired[-1] == "no_promises_in_hand_off"
    assert "refund" not in result.customer_reply.lower() and "billing team" in result.customer_reply
    assert "Original draft" in result.internal_note


def test_holding_reply_uses_customer_language(store, tickets):
    proposed = make_result(primary_issue=IssueType.OUTAGE, issue_types=[IssueType.OUTAGE], language="th",
                           action=Action.ESCALATE_TO_HUMAN, route_to=Team.INCIDENT_RESPONSE,
                           customer_reply="เราจะคืนเงินให้")
    result, _ = engine.enforce(proposed, ctx(store, tickets["T-002"]))
    assert result.customer_reply.startswith("ขออภัย")


def test_holding_reply_without_promises_is_kept(store, tickets):
    proposed = make_result(primary_issue=IssueType.BILLING, issue_types=[IssueType.BILLING],
                           customer_reply="Our Billing team is looking at the charges now.")
    result, fired = engine.enforce(proposed, ctx(store, tickets["T-001"]))
    assert "no_promises_in_hand_off" not in fired
    assert result.customer_reply == proposed.customer_reply
