from __future__ import annotations

from typing import Any

from ...scenarios import Scenario


class IntegrityToolsMixin:
    """Transaction integrity and circular funds detection tool handlers."""

    @staticmethod
    def _build_entity_transaction_graph(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "graph_ref": f"graph://{s.scenario_id}",
            "related_party_coverage": s.related_party_coverage,
        }

    @staticmethod
    def _detect_transaction_cycles(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "cycle_score": s.circular_funds_score,
            "cycle_ids": [f"CYCLE-{s.scenario_id}"] if s.circular_funds_score >= 0.7 else [],
            "evidence_id": f"EVD-INTEGRITY-{s.scenario_id}",
        }

    @staticmethod
    def _trace_funds(s: Scenario, _: dict[str, Any]) -> dict[str, Any]:
        return {"path_ref": f"path://{s.scenario_id}/material-flow", "status": "TRACED"}
