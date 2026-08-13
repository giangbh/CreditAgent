from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import ModelAdapter
from .models import CreditState, StatePatch, StateValidationError
from .prompts import prompt_for
from .scenarios import Scenario
from .tools import ToolGateway


AGENT_NAMES = {
    "A1": "Intake & Evidence Agent",
    "A2": "Cashflow Analyst",
    "A3": "Transaction Integrity Analyst",
    "A4": "Financial Capacity Analyst",
    "A5": "Policy Compliance Analyst",
    "A6": "Credit Advocate",
    "A7": "Risk Challenger",
    "A8": "Credit Assessment Manager",
    "A9": "Deal Structuring Agent",
    "A10": "Business/Upside Risk Agent",
    "A11": "Conservative Credit Risk Agent",
    "A12": "Neutral Governance Risk Agent",
    "A13": "Co-Approval Manager",
}


@dataclass
class AgentExecution:
    node_id: str
    agent_name: str
    model_name: str
    prompt: str
    context: dict[str, Any]
    output: dict[str, Any]
    patches: list[StatePatch]


class AgentRuntime:
    def __init__(self, model: ModelAdapter, tools: ToolGateway) -> None:
        self.model = model
        self.tools = tools

    def run(self, node_id: str, state: CreditState, scenario: Scenario) -> AgentExecution:
        if node_id not in AGENT_NAMES:
            raise StateValidationError(f"unknown agent node: {node_id}")
        context = getattr(self, f"_context_{node_id.lower()}")(state, scenario)
        prompt = prompt_for(node_id)
        output = self.model.generate(node_id, prompt, context)
        self._validate_output(node_id, output)
        patches = self._patches(node_id, state, output)
        return AgentExecution(
            node_id=node_id,
            agent_name=AGENT_NAMES[node_id],
            model_name=self.model.name,
            prompt=prompt,
            context=context,
            output=output,
            patches=patches,
        )

    @staticmethod
    def _data(response: dict[str, Any]) -> dict[str, Any]:
        return response.get("data", {}) if response.get("status") == "SUCCESS" else {}

    def _call(self, node: str, state: CreditState, scenario: Scenario, name: str, **arguments: Any) -> dict[str, Any]:
        return self.tools.call(node, state, scenario, name, arguments)

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

    @staticmethod
    def _context_a6(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {"reports": state.analyst_reports, "data_quality": state.data_quality}

    @staticmethod
    def _context_a7(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {"reports": state.analyst_reports, "data_quality": state.data_quality, "debate": state.credit_debate}

    @staticmethod
    def _context_a8(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {"reports": state.analyst_reports, "data_quality": state.data_quality, "debate": state.credit_debate}

    def _context_a9(self, state: CreditState, s: Scenario) -> dict[str, Any]:
        self._call("A9", state, s, "calculate_credit_capacity")
        self._call("A9", state, s, "stress_repayment_capacity")
        self._call("A9", state, s, "evaluate_policy_rule")
        self._call("A9", state, s, "resolve_approval_authority")
        amortization = self._data(
            self._call(
                "A9",
                state,
                s,
                "calculate_amortization",
                amount=state.credit_assessment.get("recommended_amount", 0),
                tenor_months=s.request["tenor_months"],
            )
        )
        pricing = self._data(self._call("A9", state, s, "resolve_pricing_band"))
        validation = self._data(self._call("A9", state, s, "validate_deal_structure"))
        return {
            "assessment": state.credit_assessment,
            "policy": state.analyst_reports["policy"],
            "cashflow": state.analyst_reports["cashflow"],
            "request": state.case_file["request"],
            "amortization": amortization,
            "pricing": pricing,
            "validation": validation,
        }

    @staticmethod
    def _context_a10(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {"deal": state.deal_proposal, "assessment": state.credit_assessment, "reports": state.analyst_reports}

    @staticmethod
    def _context_a11(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {
            "deal": state.deal_proposal,
            "assessment": state.credit_assessment,
            "financial": state.analyst_reports["financial_capacity"],
            "risk_turns": state.risk_debate,
        }

    @staticmethod
    def _context_a12(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {
            "deal": state.deal_proposal,
            "assessment": state.credit_assessment,
            "policy": state.analyst_reports["policy"],
            "risk_turns": state.risk_debate,
        }

    @staticmethod
    def _context_a13(state: CreditState, s: Scenario) -> dict[str, Any]:
        return {
            "reports": state.analyst_reports,
            "data_quality": state.data_quality,
            "assessment": state.credit_assessment,
            "deal": state.deal_proposal,
            "risk_turns": state.risk_debate,
        }

    @staticmethod
    def _validate_output(node_id: str, output: dict[str, Any]) -> None:
        if not isinstance(output, dict) or not output:
            raise StateValidationError(f"{node_id} returned an empty or invalid object")
        if node_id == "A13":
            valid = {"APPROVE_WITH_CONDITIONS", "ESCALATE_TO_CRO_RISK", "REJECT_INSUFFICIENT_EVIDENCE"}
            if output.get("status") != "DRAFT" or output.get("decision") not in valid:
                raise StateValidationError("A13 must return a DRAFT opinion with a supported decision")

    @staticmethod
    def _patches(node_id: str, state: CreditState, output: dict[str, Any]) -> list[StatePatch]:
        mapping: dict[str, list[tuple[str, str, str]]] = {
            "A1": [
                ("case_file", "case_file", "SET"),
                ("evidence_catalog", "evidence_catalog", "SET"),
                ("data_quality", "data_quality", "SET"),
            ],
            "A2": [("analyst_reports.cashflow", "", "SET")],
            "A3": [("analyst_reports.transaction_integrity", "", "SET")],
            "A4": [("analyst_reports.financial_capacity", "", "SET")],
            "A5": [("analyst_reports.policy", "", "SET")],
            "A6": [("credit_debate", "", "APPEND")],
            "A7": [("credit_debate", "", "APPEND")],
            "A8": [("credit_assessment", "", "SET")],
            "A9": [("deal_proposal", "", "SET")],
            "A10": [("risk_debate", "", "APPEND")],
            "A11": [("risk_debate", "", "APPEND")],
            "A12": [("risk_debate", "", "APPEND")],
            "A13": [("coapproval_opinion", "", "SET")],
        }
        patches = []
        for path, output_key, operation in mapping[node_id]:
            value = output[output_key] if output_key else output
            patches.append(
                StatePatch(
                    node_id=node_id,
                    path=path,
                    value=value,
                    operation=operation,
                    base_state_version=state.state_version,
                )
            )
        return patches
