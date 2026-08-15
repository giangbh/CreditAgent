from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from ..models import utc_now


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


def tool_contract_summary() -> dict[str, list[str]]:
    return {node: sorted(tools) for node, tools in TOOL_ALLOWLIST.items()}


@dataclass
class ToolResult:
    status: str
    node_id: str
    tool_name: str
    data: dict[str, Any]
    input_hash: str
    output_hash: str
    started_at: str
    completed_at: str
    error: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "status": self.status,
            "node_id": self.node_id,
            "tool_name": self.tool_name,
            "input_hash": self.input_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
        if self.status == "SUCCESS":
            res["output_hash"] = self.output_hash
            res["data"] = self.data
        else:
            res["error"] = self.error
        return res


class BaseTool:
    """Base interface for all CreditAgent tools (simulated or adapter)."""

    name: str = "base_tool"
    description: str = "Base tool interface"

    def execute(self, arguments: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("Subclasses must implement execute()")
