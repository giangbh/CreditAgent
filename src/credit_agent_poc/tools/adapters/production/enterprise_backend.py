from __future__ import annotations

from typing import Any
from ....models import ToolExecutionError
from ....scenarios import Scenario
from .cbs_adapter import ProductionCoreBankingAdapter
from .dms_idp_adapter import ProductionIDPOCREngineAdapter
from .cic_adapter import ProductionCICAdapter
from .graph_fraud_adapter import ProductionGraphFraudAdapter
from .policy_bre_adapter import ProductionPolicyBREAdapter
from .los_structuring_adapter import ProductionLOSStructuringAdapter


class ProductionEnterpriseBackend:
    """Composite Production Backend routing all 25 credit agent tools to real enterprise systems."""

    def __init__(self) -> None:
        self.cbs = ProductionCoreBankingAdapter()
        self.idp = ProductionIDPOCREngineAdapter()
        self.cic = ProductionCICAdapter()
        self.graph = ProductionGraphFraudAdapter()
        self.bre = ProductionPolicyBREAdapter()
        self.los = ProductionLOSStructuringAdapter()

    def execute(self, tool_name: str, scenario: Scenario, arguments: dict[str, Any]) -> dict[str, Any]:
        """Routes tool execution request to real backend adapter endpoint."""
        handlers = {
            # DMS & IDP Tools
            "document_inventory": lambda: self.idp.document_inventory(scenario),
            "classify_document": lambda: self.idp.classify_document(arguments.get("document_id", "DOC-001")),
            "extract_document_fields": lambda: self.idp.extract_document_fields(arguments.get("document_id", "DOC-001"), scenario),
            "parse_bank_statement": lambda: self.idp.parse_bank_statement(scenario),
            "validate_case_completeness": lambda: self.idp.validate_case_completeness(scenario),

            # Core Banking Tools
            "resolve_borrower_identity": lambda: self.cbs.resolve_borrower_identity(scenario.borrower),
            "query_transactions": lambda: self.cbs.query_transactions(scenario.scenario_id, limit=arguments.get("limit", 50)),

            # Cashflow Analytics & Capacity
            "compute_cashflow_metrics": lambda: self.cbs._post("/cashflow/compute-metrics", {"scenario_id": scenario.scenario_id}),
            "detect_cashflow_anomalies": lambda: self.cbs._post("/cashflow/detect-anomalies", {"scenario_id": scenario.scenario_id}),
            "reconcile_declared_revenue": lambda: self.cbs._post("/cashflow/reconcile-revenue", {"scenario_id": scenario.scenario_id}),
            "calculate_credit_capacity": lambda: self.cbs._post("/capacity/calculate", {"scenario_id": scenario.scenario_id}),
            "stress_repayment_capacity": lambda: self.cbs._post("/capacity/stress-test", {"scenario_id": scenario.scenario_id}),
            "assess_refinancing_pattern": lambda: self.cbs._post("/capacity/refinancing-pattern", {"scenario_id": scenario.scenario_id}),

            # Graph Anti-Fraud Tools
            "build_entity_transaction_graph": lambda: self.graph.build_entity_transaction_graph(scenario),
            "detect_transaction_cycles": lambda: self.graph.detect_transaction_cycles(scenario),
            "trace_funds": lambda: self.graph.trace_funds(scenario),

            # Policy & BRE Tools
            "search_policy": lambda: self.bre.search_policy(arguments.get("query", "working capital")),
            "get_policy_clause": lambda: self.bre.get_policy_clause(arguments.get("clause_id", "POL-WC-001")),
            "evaluate_policy_rule": lambda: self.bre.evaluate_policy_rule(scenario),
            "validate_policy_citation": lambda: self.bre.validate_policy_citation(arguments.get("policy_citation_id", "CITE-RULE-WC-BASE")),
            "resolve_approval_authority": lambda: self.bre.resolve_approval_authority(scenario),

            # LOS & Structuring Tools
            "calculate_amortization": lambda: self.los.calculate_amortization(arguments.get("amount", scenario.request.get("amount", 2_000_000_000)), arguments.get("tenor_months", scenario.request.get("tenor_months", 12))),
            "resolve_pricing_band": lambda: self.los.resolve_pricing_band(scenario),
            "validate_deal_structure": lambda: self.los.validate_deal_structure(scenario, arguments),
            "retrieve_approved_memory": lambda: self.los.retrieve_approved_memory(scenario),
        }

        if tool_name not in handlers:
            raise ToolExecutionError(f"Unknown production tool mapping: {tool_name}")

        return handlers[tool_name]()
