from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    name: str
    description: str
    expected_outcome: str
    borrower: dict[str, Any]
    request: dict[str, Any]
    documents_complete: bool = True
    statement_months: int = 12
    declared_revenue: float = 1_000_000_000
    observed_inflow: float = 950_000_000
    existing_debt_service: float = 120_000_000
    projected_debt_service: float = 180_000_000
    dscr: float = 1.55
    inflow_concentration: float = 0.32
    circular_funds_score: float = 0.05
    related_party_coverage: float = 0.9
    collateral_coverage: float = 1.4
    policy_exception: bool = False
    authority_escalation: bool = False
    forced_tool_failures: tuple[str, ...] = field(default_factory=tuple)


SCENARIOS: dict[str, Scenario] = {
    "approve_conditions": Scenario(
        scenario_id="approve_conditions",
        name="Approve with monitoring conditions",
        description="Repayment capacity is sound; customer concentration needs monitoring.",
        expected_outcome="APPROVE_WITH_CONDITIONS",
        borrower={"entity_id": "ENT-001", "segment": "SME", "industry": "distribution"},
        request={"amount": 2_000_000_000, "tenor_months": 12, "purpose": "working_capital"},
        dscr=1.62,
        inflow_concentration=0.48,
        collateral_coverage=1.35,
    ),
    "escalate_policy_exception": Scenario(
        scenario_id="escalate_policy_exception",
        name="Escalate a policy exception",
        description="Economics are acceptable but the requested tenor breaches the pilot policy.",
        expected_outcome="ESCALATE_TO_CRO_RISK",
        borrower={"entity_id": "ENT-002", "segment": "SME", "industry": "manufacturing"},
        request={"amount": 3_500_000_000, "tenor_months": 36, "purpose": "working_capital"},
        dscr=1.45,
        policy_exception=True,
        authority_escalation=True,
    ),
    "reject_missing_evidence": Scenario(
        scenario_id="reject_missing_evidence",
        name="Reject because critical evidence is missing",
        description="Only three months of statements are available and the source of repayment is unverified.",
        expected_outcome="REJECT_INSUFFICIENT_EVIDENCE",
        borrower={"entity_id": "ENT-003", "segment": "SME", "industry": "services"},
        request={"amount": 1_200_000_000, "tenor_months": 12, "purpose": "working_capital"},
        documents_complete=False,
        statement_months=3,
        dscr=1.25,
    ),
    "escalate_circular_funds": Scenario(
        scenario_id="escalate_circular_funds",
        name="Escalate suspicious circular funds",
        description="Cashflow appears strong, but graph analysis finds a high-confidence circular pattern.",
        expected_outcome="ESCALATE_TO_CRO_RISK",
        borrower={"entity_id": "ENT-004", "segment": "SME", "industry": "wholesale"},
        request={"amount": 4_000_000_000, "tenor_months": 18, "purpose": "working_capital"},
        dscr=1.7,
        circular_funds_score=0.91,
        related_party_coverage=0.95,
    ),
    "reject_weak_cashflow_high_collateral": Scenario(
        scenario_id="reject_weak_cashflow_high_collateral",
        name="Reject weak repayment despite strong collateral",
        description="Collateral is ample, but primary repayment capacity is not viable.",
        expected_outcome="REJECT_INSUFFICIENT_EVIDENCE",
        borrower={"entity_id": "ENT-005", "segment": "SME", "industry": "construction"},
        request={"amount": 5_000_000_000, "tenor_months": 24, "purpose": "working_capital"},
        declared_revenue=1_200_000_000,
        observed_inflow=620_000_000,
        dscr=0.72,
        collateral_coverage=2.8,
    ),
    "reject_tool_failure": Scenario(
        scenario_id="reject_tool_failure",
        name="Fail closed when a backend tool is unavailable",
        description="Cashflow metric backend fails; the workflow records the gap and refuses to infer values.",
        expected_outcome="REJECT_INSUFFICIENT_EVIDENCE",
        borrower={"entity_id": "ENT-006", "segment": "SME", "industry": "retail"},
        request={"amount": 900_000_000, "tenor_months": 9, "purpose": "working_capital"},
        forced_tool_failures=("compute_cashflow_metrics",),
    ),
}


def scenario_catalog() -> list[dict[str, str]]:
    return [
        {
            "scenario_id": scenario.scenario_id,
            "name": scenario.name,
            "description": scenario.description,
            "expected_outcome": scenario.expected_outcome,
        }
        for scenario in SCENARIOS.values()
    ]
