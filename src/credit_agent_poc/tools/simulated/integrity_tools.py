from __future__ import annotations

from typing import Any
from ...scenarios import Scenario
from .scenario_data import ScenarioDataGenerator


class IntegrityToolsMixin:
    """Transaction integrity and circular funds detection tool handlers."""

    @staticmethod
    def _build_entity_transaction_graph(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_build_entity_transaction_graph(s, args)

    @staticmethod
    def _detect_transaction_cycles(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_detect_transaction_cycles(s, args)

    @staticmethod
    def _trace_funds(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return ScenarioDataGenerator.get_trace_funds(s, args)
