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


if __name__ == "__main__":
    unittest.main()
