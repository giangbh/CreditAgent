from __future__ import annotations

from typing import Any
from ...scenarios import Scenario
from .scenario_data import ScenarioDataGenerator


class StructuringToolsMixin:
    """Policy rules, pricing, amortization and deal structuring tool handlers."""

    @staticmethod
    def _search_policy(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_search_policy(s, args)

    @staticmethod
    def _get_policy_clause(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_get_policy_clause(s, args)

    @staticmethod
    def _evaluate_policy_rule(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_evaluate_policy_rule(s, args)

    @staticmethod
    def _validate_policy_citation(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_validate_policy_citation(s, args)

    @staticmethod
    def _resolve_approval_authority(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_resolve_approval_authority(s, args)

    @staticmethod
    def _calculate_amortization(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_calculate_amortization(s, args)

    @staticmethod
    def _resolve_pricing_band(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_resolve_pricing_band(s, args)

    @staticmethod
    def _validate_deal_structure(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_validate_deal_structure(s, args)

    @staticmethod
    def _retrieve_approved_memory(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_retrieve_approved_memory(s, args)
