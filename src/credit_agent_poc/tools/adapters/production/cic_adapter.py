from __future__ import annotations

from typing import Any, Optional
from ....config import CONFIG
from .base_production_adapter import BaseProductionHTTPAdapter


class ProductionCICAdapter(BaseProductionHTTPAdapter):
    """Adapter kết nối Trung tâm Thông tin Tín dụng NHNN (CIC)."""

    system_code: str = "CIC_SBV"
    description: str = "National Credit Information Center of Vietnam (CIC) Production Adapter"

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        super().__init__(
            endpoint_url=endpoint_url or CONFIG.CIC_ENDPOINT_URL,
            api_key=api_key or CONFIG.BACKEND_API_KEY,
            timeout_sec=CONFIG.BACKEND_TIMEOUT_SEC,
        )

    def query_credit_score(self, tax_id_or_identity: str) -> dict[str, Any]:
        """Tra cứu điểm tín dụng & nhóm nợ xấu CIC."""
        return self._post("/credit-report/query", {"identity": tax_id_or_identity})
