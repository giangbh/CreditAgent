from __future__ import annotations

from typing import Any, Optional

from ..models import AuditEvent, CreditState, ToolAccessError, ToolExecutionError, utc_now
from ..scenarios import Scenario
from .base import TOOL_ALLOWLIST, _hash


class ToolGateway:
    """Security and audit gateway governing tool invocation per agent node."""

    def __init__(self, backend: Optional[Any] = None) -> None:
        if backend is None:
            from .simulated.simulated_backend import SimulatedBackend
            backend = SimulatedBackend()
        self.backend = backend

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
