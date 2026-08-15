from __future__ import annotations

from typing import Any

from ...scenarios import Scenario


class IntakeToolsMixin:
    """Document, OCR and Intake tool handlers."""

    @staticmethod
    def _document_inventory(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        docs = ["application", "financial_statement", "bank_statement", "company_registration"]
        if not s.documents_complete:
            docs.remove("financial_statement")
        return {
            "documents": [
                {"document_id": f"DOC-{index + 1}", "document_type": name, "status": "VALID"}
                for index, name in enumerate(docs)
            ]
        }

    @staticmethod
    def _classify_document(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return {"document_id": args.get("document_id"), "classification": "CONFIRMED", "confidence": 0.99}

    @staticmethod
    def _extract_document_fields(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"borrower": s.borrower, "request": s.request, "declared_revenue": s.declared_revenue}

    @staticmethod
    def _parse_bank_statement(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_ref": f"artifact://{s.scenario_id}/transactions",
            "statement_months": s.statement_months,
            "reconciled": True,
        }

    @staticmethod
    def _resolve_borrower_identity(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"entity_id": s.borrower["entity_id"], "status": "MATCHED", "confidence": 1.0}

    @staticmethod
    def _validate_case_completeness(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        missing = [] if s.documents_complete else ["financial_statement"]
        if s.statement_months < 6:
            missing.append("minimum_6_month_bank_statement")
        return {"complete": not missing, "missing": missing}
