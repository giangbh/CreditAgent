from __future__ import annotations

import unittest
from pathlib import Path

from credit_agent_poc.explainer import CaseExplainer, CaseExplanationReport
from credit_agent_poc.orchestrator import CreditOrchestrator
from credit_agent_poc.scenarios import SCENARIOS


class TestCaseExplainer(unittest.TestCase):
    def setUp(self):
        self.orchestrator = CreditOrchestrator()

    def test_explain_approve_conditions_scenario(self):
        result = self.orchestrator.run("approve_conditions")
        report = CaseExplainer.explain(result.state)

        self.assertIsInstance(report, CaseExplanationReport)
        self.assertEqual(report.scenario_id, "approve_conditions")
        self.assertEqual(report.final_ai_decision, "APPROVE_WITH_CONDITIONS")
        self.assertEqual(report.risk_level, "LOW")
        self.assertEqual(len(report.agent_explanations), 13)

        # Check 13 agent nodes
        node_ids = [a.node_id for a in report.agent_explanations]
        self.assertEqual(node_ids, [f"A{i}" for i in range(1, 14)])

        # Check specific agent explanations
        a1 = report.agent_explanations[0]
        self.assertEqual(a1.node_id, "A1")
        self.assertEqual(a1.verdict_signal, "GREEN")
        self.assertIn("Bóc tách OCR", a1.rationale)

        a4 = report.agent_explanations[3]
        self.assertEqual(a4.node_id, "A4")
        self.assertEqual(a4.verdict_signal, "GREEN")
        self.assertIn("dscr", a4.outputs_summary)

        # Check Markdown and HTML output generation
        md = report.to_markdown()
        self.assertIn("TỜ TRÌNH TÓM TẮT & GIẢI TRÌNH", md)
        self.assertIn("BẢNG MA TRẬN GIẢI TRÌNH CHI TIẾT 13 AGENTS", md)

        html = report.to_html()
        self.assertIn("<!doctype html>", html)
        self.assertIn("Tóm Tắt Điều Hành", html)

    def test_explain_reject_scenarios(self):
        # Test insufficient evidence scenario
        result = self.orchestrator.run("reject_missing_evidence")
        report = CaseExplainer.explain(result.state)

        self.assertEqual(report.final_ai_decision, "REJECT_INSUFFICIENT_EVIDENCE")
        self.assertEqual(report.risk_level, "CRITICAL")
        self.assertTrue(len(report.primary_decision_drivers) > 0)

        # Test circular AML transactions scenario
        result_aml = self.orchestrator.run("escalate_circular_funds")
        report_aml = CaseExplainer.explain(result_aml.state)
        self.assertEqual(report_aml.final_ai_decision, "ESCALATE_TO_CRO_RISK")
        self.assertEqual(report_aml.risk_level, "HIGH")

        a3 = report_aml.agent_explanations[2]
        self.assertEqual(a3.node_id, "A3")
        self.assertEqual(a3.verdict_signal, "RED")
        self.assertIn("AML", a3.rationale)

    def test_all_scenarios_explainer_integrity(self):
        for sc in SCENARIOS:
            result = self.orchestrator.run(sc)
            report = CaseExplainer.explain(result.state)
            self.assertEqual(len(report.agent_explanations), 13)
            self.assertEqual(len(report.stage_syntheses), 5)
            self.assertIsNotNone(report.to_dict())


if __name__ == "__main__":
    unittest.main()
