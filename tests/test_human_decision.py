from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
import json

from credit_agent_poc.db import StateRepository


class HumanDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_human_decisions.db"
        self.repo = StateRepository(db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_record_agree_with_ai_decision(self) -> None:
        decision_payload = {
            "case_id": "CASE-APPROVE_CONDITIONS",
            "run_id": "run-001",
            "user_id": "USR-1001",
            "username": "nguyenvana",
            "full_name": "Nguyễn Văn A",
            "role": "CRO",
            "branch_id": "HO_RISK",
            "ai_decision": "APPROVE_WITH_CONDITIONS",
            "human_decision": "APPROVE_WITH_CONDITIONS",
            "decision_type": "AGREE_WITH_AI",
        }
        res = self.repo.record_human_decision(decision_payload)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["decision_type"], "AGREE_WITH_AI")
        self.assertTrue(len(res["digital_signature_hash"]) > 20)

        case_decisions = self.repo.get_human_decisions_by_case("CASE-APPROVE_CONDITIONS")
        self.assertEqual(len(case_decisions), 1)
        self.assertEqual(case_decisions[0]["user_id"], "USR-1001")

    def test_override_ai_requires_justification(self) -> None:
        payload_no_justification = {
            "case_id": "CASE-APPROVE_CONDITIONS",
            "user_id": "USR-1002",
            "ai_decision": "APPROVE_WITH_CONDITIONS",
            "human_decision": "REJECT_INSUFFICIENT_EVIDENCE",
            "decision_type": "OVERRIDE_AI",
            "override_justification": "",  # Short/empty justification should fail
        }
        with self.assertRaises(ValueError):
            self.repo.record_human_decision(payload_no_justification)

        payload_valid_override = {
            "case_id": "CASE-APPROVE_CONDITIONS",
            "user_id": "USR-1002",
            "username": "tranvanb",
            "full_name": "Trần Văn B",
            "role": "Giám đốc Chi nhánh",
            "branch_id": "BRANCH_HN",
            "ai_decision": "APPROVE_WITH_CONDITIONS",
            "human_decision": "REJECT_INSUFFICIENT_EVIDENCE",
            "decision_type": "OVERRIDE_AI",
            "override_reason_category": "ADDITIONAL_COLLATERAL_RECORDED",
            "override_justification": "Dòng tiền thực tế quá yếu, tài sản bảo đảm không bù đắp được rủi ro kiệt quệ tài chính.",
        }
        res = self.repo.record_human_decision(payload_valid_override)
        self.assertEqual(res["status"], "SUCCESS")

    def test_approver_quality_report_calculation(self) -> None:
        # Record 4 decisions for USR-8821 (3 AGREE, 1 OVERRIDE)
        for i in range(3):
            self.repo.record_human_decision(
                {
                    "case_id": f"CASE-AGREE-{i}",
                    "user_id": "USR-8821",
                    "ai_decision": "APPROVE_WITH_CONDITIONS",
                    "human_decision": "APPROVE_WITH_CONDITIONS",
                    "decision_type": "AGREE_WITH_AI",
                }
            )

        self.repo.record_human_decision(
            {
                "case_id": "CASE-OVERRIDE-1",
                "user_id": "USR-8821",
                "ai_decision": "APPROVE_WITH_CONDITIONS",
                "human_decision": "REJECT_INSUFFICIENT_EVIDENCE",
                "decision_type": "OVERRIDE_AI",
                "override_reason_category": "BUSINESS_INTUITION_AND_TRACK_RECORD",
                "override_justification": "Phát hiện dấu hiệu rủi ro dòng tiền bổ sung chưa được ghi nhận.",
            }
        )

        report = self.repo.generate_approver_quality_report(user_id="USR-8821")
        self.assertEqual(report["total_decisions"], 4)
        self.assertEqual(report["agreed_with_ai_count"], 3)
        self.assertEqual(report["override_ai_count"], 1)
        self.assertEqual(report["override_rate_pct"], 25.0)
        self.assertEqual(report["agreement_rate_pct"], 75.0)
        self.assertEqual(report["qa_sampling_tier"], "ROUTINE_QA_SAMPLING")


if __name__ == "__main__":
    unittest.main()
