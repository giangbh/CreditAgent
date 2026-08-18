from __future__ import annotations

from typing import Any
from ...scenarios import Scenario
from .scenario_data import ScenarioDataGenerator


class IntakeToolsMixin:
    """Document, OCR and Intake tool handlers."""

    @staticmethod
    def _document_inventory(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_document_inventory(s, args)

    @staticmethod
    def _classify_document(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_classify_document(s, args)

    @staticmethod
    def _extract_document_fields(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_extract_document_fields(s, args)

    @staticmethod
    def _parse_bank_statement(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_parse_bank_statement(s, args)

    @staticmethod
    def _resolve_borrower_identity(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_resolve_borrower_identity(s, args)

    @staticmethod
    def _validate_case_completeness(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_validate_case_completeness(s, args)
