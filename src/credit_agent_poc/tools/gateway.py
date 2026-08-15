from __future__ import annotations

import time
from typing import Any, Optional

from ..models import AuditEvent, CreditState, ToolAccessError, ToolExecutionError, ToolRateLimitError, utc_now
from ..scenarios import Scenario
from .base import TOOL_ALLOWLIST, _hash


class RateLimiter:
    """Sliding Window Rate Limiter governing tool execution frequency per agent/gateway."""

    def __init__(self, max_calls_per_second: float = 0.0) -> None:
        self.max_calls_per_second = max_calls_per_second
        self._history: list[float] = []

    def allow(self) -> bool:
        if self.max_calls_per_second <= 0:
            return True
        now = time.time()
        # Clean timestamps older than 1 second
        self._history = [t for t in self._history if now - t < 1.0]
        if len(self._history) >= self.max_calls_per_second:
            return False
        self._history.append(now)
        return True

    def reset(self) -> None:
        self._history.clear()


class ToolGateway:
    """Security and audit gateway governing tool permission allowlists and rate limiting."""

    def __init__(self, backend: Optional[Any] = None, max_calls_per_second: float = 0.0) -> None:
        if backend is None:
            from .simulated.simulated_backend import SimulatedBackend
            backend = SimulatedBackend()
        self.backend = backend
        self.rate_limiter = RateLimiter(max_calls_per_second=max_calls_per_second)

    def is_tool_allowed(self, node_id: str, tool_name: str) -> bool:
        """Enforces fine-grained Agent Tool Permission Allowlist."""
        allowed_tools = TOOL_ALLOWLIST.get(node_id, set())
        return tool_name in allowed_tools

    def call(
        self,
        node_id: str,
        state: CreditState,
        scenario: Scenario,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        arguments = arguments or {}

        # 1. Enforce Fine-grained Agent-Tool Permission Allowlist
        if not self.is_tool_allowed(node_id, tool_name):
            state.audit.append(
                AuditEvent(
                    event="tool_call_denied",
                    node_id=node_id,
                    details={"tool_name": tool_name, "reason": "DISALLOWED_TOOL_FOR_AGENT"},
                )
            )
            raise ToolAccessError(f"{node_id} is not allowed to call {tool_name}")

        # 2. Enforce Gateway Rate Limiting
        if not self.rate_limiter.allow():
            state.audit.append(
                AuditEvent(
                    event="tool_call_rate_limited",
                    node_id=node_id,
                    details={"tool_name": tool_name, "max_calls_per_second": self.rate_limiter.max_calls_per_second},
                )
            )
            raise ToolRateLimitError(
                f"Rate limit exceeded ({self.rate_limiter.max_calls_per_second} calls/s) for {node_id} calling {tool_name}"
            )

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
