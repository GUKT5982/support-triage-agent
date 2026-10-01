from triage.data_store import MockDataStore
from triage.tools.base import Tool, ToolRegistry
from triage.tools.customer_history import GetCustomerHistoryTool
from triage.tools.knowledge_base import SearchKnowledgeBaseTool
from triage.tools.service_status import CheckServiceStatusTool


def default_tools(store: MockDataStore) -> list[Tool]:
    """Add a new tool here: subclass Tool, then append it to this list."""
    return [
        GetCustomerHistoryTool(store),
        SearchKnowledgeBaseTool(store),
        CheckServiceStatusTool(store),
    ]


__all__ = ["Tool", "ToolRegistry", "default_tools"]
