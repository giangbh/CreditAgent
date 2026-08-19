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
        """Routes tool execution request to real enterprise backend adapter endpoint."""
        doc_id = arguments.get("document_id", "DOC-001")
        scenario_id = scenario.scenario_id

        # DMS & IDP Tools
        if tool_name == "document_inventory":
            return self.idp.document_inventory(scenario)
        if tool_name == "classify_document":
            return self.idp.classify_document(doc_id)
        if tool_name == "extract_document_fields":
            return self.idp.extract_document_fields(doc_id, scenario)
        if tool_name == "parse_bank_statement":
            return self.idp.parse_bank_statement(scenario)
        if tool_name == "validate_case_completeness":
            return self.idp.validate_case_completeness(scenario)

        # Core Banking & Cashflow Analytics Tools
        if tool_name == "resolve_borrower_identity":
            return self.cbs.resolve_borrower_identity(scenario.borrower)
        if tool_name == "query_transactions":
            return self.cbs.query_transactions(scenario_id, limit=arguments.get("limit", 50))
        if tool_name == "compute_cashflow_metrics":
            return self.cbs._post("/cashflow/compute-metrics", {"scenario_id": scenario_id})
        if tool_name == "detect_cashflow_anomalies":
            return self.cbs._post("/cashflow/detect-anomalies", {"scenario_id": scenario_id})
        if tool_name == "reconcile_declared_revenue":
            return self.cbs._post("/cashflow/reconcile-revenue", {"scenario_id": scenario_id})
        if tool_name == "calculate_credit_capacity":
            return self.cbs._post("/capacity/calculate", {"scenario_id": scenario_id})
        if tool_name == "stress_repayment_capacity":
            return self.cbs._post("/capacity/stress-test", {"scenario_id": scenario_id})
        if tool_name == "assess_refinancing_pattern":
            return self.cbs._post("/capacity/refinancing-pattern", {"scenario_id": scenario_id})

        # Graph Anti-Fraud Tools
        if tool_name == "build_entity_transaction_graph":
            return self.graph.build_entity_transaction_graph(scenario)
        if tool_name == "detect_transaction_cycles":
            return self.graph.detect_transaction_cycles(scenario)
        if tool_name == "trace_funds":
            return self.graph.trace_funds(scenario)

        # Policy & BRE Tools
        if tool_name == "search_policy":
            return self.bre.search_policy(arguments.get("query", "working capital"))
        if tool_name == "get_policy_clause":
            return self.bre.get_policy_clause(arguments.get("clause_id", "POL-WC-001"))
        if tool_name == "evaluate_policy_rule":
            return self.bre.evaluate_policy_rule(scenario)
        if tool_name == "validate_policy_citation":
            return self.bre.validate_policy_citation(arguments.get("policy_citation_id", "CITE-RULE-WC-BASE"))
        if tool_name == "resolve_approval_authority":
            return self.bre.resolve_approval_authority(scenario)

        # LOS & Structuring Tools
        if tool_name == "calculate_amortization":
            amount = arguments.get("amount", scenario.request.get("amount", 2_000_000_000))
            tenor = arguments.get("tenor_months", scenario.request.get("tenor_months", 12))
            return self.los.calculate_amortization(amount, tenor)
        if tool_name == "resolve_pricing_band":
            return self.los.resolve_pricing_band(scenario)
        if tool_name == "validate_deal_structure":
            return self.los.validate_deal_structure(scenario, arguments)
        if tool_name == "retrieve_approved_memory":
            return self.los.retrieve_approved_memory(scenario)

        raise ToolExecutionError(f"Unknown production tool mapping: {tool_name}")
