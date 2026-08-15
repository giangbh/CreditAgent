from __future__ import annotations

from typing import Any

from ...models import ToolExecutionError
from ...scenarios import Scenario

from .financial_tools import FinancialToolsMixin
from .intake_tools import IntakeToolsMixin
from .integrity_tools import IntegrityToolsMixin
from .structuring_tools import StructuringToolsMixin


class SimulatedBackend(
    IntakeToolsMixin,
    FinancialToolsMixin,
    IntegrityToolsMixin,
    StructuringToolsMixin,
):
    """Deterministic stand-in for document, transaction, policy and LOS backends."""

    def execute(self, tool_name: str, scenario: Scenario, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name in scenario.forced_tool_failures:
            raise ToolExecutionError(f"simulated backend failure: {tool_name}")

        handlers = {
            "document_inventory": self._document_inventory,
            "classify_document": self._classify_document,
            "extract_document_fields": self._extract_document_fields,
            "parse_bank_statement": self._parse_bank_statement,
            "resolve_borrower_identity": self._resolve_borrower_identity,
            "validate_case_completeness": self._validate_case_completeness,
            "query_transactions": self._query_transactions,
            "compute_cashflow_metrics": self._compute_cashflow_metrics,
            "detect_cashflow_anomalies": self._detect_cashflow_anomalies,
            "build_entity_transaction_graph": self._build_entity_transaction_graph,
            "detect_transaction_cycles": self._detect_transaction_cycles,
            "trace_funds": self._trace_funds,
            "reconcile_declared_revenue": self._reconcile_declared_revenue,
            "calculate_credit_capacity": self._calculate_credit_capacity,
            "stress_repayment_capacity": self._stress_repayment_capacity,
            "assess_refinancing_pattern": self._assess_refinancing_pattern,
            "search_policy": self._search_policy,
            "get_policy_clause": self._get_policy_clause,
            "evaluate_policy_rule": self._evaluate_policy_rule,
            "validate_policy_citation": self._validate_policy_citation,
            "resolve_approval_authority": self._resolve_approval_authority,
            "calculate_amortization": self._calculate_amortization,
            "resolve_pricing_band": self._resolve_pricing_band,
            "validate_deal_structure": self._validate_deal_structure,
            "retrieve_approved_memory": self._retrieve_approved_memory,
        }
        if tool_name not in handlers:
            raise ToolExecutionError(f"unknown tool: {tool_name}")
        return handlers[tool_name](scenario, arguments)
