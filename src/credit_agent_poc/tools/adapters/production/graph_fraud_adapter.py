from __future__ import annotations

from typing import Any, Optional
from ....config import CONFIG
from ....scenarios import Scenario
from .base_production_adapter import BaseProductionHTTPAdapter


class ProductionGraphFraudAdapter(BaseProductionHTTPAdapter):
    """Adapter kết nối Graph DB (Neo4j/Memgraph) & Anti-Fraud Engine thực tế."""

    system_code: str = "GRAPH_ANTI_FRAUD"
    description: str = "Graph Database & Anti-Fraud Real-time Analytics Adapter"

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        super().__init__(
            endpoint_url=endpoint_url or CONFIG.GRAPH_FRAUD_ENDPOINT_URL,
            api_key=api_key or CONFIG.BACKEND_API_KEY,
            timeout_sec=CONFIG.BACKEND_TIMEOUT_SEC,
        )

    def build_entity_transaction_graph(self, scenario: Scenario) -> dict[str, Any]:
        """Xây dựng đồ thị giao dịch liên kết bên vay & các bên liên quan."""
        return self._post("/graph/build", {"scenario_id": scenario.scenario_id, "entity_id": scenario.borrower.get("entity_id")})

    def detect_transaction_cycles(self, scenario: Scenario) -> dict[str, Any]:
        """Quét và tính điểm rủi ro dòng tiền vòng tròn (Circular funds score)."""
        return self._post("/graph/detect-cycles", {"scenario_id": scenario.scenario_id})

    def trace_funds(self, scenario: Scenario) -> dict[str, Any]:
        """Truy vết đường đi vật lý của các dòng tiền lớn qua các tài khoản."""
        return self._post("/graph/trace-funds", {"scenario_id": scenario.scenario_id})
