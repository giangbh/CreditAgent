from __future__ import annotations

from typing import Any, Optional
from ....config import CONFIG
from ....scenarios import Scenario
from .base_production_adapter import BaseProductionHTTPAdapter


class ProductionLOSStructuringAdapter(BaseProductionHTTPAdapter):
    """Adapter kết nối LOS (Loan Originating System) & Pricing/Amortization Engine thực tế."""

    system_code: str = "LOS_STRUCTURING"
    description: str = "Loan Originating System & Pricing/Amortization Adapter"

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        super().__init__(
            endpoint_url=endpoint_url or CONFIG.LOS_STRUCTURING_ENDPOINT_URL,
            api_key=api_key or CONFIG.BACKEND_API_KEY,
            timeout_sec=CONFIG.BACKEND_TIMEOUT_SEC,
        )

    def calculate_amortization(self, amount: float, tenor_months: int) -> dict[str, Any]:
        """Tính lịch trả nợ gốc/lãi theo tenor và phương thức vay."""
        return self._post("/pricing/calculate-amortization", {"amount": amount, "tenor_months": tenor_months})

    def resolve_pricing_band(self, scenario: Scenario) -> dict[str, Any]:
        """Xác định khung lãi suất & phí áp dụng theo phân hạng rủi ro."""
        return self._post("/pricing/resolve-band", {"scenario_id": scenario.scenario_id})

    def validate_deal_structure(self, scenario: Scenario, arguments: dict[str, Any]) -> dict[str, Any]:
        """Kiểm tra tính hợp lệ của cấu trúc đề xuất vay."""
        return self._post("/deal/validate-structure", {"scenario_id": scenario.scenario_id, "arguments": arguments})

    def retrieve_approved_memory(self, scenario: Scenario) -> dict[str, Any]:
        """Truy vấn lịch sử các ngoại lệ / quyết định tín dụng tương tự đã duyệt."""
        return self._post("/memory/retrieve-approved", {"industry": scenario.borrower.get("industry")})
