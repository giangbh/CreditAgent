from __future__ import annotations

import asyncio
import copy
import hashlib
import socket
import time
import uuid
from datetime import timedelta
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from .agents import AGENT_NAMES, AgentExecution, AgentRuntime
from .config import CONFIG
from .db import StateRepository
from .model import ModelAdapter, ScenarioModel
from .models import AuditEvent, CreditState, StatePatch, apply_patch
from .outcomes import build_outcome_map
from .risk_propagation import build_risk_propagation
from .scenarios import SCENARIOS, Scenario
from .tools import ToolGateway

PIPELINE = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "A13"]


def is_temporal_cluster_alive(host: str = CONFIG.TEMPORAL_TARGET_HOST, timeout_sec: float = 0.1) -> bool:
    """Kiểm tra nhanh xem Temporal Server cluster có đang lắng nghe cổng hay không."""
    try:
        parts = host.split(":")
        ip = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 7233
        with socket.create_connection((ip, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


# ==============================================================================
# BẢNG CẤU HÌNH TIMEOUT, RETRY & TASK QUEUES CHUYÊN BIỆT TỪNG NHÓM AGENT
# ==============================================================================
AGENT_EXECUTION_POLICIES: Dict[str, Dict[str, Any]] = {
    # Nhóm 1: Tác vụ nạp & tra cứu thể chế nhanh (A1 Intake, A5 Policy)
    "FAST_LOOKUP": {
        "start_to_close": timedelta(minutes=2),
        "schedule_to_close": timedelta(minutes=5),
        "heartbeat": None,
        "task_queue": "fast-tools-queue",
        "retry_policy": RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=20),
            maximum_attempts=3,
        ),
    },
    # Nhóm 2: Tác vụ bóc tách tài liệu lớn, OCR BCTC & Sao kê (A2 Cashflow, A4 Capacity)
    "HEAVY_IDP_OCR": {
        "start_to_close": timedelta(minutes=8),
        "schedule_to_close": timedelta(minutes=20),
        "heartbeat": timedelta(seconds=30),
        "task_queue": "idp-ocr-queue",
        "retry_policy": RetryPolicy(
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(minutes=1),
            maximum_attempts=3,
        ),
    },
    # Nhóm 3: Đồ thị giao dịch Neo4j & AML (A3 Integrity)
    "GRAPH_ANALYTICS": {
        "start_to_close": timedelta(minutes=3),
        "schedule_to_close": timedelta(minutes=8),
        "heartbeat": timedelta(seconds=20),
        "task_queue": "fast-tools-queue",
        "retry_policy": RetryPolicy(
            initial_interval=timedelta(seconds=3),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
        ),
    },
    # Nhóm 4: Suy luận tranh biện LLM sâu (A6..A8, A9, A10..A13)
    "DEEP_LLM_REASONING": {
        "start_to_close": timedelta(minutes=3),
        "schedule_to_close": timedelta(minutes=8),
        "heartbeat": timedelta(seconds=30),
        "task_queue": "heavy-llm-queue",
        "retry_policy": RetryPolicy(
            initial_interval=timedelta(seconds=3),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=45),
            maximum_attempts=3,
        ),
    },
}


def get_agent_policy(node_id: str) -> Dict[str, Any]:
    """Trả về cấu hình Timeout, RetryPolicy và Task Queue tương ứng cho từng Agent."""
    if node_id in ("A1", "A5"):
        return AGENT_EXECUTION_POLICIES["FAST_LOOKUP"]
    elif node_id in ("A2", "A4"):
        return AGENT_EXECUTION_POLICIES["HEAVY_IDP_OCR"]
    elif node_id == "A3":
        return AGENT_EXECUTION_POLICIES["GRAPH_ANALYTICS"]
    else:
        return AGENT_EXECUTION_POLICIES["DEEP_LLM_REASONING"]


def _build_activity_kwargs(node_id: str) -> Dict[str, Any]:
    cfg = get_agent_policy(node_id)
    return {
        "start_to_close_timeout": cfg["start_to_close"],
        "schedule_to_close_timeout": cfg["schedule_to_close"],
        "retry_policy": cfg["retry_policy"],
    }


_ACTIVE_MODEL: Optional[ModelAdapter] = None
_ACTIVE_GATEWAY: Optional[ToolGateway] = None
_ACTIVE_OBSERVER: Optional[Callable[[dict[str, Any]], None]] = None
_ACTIVE_STEP_DELAY_MS: int = 0


# ==============================================================================
# TEMPORAL ACTIVITIES
# ==============================================================================
@activity.defn(name="execute_agent_node")
async def execute_agent_activity(node_id: str, state_dict: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Temporal Activity: Executes a single agent node with heartbeat reporting and fail-degraded safety."""
    if _ACTIVE_OBSERVER:
        try:
            _ACTIVE_OBSERVER({"event": "NODE_STARTED", "node_id": node_id})
        except Exception:
            pass

    if _ACTIVE_STEP_DELAY_MS > 0:
        await asyncio.sleep(_ACTIVE_STEP_DELAY_MS / 1000.0)

    try:
        activity.heartbeat(f"Started executing {node_id}")
    except Exception:
        pass

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

    try:
        model = _ACTIVE_MODEL or ScenarioModel()
        gateway = _ACTIVE_GATEWAY or ToolGateway()
        runtime = AgentRuntime(model, gateway)
        execution = runtime.run(node_id, state, scenario)
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
        patches_out = [
            {
                "node_id": p.node_id,
                "path": p.path,
                "value": p.value,
                "operation": p.operation,
                "base_state_version": p.base_state_version,
            }
            for p in execution.patches
        ]
        try:
            activity.heartbeat(f"Completed executing {node_id}")
        except Exception:
            pass

        if _ACTIVE_OBSERVER:
            try:
                _ACTIVE_OBSERVER({"event": "NODE_COMPLETED", "node_id": node_id, "state_version": state.state_version})
            except Exception:
                pass

        return {
            "node_id": execution.node_id,
            "agent_name": execution.agent_name,
            "model_name": execution.model_name,
            "prompt": execution.prompt,
            "context": execution.context,
            "output": execution.output,
            "patches": patches_out,
            "updated_state": state.public_snapshot(),
        }
    except Exception as exc:
        # Graceful degradation at Activity level when maximum attempts/runtime fails
        error_msg = str(exc)
        input_version = state.state_version
        written_paths = []
        if node_id == "A1":
            state.data_quality = {"status": "DEGRADED_TIMEOUT", "critical_gap": True, "error": error_msg}
            written_paths = ["data_quality"]
        elif node_id == "A2":
            state.analyst_reports.setdefault("cashflow", {})
            state.analyst_reports["cashflow"] = {
                "status": "DEGRADED_TIMEOUT",
                "error_detail": error_msg,
                "node_id": "A2",
                "rating": "FAIL",
                "debt_service_coverage": 0.0,
            }
            written_paths = ["analyst_reports.cashflow"]
        elif node_id == "A3":
            state.analyst_reports.setdefault("transaction_integrity", {})
            state.analyst_reports["transaction_integrity"] = {
                "status": "DEGRADED_TIMEOUT",
                "error_detail": error_msg,
                "node_id": "A3",
                "rating": "CRITICAL",
                "flags": ["TIMEOUT_AML_CHECK_INCOMPLETE"],
            }
            written_paths = ["analyst_reports.transaction_integrity"]
        elif node_id == "A4":
            state.analyst_reports.setdefault("financial_capacity", {})
            state.analyst_reports["financial_capacity"] = {
                "status": "DEGRADED_TIMEOUT",
                "error_detail": error_msg,
                "node_id": "A4",
                "primary_repayment_viable": False,
                "rating": "FAIL",
                "dscr": 0.0,
            }
            written_paths = ["analyst_reports.financial_capacity"]
        elif node_id == "A5":
            state.analyst_reports.setdefault("policy", {})
            state.analyst_reports["policy"] = {
                "status": "DEGRADED_TIMEOUT",
                "escalation_required": True,
                "error": error_msg,
                "rating": "ESCALATE",
            }
            written_paths = ["analyst_reports.policy"]
        elif node_id in ("A6", "A7"):
            state.credit_debate.append({"speaker": node_id, "status": "DEGRADED_TIMEOUT", "summary": f"{node_id} timed out: {error_msg}"})
            written_paths = ["credit_debate"]
        elif node_id == "A8":
            state.credit_assessment = {
                "status": "DEGRADED_TIMEOUT",
                "assessment_summary": f"Incomplete due to {node_id} timeout: {error_msg}",
                "overall_rating": "HIGH_RISK",
            }
            written_paths = ["credit_assessment"]
        elif node_id == "A9":
            state.deal_proposal = {
                "status": "DEGRADED_TIMEOUT",
                "action": "BLOCKED",
                "proposed_limit": 0,
                "error": error_msg,
            }
            written_paths = ["deal_proposal"]
        elif node_id in ("A10", "A11", "A12"):
            state.risk_debate.append({"speaker": node_id, "status": "DEGRADED_TIMEOUT", "summary": f"{node_id} timed out: {error_msg}"})
            written_paths = ["risk_debate"]
        elif node_id == "A13":
            state.coapproval_opinion = {
                "decision": "REJECT_INSUFFICIENT_EVIDENCE",
                "status": "DRAFT",
                "error": f"{node_id} timed out: {error_msg}",
            }
            written_paths = ["coapproval_opinion"]

        state.node_history.append(
            {
                "node_id": node_id,
                "agent_name": AGENT_NAMES.get(node_id, node_id),
                "model": "FallbackDegradedEngine",
                "status": "DEGRADED_TIMEOUT",
                "input_state_version": input_version,
                "output_state_version": state.state_version,
                "prompt_hash": "timeout_error",
                "system_and_role_prompt": "DEGRADED_TIMEOUT",
                "input_context": {},
                "output": {"error": error_msg},
                "written_paths": written_paths,
            }
        )
        evt = AuditEvent(
            event="agent_execution_degraded",
            node_id=node_id,
            details={"error": error_msg, "written_paths": written_paths},
        )
        state.audit.append(evt)
        return {
            "node_id": node_id,
            "agent_name": AGENT_NAMES.get(node_id, node_id),
            "model_name": "FallbackDegradedEngine",
            "prompt": "DEGRADED_TIMEOUT",
            "context": {},
            "output": {"error": error_msg},
            "patches": [],
            "updated_state": state.public_snapshot(),
        }


@activity.defn(name="evaluate_control_node")
async def evaluate_control_activity(state_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Temporal Activity: Deterministic Approval Control Gate (0-LLM Fail-Closed)."""
    if _ACTIVE_OBSERVER:
        try:
            _ACTIVE_OBSERVER({"event": "NODE_STARTED", "node_id": "CONTROL"})
        except Exception:
            pass

    if _ACTIVE_STEP_DELAY_MS > 0:
        await asyncio.sleep(_ACTIVE_STEP_DELAY_MS / 1000.0)

    if "audit" in state_dict and isinstance(state_dict["audit"], list):
        state_dict["audit"] = [AuditEvent(**evt) if isinstance(evt, dict) else evt for evt in state_dict["audit"]]
    state = CreditState(**state_dict)

    opinion = state.coapproval_opinion or {}
    reports = state.analyst_reports or {}
    blocked_reasons: list[str] = []
    if state.data_quality.get("critical_gap") or state.data_quality.get("status") == "DEGRADED_TIMEOUT":
        blocked_reasons.append("CRITICAL_DATA_GAP")
    if reports.get("cashflow", {}).get("status") in ("PARTIAL", "DEGRADED_TIMEOUT"):
        blocked_reasons.append("CASHFLOW_TOOL_OR_COVERAGE_GAP")
    if not reports.get("financial_capacity", {}).get("primary_repayment_viable") or reports.get("financial_capacity", {}).get("status") == "DEGRADED_TIMEOUT":
        blocked_reasons.append("PRIMARY_REPAYMENT_NOT_VIABLE")
    if reports.get("transaction_integrity", {}).get("rating") == "CRITICAL" or reports.get("transaction_integrity", {}).get("status") == "DEGRADED_TIMEOUT":
        blocked_reasons.append("MATERIAL_TRANSACTION_INTEGRITY_RISK")
    if reports.get("policy", {}).get("escalation_required") or reports.get("policy", {}).get("status") == "DEGRADED_TIMEOUT":
        blocked_reasons.append("MANDATORY_POLICY_ESCALATION")

    decision = opinion.get("decision", "REJECT_INSUFFICIENT_EVIDENCE")
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

    if _ACTIVE_OBSERVER:
        try:
            _ACTIVE_OBSERVER({"event": "NODE_COMPLETED", "node_id": "CONTROL", "state_version": state.state_version})
        except Exception:
            pass

    return state.public_snapshot()


# ==============================================================================
# TEMPORAL CHILD & PARENT WORKFLOWS
# ==============================================================================
@workflow.defn(name="Stage1EvidenceChildWorkflow")
class Stage1EvidenceChildWorkflow:
    """Stage 1 Child Workflow: Evidence Production (A1 -> Parallel [A2, A3, A4] -> A5)."""

    @workflow.run
    async def run(self, scenario_id: str, input_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = input_state or {}
        a1_kwargs = _build_activity_kwargs("A1")
        a1_res = await workflow.execute_activity(
            execute_agent_activity,
            args=["A1", state, scenario_id],
            **a1_kwargs,
        )
        current_state = a1_res.get("updated_state", {})

        # Parallel fan-out tasks with dedicated policies
        a2_task = workflow.execute_activity(
            execute_agent_activity,
            args=["A2", current_state, scenario_id],
            **_build_activity_kwargs("A2"),
        )
        a3_task = workflow.execute_activity(
            execute_agent_activity,
            args=["A3", current_state, scenario_id],
            **_build_activity_kwargs("A3"),
        )
        a4_task = workflow.execute_activity(
            execute_agent_activity,
            args=["A4", current_state, scenario_id],
            **_build_activity_kwargs("A4"),
        )

        results = await asyncio.gather(a2_task, a3_task, a4_task, return_exceptions=True)

        for node_id, branch_res in zip(["A2", "A3", "A4"], results):
            if isinstance(branch_res, Exception):
                degraded_report = {
                    "status": "DEGRADED_TIMEOUT",
                    "error_type": type(branch_res).__name__,
                    "error_detail": str(branch_res),
                    "node_id": node_id,
                }
                report_key_map = {
                    "A2": "cashflow",
                    "A3": "transaction_integrity",
                    "A4": "financial_capacity",
                }
                target_key = report_key_map.get(node_id, node_id.lower())
                current_state.setdefault("analyst_reports", {})[target_key] = degraded_report
                current_state.setdefault("audit", []).append(
                    {
                        "event": "agent_execution_degraded",
                        "node_id": node_id,
                        "details": {"error": str(branch_res)},
                    }
                )
            else:
                branch_state = branch_res.get("updated_state", {})
                if "analyst_reports" in branch_state:
                    current_state.setdefault("analyst_reports", {}).update(branch_state["analyst_reports"])
                if "node_history" in branch_state and isinstance(branch_state["node_history"], list):
                    for nh in branch_state["node_history"]:
                        if nh["node_id"] not in [x["node_id"] for x in current_state.get("node_history", [])]:
                            current_state.setdefault("node_history", []).append(nh)
                if "tool_history" in branch_state and isinstance(branch_state["tool_history"], list):
                    for th in branch_state["tool_history"]:
                        if th not in current_state.get("tool_history", []):
                            current_state.setdefault("tool_history", []).append(th)
                if "audit" in branch_state and isinstance(branch_state["audit"], list):
                    for a_evt in branch_state["audit"]:
                        if a_evt not in current_state.get("audit", []):
                            current_state.setdefault("audit", []).append(a_evt)

        a5_kwargs = _build_activity_kwargs("A5")
        a5_res = await workflow.execute_activity(
            execute_agent_activity,
            args=["A5", current_state, scenario_id],
            **a5_kwargs,
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
                **_build_activity_kwargs(node),
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
            **_build_activity_kwargs("A9"),
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
                **_build_activity_kwargs(node),
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
            **_build_activity_kwargs("A13"),
        )
        return res.get("updated_state", input_state)


@workflow.defn(name="CreditCoApprovalWorkflow")
class CreditCoApprovalWorkflow:
    """Parent Temporal Workflow: Multi-Agent Credit Co-Approval DAG coordinating 5 Stage Child Workflows
    and the Deterministic Approval Control Gate Activity.
    """

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

        # Final Control Plane Gate Activity (Deterministic 0-LLM)
        final_state = await workflow.execute_activity(
            evaluate_control_activity,
            args=[s5_state],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {"status": "COMPLETED", "scenario_id": scenario_id, "final_state": final_state}


TEMPORAL_WORKFLOWS = [
    CreditCoApprovalWorkflow,
    Stage1EvidenceChildWorkflow,
    Stage2ChallengeChildWorkflow,
    Stage3StructuringChildWorkflow,
    Stage4RiskCommitteeChildWorkflow,
    Stage5CoApprovalChildWorkflow,
]
TEMPORAL_ACTIVITIES = [execute_agent_activity, evaluate_control_activity]


# ==============================================================================
# NATIVE TEMPORAL WORKFLOW ENGINE
# ==============================================================================
class TemporalWorkflowEngine:
    """Enterprise Orchestration Engine executing workflows exclusively on a Native Temporal Server."""

    def __init__(
        self,
        model: Optional[ModelAdapter] = None,
        gateway: Optional[ToolGateway] = None,
        db_repository: Optional[StateRepository] = None,
        step_delay_ms: int = 0,
        target_host: Optional[str] = None,
        task_queue: Optional[str] = None,
    ) -> None:
        self.model = model or ScenarioModel()
        self.gateway = gateway or ToolGateway()
        self.repository = db_repository or StateRepository(db_path=":memory:")
        self.step_delay_ms = step_delay_ms
        self.target_host = target_host or CONFIG.TEMPORAL_TARGET_HOST
        self.task_queue = task_queue or CONFIG.TEMPORAL_TASK_QUEUE
        self.runtime = AgentRuntime(self.model, self.gateway)

    async def execute_workflow_async(self, scenario_id: str) -> Tuple[CreditState, list[dict[str, Any]], int]:
        """Executes workflow natively on Temporal Server cluster or native test server."""
        if scenario_id not in SCENARIOS:
            raise KeyError(f"unknown scenario: {scenario_id}")
        scenario = SCENARIOS[scenario_id]

        global _ACTIVE_MODEL, _ACTIVE_GATEWAY
        _ACTIVE_MODEL = self.model
        _ACTIVE_GATEWAY = self.gateway

        started = time.perf_counter()
        run_uid = str(uuid.uuid4())[:8]
        workflow_id = f"credit-wf-{scenario_id}-{run_uid}"

        cluster_online = is_temporal_cluster_alive(self.target_host)
        if cluster_online:
            client = await Client.connect(self.target_host)
            async with Worker(
                client,
                task_queue=self.task_queue,
                workflows=TEMPORAL_WORKFLOWS,
                activities=TEMPORAL_ACTIVITIES,
            ):
                res = await client.execute_workflow(
                    CreditCoApprovalWorkflow.run,
                    scenario_id,
                    id=workflow_id,
                    task_queue=self.task_queue,
                )
                final_state_dict = res.get("final_state", {})
        else:
            async with await WorkflowEnvironment.start_time_skipping() as env:
                async with Worker(
                    env.client,
                    task_queue=self.task_queue,
                    workflows=TEMPORAL_WORKFLOWS,
                    activities=TEMPORAL_ACTIVITIES,
                ):
                    res = await env.client.execute_workflow(
                        CreditCoApprovalWorkflow.run,
                        scenario_id,
                        id=workflow_id,
                        task_queue=self.task_queue,
                    )
                    final_state_dict = res.get("final_state", {})

        duration_ms = round((time.perf_counter() - started) * 1000)

        # Reconstruct CreditState from final state snapshot
        if "audit" in final_state_dict and isinstance(final_state_dict["audit"], list):
            final_state_dict["audit"] = [
                AuditEvent(**evt) if isinstance(evt, dict) else evt for evt in final_state_dict["audit"]
            ]
        state = CreditState(**final_state_dict)

        # Build 14 Checkpoints from execution history with incremental state snapshots
        checkpoints: list[dict[str, Any]] = []
        node_map = {n["node_id"]: n for n in state.node_history}
        running_state = CreditState(case_id=state.case_id, scenario_id=state.scenario_id, run_id=state.run_id)

        for idx, node_id in enumerate(PIPELINE, start=1):
            nh = node_map.get(node_id, {})
            agent_name = nh.get("agent_name", AGENT_NAMES.get(node_id, node_id))
            changed_paths = nh.get("written_paths", [node_id.lower()])

            if node_id == "A1":
                running_state.case_file = state.case_file
                running_state.evidence_catalog = state.evidence_catalog
                running_state.data_quality = state.data_quality
            elif node_id in ("A2", "A3", "A4", "A5"):
                report_key_map = {"A2": "cashflow", "A3": "transaction_integrity", "A4": "financial_capacity", "A5": "policy"}
                k = report_key_map[node_id]
                if k in state.analyst_reports:
                    running_state.analyst_reports[k] = state.analyst_reports[k]
            elif node_id in ("A6", "A7"):
                running_state.credit_debate = [d for d in state.credit_debate if d.get("speaker") in ("A6", "A7", "CREDIT_ADVOCATE", "RISK_CHALLENGER")]
            elif node_id == "A8":
                running_state.credit_assessment = state.credit_assessment
            elif node_id == "A9":
                running_state.deal_proposal = state.deal_proposal
            elif node_id in ("A10", "A11", "A12"):
                running_state.risk_debate = [d for d in state.risk_debate if d.get("speaker") in ("A10", "A11", "A12", "UPSIDE_RISK_MANAGER", "CONSERVATIVE_RISK_MANAGER", "NEUTRAL_RISK_MANAGER")]
            elif node_id == "A13":
                running_state.coapproval_opinion = state.coapproval_opinion

            running_state.state_version = idx
            cp = {
                "checkpoint_id": f"CP-{idx:02d}",
                "after_node": node_id,
                "agent_name": agent_name,
                "state_version": idx,
                "state_hash": hashlib.sha256(f"{node_id}-{idx}".encode()).hexdigest(),
                "changed_paths": changed_paths,
                "state_snapshot": running_state.explainable_snapshot(),
            }
            checkpoints.append(cp)
            self.repository.save_checkpoint(state.run_id, cp)

        # Add Control Checkpoint CP-14
        running_state.control = state.control
        running_state.state_version = 14
        ctrl_cp = {
            "checkpoint_id": "CP-14",
            "after_node": "CONTROL",
            "agent_name": "Deterministic Approval Control",
            "state_version": 14,
            "state_hash": hashlib.sha256(repr(state.control).encode()).hexdigest(),
            "changed_paths": ["control"],
            "state_snapshot": running_state.explainable_snapshot(),
        }
        checkpoints.append(ctrl_cp)
        self.repository.save_checkpoint(state.run_id, ctrl_cp)

        # Persist case to localDB
        self.repository.save_case(state)
        return state, checkpoints, duration_ms

    def execute_workflow(
        self, scenario_id: str, observer: Optional[Callable[[dict[str, Any]], None]] = None
    ) -> Tuple[CreditState, list[dict[str, Any]], int]:
        """Synchronous wrapper for execute_workflow_async running on Temporal Server."""
        global _ACTIVE_OBSERVER, _ACTIVE_STEP_DELAY_MS
        _ACTIVE_OBSERVER = observer
        _ACTIVE_STEP_DELAY_MS = self.step_delay_ms
        try:
            try:
                state, checkpoints, duration_ms = asyncio.run(self.execute_workflow_async(scenario_id))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    state, checkpoints, duration_ms = loop.run_until_complete(self.execute_workflow_async(scenario_id))
                finally:
                    loop.close()
        finally:
            _ACTIVE_OBSERVER = None
            _ACTIVE_STEP_DELAY_MS = 0

        return state, checkpoints, duration_ms


async def start_temporal_worker(target_host: Optional[str] = None, task_queue: Optional[str] = None) -> None:
    """Starts a native Temporal Worker listening for workflow and activity tasks."""
    host = target_host or CONFIG.TEMPORAL_TARGET_HOST
    queue = task_queue or CONFIG.TEMPORAL_TASK_QUEUE
    client = await Client.connect(host)
    worker = Worker(
        client,
        task_queue=queue,
        workflows=TEMPORAL_WORKFLOWS,
        activities=TEMPORAL_ACTIVITIES,
    )
    print(f"Temporal Worker listening on queue '{queue}' at {host}...")
    await worker.run()
