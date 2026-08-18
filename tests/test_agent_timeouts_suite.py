from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from credit_agent_poc.db import StateRepository
from credit_agent_poc.workflow import TemporalWorkflowEngine, PIPELINE


class AgentTimeoutMatrixTestSuite(unittest.TestCase):
    """Kiểm thử chuyên sâu 13 kịch bản Timeout độc lập cho từng Agent (A1 -> A13).
    Mục tiêu: Đảm bảo khi bất kỳ Agent nào bị timeout/lỗi, hệ thống KHÔNG crash sập,
    ghi nhận trạng thái DEGRADED_TIMEOUT minh bạch và thực thi đúng nguyên tắc Fail-Closed.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_timeouts.db"
        self.repository = StateRepository(db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run_with_single_agent_timeout(self, timed_out_node: str):
        """Helper chạy workflow kịch bản approve_conditions với 1 agent bị timeout."""
        engine = TemporalWorkflowEngine(db_repository=self.repository)
        from credit_agent_poc.agents import AgentRuntime
        original_run = AgentRuntime.run

        def failing_run(self_runtime, node_id, state, scenario):
            if node_id == timed_out_node:
                raise TimeoutError(f"Simulated Activity Timeout for agent {node_id} after 3 retries")
            return original_run(self_runtime, node_id, state, scenario)

        AgentRuntime.run = failing_run
        try:
            state, checkpoints, duration_ms = engine.execute_workflow("approve_conditions")
            return state, checkpoints, duration_ms
        finally:
            AgentRuntime.run = original_run

    def test_timeout_A1_intake_evidence(self) -> None:
        """Kịch bản A1 Intake bị timeout: Không bóc tách được CIF/Hồ sơ gốc -> Khóa an toàn vì thiếu dữ liệu."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A1")
        self.assertEqual(len(checkpoints), 14)
        self.assertEqual(state.data_quality.get("status"), "DEGRADED_TIMEOUT")
        self.assertTrue(state.data_quality.get("critical_gap"))
        # Control gate phải nhận diện được CRITICAL_DATA_GAP
        self.assertIn("CRITICAL_DATA_GAP", state.control.get("blocked_reasons", []))
        self.assertIn(state.control.get("status"), ("BLOCKED_INVALID_OPINION", "HUMAN_REVIEW_RECOMMENDED_REJECT"))

    def test_timeout_A2_cashflow_analyst(self) -> None:
        """Kịch bản A2 Cashflow bị timeout: Thiếu phân tích dòng tiền sao kê -> Control Gate kích hoạt khoảng trống dòng tiền."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A2")
        self.assertEqual(len(checkpoints), 14)
        self.assertEqual(state.analyst_reports.get("cashflow", {}).get("status"), "DEGRADED_TIMEOUT")
        self.assertIn("CASHFLOW_TOOL_OR_COVERAGE_GAP", state.control.get("blocked_reasons", []))

    def test_timeout_A3_integrity_analyst(self) -> None:
        """Kịch bản A3 Integrity bị timeout: Không quét được đồ thị giao dịch AML -> Chặn duyệt vì rủi ro liêm chính."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A3")
        self.assertEqual(len(checkpoints), 14)
        self.assertEqual(state.analyst_reports.get("transaction_integrity", {}).get("status"), "DEGRADED_TIMEOUT")
        self.assertIn("MATERIAL_TRANSACTION_INTEGRITY_RISK", state.control.get("blocked_reasons", []))

    def test_timeout_A4_financial_capacity_analyst(self) -> None:
        """Kịch bản A4 Capacity bị timeout: OCR BCTC không kịp -> Khóa do chưa xác minh khả năng trả nợ gốc."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A4")
        self.assertEqual(len(checkpoints), 14)
        self.assertEqual(state.analyst_reports.get("financial_capacity", {}).get("status"), "DEGRADED_TIMEOUT")
        self.assertIn("PRIMARY_REPAYMENT_NOT_VIABLE", state.control.get("blocked_reasons", []))

    def test_timeout_A5_policy_compliance(self) -> None:
        """Kịch bản A5 Policy bị timeout: Chưa đối soát thể chế -> Bắt buộc leo thang kiểm soát thể chế."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A5")
        self.assertEqual(len(checkpoints), 14)
        self.assertEqual(state.analyst_reports.get("policy", {}).get("status"), "DEGRADED_TIMEOUT")
        self.assertIn("MANDATORY_POLICY_ESCALATION", state.control.get("blocked_reasons", []))

    def test_timeout_A6_credit_advocate(self) -> None:
        """Kịch bản A6 Advocate bị timeout: Thiếu bên biện hộ -> Vòng tranh biện ghi nhận sự cố nhưng luồng vẫn thông suốt."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A6")
        self.assertEqual(len(checkpoints), 14)
        degraded_debate = [d for d in state.credit_debate if d.get("speaker") == "A6" and d.get("status") == "DEGRADED_TIMEOUT"]
        self.assertGreaterEqual(len(degraded_debate), 1)

    def test_timeout_A7_risk_challenger(self) -> None:
        """Kịch bản A7 Challenger bị timeout: Thiếu bên phản biện rủi ro -> Ghi nhận suy giảm trong debate."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A7")
        self.assertEqual(len(checkpoints), 14)
        degraded_debate = [d for d in state.credit_debate if d.get("speaker") == "A7" and d.get("status") == "DEGRADED_TIMEOUT"]
        self.assertGreaterEqual(len(degraded_debate), 1)

    def test_timeout_A8_assessment_manager(self) -> None:
        """Kịch bản A8 Arbiter bị timeout: Báo cáo tổng hợp thẩm định bị gián đoạn -> Ghi nhận DEGRADED_TIMEOUT."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A8")
        self.assertEqual(len(checkpoints), 14)
        self.assertEqual(state.credit_assessment.get("status"), "DEGRADED_TIMEOUT")

    def test_timeout_A9_deal_structuring(self) -> None:
        """Kịch bản A9 Deal Structuring bị timeout: Không thể đề xuất hạn mức -> Khóa phương án giải ngân."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A9")
        self.assertEqual(len(checkpoints), 14)
        self.assertEqual(state.deal_proposal.get("status"), "DEGRADED_TIMEOUT")
        self.assertEqual(state.deal_proposal.get("action"), "BLOCKED")
        self.assertEqual(state.deal_proposal.get("proposed_limit"), 0)

    def test_timeout_A10_business_risk(self) -> None:
        """Kịch bản A10 Upside Risk bị timeout: Thiếu đánh giá cơ hội -> Ghi nhận vào risk debate."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A10")
        self.assertEqual(len(checkpoints), 14)
        degraded_risk = [d for d in state.risk_debate if d.get("speaker") == "A10" and d.get("status") == "DEGRADED_TIMEOUT"]
        self.assertGreaterEqual(len(degraded_risk), 1)

    def test_timeout_A11_conservative_risk(self) -> None:
        """Kịch bản A11 Conservative Risk bị timeout: Thiếu góc nhìn thận trọng -> Ghi nhận vào risk debate."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A11")
        self.assertEqual(len(checkpoints), 14)
        degraded_risk = [d for d in state.risk_debate if d.get("speaker") == "A11" and d.get("status") == "DEGRADED_TIMEOUT"]
        self.assertGreaterEqual(len(degraded_risk), 1)

    def test_timeout_A12_neutral_risk(self) -> None:
        """Kịch bản A12 Neutral Risk bị timeout: Thiếu góc nhìn quản trị trung lập -> Ghi nhận vào risk debate."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A12")
        self.assertEqual(len(checkpoints), 14)
        degraded_risk = [d for d in state.risk_debate if d.get("speaker") == "A12" and d.get("status") == "DEGRADED_TIMEOUT"]
        self.assertGreaterEqual(len(degraded_risk), 1)

    def test_timeout_A13_coapproval_opinion(self) -> None:
        """Kịch bản A13 Co-Approval Opinion bị timeout: Tự động rơi về phương án an toàn nhất (REJECT_INSUFFICIENT_EVIDENCE DRAFT)."""
        state, checkpoints, duration = self._run_with_single_agent_timeout("A13")
        self.assertEqual(len(checkpoints), 14)
        self.assertEqual(state.coapproval_opinion.get("decision"), "REJECT_INSUFFICIENT_EVIDENCE")
        self.assertEqual(state.control.get("status"), "HUMAN_REVIEW_RECOMMENDED_REJECT")

    def test_all_13_agents_timeout_individually_matrix(self) -> None:
        """Chạy vòng lặp kiểm tra toàn bộ 13 Agents A1 -> A13 độc lập:
        Khẳng định 100% các trường hợp đều không làm sập luồng và luôn sinh ra đúng 14 checkpoints."""
        for node_id in PIPELINE:
            with self.subTest(agent=node_id):
                state, checkpoints, duration = self._run_with_single_agent_timeout(node_id)
                self.assertEqual(len(checkpoints), 14, f"Checkpoints count mismatch when {node_id} timed out")
                self.assertIsNotNone(state.control.get("status"), f"Control status missing when {node_id} timed out")

                # Kiểm tra có sự kiện audit degradation cho node tương ứng
                degrade_evts = [e for e in state.audit if e.event == "agent_execution_degraded" and e.node_id == node_id]
                self.assertGreaterEqual(len(degrade_evts), 1, f"Audit event for {node_id} degradation was not logged correctly")


if __name__ == "__main__":
    unittest.main()
