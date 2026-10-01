from pydantic import BaseModel, Field

from triage.data_store import MockDataStore
from triage.tools.base import Tool


class CustomerHistoryParams(BaseModel):
    customer_id: str = Field(description="Customer ID from the ticket header, e.g. 'C-001'.")


class GetCustomerHistoryTool(Tool):
    name = "get_customer_history"
    description = (
        "Look up a customer's plan, tenure, seats, data region, previous tickets, subscription state "
        "and recent billing events. Call this first for every ticket."
    )
    Params = CustomerHistoryParams

    def __init__(self, store: MockDataStore):
        self._store = store

    def run(self, params: CustomerHistoryParams) -> dict:
        customer = self._store.get_customer(params.customer_id)
        if customer is None:
            return {"error": f"Customer {params.customer_id} not found"}
        return customer.model_dump()
