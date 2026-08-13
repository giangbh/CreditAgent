import unittest

from credit_agent_poc.orchestrator import CreditOrchestrator


class OutcomeClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {
            result.scenario_id: result.to_dict()
            for result in CreditOrchestrator().run_all()
        }

    def assert_levels(self, scenario_id, expected):
        outcomes = self.results[scenario_id]["node_outcomes"]
        for node_id, level in expected.items():
            with self.subTest(scenario=scenario_id, node=node_id):
                self.assertEqual(outcomes[node_id]["level"], level)
                self.assertEqual(outcomes[node_id]["execution_status"], "COMPLETED")
                self.assertTrue(outcomes[node_id]["reason"])

    def test_conditional_approval_shows_warnings_without_false_failures(self):
        self.assert_levels(
            "approve_conditions",
            {"A2": "WARNING", "A9": "WARNING", "A13": "WARNING", "CONTROL": "PASS"},
        )

    def test_policy_exception_is_visibly_escalated(self):
        self.assert_levels(
            "escalate_policy_exception",
            {"A5": "ESCALATE", "A7": "ESCALATE", "A9": "ESCALATE", "A13": "ESCALATE", "CONTROL": "ESCALATE"},
        )

    def test_circular_funds_separates_failed_finding_from_escalation_route(self):
        self.assert_levels(
            "escalate_circular_funds",
            {"A3": "FAIL", "A5": "ESCALATE", "A7": "FAIL", "A13": "ESCALATE", "CONTROL": "ESCALATE"},
        )

    def test_missing_evidence_and_weak_repayment_are_failures(self):
        self.assert_levels(
            "reject_missing_evidence",
            {"A1": "FAIL", "A4": "FAIL", "A8": "FAIL", "A9": "FAIL", "A13": "FAIL", "CONTROL": "FAIL"},
        )

    def test_backend_tool_failure_fails_closed(self):
        self.assert_levels(
            "reject_tool_failure",
            {"A2": "FAIL", "A8": "FAIL", "A13": "FAIL", "CONTROL": "FAIL"},
        )

    def test_outcomes_are_auditable_against_versioned_policy(self):
        result = self.results["approve_conditions"]
        self.assertEqual(result["outcome_policy"]["policy_id"], "credit-agent-business-outcome")
        self.assertEqual(result["outcome_policy"]["version"], "1.1.0")
        for outcome in result["node_outcomes"].values():
            self.assertEqual(outcome["rule_version"], "1.1.0")
            self.assertTrue(outcome["reason_code"])

    def test_circular_funds_risk_is_traced_to_control(self):
        propagation = self.results["escalate_circular_funds"]["risk_propagation"]
        circular = next(risk for risk in propagation["risks"] if risk["risk_code"] == "CIRCULAR_FUNDS_PATTERN")
        self.assertEqual(circular["source_node"], "A3")
        self.assertEqual(circular["path"], ["A3", "A5", "A7", "A8", "A10", "A11", "A12", "A13", "CONTROL"])
        self.assertEqual(circular["terminal_node"], "CONTROL")

    def test_cashflow_condition_propagates_into_conditional_opinion(self):
        propagation = self.results["approve_conditions"]["risk_propagation"]
        cashflow = next(risk for risk in propagation["risks"] if risk["risk_code"] == "CASHFLOW_QUALITY_OR_COVERAGE")
        self.assertEqual(cashflow["source_node"], "A2")
        self.assertIn("A9", cashflow["path"])
        self.assertEqual(cashflow["terminal_node"], "A13")


if __name__ == "__main__":
    unittest.main()
