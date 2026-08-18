from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .agents import AGENT_NAMES, AgentRuntime
from .config import CONFIG
from .db import StateRepository
from .model import ModelAdapter, ScenarioModel
from .models import CreditState
from .outcomes import OUTCOME_POLICY, build_outcome_map
from .risk_propagation import build_risk_propagation
from .scenarios import SCENARIOS, Scenario
from .tools import ToolGateway
from .workflow import TemporalWorkflowEngine, PIPELINE

RunObserver = Callable[[dict[str, Any]], None]


@dataclass
class RunResult:
    scenario_id: str
    scenario_name: str
    expected_outcome: str
    actual_outcome: str
    outcome_matches: bool
    duration_ms: int
    state: CreditState
    checkpoints: list[dict[str, Any]]
    engine_type: str = "temporal"

    def to_dict(self) -> dict[str, Any]:
        engine_label = f"Native Temporal.io Server Engine ({CONFIG.TEMPORAL_TARGET_HOST})"

        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "expected_outcome": self.expected_outcome,
            "actual_outcome": self.actual_outcome,
            "outcome_matches": self.outcome_matches,
            "duration_ms": self.duration_ms,
            "engine_info": {
                "engine_type": self.engine_type,
                "engine_label": engine_label,
                "is_temporal": True,
                "is_cluster": True,
                "temporal_ui_url": CONFIG.TEMPORAL_UI_URL,
            },
            "pipeline": PIPELINE,
            "checkpoints": self.checkpoints,
            "node_outcomes": build_outcome_map(self.state),
            "outcome_policy": {
                "policy_id": OUTCOME_POLICY["policy_id"],
                "version": OUTCOME_POLICY["version"],
            },
            "risk_propagation": build_risk_propagation(self.state),
            "state": self.state.public_snapshot(),
        }


class CreditOrchestrator:
    """Enterprise Credit Orchestrator executing multi-agent workflows exclusively on Temporal Server."""

    def __init__(
        self,
        model: Optional[ModelAdapter] = None,
        gateway: Optional[ToolGateway] = None,
        db_repository: Optional[StateRepository] = None,
        engine: str = "temporal",
        step_delay_ms: int = 0,
    ) -> None:
        self.model = model or ScenarioModel()
        self.gateway = gateway or ToolGateway()
        self.repository = db_repository or StateRepository(db_path=":memory:")
        self.engine_type = engine
        self.step_delay_ms = step_delay_ms
        self.runtime = AgentRuntime(self.model, self.gateway)
        self.temporal_engine = TemporalWorkflowEngine(
            model=self.model,
            gateway=self.gateway,
            db_repository=self.repository,
            step_delay_ms=self.step_delay_ms,
        )

    def run(self, scenario_id: str, observer: Optional[RunObserver] = None) -> RunResult:
        if scenario_id not in SCENARIOS:
            raise KeyError(f"unknown scenario: {scenario_id}")
        scenario = SCENARIOS[scenario_id]

        state, checkpoints, duration_ms = self.temporal_engine.execute_workflow(scenario_id, observer)
        actual = state.coapproval_opinion.get("decision", "REJECT_INSUFFICIENT_EVIDENCE")

        return RunResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            expected_outcome=scenario.expected_outcome,
            actual_outcome=actual,
            outcome_matches=actual == scenario.expected_outcome,
            duration_ms=duration_ms,
            state=state,
            checkpoints=checkpoints,
            engine_type="temporal",
        )

    def run_all(self) -> list[RunResult]:
        return [self.run(scenario_id) for scenario_id in SCENARIOS]
