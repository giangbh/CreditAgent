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

    def test_circuit_breaker_trips_to_open_and_fallbacks(self):
        from credit_agent_poc.tools import CircuitBreaker, CircuitState
        scenario = SCENARIOS["reject_tool_failure"]
        state = CreditState(case_id="CASE-FAIL", scenario_id=scenario.scenario_id, run_id="RUN-FAIL")
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=1.0)
        gateway = ToolGateway(circuit_breaker=cb)

        # Call 1 fails (ToolExecutionError) -> failure_count = 1
        res1 = gateway.call("A2", state, scenario, "compute_cashflow_metrics")
        self.assertEqual(res1["status"], "ERROR")
        self.assertEqual(cb.get_state("compute_cashflow_metrics"), CircuitState.CLOSED)

        # Call 2 fails -> failure_count = 2 >= threshold -> trips to OPEN
        res2 = gateway.call("A2", state, scenario, "compute_cashflow_metrics")
        self.assertEqual(res2["status"], "ERROR")
        self.assertEqual(cb.get_state("compute_cashflow_metrics"), CircuitState.OPEN)
        self.assertEqual(state.audit[-2].event, "circuit_breaker_opened")

        # Call 3 while OPEN -> activates Degraded Fallback Mode
        res3 = gateway.call("A2", state, scenario, "compute_cashflow_metrics")
        self.assertEqual(res3["status"], "DEGRADED_MODE")
        self.assertTrue(res3["degraded"])
        self.assertEqual(res3["reason"], "CIRCUIT_BREAKER_OPEN")
        self.assertEqual(state.audit[-1].event, "tool_call_fallback")

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

    def test_enterprise_audit_logger_end_to_end_traceability(self):
        import json
        import os
        from credit_agent_poc.logger import EnterpriseAuditLogger
        
        result = CreditOrchestrator().run("approve_conditions")
        trace_id = result.state.trace_id
        self.assertTrue(trace_id.startswith("tr-"))
        
        log_file = EnterpriseAuditLogger.get_logger().log_file_path
        self.assertTrue(os.path.exists(log_file))
        
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        matching_logs = [json.loads(line) for line in lines if json.loads(line).get("trace_id") == trace_id]
        self.assertGreater(len(matching_logs), 10)
        
        components = {log["component"] for log in matching_logs}
        self.assertIn("AGENT_RUNTIME", components)
        self.assertIn("TOOL_GATEWAY", components)
        self.assertIn("LLM_ADAPTER", components)

    def test_stage2_dialectical_debate_synthesis_and_covenants(self):
        result = CreditOrchestrator().run("approve_conditions")
        debate = result.state.credit_debate
        assessment = result.state.credit_assessment

        # Verify A6 Advocate output
        a6_turn = next((t for t in debate if t["speaker"] == "CREDIT_ADVOCATE"), None)
        self.assertIsNotNone(a6_turn)
        self.assertIn("strengths", a6_turn)
        self.assertIn("growth_rationale", a6_turn)

        # Verify A7 Challenger output
        a7_turn = next((t for t in debate if t["speaker"] == "RISK_CHALLENGER"), None)
        self.assertIsNotNone(a7_turn)
        self.assertIn("downside_scenarios", a7_turn)
        self.assertIn("attack_vectors", a7_turn)

        # Verify A8 Assessment Manager synthesis & covenants
        self.assertIn("synthesis_matrix", assessment)
        self.assertIn("required_covenants", assessment)
        self.assertIn("conditions_precedent", assessment)
        self.assertGreater(len(assessment["synthesis_matrix"]), 0)
        self.assertGreater(len(assessment["required_covenants"]), 0)


if __name__ == "__main__":
    unittest.main()
