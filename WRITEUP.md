# Write-up

## Architecture decisions

- **Single agent + tool-calling loop, not multi-agent or a graph framework.** Triage is one decision
  over a small toolset; one loop is easier to read, debug and test. LangGraph would be worth it once
  there are branching workflows (e.g. auto-refund approval, human-in-the-loop resume).
- **Structured output via a `submit_triage` tool** whose schema is the Pydantic `TriageResult`.
  `tool_choice="required"` means no free text; validation errors are fed back so the model
  self-corrects. One model defines the output contract, the tool schema and validation.
- **LLM proposes, rules decide.** Judgement (sentiment, mixed intents, language, reply drafting) is
  left to the model; non-negotiable policy (money at risk → Billing, enterprise outage → Incident
  Response, no ungrounded auto-replies) is deterministic and unit-tested. Rules can only escalate.
- **Tools check facts the customer can't see**: CRM billing events (3 pending charges + stuck
  provisioning) and internal regional monitoring (status page says OK, ap-southeast has 42% 5xx).
- **Dependency injection** (`ChatClient`, `MockDataStore`, `ToolRegistry`, rule list) so every part is
  swappable and the whole loop is tested offline with a scripted fake LLM.

## What could go wrong → mitigation

| Risk | Mitigation |
|---|---|
| Under-classifying a critical ticket | Guardrail floors; urgency can only go up; eval tracks critical recall separately |
| Bot promises refunds/credits on a team's behalf (seen in a real run) | Hand-off replies scanned; a promise is replaced by a holding reply, original kept in the note |
| Hallucinated policy | Unknown KB ids removed; auto-reply requires a KB citation |
| Auto-reply says "we logged it" but nobody owns it | Bugs → Engineering, feature requests → Product as `follow_up_teams`, enforced by a rule |
| Model misreads data (read 0.42 as 0.42%) | Tool outputs carry explicit units (`http_5xx_rate_pct`) |
| Prompt injection in ticket text | Ticket wrapped as data; read-only tools; final routing enforced by rules, not the model |
| Invalid / missing output, API timeout | Schema validation + retry; SDK retries; fallback = escalate to human |
| Bad key / model name | Fails fast with a clear message; never mass-escalates tickets |
| Status page or KB is stale (T-002, T-003) | Monitoring tool beats status page; prompt asks to flag KB contradictions internally |
| Wrong language reply | Language extracted; reply-language check in eval; Thai prompt examples if needed |
| Cost / latency | Max steps cap; small model by default; one KB search per issue |

## How I'd evaluate in production

1. **Offline golden set** from historical tickets labelled by senior agents (incl. Thai and mixed-
   intent threads). Per-field accuracy; **critical recall** is the headline metric because a missed
   critical costs far more than an over-escalation. Run each ticket several times for consistency.
2. **Shadow mode** first: the agent triages in parallel with humans; measure agreement before it
   acts.
3. **Online metrics**: human override rate by field, re-open rate and CSAT for auto-responses,
   time-to-first-response for critical tickets, guardrail fire rate (high = prompt needs work).
4. **Reply quality**: LLM-as-judge rubric (accurate to KB, answers every question, tone, language)
   calibrated against a human-scored sample.
5. **Regression gate**: prompt, model or rule changes must pass the golden set in CI before deploy.
