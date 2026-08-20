from __future__ import annotations

from typing import Any, Iterable

from .models import CreditState


NODE_ORDER = [f"A{i}" for i in range(1, 14)] + ["CONTROL"]
ALIASES = {
    "high_customer_concentration": "CASHFLOW_QUALITY_OR_COVERAGE",
    "cashflow_quality_or_coverage": "CASHFLOW_QUALITY_OR_COVERAGE",
    "cashflow_metrics_unavailable": "CASHFLOW_QUALITY_OR_COVERAGE",
    "deterministic_cashflow_backend_failed": "CASHFLOW_QUALITY_OR_COVERAGE",
    "CASHFLOW_TOOL_OR_COVERAGE_GAP": "CASHFLOW_QUALITY_OR_COVERAGE",
    "COND-CONCENTRATION": "CASHFLOW_QUALITY_OR_COVERAGE",
    "pattern_consistent_with_circular_funds": "CIRCULAR_FUNDS_PATTERN",
    "circular_funds_pattern": "CIRCULAR_FUNDS_PATTERN",
    "MATERIAL_TRANSACTION_INTEGRITY_RISK": "CIRCULAR_FUNDS_PATTERN",
    "weak_primary_repayment": "WEAK_PRIMARY_REPAYMENT",
    "primary_repayment_not_demonstrated": "WEAK_PRIMARY_REPAYMENT",
    "PRIMARY_REPAYMENT_NOT_VIABLE": "WEAK_PRIMARY_REPAYMENT",
    "mandatory_policy_escalation": "MANDATORY_POLICY_ESCALATION",
    "stress_case_below_1x": "STRESS_CASE_BELOW_1X",
}


def _normalized(values: Iterable[Any]) -> set[str]:
    return {ALIASES.get(str(value), str(value).upper()) for value in values if value}


def _signals(node_id: str, output: dict[str, Any], state: CreditState) -> set[str]:
    values: list[Any] = []
    for key in ("findings", "data_gaps", "challenges", "unresolved_risks", "residual_risks", "concessions"):
        value = output.get(key, [])
        values.extend(value if isinstance(value, list) else [value])
    if output.get("finding") and output.get("rating") != "PASS":
        values.append(output["finding"])
    values.extend(condition.get("condition_id") for condition in output.get("conditions", []))
    if node_id == "A1" and output.get("data_quality", {}).get("critical_gap"):
        values.append("CRITICAL_DATA_GAP")
    if node_id == "A4" and output.get("primary_repayment_viable") is False:
        values.append("weak_primary_repayment")
    if node_id in {"A5", "A12"} and output.get("escalation_required"):
        values.append("mandatory_policy_escalation")
    if node_id == "A5" and output.get("rule_id") == "RULE-INTEGRITY-007":
        values.append("circular_funds_pattern")
    if node_id == "CONTROL":
        values.extend(state.control.get("blocked_reasons", []))
        if state.control.get("status") == "ESCALATED_FOR_HUMAN_REVIEW":
            values.append("mandatory_policy_escalation")
    return _normalized(values)


def build_risk_propagation(state: CreditState) -> dict[str, Any]:
    outputs = {node["node_id"]: node.get("output", {}) for node in state.node_history}
    outputs["CONTROL"] = state.control
    signals_by_node = {node: _signals(node, outputs.get(node, {}), state) for node in NODE_ORDER}
    risks = []
    for risk_code in sorted(set().union(*signals_by_node.values())):
        path = [node for node in NODE_ORDER if risk_code in signals_by_node[node]]
        if len(path) < 2:
            continue
        risks.append(
            {
                "risk_code": risk_code,
                "source_node": path[0],
                "path": path,
                "edges": [{"from": left, "to": right} for left, right in zip(path, path[1:])],
                "terminal_node": path[-1],
            }
        )
    return {
        "risk_count": len(risks),
        "risks": risks,
        "nodes_with_propagated_risk": sorted({node for risk in risks for node in risk["path"]}, key=NODE_ORDER.index),
    }
