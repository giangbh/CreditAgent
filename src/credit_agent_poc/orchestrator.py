from __future__ import annotations

import copy
import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

from .agents import AGENT_NAMES, AgentExecution, AgentRuntime
from .config import CONFIG
from .db import StateRepository

from .model import ModelAdapter, ScenarioModel
from .models import AuditEvent, CreditState, StatePatch, apply_patch
from .outcomes import OUTCOME_POLICY, build_outcome_map
from .risk_propagation import build_risk_propagation
from .scenarios import SCENARIOS, Scenario
from .tools import ToolGateway
from .workflow import TemporalWorkflowEngine


PIPELINE = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "A13"]
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
        engine_label = "Temporal.io Workflow Engine (In-Memory Simulation)"
        if self.engine_type == "temporal-cluster":
            engine_label = f"Native Temporal Server Cluster ({CONFIG.TEMPORAL_TARGET_HOST})"
        elif self.engine_type == "legacy":
            engine_label = "Legacy Python Orchestrator (Mock/In-Process)"

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
                "is_temporal": self.engine_type in ("temporal", "temporal-cluster"),
                "is_cluster": self.engine_type == "temporal-cluster",
                "temporal_ui_url": CONFIG.TEMPORAL_UI_URL if self.engine_type == "temporal-cluster" else None,
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

        if self.engine_type in ("temporal", "temporal-cluster"):
            if self.engine_type == "temporal-cluster":
                import asyncio
                asyncio.run(self.temporal_engine.execute_native_temporal_cluster(scenario_id))
            state, checkpoints, duration_ms = self.temporal_engine.execute_workflow(scenario_id, observer)
            actual = state.coapproval_opinion["decision"]
            return RunResult(
                scenario_id=scenario.scenario_id,
                scenario_name=scenario.name,
                expected_outcome=scenario.expected_outcome,
                actual_outcome=actual,
                outcome_matches=actual == scenario.expected_outcome,
                duration_ms=duration_ms,
                state=state,
                checkpoints=checkpoints,
                engine_type=self.engine_type,
            )

        state = CreditState(
            case_id=f"CASE-{scenario.scenario_id.upper()}",
            scenario_id=scenario.scenario_id,
            run_id=str(uuid.uuid4()),
        )
        state.audit.append(AuditEvent(event="run_started", node_id="ORCHESTRATOR", details={"scenario": scenario_id}))
        self.repository.save_case(state)
        checkpoints: list[dict[str, Any]] = []
        started = time.perf_counter()

        self._execute_and_commit("A1", state, scenario, checkpoints, observer)
        self._execute_evidence_fanout(state, scenario, checkpoints, observer)
        for node_id in ["A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "A13"]:
            self._execute_and_commit(node_id, state, scenario, checkpoints, observer)

        self._emit(observer, "NODE_STARTED", "CONTROL", state, agent_name="Deterministic Approval Control")
        self._evaluate_control(state)
        self._checkpoint("CONTROL", state, checkpoints)
        self._emit(observer, "NODE_COMPLETED", "CONTROL", state, agent_name="Deterministic Approval Control")
        duration_ms = round((time.perf_counter() - started) * 1000)
        actual = state.coapproval_opinion["decision"]
        state.audit.append(
            AuditEvent(
                event="run_completed",
                node_id="ORCHESTRATOR",
                details={"actual_outcome": actual, "duration_ms": duration_ms},
            )
        )
        self.repository.save_case(state)
        return RunResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            expected_outcome=scenario.expected_outcome,
            actual_outcome=actual,
            outcome_matches=actual == scenario.expected_outcome,
            duration_ms=duration_ms,
            state=state,
            checkpoints=checkpoints,
            engine_type="legacy",
        )

    def run_all(self) -> list[RunResult]:
        return [self.run(scenario_id) for scenario_id in SCENARIOS]

    def _execute_evidence_fanout(
        self,
        state: CreditState,
        scenario: Scenario,
        checkpoints: list[dict[str, Any]],
        observer: Optional[RunObserver],
    ) -> None:
        base_tool_count = len(state.tool_history)
        base_audit_count = len(state.audit)

        def execute_isolated(node_id: str) -> tuple[AgentExecution, CreditState]:
            branch_state = copy.deepcopy(state)
            self._emit(observer, "NODE_STARTED", node_id, branch_state, agent_name=AGENT_NAMES[node_id])
            self._delay()
            return self.runtime.run(node_id, branch_state, scenario), branch_state

        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="evidence-agent") as executor:
            futures = {node: executor.submit(execute_isolated, node) for node in ("A2", "A3", "A4")}
            branch_results = {node: futures[node].result() for node in ("A2", "A3", "A4")}

        for node_id in ("A2", "A3", "A4"):
            execution, branch_state = branch_results[node_id]
            state.tool_history.extend(branch_state.tool_history[base_tool_count:])
            state.audit.extend(branch_state.audit[base_audit_count:])
            self._commit_execution(execution, state)
            self._checkpoint(node_id, state, checkpoints)
            self._emit(observer, "NODE_COMPLETED", node_id, state, agent_name=AGENT_NAMES[node_id])

    def _execute_and_commit(
        self,
        node_id: str,
        state: CreditState,
        scenario: Scenario,
        checkpoints: list[dict[str, Any]],
        observer: Optional[RunObserver],
    ) -> None:
        self._emit(observer, "NODE_STARTED", node_id, state, agent_name=AGENT_NAMES[node_id])
        self._delay()
        execution = self.runtime.run(node_id, state, scenario)
        self._commit_execution(execution, state)
        self._checkpoint(node_id, state, checkpoints)
        self._emit(observer, "NODE_COMPLETED", node_id, state, agent_name=AGENT_NAMES[node_id])

    @staticmethod
    def _commit_execution(execution: AgentExecution, state: CreditState) -> None:
        input_version = state.state_version
        for patch in execution.patches:
            apply_patch(state, replace(patch, base_state_version=state.state_version))
        state.node_history.append(
            {
                "node_id": execution.node_id,
                "agent_name": execution.agent_name,
                "model": execution.model_name,
                "status": "COMPLETED",
                "input_state_version": input_version,
                "output_state_version": state.state_version,
                "prompt_hash": hashlib.sha256(execution.prompt.encode()).hexdigest(),
                "system_and_role_prompt": execution.prompt,
                "input_context": copy.deepcopy(execution.context),
                "output": copy.deepcopy(execution.output),
                "written_paths": [patch.path for patch in execution.patches],
            }
        )
        state.audit.append(
            AuditEvent(
                event="agent_node_completed",
                node_id=execution.node_id,
                details={"written_paths": [patch.path for patch in execution.patches]},
            )
        )

    def _delay(self) -> None:
        if self.step_delay_ms:
            time.sleep(self.step_delay_ms / 1000)

    @staticmethod
    def _emit(
        observer: Optional[RunObserver],
        event: str,
        node_id: str,
        state: CreditState,
        **details: Any,
    ) -> None:
        if observer:
            observer(
                {
                    "event": event,
                    "node_id": node_id,
                    "state_version": state.state_version,
                    "timestamp": time.time(),
                    **details,
                }
            )

    @staticmethod
    def _checkpoint(node_id: str, state: CreditState, checkpoints: list[dict[str, Any]]) -> None:
        snapshot = state.explainable_snapshot()
        if node_id == "CONTROL":
            changed_paths = ["control"]
            agent_name = "Deterministic Approval Control"
        else:
            execution = state.node_history[-1]
            changed_paths = execution["written_paths"]
            agent_name = execution["agent_name"]
        checkpoints.append(
            {
                "checkpoint_id": f"CP-{len(checkpoints) + 1:02d}",
                "after_node": node_id,
                "agent_name": agent_name,
                "state_version": state.state_version,
                "state_hash": hashlib.sha256(repr(snapshot).encode()).hexdigest(),
                "changed_paths": changed_paths,
                "state_snapshot": snapshot,
            }
        )

    @staticmethod
    def _evaluate_control(state: CreditState) -> None:
        opinion = state.coapproval_opinion
        reports = state.analyst_reports
        blocked_reasons: list[str] = []
        if state.data_quality.get("critical_gap"):
            blocked_reasons.append("CRITICAL_DATA_GAP")
        if reports["cashflow"].get("status") == "PARTIAL":
            blocked_reasons.append("CASHFLOW_TOOL_OR_COVERAGE_GAP")
        if not reports["financial_capacity"].get("primary_repayment_viable"):
            blocked_reasons.append("PRIMARY_REPAYMENT_NOT_VIABLE")
        if reports["transaction_integrity"].get("rating") == "CRITICAL":
            blocked_reasons.append("MATERIAL_TRANSACTION_INTEGRITY_RISK")
        if reports["policy"].get("escalation_required"):
            blocked_reasons.append("MANDATORY_POLICY_ESCALATION")

        decision = opinion["decision"]
        invalid_opinion = decision == "APPROVE_WITH_CONDITIONS" and (
            bool(blocked_reasons) or state.deal_proposal.get("action") != "PROPOSE"
        )
        if invalid_opinion:
            status = "BLOCKED_INVALID_OPINION"
        elif decision == "APPROVE_WITH_CONDITIONS":
            status = "READY_FOR_HUMAN_REVIEW"
        elif decision == "ESCALATE_TO_CRO_RISK":
            status = "ESCALATED_FOR_HUMAN_REVIEW"
        else:
            status = "HUMAN_REVIEW_RECOMMENDED_REJECT"

        control = {
            "status": status,
            "opinion_validated": not invalid_opinion,
            "blocked_reasons": blocked_reasons,
            "allowed_actions": ["VIEW_EVIDENCE", "HUMAN_REVIEW"],
            "ai_can_approve": False,
            "ai_can_disburse": False,
        }
        apply_patch(
            state,
            StatePatch(
                node_id="CONTROL",
                path="control",
                value=control,
                base_state_version=state.state_version,
            ),
        )
        state.audit.append(
            AuditEvent(
                event="approval_control_evaluated",
                node_id="CONTROL",
                details={"status": status, "blocked_reasons": blocked_reasons},
            )
        )
