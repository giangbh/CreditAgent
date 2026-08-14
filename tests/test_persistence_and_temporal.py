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


if __name__ == "__main__":
    unittest.main()
