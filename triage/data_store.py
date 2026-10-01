"""Read-only access to mock data. Swap this class for real CRM / KB / monitoring clients."""

import json
from functools import cached_property
from pathlib import Path

from triage.models import Customer, Ticket


class MockDataStore:
    def __init__(self, data_dir: Path):
        self._dir = Path(data_dir)

    def _load(self, filename: str):
        with open(self._dir / filename, encoding="utf-8") as f:
            return json.load(f)

    @cached_property
    def customers(self) -> dict[str, Customer]:
        return {c["id"]: Customer(**c) for c in self._load("customers.json")}

    @cached_property
    def knowledge_base(self) -> list[dict]:
        return self._load("knowledge_base.json")

    @cached_property
    def service_status(self) -> dict:
        return self._load("service_status.json")

    @cached_property
    def sample_tickets(self) -> list[Ticket]:
        return [Ticket(**t) for t in self._load("tickets.json")]

    def get_customer(self, customer_id: str) -> Customer | None:
        return self.customers.get(customer_id)

    @property
    def kb_ids(self) -> frozenset[str]:
        return frozenset(a["id"] for a in self.knowledge_base)
