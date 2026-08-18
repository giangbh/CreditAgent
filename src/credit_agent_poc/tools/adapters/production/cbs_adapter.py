from __future__ import annotations

from typing import Any, Optional
from ....config import CONFIG
from .base_production_adapter import BaseProductionHTTPAdapter


class ProductionCoreBankingAdapter(BaseProductionHTTPAdapter):
    """Adapter kết nối trực tiếp hệ thống Core Banking (CBS) thực tế qua REST API."""

    system_code: str = "CORE_BANKING_CBS"
    description: str = "Enterprise Core Banking System (CBS) Production Adapter"

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        super().__init__(
            endpoint_url=endpoint_url or CONFIG.CBS_ENDPOINT_URL,
            api_key=api_key or CONFIG.BACKEND_API_KEY,
            timeout_sec=CONFIG.BACKEND_TIMEOUT_SEC,
        )

    def resolve_borrower_identity(self, borrower: dict[str, Any]) -> dict[str, Any]:
        """Tra cứu đối soát danh tính CIF khách hàng vay từ CBS."""
        return self._post("/cif/resolve-identity", {"borrower": borrower})

    def query_transactions(self, scenario_id: str, limit: int = 50) -> dict[str, Any]:
        """Truy vấn dữ liệu giao dịch chi tiết từ CBS Ledger."""
        return self._post("/transactions/query", {"scenario_id": scenario_id, "limit": limit})
