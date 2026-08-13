from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import CreditState


@dataclass(frozen=True)
class NodeOutcome:
    level: str
    label: str
    reason: str
    execution_status: str = "COMPLETED"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _outcome(level: str, reason: str) -> NodeOutcome:
    return NodeOutcome(level=level, label=level, reason=reason)


def classify_agent_outcome(node_id: str, output: dict[str, Any]) -> NodeOutcome:
    """Classify business outcome independently from technical execution status."""
    if node_id == "A1":
        quality = output.get("data_quality", {})
        if quality.get("critical_gap") or quality.get("overall") == "INSUFFICIENT":
            return _outcome("FAIL", "Critical evidence gap")
        if quality.get("human_review_required") or quality.get("missing"):
            return _outcome("WARNING", "Evidence needs human review")
        return _outcome("PASS", "Required evidence is sufficient")

    if node_id == "A2":
        if output.get("status") != "COMPLETE" or output.get("rating") in {"FAIL", "UNKNOWN"}:
            return _outcome("FAIL", "Cashflow result unavailable or failed")
        if output.get("rating") != "PASS" or output.get("findings"):
            return _outcome("WARNING", "Cashflow findings need controls")
        return _outcome("PASS", "Cashflow evidence passed")

    if node_id == "A3":
        if output.get("rating") in {"CRITICAL", "FAIL"}:
            return _outcome("FAIL", "Material transaction-integrity risk")
        if output.get("rating") != "PASS" or output.get("related_party_coverage", 1) < 0.8:
            return _outcome("WARNING", "Transaction integrity needs review")
        return _outcome("PASS", "No material integrity pattern")

    if node_id == "A4":
        if output.get("rating") == "FAIL" or output.get("primary_repayment_viable") is False:
            return _outcome("FAIL", "Primary repayment is not viable")
        if output.get("stressed_dscr", 99) < 1.1 or output.get("revenue_match_ratio", 1) < 0.8:
            return _outcome("WARNING", "Repayment capacity is marginal")
        return _outcome("PASS", "Repayment capacity passed")

    if node_id == "A5":
        if not output.get("citation_valid", True) or output.get("disposition") == "HARD_BLOCK":
            return _outcome("FAIL", "Policy hard block or invalid citation")
        if output.get("escalation_required") or output.get("disposition") == "MANDATORY_ESCALATION":
            return _outcome("ESCALATE", "Mandatory policy escalation")
        if output.get("disposition") not in {"ADVISORY", "PASS"}:
            return _outcome("WARNING", "Policy condition must be resolved")
        return _outcome("PASS", "No blocking policy exception")

    if node_id == "A6":
        if output.get("thesis") == "not_currently_supportable":
            return _outcome("FAIL", "Credit case is not supportable")
        if output.get("concessions"):
            return _outcome("WARNING", "Support requires concessions")
        return _outcome("PASS", "Credit thesis is supportable")

    if node_id == "A7":
        challenges = set(output.get("challenges", []))
        if challenges & {"weak_primary_repayment", "circular_funds_pattern"}:
            return _outcome("FAIL", "Material risk challenge confirmed")
        if "mandatory_policy_escalation" in challenges:
            return _outcome("ESCALATE", "Risk challenge requires escalation")
        if challenges:
            return _outcome("WARNING", "Residual risk needs mitigation")
        return _outcome("PASS", "No material challenge remains")

    if node_id == "A8":
        rating = output.get("rating")
        if rating in {"REJECT", "HOLD_FOR_INFO"}:
            return _outcome("FAIL", "Assessment cannot proceed")
        if rating != "APPROVE" or output.get("unresolved_risks"):
            return _outcome("WARNING", "Assessment retains unresolved risk")
        return _outcome("PASS", "Assessment supports proceeding")

    if node_id == "A9":
        action = output.get("action")
        if action == "ESCALATE":
            return _outcome("ESCALATE", "No valid structure within authority")
        if action == "DECLINE" or not output.get("validation", {}).get("valid", True):
            return _outcome("FAIL", "Deal structure is not viable")
        if output.get("conditions"):
            return _outcome("WARNING", "Proposal includes binding conditions")
        return _outcome("PASS", "Deal structure is valid")

    if node_id in {"A10", "A11"}:
        position = output.get("position")
        if position == "OPPOSE":
            return _outcome("FAIL", "Committee perspective opposes")
        if position == "ESCALATE":
            return _outcome("ESCALATE", "Committee perspective escalates")
        if position == "MODIFY":
            return _outcome("WARNING", "Committee requests modification")
        return _outcome("PASS", "Committee perspective supports")

    if node_id == "A12":
        if output.get("auditability") == "FAIL":
            return _outcome("FAIL", "Decision record is not auditable")
        if output.get("escalation_required") or output.get("position") == "ESCALATE":
            return _outcome("ESCALATE", "Governance escalation required")
        if output.get("position") == "MODIFY" or output.get("material_dissent"):
            return _outcome("WARNING", "Material dissent remains")
        return _outcome("PASS", "Governance review passed")

    if node_id == "A13":
        decision = output.get("decision")
        if decision == "ESCALATE_TO_CRO_RISK":
            return _outcome("ESCALATE", "Draft opinion requires CRO review")
        if decision == "REJECT_INSUFFICIENT_EVIDENCE":
            return _outcome("FAIL", "Draft opinion recommends rejection")
        if decision == "APPROVE_WITH_CONDITIONS":
            return _outcome("WARNING", "Approval remains conditional and human-owned")
        return _outcome("WARNING", "Draft opinion needs human validation")

    return _outcome("UNKNOWN", "No business outcome rule")


def classify_control_outcome(control: dict[str, Any]) -> NodeOutcome:
    status = control.get("status")
    if status == "READY_FOR_HUMAN_REVIEW":
        return _outcome("PASS", "Control checks passed for human review")
    if status == "ESCALATED_FOR_HUMAN_REVIEW":
        return _outcome("ESCALATE", "Routed to higher human authority")
    if status in {"HUMAN_REVIEW_RECOMMENDED_REJECT", "BLOCKED_INVALID_OPINION"}:
        return _outcome("FAIL", "Control recommends reject or blocks opinion")
    return _outcome("WARNING", "Control status needs review")


def build_outcome_map(state: CreditState) -> dict[str, dict[str, str]]:
    outcomes = {
        node["node_id"]: classify_agent_outcome(node["node_id"], node["output"]).to_dict()
        for node in state.node_history
    }
    outcomes["CONTROL"] = classify_control_outcome(state.control).to_dict()
    return outcomes
