"""Domain models shared by the agent, tools and guardrails."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return _URGENCY_RANK[self]

    def at_least(self, floor: "Urgency") -> "Urgency":
        """Return the higher of self and floor (urgency can be raised, never lowered)."""
        return self if self.rank >= floor.rank else floor


_URGENCY_RANK = {Urgency.LOW: 0, Urgency.MEDIUM: 1, Urgency.HIGH: 2, Urgency.CRITICAL: 3}


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"


class IssueType(str, Enum):
    BILLING = "billing"
    OUTAGE = "outage"
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    HOW_TO = "how_to"
    ACCOUNT = "account"
    OTHER = "other"


class Action(str, Enum):
    AUTO_RESPOND = "auto_respond"
    ROUTE_TO_SPECIALIST = "route_to_specialist"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class Team(str, Enum):
    BILLING = "billing"
    TECHNICAL_SUPPORT = "technical_support"
    ENGINEERING = "engineering"
    INCIDENT_RESPONSE = "incident_response"
    PRODUCT = "product"
    CUSTOMER_SUCCESS = "customer_success"


# ---------- Input ----------

class Message(BaseModel):
    sent_at: str
    text: str


class Ticket(BaseModel):
    id: str
    customer_id: str
    channel: str = "email"
    messages: list[Message] = Field(min_length=1)

    @property
    def full_text(self) -> str:
        return "\n".join(m.text for m in self.messages)


class Customer(BaseModel):
    model_config = ConfigDict(extra="allow")  # CRM records carry more fields than we model

    id: str
    name: str
    plan: str
    tenure_months: int
    seats: int = 1
    region: str
    data_region: str
    previous_tickets: int = 0
    billing_events: list[dict] = Field(default_factory=list)


# ---------- Output ----------

class TriageResult(BaseModel):
    """Final decision. Its JSON schema is also the parameter schema of the `submit_triage` tool."""

    urgency: Urgency
    urgency_reason: str = Field(description="One sentence explaining the urgency level.")
    product_area: str = Field(description="Product area affected, e.g. 'billing/upgrade', 'web app', 'desktop app appearance'.")
    primary_issue: IssueType
    issue_types: list[IssueType] = Field(min_length=1, description="All issue types in the ticket, including the primary one.")
    sentiment: Sentiment
    language: str = Field(description="ISO 639-1 code of the customer's language, e.g. 'en', 'th'.")
    summary: str = Field(description="2-3 sentence summary of the whole thread for the agent who picks it up.")
    key_facts: list[str] = Field(description="Concrete facts: amounts, error codes, deadlines, affected users, versions.")
    kb_article_ids: list[str] = Field(default_factory=list, description="IDs of knowledge base articles used.")
    action: Action
    route_to: Team | None = Field(default=None, description="Required unless action is auto_respond.")
    follow_up_teams: list[Team] = Field(
        default_factory=list,
        description="Teams that must still act on part of the ticket (e.g. engineering for a bug, product for a "
                    "feature request), even when the customer reply is automatic.",
    )
    action_reason: str
    customer_reply: str = Field(description="Reply to send (auto_respond) or holding reply (otherwise), in the customer's language.")
    internal_note: str = Field(description="Note for the receiving team: what was checked, what to do next.")
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _route_required_when_handing_off(self) -> "TriageResult":
        if self.action != Action.AUTO_RESPOND and self.route_to is None:
            raise ValueError("route_to is required when action is route_to_specialist or escalate_to_human")
        if self.primary_issue not in self.issue_types:
            self.issue_types = [self.primary_issue, *self.issue_types]
        return self
