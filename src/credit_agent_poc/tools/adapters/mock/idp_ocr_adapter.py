from __future__ import annotations

from typing import Any
from ..base_adapter import BaseBankAdapter


class IDPOCRAdapter(BaseBankAdapter):
    """Adapter trích xuất tài liệu IDP/OCR (Mock)."""

    system_code: str = "IDP_OCR_ENGINE"
    description: str = "Enterprise Intelligent Document Processing & OCR Engine (Mock)"

    def extract_fields(self, document_id: str) -> dict[str, Any]:
        """Trích xuất các trường dữ liệu quan trọng từ tài liệu đã upload."""
        return {
            "system": self.system_code,
            "document_id": document_id,
            "ocr_confidence": 0.985,
            "status": "COMPLETED",
        }

    def query(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "extract_fields":
            return self.extract_fields(params.get("document_id", ""))
        return {"status": "ERROR", "message": f"Unsupported action: {action}"}
