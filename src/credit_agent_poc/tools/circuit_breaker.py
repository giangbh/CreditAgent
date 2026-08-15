from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, Dict, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Circuit Breaker protecting external Bank Tool APIs from cascading failures."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 5.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._states: Dict[str, CircuitState] = {}
        self._failure_counts: Dict[str, int] = {}
        self._last_failure_times: Dict[str, float] = {}

    def get_state(self, tool_name: str) -> CircuitState:
        state = self._states.get(tool_name, CircuitState.CLOSED)
        if state == CircuitState.OPEN:
            last_failed = self._last_failure_times.get(tool_name, 0.0)
            if time.time() - last_failed >= self.cooldown_seconds:
                self._states[tool_name] = CircuitState.HALF_OPEN
                return CircuitState.HALF_OPEN
        return state

    def allow_execution(self, tool_name: str) -> bool:
        state = self.get_state(tool_name)
        return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self, tool_name: str) -> None:
        self._states[tool_name] = CircuitState.CLOSED
        self._failure_counts[tool_name] = 0

    def record_failure(self, tool_name: str) -> CircuitState:
        count = self._failure_counts.get(tool_name, 0) + 1
        self._failure_counts[tool_name] = count
        self._last_failure_times[tool_name] = time.time()
        if count >= self.failure_threshold:
            self._states[tool_name] = CircuitState.OPEN
            return CircuitState.OPEN
        return self._states.get(tool_name, CircuitState.CLOSED)

    def reset(self, tool_name: Optional[str] = None) -> None:
        if tool_name:
            self._states[tool_name] = CircuitState.CLOSED
            self._failure_counts[tool_name] = 0
            self._last_failure_times[tool_name] = 0.0
        else:
            self._states.clear()
            self._failure_counts.clear()
            self._last_failure_times.clear()
