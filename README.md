# Support Ticket Triage Agent

An LLM agent (OpenAI tool calling) that triages support tickets: classifies urgency, extracts
key information, searches a knowledge base, and decides whether to auto-respond, route to a
specialist, or escalate to a human. Deterministic guardrails enforce business policy on top of
the model's decision.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then put your key in OPENAI_API_KEY
```

Run the three sample tickets:

```bash
python -m triage                 # all sample tickets, human-readable
python -m triage --ticket T-002  # one ticket
python -m triage --trace         # also show every tool call
python -m triage --json          # machine-readable output
python -m triage --file my_ticket.json   # your own ticket(s), same shape as data/tickets.json
```

Tests (offline, no API key; the LLM is replaced by a scripted fake):

```bash
pytest
```

Evaluation against labelled expectations (uses the real model):

```bash
python -m evals.run_eval --runs 3
```

### Configuration (`.env`)

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | - | required for `triage` and `evals` |
| `TRIAGE_MODEL` | `gpt-4.1-mini` | any chat model with tool calling |
| `TRIAGE_TEMPERATURE` | `0` | leave empty for models that don't accept temperature |
| `TRIAGE_MAX_STEPS` | `6` | max LLM turns before falling back to a human |
| `TRIAGE_CONFIDENCE_THRESHOLD` | `0.7` | below this, auto-responses go to a human |

## How it works

```
ticket ──► TriageAgent loop ──────────────────────────────► GuardrailEngine ──► TriageOutcome
            │  LLM chooses tools (tool_choice=required)        deterministic rules:
            │   • get_customer_history                         money at risk, enterprise outage,
            │   • search_knowledge_base                        unknown KB ids, ungrounded reply,
            │   • check_service_status                         low confidence, angry ≠ low
            └─ submit_triage(TriageResult)  ◄── schema-validated; errors fed back to the model
```

1. The ticket thread is rendered as data (inside `<ticket_messages>`) after the system prompt.
2. The model must call a tool every turn and finishes by calling `submit_triage`, whose
   parameters are the JSON schema of the Pydantic `TriageResult` model.
3. Invalid submissions are returned to the model with the validation error so it can fix them.
4. If the model never submits, or the API fails, a safe fallback escalates the ticket to a human.
5. Guardrails apply policy that must not depend on the model. Rules can only make a decision safer
   (raise urgency or hand off to a human). Both the model's proposal and the final result are kept,
   so you can measure how often guardrails had to intervene.

## Project structure

```
triage/
  agent.py            agent loop, submit tool, fallback
  guardrails.py       post-LLM business rules
  models.py           Pydantic domain + output models (single source of truth for schemas)
  llm.py              ChatClient protocol + OpenAI adapter
  tools/              one file per tool; base.py has Tool + ToolRegistry
  prompts/system_prompt.md
  data_store.py       mock CRM / KB / monitoring (JSON in data/)
  factory.py          wires everything together
  cli.py              terminal interface
data/                 sample tickets, customers, knowledge base, service status
evals/                expected labels + eval runner
tests/                offline unit tests (tools, guardrails, agent loop)
WRITEUP.md            architecture decisions, risks, evaluation plan
```

## Extending

- **New tool**: create `triage/tools/my_tool.py` with a `Params` Pydantic model and a `run()`
  method, then add it to `default_tools()` in `triage/tools/__init__.py`. The schema sent to the
  model is generated from `Params`.
- **New policy rule**: add a class with `name` and `apply(result, ctx)` in `guardrails.py`, then
  add it to `default_rules()`.
- **Real backends**: replace `MockDataStore` (or individual tools) with CRM / vector search /
  monitoring clients; the agent does not change.
- **Another LLM vendor**: implement `ChatClient.complete()` in `llm.py`.
- **API instead of CLI**: wrap `build_agent(...)[0].triage(ticket)` in a FastAPI endpoint.

## Sample tickets: expected behaviour

| Ticket | Expected | Why |
|---|---|---|
| T-001 Free plan, 3 pending charges | critical, escalate to Billing | money taken, Pro not provisioned, 2-hour deadline, dispute threat |
| T-002 Enterprise TH, HTTP 500 | critical, escalate to Incident Response, reply in Thai | whole org down; status page says OK but `check_service_status` shows 42% 5xx in ap-southeast |
| T-003 Pro, dark mode | low, auto-respond with KB-008 workaround (or route), log feature request | known macOS app bug; earlier support reply was misleading; scheduling is a feature request |
