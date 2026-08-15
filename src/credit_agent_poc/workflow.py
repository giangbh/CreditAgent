from __future__ import annotations

import asyncio
import copy
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from .agents import AGENT_NAMES, AgentExecution, AgentRuntime
from .db import StateRepository
from .model import ModelAdapter, ScenarioModel
from .models import AuditEvent, CreditState, StatePatch, apply_patch
from .outcomes import build_outcome_map
from .risk_propagation import build_risk_propagation
from .scenarios import SCENARIOS, Scenario
from .tools import ToolGateway

# Check if temporalio is installed for native Temporal Server execution
try:
    from temporalio import activity, workflow
    from temporalio.client import Client
    from temporalio.worker import Worker
    TEMPORAL_SDK_AVAILABLE = True
except ImportError:
    TEMPORAL_SDK_AVAILABLE = False
    Worker = None  # type: ignore
    # Mock decorators if temporalio package is not installed in standard python environment
    class _MockDecorator:
        def defn(self, *args: Any, **kwargs: Any) -> Callable[[Any], Any]:
            return lambda fn: fn

        def run(self, *args: Any, **kwargs: Any) -> Callable[[Any], Any]:
            return lambda fn: fn

    workflow = _MockDecorator()  # type: ignore
    activity = _MockDecorator()  # type: ignore


PIPELINE = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "A13"]


@activity.defn(name="execute_agent_node")
async def execute_agent_activity(node_id: str, state_dict: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Temporal Activity: Executes a single agent node execution."""
    scenario = SCENARIOS[scenario_id]
    if state_dict:
        if "audit" in state_dict and isinstance(state_dict["audit"], list):
            state_dict["audit"] = [AuditEvent(**evt) if isinstance(evt, dict) else evt for evt in state_dict["audit"]]
        state = CreditState(**state_dict)
    else:
        state = CreditState(
            case_id=f"CASE-{scenario.scenario_id.upper()}",
            scenario_id=scenario.scenario_id,
            run_id=str(uuid.uuid4()),
        )
    runtime = AgentRuntime(ScenarioModel(), ToolGateway())
    execution = runtime.run(node_id, state, scenario)
    for patch in execution.patches:
        apply_patch(state, replace(patch, base_state_version=state.state_version))
    return {
        "node_id": execution.node_id,
        "agent_name": execution.agent_name,
        "model_name": execution.model_name,
        "prompt": execution.prompt,
        "context": execution.context,
        "output": execution.output,
        "patches": [
            {
                "node_id": p.node_id,
                "path": p.path,
                "value": p.value,
                "operation": p.operation,
                "base_state_version": p.base_state_version,
            }
            for p in execution.patches
        ],
        "updated_state": state.public_snapshot(),
    }


@workflow.defn(name="Stage1EvidenceChildWorkflow")
class Stage1EvidenceChildWorkflow:
    """Stage 1 Child Workflow: Evidence Production (A1 -> Parallel [A2, A3, A4] -> A5)."""

    @workflow.run
    async def run(self, scenario_id: str, input_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = input_state or {}
        a1_res = await workflow.execute_activity(
            execute_agent_activity,
            args=["A1", state, scenario_id],
            schedule_to_close_timeout=timedelta(seconds=30),
        )
        current_state = a1_res.get("updated_state", {})

        a2_task = workflow.execute_activity(
            execute_agent_activity, args=["A2", current_state, scenario_id], schedule_to_close_timeout=timedelta(seconds=30)
        )
        a3_task = workflow.execute_activity(
            execute_agent_activity, args=["A3", current_state, scenario_id], schedule_to_close_timeout=timedelta(seconds=30)
        )
        a4_task = workflow.execute_activity(
            execute_agent_activity, args=["A4", current_state, scenario_id], schedule_to_close_timeout=timedelta(seconds=30)
        )

        a2_res, a3_res, a4_res = await asyncio.gather(a2_task, a3_task, a4_task)

        for branch_res in (a2_res, a3_res, a4_res):
            branch_state = branch_res.get("updated_state", {})
            if "analyst_reports" in branch_state:
                current_state.setdefault("analyst_reports", {}).update(branch_state["analyst_reports"])
            if "audit" in branch_state and isinstance(branch_state["audit"], list):
                current_state.setdefault("audit", []).extend(branch_state["audit"])

        a5_res = await workflow.execute_activity(
            execute_agent_activity,
            args=["A5", current_state, scenario_id],
            schedule_to_close_timeout=timedelta(seconds=30),
        )
        return a5_res.get("updated_state", current_state)


@workflow.defn(name="Stage2ChallengeChildWorkflow")
class Stage2ChallengeChildWorkflow:
    """Stage 2 Child Workflow: Credit Debate & Challenge (A6 -> A7 -> A8)."""

    @workflow.run
    async def run(self, scenario_id: str, input_state: Dict[str, Any]) -> Dict[str, Any]:
        current_state = input_state
        for node in ["A6", "A7", "A8"]:
            res = await workflow.execute_activity(
                execute_agent_activity,
                args=[node, current_state, scenario_id],
                schedule_to_close_timeout=timedelta(seconds=30),
            )
            current_state = res.get("updated_state", current_state)
        return current_state


@workflow.defn(name="Stage3StructuringChildWorkflow")
class Stage3StructuringChildWorkflow:
    """Stage 3 Child Workflow: Deal Structuring (A9)."""

    @workflow.run
    async def run(self, scenario_id: str, input_state: Dict[str, Any]) -> Dict[str, Any]:
        res = await workflow.execute_activity(
            execute_agent_activity,
            args=["A9", input_state, scenario_id],
            schedule_to_close_timeout=timedelta(seconds=30),
        )
        return res.get("updated_state", input_state)


@workflow.defn(name="Stage4RiskCommitteeChildWorkflow")
class Stage4RiskCommitteeChildWorkflow:
    """Stage 4 Child Workflow: Risk Committee Debate (A10 -> A11 -> A12)."""

    @workflow.run
    async def run(self, scenario_id: str, input_state: Dict[str, Any]) -> Dict[str, Any]:
        current_state = input_state
        for node in ["A10", "A11", "A12"]:
            res = await workflow.execute_activity(
                execute_agent_activity,
                args=[node, current_state, scenario_id],
                schedule_to_close_timeout=timedelta(seconds=30),
            )
            current_state = res.get("updated_state", current_state)
        return current_state


@workflow.defn(name="Stage5CoApprovalChildWorkflow")
class Stage5CoApprovalChildWorkflow:
    """Stage 5 Child Workflow: Co-Approval Manager Advisory Opinion (A13)."""

    @workflow.run
    async def run(self, scenario_id: str, input_state: Dict[str, Any]) -> Dict[str, Any]:
        res = await workflow.execute_activity(
            execute_agent_activity,
            args=["A13", input_state, scenario_id],
            schedule_to_close_timeout=timedelta(seconds=30),
        )
        return res.get("updated_state", input_state)


@workflow.defn(name="CreditCoApprovalWorkflow")
class CreditCoApprovalWorkflow:
    """Parent Temporal Workflow: Multi-Agent Credit Co-Approval DAG coordinating 5 Stage Child Workflows."""

    @workflow.run
    async def run(self, scenario_id: str) -> Dict[str, Any]:
        workflow_id = workflow.info().workflow_id if hasattr(workflow, "info") and callable(workflow.info) else "credit-wf"

        # Stage 1 Child Workflow
        s1_state = await workflow.execute_child_workflow(
            Stage1EvidenceChildWorkflow.run,
            args=[scenario_id, {}],
            id=f"{workflow_id}-stage1",
        )

        # Stage 2 Child Workflow
        s2_state = await workflow.execute_child_workflow(
            Stage2ChallengeChildWorkflow.run,
            args=[scenario_id, s1_state],
            id=f"{workflow_id}-stage2",
        )

        # Stage 3 Child Workflow
        s3_state = await workflow.execute_child_workflow(
            Stage3StructuringChildWorkflow.run,
            args=[scenario_id, s2_state],
            id=f"{workflow_id}-stage3",
        )

        # Stage 4 Child Workflow
        s4_state = await workflow.execute_child_workflow(
            Stage4RiskCommitteeChildWorkflow.run,
            args=[scenario_id, s3_state],
            id=f"{workflow_id}-stage4",
        )

        # Stage 5 Child Workflow
        s5_state = await workflow.execute_child_workflow(
            Stage5CoApprovalChildWorkflow.run,
            args=[scenario_id, s4_state],
            id=f"{workflow_id}-stage5",
        )

        return {"status": "COMPLETED", "scenario_id": scenario_id, "final_state": s5_state}


class TemporalWorkflowEngine:
    """Orchestration Engine managing workflow DAG execution with Temporal semantics
    and localDB persistence.
    """

    def __init__(
        self,
        model: Optional[ModelAdapter] = None,
        gateway: Optional[ToolGateway] = None,
        db_repository: Optional[StateRepository] = None,
        step_delay_ms: int = 0,
    ) -> None:
        self.model = model or ScenarioModel()
        self.gateway = gateway or ToolGateway()
        self.runtime = AgentRuntime(self.model, self.gateway)
        self.repository = db_repository or StateRepository(db_path=":memory:")
        self.step_delay_ms = step_delay_ms

    async def execute_native_temporal_cluster(self, scenario_id: str, target_host: str = "localhost:7233") -> Any:
        """Connects natively to a live Temporal Server cluster using temporalio SDK."""
        if not TEMPORAL_SDK_AVAILABLE:
            raise RuntimeError("temporalio package is not installed. Please run `pip install temporalio`.")
        client = await Client.connect(target_host)
        handle = await client.start_workflow(
            CreditCoApprovalWorkflow.run,
            scenario_id,
            id=f"credit-workflow-{scenario_id}-{str(uuid.uuid4())[:8]}",
            task_queue="credit-approval-queue",
        )
        return await handle.result()

    def execute_workflow(
        self, scenario_id: str, observer: Optional[Callable[[dict[str, Any]], None]] = None
    ) -> Tuple[CreditState, list[dict[str, Any]], int]:
        if scenario_id not in SCENARIOS:
            raise KeyError(f"unknown scenario: {scenario_id}")
        scenario = SCENARIOS[scenario_id]
        state = CreditState(
            case_id=f"CASE-{scenario.scenario_id.upper()}",
            scenario_id=scenario.scenario_id,
            run_id=str(uuid.uuid4()),
        )
        state.audit.append(AuditEvent(event="run_started", node_id="TEMPORAL_WORKFLOW", details={"scenario": scenario_id}))
        self.repository.save_case(state)
        checkpoints: list[dict[str, Any]] = []
        started = time.perf_counter()

        # Step 1: A1 Intake Node
        self._execute_node("A1", state, scenario, checkpoints, observer)

        # Step 2: Parallel Fan-out Barrier (A2 Cashflow, A3 Integrity, A4 Capacity)
        self._execute_fanout_barrier(state, scenario, checkpoints, observer)

        # Step 3: Sequential Nodes A5 .. A13
        for node_id in ["A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "A13"]:
            self._execute_node(node_id, state, scenario, checkpoints, observer)

        # Step 4: Control Evaluation Node
        self._emit(observer, "NODE_STARTED", "CONTROL", state, agent_name="Deterministic Approval Control")
        self._evaluate_control(state)
        self._checkpoint("CONTROL", state, checkpoints)
        self._emit(observer, "NODE_COMPLETED", "CONTROL", state, agent_name="Deterministic Approval Control")

        duration_ms = round((time.perf_counter() - started) * 1000)
        state.audit.append(
            AuditEvent(
                event="run_completed",
                node_id="TEMPORAL_WORKFLOW",
                details={"actual_outcome": state.coapproval_opinion.get("decision"), "duration_ms": duration_ms},
            )
        )
        # Persist final state to localDB
        self.repository.save_case(state)
        return state, checkpoints, duration_ms

    def _execute_fanout_barrier(
        self,
        state: CreditState,
        scenario: Scenario,
        checkpoints: list[dict[str, Any]],
        observer: Optional[Callable[[dict[str, Any]], None]],
    ) -> None:
        base_tool_count = len(state.tool_history)
        base_audit_count = len(state.audit)

        def execute_isolated(node_id: str) -> tuple[AgentExecution, CreditState]:
            branch_state = copy.deepcopy(state)
            self._emit(observer, "NODE_STARTED", node_id, branch_state, agent_name=AGENT_NAMES[node_id])
            if self.step_delay_ms:
                time.sleep(self.step_delay_ms / 1000)
            return self.runtime.run(node_id, branch_state, scenario), branch_state

        # Execute parallel activities
        results = {}
        for node in ("A2", "A3", "A4"):
            results[node] = execute_isolated(node)

        # Merge activity state patches
        for node_id in ("A2", "A3", "A4"):
            execution, branch_state = results[node_id]
            state.tool_history.extend(branch_state.tool_history[base_tool_count:])
            state.audit.extend(branch_state.audit[base_audit_count:])
            self._commit_execution(execution, state)
            self._checkpoint(node_id, state, checkpoints)
            self._emit(observer, "NODE_COMPLETED", node_id, state, agent_name=AGENT_NAMES[node_id])

    def _execute_node(
        self,
        node_id: str,
        state: CreditState,
        scenario: Scenario,
        checkpoints: list[dict[str, Any]],
        observer: Optional[Callable[[dict[str, Any]], None]],
    ) -> None:
        self._emit(observer, "NODE_STARTED", node_id, state, agent_name=AGENT_NAMES[node_id])
        if self.step_delay_ms:
            time.sleep(self.step_delay_ms / 1000)
        execution = self.runtime.run(node_id, state, scenario)
        self._commit_execution(execution, state)
        self._checkpoint(node_id, state, checkpoints)
        self._emit(observer, "NODE_COMPLETED", node_id, state, agent_name=AGENT_NAMES[node_id])

    def _commit_execution(self, execution: AgentExecution, state: CreditState) -> None:
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
        evt = AuditEvent(
            event="agent_node_completed",
            node_id=execution.node_id,
            details={"written_paths": [patch.path for patch in execution.patches]},
        )
        state.audit.append(evt)
        self.repository.log_audit_event(state.run_id, evt)

    def _checkpoint(self, node_id: str, state: CreditState, checkpoints: list[dict[str, Any]]) -> None:
        snapshot = state.explainable_snapshot()
        if node_id == "CONTROL":
            changed_paths = ["control"]
            agent_name = "Deterministic Approval Control"
        else:
            execution = state.node_history[-1]
            changed_paths = execution["written_paths"]
            agent_name = execution["agent_name"]
        cp = {
            "checkpoint_id": f"CP-{len(checkpoints) + 1:02d}",
            "after_node": node_id,
            "agent_name": agent_name,
            "state_version": state.state_version,
            "state_hash": hashlib.sha256(repr(snapshot).encode()).hexdigest(),
            "changed_paths": changed_paths,
            "state_snapshot": snapshot,
        }
        checkpoints.append(cp)
        # Persist checkpoint to localDB
        self.repository.save_checkpoint(state.run_id, cp)
        self.repository.save_case(state)

    def _evaluate_control(self, state: CreditState) -> None:
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
        evt = AuditEvent(
            event="approval_control_evaluated",
            node_id="CONTROL",
            details={"status": status, "blocked_reasons": blocked_reasons},
        )
        state.audit.append(evt)
        self.repository.log_audit_event(state.run_id, evt)

    @staticmethod
    def _emit(
        observer: Optional[Callable[[dict[str, Any]], None]],
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


async def start_temporal_worker(target_host: str = "localhost:7233", task_queue: str = "credit-approval-queue") -> None:
    """Starts a native Temporal Worker listening for workflow and activity tasks."""
    if not TEMPORAL_SDK_AVAILABLE:
        raise RuntimeError("temporalio package is not installed.")
    client = await Client.connect(target_host)
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[
            CreditCoApprovalWorkflow,
            Stage1EvidenceChildWorkflow,
            Stage2ChallengeChildWorkflow,
            Stage3StructuringChildWorkflow,
            Stage4RiskCommitteeChildWorkflow,
            Stage5CoApprovalChildWorkflow,
        ],
        activities=[execute_agent_activity],
    )
    print(f"Temporal Worker listening on queue '{task_queue}' at {target_host}...")
    await worker.run()
