from triage.models import Action, IssueType, Sentiment, Team, TriageResult, Urgency


def make_result(**overrides) -> TriageResult:
    base = dict(
        urgency=Urgency.LOW, urgency_reason="r", product_area="app", primary_issue=IssueType.HOW_TO,
        issue_types=[IssueType.HOW_TO], sentiment=Sentiment.NEUTRAL, language="en", summary="s",
        key_facts=[], kb_article_ids=["KB-007"], action=Action.AUTO_RESPOND, route_to=None,
        action_reason="a", customer_reply="hi", internal_note="", confidence=0.9,
    )
    base.update(overrides)
    if base["action"] != Action.AUTO_RESPOND and base["route_to"] is None:
        base["route_to"] = Team.TECHNICAL_SUPPORT
    return TriageResult(**base)
