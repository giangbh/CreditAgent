from __future__ import annotations

from typing import Any

from .base_adapter import BaseBankAdapter


class CollateralAdapter(BaseBankAdapter):
    """Adapter Tra cứu & Định giá Tài sản Bảo đảm (TSBĐ)."""

    system_code: str = "COLLATERAL_VALUATION"
    description: str = "Collateral Valuation & Asset Registry Service Adapter"

    def valuate_asset(self, asset_id: str, asset_type: str) -> dict[str, Any]:
        """Định giá tài sản bảo đảm (Bất động sản / Động sản / Giấy tờ có giá)."""
        return {
            "system": self.system_code,
            "asset_id": asset_id,
            "asset_type": asset_type,
            "valuation_value_vnd": 15000000000,
            "ltv_max_ratio": 0.70,
            "status": "SUCCESS",
        }

    def query(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "valuate_asset":
            return self.valuate_asset(params.get("asset_id", ""), params.get("asset_type", "REAL_ESTATE"))
        return {"status": "ERROR", "message": f"Unsupported action: {action}"}
