from __future__ import annotations

from typing import Any
from ...scenarios import Scenario
from .scenario_data import ScenarioDataGenerator


class FinancialToolsMixin:
    """Cashflow metrics and capacity assessment tool handlers."""

    @staticmethod
    def _query_transactions(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_query_transactions(s, args)

    @staticmethod
    def _compute_cashflow_metrics(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_compute_cashflow_metrics(s, args)

    @staticmethod
    def _detect_cashflow_anomalies(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_detect_cashflow_anomalies(s, args)

    @staticmethod
    def _reconcile_declared_revenue(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_reconcile_declared_revenue(s, args)

    @staticmethod
    def _calculate_credit_capacity(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_calculate_credit_capacity(s, args)

    @staticmethod
    def _stress_repayment_capacity(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_stress_repayment_capacity(s, args)

    @staticmethod
    def _assess_refinancing_pattern(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_assess_refinancing_pattern(s, args)
