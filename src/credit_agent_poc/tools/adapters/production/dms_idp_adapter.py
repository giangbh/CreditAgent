from __future__ import annotations

from typing import Any, Optional
from ....config import CONFIG
from ....scenarios import Scenario
from .base_production_adapter import BaseProductionHTTPAdapter


class ProductionIDPOCREngineAdapter(BaseProductionHTTPAdapter):
    """Adapter kết nối trực tiếp hệ thống Quản lý Tài liệu & IDP/OCR Engine thực tế."""

    system_code: str = "DMS_IDP_OCR"
    description: str = "Enterprise DMS & IDP/OCR Engine Production Adapter"

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        super().__init__(
            endpoint_url=endpoint_url or CONFIG.DMS_OCR_ENDPOINT_URL,
            api_key=api_key or CONFIG.BACKEND_API_KEY,
            timeout_sec=CONFIG.BACKEND_TIMEOUT_SEC,
        )

    def document_inventory(self, scenario: Scenario) -> dict[str, Any]:
        """Lấy danh mục tất cả tài liệu chứng từ trong hồ sơ từ DMS."""
        return self._post("/documents/inventory", {"scenario_id": scenario.scenario_id, "borrower_id": scenario.borrower.get("entity_id")})

    def classify_document(self, document_id: str) -> dict[str, Any]:
        """Phân loại tài liệu bằng IDP OCR Engine."""
        return self._post("/ocr/classify", {"document_id": document_id})

    def extract_document_fields(self, document_id: str, scenario: Scenario) -> dict[str, Any]:
        """Trích xuất các trường dữ liệu quan trọng (Doanh thu, BCTC, MST)."""
        return self._post("/ocr/extract-fields", {"document_id": document_id, "scenario_id": scenario.scenario_id})

    def parse_bank_statement(self, scenario: Scenario) -> dict[str, Any]:
        """Bóc tách cấu trúc file sao kê ngân hàng & cân đối số dư."""
        return self._post("/ocr/parse-statement", {"scenario_id": scenario.scenario_id, "months": scenario.statement_months})

    def validate_case_completeness(self, scenario: Scenario) -> dict[str, Any]:
        """Kiểm tra tính đầy đủ của bộ hồ sơ tín dụng từ LOS/DMS."""
        return self._post("/case/validate-completeness", {"scenario_id": scenario.scenario_id})
