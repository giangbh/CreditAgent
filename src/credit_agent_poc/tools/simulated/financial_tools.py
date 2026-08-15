from __future__ import annotations

from typing import Any

from ...scenarios import Scenario


class FinancialToolsMixin:
    """Cashflow metrics and capacity assessment tool handlers."""

    @staticmethod
    def _query_transactions(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_ref": f"artifact://{s.scenario_id}/transaction-query",
            "record_count": s.statement_months * 120,
            "coverage_months": s.statement_months,
        }

    @staticmethod
    def _compute_cashflow_metrics(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "metric_id": f"METRIC-CASH-{s.scenario_id}",
            "observed_inflow": s.observed_inflow,
            "inflow_concentration": s.inflow_concentration,
            "coverage_months": s.statement_months,
        }

    @staticmethod
    def _detect_cashflow_anomalies(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "anomalies": ["high_customer_concentration"] if s.inflow_concentration >= 0.45 else [],
            "evidence_id": f"EVD-CASH-{s.scenario_id}",
        }

    @staticmethod
    def _reconcile_declared_revenue(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        ratio = s.observed_inflow / s.declared_revenue if s.declared_revenue else 0
        return {"calculation_ref": f"CALC-REV-{s.scenario_id}", "match_ratio": round(ratio, 4)}

    @staticmethod
    def _calculate_credit_capacity(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        supported_amount = s.request["amount"] if s.dscr >= 1.2 else max(0, int(s.request["amount"] * s.dscr / 1.2))
        return {
            "calculation_ref": f"CALC-CAP-{s.scenario_id}",
            "dscr": s.dscr,
            "supported_amount": supported_amount,
            "primary_repayment_viable": s.dscr >= 1.2 and s.statement_months >= 6,
        }

    @staticmethod
    def _stress_repayment_capacity(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        stressed = round(s.dscr * 0.78, 2)
        return {"calculation_ref": f"CALC-STRESS-{s.scenario_id}", "stressed_dscr": stressed, "passes": stressed >= 1.0}

    @staticmethod
    def _assess_refinancing_pattern(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"finding": "NONE_DETECTED", "evidence_id": f"EVD-REFI-{s.scenario_id}"}
