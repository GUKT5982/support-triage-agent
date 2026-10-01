import json

from triage.tools import ToolRegistry, default_tools


def run(store, name, **args):
    return ToolRegistry(default_tools(store)).execute(name, json.dumps(args))


def test_customer_history_returns_billing_events(store):
    out = run(store, "get_customer_history", customer_id="C-001")
    assert out["plan"] == "free"
    assert sum(e["status"] == "pending" for e in out["billing_events"]) == 3


def test_customer_history_unknown_customer(store):
    assert "error" in run(store, "get_customer_history", customer_id="C-999")


def test_kb_search_finds_duplicate_charge_article(store):
    ids = [r["id"] for r in run(store, "search_knowledge_base", query="pending duplicate charges refund")["results"]]
    assert "KB-002" in ids


def test_kb_search_finds_known_macos_dark_mode_bug(store):
    ids = [r["id"] for r in run(store, "search_knowledge_base", query="macOS system dark mode not working")["results"]]
    assert ids[0] == "KB-008"


def test_status_detects_mismatch_in_asia(store):
    out = run(store, "check_service_status", region="Asia")
    assert out["region"] == "ap-southeast"
    assert out["anomaly_detected"] and out["status_page_mismatch"]


def test_status_healthy_region(store):
    assert run(store, "check_service_status", region="us-east")["anomaly_detected"] is False


def test_registry_returns_errors_instead_of_raising(store):
    registry = ToolRegistry(default_tools(store))
    assert "error" in registry.execute("nope", "{}")
    assert "error" in registry.execute("search_knowledge_base", "not json")
    assert "error" in registry.execute("search_knowledge_base", json.dumps({"top_k": 3}))  # missing query


def test_schemas_are_self_contained(store):
    for schema in ToolRegistry(default_tools(store)).openai_schemas():
        assert "$ref" not in json.dumps(schema)
