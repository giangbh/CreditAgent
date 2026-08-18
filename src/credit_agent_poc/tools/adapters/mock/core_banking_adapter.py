from __future__ import annotations

from typing import Any
from ..base_adapter import BaseBankAdapter


class CoreBankingAdapter(BaseBankAdapter):
    """Adapter truy vấn Core Banking System (Mock)."""

    system_code: str = "CORE_BANKING"
    description: str = "Enterprise Core Banking Real-time API Adapter (Mock)"

    def fetch_account_statement(self, account_number: str, months: int = 6) -> dict[str, Any]:
        """Truy vấn lịch sử giao dịch & sao kê dòng tiền thực tế."""
        return {
            "system": self.system_code,
            "account_number": account_number,
            "coverage_months": months,
            "currency": "VND",
            "status": "SUCCESS",
        }

    def query(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "fetch_account_statement":
            return self.fetch_account_statement(params.get("account_number", ""), params.get("months", 6))
        return {"status": "ERROR", "message": f"Unsupported action: {action}"}
