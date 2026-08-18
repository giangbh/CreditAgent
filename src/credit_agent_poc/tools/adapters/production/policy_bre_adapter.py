from __future__ import annotations

from typing import Any, Optional
from ....config import CONFIG
from ....scenarios import Scenario
from .base_production_adapter import BaseProductionHTTPAdapter


class ProductionPolicyBREAdapter(BaseProductionHTTPAdapter):
    """Adapter kết nối Vector DB (Policy RAG) & Business Rule Engine (BRE) thực tế."""

    system_code: str = "POLICY_BRE"
    description: str = "Enterprise Policy Vector RAG & Business Rule Engine Adapter"

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        super().__init__(
            endpoint_url=endpoint_url or CONFIG.POLICY_BRE_ENDPOINT_URL,
            api_key=api_key or CONFIG.BACKEND_API_KEY,
            timeout_sec=CONFIG.BACKEND_TIMEOUT_SEC,
        )

    def search_policy(self, query: str) -> dict[str, Any]:
        """Tìm kiếm văn bản chính sách tín dụng bằng RAG Vector Search."""
        return self._post("/policy/search", {"query": query})

    def get_policy_clause(self, clause_id: str) -> dict[str, Any]:
        """Trích xuất chi tiết điều khoản chính sách tín dụng."""
        return self._post("/policy/clause", {"clause_id": clause_id})

    def evaluate_policy_rule(self, scenario: Scenario) -> dict[str, Any]:
        """Đánh giá quy tắc tuân thủ tín dụng qua BRE Rule Engine."""
        return self._post("/bre/evaluate-rule", {"scenario_id": scenario.scenario_id})

    def validate_policy_citation(self, citation_id: str) -> dict[str, Any]:
        """Kiểm tra tính hiệu lực và trích dẫn văn bản pháp lý."""
        return self._post("/policy/validate-citation", {"policy_citation_id": citation_id})

    def resolve_approval_authority(self, scenario: Scenario) -> dict[str, Any]:
        """Xác định cấp phê duyệt có thẩm quyền từ Ma trận Phân cấp Hạn mức."""
        return self._post("/authority/resolve", {"scenario_id": scenario.scenario_id})
