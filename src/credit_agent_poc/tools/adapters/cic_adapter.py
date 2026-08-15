from __future__ import annotations

from typing import Any

from .base_adapter import BaseBankAdapter


class CICAdapter(BaseBankAdapter):
    """Adapter tra cứu Trung tâm Thông tin Tín dụng NHNN (CIC)."""

    system_code: str = "CIC_SBV"
    description: str = "National Credit Information Center of Vietnam (CIC) Adapter"

    def query_credit_score(self, tax_id_or_identity: str) -> dict[str, Any]:
        """Tra cứu điểm tín dụng & nhóm nợ xấu CIC."""
        return {
            "system": self.system_code,
            "query_target": tax_id_or_identity,
            "credit_score": 750,
            "debt_group": "NHOM_1_DU_NO_CHUAN",
            "active_contracts": 2,
            "status": "SUCCESS",
        }

    def query(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "query_credit_score":
            return self.query_credit_score(params.get("identity", ""))
        return {"status": "ERROR", "message": f"Unsupported action: {action}"}
