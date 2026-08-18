from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from credit_agent_poc.db import StateRepository
from credit_agent_poc.models import AuditEvent, CreditState
from credit_agent_poc.orchestrator import CreditOrchestrator
from credit_agent_poc.workflow import TemporalWorkflowEngine


class PersistenceAndTemporalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_credit_agent.db"
        self.repository = StateRepository(db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sqlite_repository_save_and_load_case(self) -> None:
        state = CreditState(case_id="CASE-TEST-01", scenario_id="approve_conditions", run_id="run-123")
        state.state_version = 5
        state.coapproval_opinion = {"decision": "APPROVE_WITH_CONDITIONS"}
        state.audit.append(AuditEvent(event="test_event", node_id="A1", details={"key": "val"}))

        self.repository.save_case(state)

        loaded = self.repository.load_case("CASE-TEST-01")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.case_id, "CASE-TEST-01")
        self.assertEqual(loaded.state_version, 5)
        self.assertEqual(loaded.coapproval_opinion["decision"], "APPROVE_WITH_CONDITIONS")
        self.assertEqual(len(loaded.audit), 1)
        self.assertEqual(loaded.audit[0].event, "test_event")

    def test_sqlite_repository_checkpoints_and_audit(self) -> None:
        checkpoint = {
            "checkpoint_id": "CP-01",
            "after_node": "A1",
            "agent_name": "Intake & Evidence Agent",
            "state_version": 1,
            "state_hash": "dummyhash123",
            "changed_paths": ["case_file"],
            "state_snapshot": {"case_id": "CASE-TEST-01"},
        }
        self.repository.save_checkpoint("run-123", checkpoint)

        cps = self.repository.get_checkpoints("run-123")
        self.assertEqual(len(cps), 1)
        self.assertEqual(cps[0]["checkpoint_id"], "CP-01")
        self.assertEqual(cps[0]["after_node"], "A1")
        self.assertEqual(cps[0]["changed_paths"], ["case_file"])

    def test_temporal_workflow_engine_executes_scenarios(self) -> None:
        temporal_engine = TemporalWorkflowEngine(db_repository=self.repository)
        state, checkpoints, duration_ms = temporal_engine.execute_workflow("approve_conditions")

        self.assertEqual(state.scenario_id, "approve_conditions")
        self.assertEqual(state.coapproval_opinion["decision"], "APPROVE_WITH_CONDITIONS")
        self.assertEqual(len(checkpoints), 14)
        self.assertGreater(duration_ms, 0)

        # Verify state persisted into SQLite localDB
        loaded = self.repository.load_case(state.case_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.run_id, state.run_id)

    def test_orchestrator_defaults_to_temporal_and_localdb(self) -> None:
        orchestrator = CreditOrchestrator(db_repository=self.repository, engine="temporal")
        result = orchestrator.run("approve_conditions")

        self.assertTrue(result.outcome_matches)
        self.assertEqual(result.actual_outcome, "APPROVE_WITH_CONDITIONS")
        self.assertEqual(len(result.checkpoints), 14)

    def test_agent_policies_configuration(self) -> None:
        from credit_agent_poc.workflow import AGENT_EXECUTION_POLICIES, get_agent_policy, PIPELINE

        self.assertIn("FAST_LOOKUP", AGENT_EXECUTION_POLICIES)
        self.assertIn("HEAVY_IDP_OCR", AGENT_EXECUTION_POLICIES)
        self.assertIn("GRAPH_ANALYTICS", AGENT_EXECUTION_POLICIES)
        self.assertIn("DEEP_LLM_REASONING", AGENT_EXECUTION_POLICIES)

        for node_id in PIPELINE:
            policy = get_agent_policy(node_id)
            self.assertIsNotNone(policy)
            self.assertIn("start_to_close", policy)
            self.assertIn("schedule_to_close", policy)
            self.assertIn("retry_policy", policy)
            self.assertIn("task_queue", policy)

        # Verify specific queue assignments
        self.assertEqual(get_agent_policy("A1")["task_queue"], "fast-tools-queue")
        self.assertEqual(get_agent_policy("A2")["task_queue"], "idp-ocr-queue")
        self.assertEqual(get_agent_policy("A3")["task_queue"], "fast-tools-queue")
        self.assertEqual(get_agent_policy("A4")["task_queue"], "idp-ocr-queue")
        self.assertEqual(get_agent_policy("A6")["task_queue"], "heavy-llm-queue")

    def test_temporal_stage1_fanout_resilient_to_agent_degradation(self) -> None:
        temporal_engine = TemporalWorkflowEngine(db_repository=self.repository)

        from credit_agent_poc.agents import AgentRuntime
        original_run = AgentRuntime.run
        def failing_run(self_runtime, node_id, b_state, sc):
            if node_id == "A4":
                raise TimeoutError("OCR Service timed out after 3 retries (5 minutes)")
            return original_run(self_runtime, node_id, b_state, sc)

        AgentRuntime.run = failing_run
        try:
            state, checkpoints, duration = temporal_engine.execute_workflow("approve_conditions")

            # Check that A4 degradation was recorded gracefully without crashing
            self.assertIn("financial_capacity", state.analyst_reports)
            self.assertEqual(state.analyst_reports["financial_capacity"]["status"], "DEGRADED_TIMEOUT")
            self.assertIn("OCR Service timed out", state.analyst_reports["financial_capacity"]["error_detail"])

            # Check audit event for degradation
            degraded_events = [e for e in state.audit if e.event == "agent_execution_degraded"]
            self.assertGreaterEqual(len(degraded_events), 1)
            self.assertEqual(degraded_events[0].node_id, "A4")
        finally:
            AgentRuntime.run = original_run


if __name__ == "__main__":
    unittest.main()



