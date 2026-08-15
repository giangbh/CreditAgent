import unittest

from credit_agent_poc.models import CreditState, StatePatch, StateValidationError, ToolAccessError, apply_patch
from credit_agent_poc.model import ScenarioModel
from credit_agent_poc.orchestrator import CreditOrchestrator, PIPELINE
from credit_agent_poc.scenarios import SCENARIOS
from credit_agent_poc.tools import TOOL_ALLOWLIST, ToolGateway


class OrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {result.scenario_id: result for result in CreditOrchestrator().run_all()}

    def test_all_scenarios_match_expected_outcomes(self):
        self.assertEqual(set(self.results), set(SCENARIOS))
        for result in self.results.values():
            with self.subTest(result.scenario_id):
                self.assertTrue(result.outcome_matches)

    def test_all_thirteen_agents_execute_in_order(self):
        for result in self.results.values():
            with self.subTest(result.scenario_id):
                self.assertEqual([node["node_id"] for node in result.state.node_history], PIPELINE)
                self.assertEqual(len(result.state.node_history), 13)
                self.assertEqual(len(result.checkpoints), 14)

    def test_control_plane_never_grants_ai_approval_or_disbursement(self):
        for result in self.results.values():
            with self.subTest(result.scenario_id):
                self.assertFalse(result.state.control["ai_can_approve"])
                self.assertFalse(result.state.control["ai_can_disburse"])
                self.assertNotIn("APPROVE", result.state.control["allowed_actions"])
                self.assertNotIn("DISBURSE", result.state.control["allowed_actions"])

    def test_backend_failure_fails_closed(self):
        result = self.results["reject_tool_failure"]
        failed_calls = [call for call in result.state.tool_history if call["status"] == "ERROR"]
        self.assertEqual([call["tool_name"] for call in failed_calls], ["compute_cashflow_metrics"])
        self.assertEqual(result.actual_outcome, "REJECT_INSUFFICIENT_EVIDENCE")
        self.assertIn("CASHFLOW_TOOL_OR_COVERAGE_GAP", result.state.control["blocked_reasons"])

    def test_collateral_does_not_cure_weak_repayment(self):
        result = self.results["reject_weak_cashflow_high_collateral"]
        self.assertEqual(result.actual_outcome, "REJECT_INSUFFICIENT_EVIDENCE")
        self.assertIn("PRIMARY_REPAYMENT_NOT_VIABLE", result.state.control["blocked_reasons"])

    def test_approve_scenario_has_explicit_condition(self):
        result = self.results["approve_conditions"]
        conditions = result.state.coapproval_opinion["conditions"]
        self.assertEqual(conditions[0]["condition_id"], "COND-CONCENTRATION")
        self.assertEqual(result.state.control["status"], "READY_FOR_HUMAN_REVIEW")

    def test_agent_trace_contains_bounded_input_output_and_tools(self):
        result = self.results["approve_conditions"]
        for node in result.state.node_history:
            with self.subTest(node["node_id"]):
                self.assertIsInstance(node["input_context"], dict)
                self.assertIsInstance(node["output"], dict)
                self.assertTrue(node["system_and_role_prompt"])
        self.assertTrue(all("node_id" in call for call in result.state.tool_history))

    def test_every_checkpoint_contains_bounded_explainable_state(self):
        result = self.results["approve_conditions"]
        for checkpoint in result.checkpoints:
            with self.subTest(checkpoint["after_node"]):
                snapshot = checkpoint["state_snapshot"]
                self.assertEqual(snapshot["state_version"], checkpoint["state_version"])
                self.assertTrue(checkpoint["changed_paths"])
                self.assertTrue(checkpoint["state_hash"])
                self.assertNotIn("audit", snapshot)
                self.assertNotIn("tool_history", snapshot)
                self.assertNotIn("node_history", snapshot)

    def test_checkpoint_values_show_state_evolution(self):
        checkpoints = self.results["approve_conditions"].checkpoints
        after_a1 = next(cp for cp in checkpoints if cp["after_node"] == "A1")
        after_a2 = next(cp for cp in checkpoints if cp["after_node"] == "A2")
        after_control = checkpoints[-1]
        self.assertEqual(after_a1["state_snapshot"]["analyst_reports"], {})
        self.assertIn("cashflow", after_a2["state_snapshot"]["analyst_reports"])
        self.assertEqual(after_control["state_snapshot"]["control"]["status"], "READY_FOR_HUMAN_REVIEW")

    def test_observer_reports_start_and_completion_for_every_node(self):
        events = []
        CreditOrchestrator().run("approve_conditions", observer=events.append)
        for node_id in PIPELINE + ["CONTROL"]:
            with self.subTest(node_id):
                node_events = [event["event"] for event in events if event["node_id"] == node_id]
                self.assertEqual(node_events, ["NODE_STARTED", "NODE_COMPLETED"])


class BoundaryTests(unittest.TestCase):
    def test_state_ownership_rejects_wrong_path(self):
        state = CreditState(case_id="CASE-X", scenario_id="test", run_id="RUN-X")
        with self.assertRaises(StateValidationError):
            apply_patch(
                state,
                StatePatch(node_id="A6", path="control", value={"status": "APPROVED"}, base_state_version=0),
            )

    def test_stale_patch_is_rejected(self):
        state = CreditState(case_id="CASE-X", scenario_id="test", run_id="RUN-X", state_version=2)
        with self.assertRaises(StateValidationError):
            apply_patch(state, StatePatch(node_id="A8", path="credit_assessment", value={}, base_state_version=1))

    def test_tool_gateway_denies_tool_free_agent(self):
        scenario = SCENARIOS["approve_conditions"]
        state = CreditState(case_id="CASE-X", scenario_id=scenario.scenario_id, run_id="RUN-X")
        with self.assertRaises(ToolAccessError):
            ToolGateway().call("A13", state, scenario, "evaluate_policy_rule")
        self.assertEqual(state.audit[-1].event, "tool_call_denied")

    def test_only_evidence_and_structuring_agents_have_tools(self):
        for node_id in ["A6", "A7", "A8", "A10", "A11", "A12", "A13"]:
            self.assertEqual(TOOL_ALLOWLIST[node_id], set())

    def test_tool_gateway_rate_limiting(self):
        from credit_agent_poc.models import ToolRateLimitError
        scenario = SCENARIOS["approve_conditions"]
        state = CreditState(case_id="CASE-X", scenario_id=scenario.scenario_id, run_id="RUN-X")
        gateway = ToolGateway(max_calls_per_second=2)
        gateway.call("A1", state, scenario, "document_inventory")
        gateway.call("A1", state, scenario, "classify_document", {"document_id": "DOC-1"})
        with self.assertRaises(ToolRateLimitError):
            gateway.call("A1", state, scenario, "extract_document_fields")
        self.assertEqual(state.audit[-1].event, "tool_call_rate_limited")

    def test_control_rejects_an_unsafe_approve_opinion(self):
        class UnsafeApproveModel(ScenarioModel):
            @staticmethod
            def _a13(context):
                return {
                    "status": "DRAFT",
                    "decision": "APPROVE_WITH_CONDITIONS",
                    "confidence": 0.99,
                    "conditions": [],
                    "residual_risks": [],
                    "human_final_authority_required": True,
                }

        result = CreditOrchestrator(model=UnsafeApproveModel()).run("reject_weak_cashflow_high_collateral")
        self.assertEqual(result.state.control["status"], "BLOCKED_INVALID_OPINION")
        self.assertFalse(result.state.control["opinion_validated"])
        self.assertIn("PRIMARY_REPAYMENT_NOT_VIABLE", result.state.control["blocked_reasons"])


if __name__ == "__main__":
    unittest.main()
