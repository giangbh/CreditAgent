from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


PatchOperation = Literal["SET", "APPEND"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class StatePatch:
    node_id: str
    path: str
    value: Any
    operation: PatchOperation = "SET"
    base_state_version: int = 0


@dataclass
class AuditEvent:
    event: str
    node_id: str
    timestamp: str = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CreditState:
    case_id: str
    scenario_id: str
    run_id: str
    case_revision: int = 1
    state_version: int = 0
    case_file: dict[str, Any] = field(default_factory=dict)
    evidence_catalog: list[dict[str, Any]] = field(default_factory=list)
    data_quality: dict[str, Any] = field(default_factory=dict)
    analyst_reports: dict[str, Any] = field(default_factory=dict)
    credit_debate: list[dict[str, Any]] = field(default_factory=list)
    credit_assessment: dict[str, Any] = field(default_factory=dict)
    deal_proposal: dict[str, Any] = field(default_factory=dict)
    risk_debate: list[dict[str, Any]] = field(default_factory=list)
    coapproval_opinion: dict[str, Any] = field(default_factory=dict)
    control: dict[str, Any] = field(default_factory=dict)
    tool_history: list[dict[str, Any]] = field(default_factory=list)
    node_history: list[dict[str, Any]] = field(default_factory=list)
    audit: list[AuditEvent] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(dataclasses.asdict(self))

    def public_snapshot(self) -> dict[str, Any]:
        data = self.snapshot()
        data["audit"] = [dataclasses.asdict(event) for event in self.audit]
        return data

    def explainable_snapshot(self) -> dict[str, Any]:
        """Bounded business State for per-step explanation without trace duplication."""
        data = self.snapshot()
        for trace_field in ("audit", "tool_history", "node_history"):
            data.pop(trace_field)
        return data


class StateValidationError(ValueError):
    pass


class ToolAccessError(PermissionError):
    pass


class ToolExecutionError(RuntimeError):
    pass


OWNERSHIP: dict[str, set[str]] = {
    "A1": {"case_file", "evidence_catalog", "data_quality"},
    "A2": {"analyst_reports.cashflow"},
    "A3": {"analyst_reports.transaction_integrity"},
    "A4": {"analyst_reports.financial_capacity"},
    "A5": {"analyst_reports.policy"},
    "A6": {"credit_debate"},
    "A7": {"credit_debate"},
    "A8": {"credit_assessment"},
    "A9": {"deal_proposal"},
    "A10": {"risk_debate"},
    "A11": {"risk_debate"},
    "A12": {"risk_debate"},
    "A13": {"coapproval_opinion"},
    "CONTROL": {"control"},
}


def _path_is_owned(node_id: str, path: str) -> bool:
    return any(path == owned or path.startswith(f"{owned}.") for owned in OWNERSHIP[node_id])


def apply_patch(state: CreditState, patch: StatePatch) -> None:
    if patch.node_id not in OWNERSHIP:
        raise StateValidationError(f"unknown node: {patch.node_id}")
    if patch.base_state_version != state.state_version:
        raise StateValidationError(
            f"stale patch: expected state_version={state.state_version}, "
            f"got {patch.base_state_version}"
        )
    if not _path_is_owned(patch.node_id, patch.path):
        raise StateValidationError(f"{patch.node_id} cannot write {patch.path}")

    parts = patch.path.split(".")
    target: Any = state
    for part in parts[:-1]:
        target = getattr(target, part) if dataclasses.is_dataclass(target) else target.setdefault(part, {})
    key = parts[-1]

    if patch.operation == "SET":
        if dataclasses.is_dataclass(target):
            setattr(target, key, copy.deepcopy(patch.value))
        else:
            target[key] = copy.deepcopy(patch.value)
    elif patch.operation == "APPEND":
        collection = getattr(target, key) if dataclasses.is_dataclass(target) else target[key]
        if not isinstance(collection, list):
            raise StateValidationError(f"APPEND target is not a list: {patch.path}")
        collection.append(copy.deepcopy(patch.value))
    else:
        raise StateValidationError(f"unsupported operation: {patch.operation}")

    state.state_version += 1
    state.audit.append(
        AuditEvent(
            event="state_patch_committed",
            node_id=patch.node_id,
            details={"path": patch.path, "operation": patch.operation},
        )
    )
