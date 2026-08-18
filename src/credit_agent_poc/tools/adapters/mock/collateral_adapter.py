from __future__ import annotations

from typing import Any
from ..base_adapter import BaseBankAdapter


class CollateralAdapter(BaseBankAdapter):
    """Adapter truy vấn Hệ thống Định giá & Quản lý Tài sản Bảo đảm (Mock)."""

    system_code: str = "COLLATERAL_VALUATION"
    description: str = "Enterprise Collateral Valuation & LTV System Adapter"

    def assess_collateral_value(self, collateral_id: str) -> dict[str, Any]:
        """Tra cứu giá trị định giá tài sản bảo đảm & LTV tối đa."""
        return {
            "system": self.system_code,
            "collateral_id": collateral_id,
            "valuation_amount": 2_800_000_000,
            "asset_type": "REAL_ESTATE",
            "max_ltv": 0.70,
            "status": "VALIDATED",
        }

    def query(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "assess_collateral_value":
            return self.assess_collateral_value(params.get("collateral_id", ""))
        return {"status": "ERROR", "message": f"Unsupported action: {action}"}
