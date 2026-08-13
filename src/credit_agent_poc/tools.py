from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from .models import AuditEvent, CreditState, ToolAccessError, ToolExecutionError, utc_now
from .scenarios import Scenario


TOOL_ALLOWLIST: dict[str, set[str]] = {
    "A1": {
        "document_inventory",
        "classify_document",
        "extract_document_fields",
        "parse_bank_statement",
        "resolve_borrower_identity",
        "validate_case_completeness",
    },
    "A2": {"query_transactions", "compute_cashflow_metrics", "detect_cashflow_anomalies"},
    "A3": {
        "query_transactions",
        "build_entity_transaction_graph",
        "detect_transaction_cycles",
        "trace_funds",
    },
    "A4": {
        "reconcile_declared_revenue",
        "calculate_credit_capacity",
        "stress_repayment_capacity",
        "assess_refinancing_pattern",
    },
    "A5": {
        "search_policy",
        "get_policy_clause",
        "evaluate_policy_rule",
        "validate_policy_citation",
        "resolve_approval_authority",
    },
    "A6": set(),
    "A7": set(),
    "A8": set(),
    "A9": {
        "calculate_credit_capacity",
        "stress_repayment_capacity",
        "evaluate_policy_rule",
        "resolve_approval_authority",
        "calculate_amortization",
        "resolve_pricing_band",
        "validate_deal_structure",
    },
    "A10": set(),
    "A11": set(),
    "A12": set(),
    "A13": set(),
}


def _hash(data: Any) -> str:
    encoded = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


class SimulatedBackend:
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
    def _build_entity_transaction_graph(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "graph_ref": f"graph://{s.scenario_id}",
            "related_party_coverage": s.related_party_coverage,
        }

    @staticmethod
    def _detect_transaction_cycles(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "cycle_score": s.circular_funds_score,
            "cycle_ids": [f"CYCLE-{s.scenario_id}"] if s.circular_funds_score >= 0.7 else [],
            "evidence_id": f"EVD-INTEGRITY-{s.scenario_id}",
        }

    @staticmethod
    def _trace_funds(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"path_ref": f"path://{s.scenario_id}/material-flow", "status": "TRACED"}

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

    @staticmethod
    def _search_policy(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"candidate_clause_ids": ["POL-WC-001", "POL-WC-017"], "policy_snapshot_id": "POLICY-POC-v1"}

    @staticmethod
    def _get_policy_clause(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "clause_id": args.get("clause_id", "POL-WC-001"),
            "effective": True,
            "product": "working_capital",
            "source_ref": "policy://poc/v1/working-capital",
        }

    @staticmethod
    def _evaluate_policy_rule(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        if s.circular_funds_score >= 0.8:
            disposition = "MANDATORY_ESCALATION"
            rule_id = "RULE-INTEGRITY-007"
        elif s.policy_exception:
            disposition = "MANDATORY_ESCALATION"
            rule_id = "RULE-TENOR-003"
        else:
            disposition = "ADVISORY"
            rule_id = "RULE-WC-BASE"
        return {"rule_id": rule_id, "disposition": disposition, "policy_citation_id": f"CITE-{rule_id}"}

    @staticmethod
    def _validate_policy_citation(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return {"policy_citation_id": args.get("policy_citation_id"), "valid": True, "policy_snapshot_id": "POLICY-POC-v1"}

    @staticmethod
    def _resolve_approval_authority(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"authority": "CRO_RISK" if s.authority_escalation else "CREDIT_COMMITTEE", "escalation_required": s.authority_escalation}

    @staticmethod
    def _calculate_amortization(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        amount = args.get("amount", s.request["amount"])
        tenor = args.get("tenor_months", s.request["tenor_months"])
        return {"calculation_ref": f"CALC-AMORT-{s.scenario_id}", "monthly_principal": round(amount / tenor, 2)}

    @staticmethod
    def _resolve_pricing_band(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"pricing_band": "RISK_ADJUSTED_B", "source_ref": "pricing://poc/v1/band-b"}

    @staticmethod
    def _validate_deal_structure(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        valid = s.dscr >= 1.2 and not (s.circular_funds_score >= 0.8)
        if s.policy_exception:
            valid = False
        return {"valid": valid, "violations": [] if valid else ["requires_escalation_or_decline"]}

    @staticmethod
    def _retrieve_approved_memory(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"entries": [], "note": "disabled in POC by default"}


class ToolGateway:
    def __init__(self, backend: Optional[SimulatedBackend] = None) -> None:
        self.backend = backend or SimulatedBackend()

    def call(
        self,
        node_id: str,
        state: CreditState,
        scenario: Scenario,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        arguments = arguments or {}
        if tool_name not in TOOL_ALLOWLIST.get(node_id, set()):
            state.audit.append(
                AuditEvent(
                    event="tool_call_denied",
                    node_id=node_id,
                    details={"tool_name": tool_name},
                )
            )
            raise ToolAccessError(f"{node_id} is not allowed to call {tool_name}")

        request = {
            "node_id": node_id,
            "tool_name": tool_name,
            "case_id": state.case_id,
            "case_revision": state.case_revision,
            "state_version": state.state_version,
            "arguments": arguments,
        }
        started_at = utc_now()
        try:
            data = self.backend.execute(tool_name, scenario, arguments)
            response = {
                "status": "SUCCESS",
                "node_id": node_id,
                "tool_name": tool_name,
                "input_hash": _hash(request),
                "output_hash": _hash(data),
                "data": data,
                "started_at": started_at,
                "completed_at": utc_now(),
            }
        except ToolExecutionError as exc:
            response = {
                "status": "ERROR",
                "node_id": node_id,
                "tool_name": tool_name,
                "input_hash": _hash(request),
                "error": {"code": "SIMULATED_BACKEND_FAILURE", "retryable": False, "message_safe": str(exc)},
                "started_at": started_at,
                "completed_at": utc_now(),
            }
        state.tool_history.append(response)
        state.audit.append(
            AuditEvent(
                event="tool_call_completed",
                node_id=node_id,
                details={"tool_name": tool_name, "status": response["status"]},
            )
        )
        return response


def tool_contract_summary() -> dict[str, list[str]]:
    return {node: sorted(tools) for node, tools in TOOL_ALLOWLIST.items()}
