from pydantic import BaseModel, Field

from triage.data_store import MockDataStore
from triage.tools.base import Tool

ERROR_RATE_ANOMALY_THRESHOLD = 0.05  # >5% HTTP 5xx = something is wrong regardless of the status page


class ServiceStatusParams(BaseModel):
    region: str = Field(description="Data region (e.g. 'ap-southeast') or a common name like 'Asia', 'TH', 'EU'.")


class CheckServiceStatusTool(Tool):
    name = "check_service_status"
    description = (
        "Check a region's health using INTERNAL monitoring (5xx error rate, latency, open incidents) and compare "
        "it to the public status page. Use for any report of errors, downtime or access problems."
    )
    Params = ServiceStatusParams

    def __init__(self, store: MockDataStore):
        self._store = store

    def run(self, params: ServiceStatusParams) -> dict:
        status = self._store.service_status
        key = params.region.strip().lower()
        region = status["region_aliases"].get(key, key)
        data = status["regions"].get(region)
        if data is None:
            return {"error": f"Unknown region '{params.region}'. Known: {sorted(status['regions'])}"}

        anomaly = data["monitoring"]["http_5xx_rate"] > ERROR_RATE_ANOMALY_THRESHOLD
        return {
            "region": region,
            "public_status_page": status["public_status_page"]["overall"],
            "public_region_status": data["public_status"],
            "monitoring": data["monitoring"],
            "open_incidents": data["open_incidents"],
            "anomaly_detected": anomaly,
            "status_page_mismatch": anomaly and data["public_status"] == "operational",
        }
