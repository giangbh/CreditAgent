from __future__ import annotations

from typing import Any

from ...scenarios import Scenario


class StructuringToolsMixin:
    """Policy rules, pricing, amortization and deal structuring tool handlers."""

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
