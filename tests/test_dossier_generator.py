from __future__ import annotations

import unittest
from credit_agent_poc.dossier_generator import SyntheticDossierGenerator
from credit_agent_poc.orchestrator import CreditOrchestrator
from credit_agent_poc.scenarios import SCENARIOS


class TestSyntheticDossierGenerator(unittest.TestCase):
    def test_generate_single_scenario(self):
        scenario = SyntheticDossierGenerator.generate_scenario()
        self.assertIsNotNone(scenario.scenario_id)
        self.assertTrue(len(scenario.borrower["name"]) > 5)
        self.assertTrue(scenario.borrower["tax_code"].startswith(("010", "030", "360", "370", "040")))
        self.assertTrue(scenario.declared_revenue > 0)
        self.assertTrue(scenario.request["amount"] > 0)

    def test_generate_specific_archetypes(self):
        healthy = SyntheticDossierGenerator.generate_scenario(archetype="HEALTHY_PRIME")
        self.assertEqual(healthy.expected_outcome, "APPROVE_WITH_CONDITIONS")
        self.assertGreaterEqual(healthy.dscr, 1.45)
        self.assertTrue(healthy.documents_complete)

        aml = SyntheticDossierGenerator.generate_scenario(archetype="SUSPICIOUS_AML")
        self.assertEqual(aml.expected_outcome, "ESCALATE_TO_CRO_RISK")
        self.assertGreaterEqual(aml.circular_funds_score, 0.80)

        weak = SyntheticDossierGenerator.generate_scenario(archetype="WEAK_CASHFLOW")
        self.assertEqual(weak.expected_outcome, "REJECT_INSUFFICIENT_EVIDENCE")
        self.assertLess(weak.dscr, 1.0)

        incomplete = SyntheticDossierGenerator.generate_scenario(archetype="INCOMPLETE_DOCS")
        self.assertEqual(incomplete.expected_outcome, "REJECT_INSUFFICIENT_EVIDENCE")
        self.assertFalse(incomplete.documents_complete)

    def test_generate_batch_and_register(self):
        scenarios = SyntheticDossierGenerator.generate_batch(count=5)
        self.assertEqual(len(scenarios), 5)
        for s in scenarios:
            self.assertIn(s.scenario_id, SCENARIOS)

    def test_execute_dynamic_scenario_in_orchestrator(self):
        scenario = SyntheticDossierGenerator.generate_and_register(archetype="HEALTHY_PRIME")
        orchestrator = CreditOrchestrator()
        result = orchestrator.run(scenario.scenario_id)
        self.assertIsNotNone(result.actual_outcome)
        self.assertEqual(result.state.scenario_id, scenario.scenario_id)
        self.assertEqual(len(result.state.node_history), 13)
        self.assertEqual(result.state.control["status"], "READY_FOR_HUMAN_REVIEW")


if __name__ == "__main__":
    unittest.main()
