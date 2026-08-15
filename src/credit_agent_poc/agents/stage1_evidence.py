from __future__ import annotations

from typing import Any, Callable

from ..models import CreditState
from ..scenarios import Scenario


class Stage1EvidenceMixin:
    """Context builders for Stage 1 Evidence Production Agents (A1 - A5)."""

    _call: Callable[..., dict[str, Any]]
    _data: Callable[[dict[str, Any]], dict[str, Any]]

    def _context_a1(self, state: CreditState, s: Scenario) -> dict[str, Any]:
        inventory = self._data(self._call("A1", state, s, "document_inventory"))
        for document in inventory.get("documents", []):
            self._call("A1", state, s, "classify_document", document_id=document["document_id"])
        fields = self._data(self._call("A1", state, s, "extract_document_fields"))
        statement = self._data(self._call("A1", state, s, "parse_bank_statement"))
        identity = self._data(self._call("A1", state, s, "resolve_borrower_identity"))
        completeness = self._data(self._call("A1", state, s, "validate_case_completeness"))
        return {
            "inventory": inventory,
            "fields": fields,
            "statement": statement,
            "identity": identity,
            "completeness": completeness,
        }

    def _context_a2(self, state: CreditState, s: Scenario) -> dict[str, Any]:
        query = self._call("A2", state, s, "query_transactions")
        metrics = self._call("A2", state, s, "compute_cashflow_metrics")
        anomalies = self._call("A2", state, s, "detect_cashflow_anomalies")
        return {
            "query": self._data(query),
            "metrics": self._data(metrics),
            "anomalies": self._data(anomalies),
            "tool_error": next((r["error"] for r in (query, metrics, anomalies) if r["status"] == "ERROR"), None),
        }

    def _context_a3(self, state: CreditState, s: Scenario) -> dict[str, Any]:
        self._call("A3", state, s, "query_transactions")
        graph = self._data(self._call("A3", state, s, "build_entity_transaction_graph"))
        cycles = self._data(self._call("A3", state, s, "detect_transaction_cycles"))
        path = self._data(self._call("A3", state, s, "trace_funds"))
        return {"graph": graph, "cycles": cycles, "path": path}

    def _context_a4(self, state: CreditState, s: Scenario) -> dict[str, Any]:
        revenue = self._data(self._call("A4", state, s, "reconcile_declared_revenue"))
        capacity = self._data(self._call("A4", state, s, "calculate_credit_capacity"))
        stress = self._data(self._call("A4", state, s, "stress_repayment_capacity"))
        refinancing = self._data(self._call("A4", state, s, "assess_refinancing_pattern"))
        return {"revenue": revenue, "capacity": capacity, "stress": stress, "refinancing": refinancing}

    def _context_a5(self, state: CreditState, s: Scenario) -> dict[str, Any]:
        search = self._data(self._call("A5", state, s, "search_policy"))
        clause = self._data(
            self._call("A5", state, s, "get_policy_clause", clause_id=search["candidate_clause_ids"][0])
        )
        rule = self._data(self._call("A5", state, s, "evaluate_policy_rule"))
        citation = self._data(
            self._call("A5", state, s, "validate_policy_citation", policy_citation_id=rule["policy_citation_id"])
        )
        authority = self._data(self._call("A5", state, s, "resolve_approval_authority"))
        return {"search": search, "clause": clause, "rule": rule, "citation": citation, "authority": authority}
