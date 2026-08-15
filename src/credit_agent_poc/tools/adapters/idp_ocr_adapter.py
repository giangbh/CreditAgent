from __future__ import annotations

from typing import Any

from .base_adapter import BaseBankAdapter


class IDPOCRAdapter(BaseBankAdapter):
    """Adapter trích xuất Báo cáo tài chính & Chứng từ doanh nghiệp via IDP/OCR."""

    system_code: str = "IDP_OCR_SERVICE"
    description: str = "Intelligent Document Processing & Financial OCR Engine"

    def extract_financial_statement(self, document_ref: str) -> dict[str, Any]:
        """Trích xuất dữ liệu Báo cáo Tài chính tự động."""
        return {
            "system": self.system_code,
            "document_ref": document_ref,
            "extracted_tables": ["BALANCE_SHEET", "INCOME_STATEMENT", "CASHFLOW_STATEMENT"],
            "confidence_score": 0.98,
            "status": "SUCCESS",
        }

    def query(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "extract_financial_statement":
            return self.extract_financial_statement(params.get("document_ref", ""))
        return {"status": "ERROR", "message": f"Unsupported action: {action}"}
