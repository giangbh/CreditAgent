from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from credit_agent_poc.db import StateRepository
from credit_agent_poc.models import CreditState, AuditEvent


class ControlLayerAcceptanceCriteriaTests(unittest.TestCase):
    """Unit tests validating the 20 Acceptance Criteria for Control Layer & Human Decision Gate
    as specified in docs/06_luong_phe_duyet_con_nguoi_va_danh_gia_chat_luong.md v2.0.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_control_gate.db"
        self.repo = StateRepository(db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # --- AC 1: No opinion -> SIGN and SIGN_WITH_DIVERGENCE disallowed ---
    def test_ac1_no_opinion_disallows_signing(self) -> None:
        allowed_actions, blocked_reasons = self.repo.evaluate_control_gate(
            case_id="CASE-NO-OPINION",
            opinion=None,
            actor_role="BRANCH_DIRECTOR",
        )
        self.assertNotIn("SIGN", allowed_actions)
        self.assertNotIn("SIGN_WITH_DIVERGENCE", allowed_actions)
        self.assertIn("NO_VALID_OPINION", blocked_reasons)

    # --- AC 2: Stale opinion (case_revision mismatch) blocks completion ---
    def test_ac2_stale_or_invalid_opinion_blocks_completion_actions(self) -> None:
        stale_opinion = {
            "opinion_id": "OPINION-001",
            "opinion_version": 1,
            "case_revision": 1,  # Case is at revision 2
            "status": "VALIDATED",
            "decision": "APPROVE_WITH_CONDITIONS",
        }
        allowed_actions, blocked_reasons = self.repo.evaluate_control_gate(
            case_id="CASE-STALE",
            opinion=stale_opinion,
            current_case_revision=2,
            actor_role="BRANCH_DIRECTOR",
        )
        self.assertNotIn("SIGN", allowed_actions)
        self.assertIn("OPINION_STALE", blocked_reasons)

    # --- AC 3: Disallowed action API request is rejected with 409 ---
    def test_ac3_disallowed_action_returns_409(self) -> None:
        # Case with no valid opinion trying to execute SIGN action directly
        payload = {
            "case_id": "CASE-DISALLOWED",
            "opinion_id": None,
            "action": "SIGN",
            "human_decision": "APPROVED",
            "actor_id": "USR-101",
            "actor_role": "BRANCH_DIRECTOR",
        }
        with self.assertRaises(ValueError) as ctx:
            self.repo.record_human_decision_v2(payload)
        self.assertIn("409", str(ctx.exception))
        self.assertIn("ACTION_NOT_ALLOWED", str(ctx.exception))

    # --- AC 4: Revision change supersedes previous acknowledgements ---
    def test_ac4_revision_change_supersedes_acknowledgement(self) -> None:
        ack_id = self.repo.record_acknowledgement(
            case_id="CASE-REV-CHANGE",
            opinion_id="OP-100",
            opinion_version=1,
            actor_id="USR-101",
            warning_hash="hash-v1",
            acknowledged_finding_ids=["F-1", "F-2"],
        )

        active_ack = self.repo.get_active_acknowledgement("CASE-REV-CHANGE", opinion_version=1)
        self.assertIsNotNone(active_ack)

        # Increment revision and invalidate
        self.repo.supersede_acknowledgements_for_case("CASE-REV-CHANGE", reason="NEW_CASE_REVISION")

        active_ack_after = self.repo.get_active_acknowledgement("CASE-REV-CHANGE", opinion_version=1)
        self.assertIsNone(active_ack_after)

    # --- AC 5: HARD_BLOCK without authority returns 403 ---
    def test_ac5_hard_block_without_authority_returns_403(self) -> None:
        hard_blocked_opinion = {
            "opinion_id": "OPINION-BLOCKED",
            "opinion_version": 1,
            "case_revision": 1,
            "status": "VALIDATED",
            "decision": "REJECT_INSUFFICIENT_EVIDENCE",
            "hard_block": True,
        }
        payload = {
            "case_id": "CASE-HARD-BLOCK",
            "opinion_id": "OPINION-BLOCKED",
            "opinion_version": 1,
            "action": "SIGN_WITH_DIVERGENCE",
            "human_decision": "APPROVED",
            "alignment": "DIVERGENT",
            "divergence_reason_code": "NEW_EVIDENCE_PROVIDED",
            "divergence_narrative": "Đã kiểm tra bổ sung hồ sơ chứng minh dòng tiền thực tế hợp lệ từ hợp đồng xuất khẩu mới.",
            "actor_id": "USR-BRANCH-DIR",
            "actor_role": "BRANCH_DIRECTOR",
            "acknowledgement_id": "ACK-001",
        }
        with self.assertRaises(ValueError) as ctx:
            self.repo.record_human_decision_v2(payload, opinion_dict=hard_blocked_opinion)
        self.assertIn("403", str(ctx.exception))
        self.assertIn("INSUFFICIENT_AUTHORITY", str(ctx.exception))

    # --- AC 6 & AC 7: Integrity Seal payload verification & non-empty SHA-256 ---
    def test_ac6_and_ac7_integrity_seal_is_valid_and_never_empty_sha256(self) -> None:
        payload = {
            "case_id": "CASE-SEAL-TEST",
            "opinion_id": "OP-999",
            "opinion_version": 1,
            "action": "SIGN_WITH_DIVERGENCE",
            "human_decision": "REJECTED",
            "alignment": "DIVERGENT",
            "divergence_reason_code": "WEAK_REPAYMENT_CAPACITY_CONFIRMED",
            "divergence_narrative": "Đã đối soát báo cáo lưu chuyển tiền tệ chi tiết 6 tháng qua và phát hiện rủi ro kiệt quệ thanh khoản nghiêm trọng của doanh nghiệp vay.",
            "actor_id": "USR-8821",
            "actor_role": "CRO",
            "acknowledgement_id": "ACK-8821",
            "idempotency_key": "IDEM-001",
        }

        opinion_dict = {
            "opinion_id": "OP-999",
            "opinion_version": 1,
            "case_revision": 1,
            "status": "VALIDATED",
            "decision": "APPROVE_WITH_CONDITIONS",
            "hard_block": False,
        }

        res = self.repo.record_human_decision_v2(payload, opinion_dict=opinion_dict)
        seal = res["integrity_seal"]

        empty_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertNotEqual(seal, empty_sha256)
        self.assertEqual(len(seal), 64)

    # --- AC 8: Tampered decision record fails seal verification ---
    def test_ac8_tampered_decision_record_fails_seal_verification(self) -> None:
        payload = {
            "case_id": "CASE-TAMPER",
            "opinion_id": "OP-555",
            "opinion_version": 1,
            "action": "SIGN_WITH_DIVERGENCE",
            "human_decision": "REJECTED",
            "alignment": "DIVERGENT",
            "divergence_reason_code": "WEAK_REPAYMENT_CAPACITY_CONFIRMED",
            "divergence_narrative": "Đã đối soát báo cáo lưu chuyển tiền tệ chi tiết 6 tháng qua và phát hiện rủi ro kiệt quệ thanh khoản nghiêm trọng của doanh nghiệp vay.",
            "actor_id": "USR-AUDIT",
            "actor_role": "CRO",
            "acknowledgement_id": "ACK-555",
            "idempotency_key": "IDEM-TAMPER",
        }
        opinion_dict = {
            "opinion_id": "OP-555",
            "opinion_version": 1,
            "case_revision": 1,
            "status": "VALIDATED",
            "decision": "APPROVE_WITH_CONDITIONS",
            "hard_block": False,
        }
        res = self.repo.record_human_decision_v2(payload, opinion_dict=opinion_dict)
        decision_id = res["decision_id"]

        is_valid_before = self.repo.verify_decision_integrity_seal(decision_id)
        self.assertTrue(is_valid_before)

        # Tamper directly in database
        with self.repo._connect() as conn:
            conn.execute(
                "UPDATE human_decisions SET approved_amount = 99999999999 WHERE decision_id = ?",
                (decision_id,),
            )

        is_valid_after = self.repo.verify_decision_integrity_seal(decision_id)
        self.assertFalse(is_valid_after)

    # --- AC 15: Idempotency Key prevents duplicate records ---
    def test_ac15_idempotency_key_prevents_duplicate_records(self) -> None:
        payload = {
            "case_id": "CASE-IDEMPOTENCY",
            "opinion_id": "OP-777",
            "opinion_version": 1,
            "action": "SIGN_WITH_DIVERGENCE",
            "human_decision": "REJECTED",
            "alignment": "DIVERGENT",
            "divergence_reason_code": "WEAK_REPAYMENT_CAPACITY_CONFIRMED",
            "divergence_narrative": "Đã đối soát báo cáo lưu chuyển tiền tệ chi tiết 6 tháng qua và phát hiện rủi ro kiệt quệ thanh khoản nghiêm trọng của doanh nghiệp vay.",
            "actor_id": "USR-777",
            "actor_role": "CRO",
            "acknowledgement_id": "ACK-777",
            "idempotency_key": "UNIQUE-KEY-12345",
        }
        opinion_dict = {
            "opinion_id": "OP-777",
            "opinion_version": 1,
            "case_revision": 1,
            "status": "VALIDATED",
            "decision": "APPROVE_WITH_CONDITIONS",
            "hard_block": False,
        }

        res1 = self.repo.record_human_decision_v2(payload, opinion_dict=opinion_dict)
        res2 = self.repo.record_human_decision_v2(payload, opinion_dict=opinion_dict)

        self.assertEqual(res1["decision_id"], res2["decision_id"])
        self.assertEqual(res2["status"], "SUCCESS_IDEMPOTENT")

    # --- AC 17: Divergent decision requires reason code & narrative >= 120 chars ---
    def test_ac17_divergent_decision_requires_code_and_narrative(self) -> None:
        short_narrative_payload = {
            "case_id": "CASE-SHORT",
            "opinion_id": "OP-111",
            "opinion_version": 1,
            "action": "SIGN_WITH_DIVERGENCE",
            "human_decision": "REJECTED",
            "alignment": "DIVERGENT",
            "divergence_reason_code": "WEAK_REPAYMENT_CAPACITY_CONFIRMED",
            "divergence_narrative": "Quá ngắn",  # Under 120 chars
            "actor_id": "USR-111",
            "actor_role": "CRO",
            "acknowledgement_id": "ACK-111",
        }
        opinion_dict = {
            "opinion_id": "OP-111",
            "opinion_version": 1,
            "case_revision": 1,
            "status": "VALIDATED",
            "decision": "APPROVE_WITH_CONDITIONS",
            "hard_block": False,
        }
        with self.assertRaises(ValueError) as ctx:
            self.repo.record_human_decision_v2(short_narrative_payload, opinion_dict=opinion_dict)
        self.assertIn("422", str(ctx.exception))
        self.assertIn("NARRATIVE_TOO_SHORT", str(ctx.exception))

    # --- AC 20: Negative AI opinion disallows direct SIGN (requires SIGN_WITH_DIVERGENCE) ---
    def test_ac20_negative_opinion_disallows_direct_signed_status(self) -> None:
        negative_opinion = {
            "opinion_id": "OP-NEG",
            "opinion_version": 1,
            "case_revision": 1,
            "status": "VALIDATED",
            "decision": "REJECT_INSUFFICIENT_EVIDENCE",
            "hard_block": False,
        }

        allowed_actions, _ = self.repo.evaluate_control_gate(
            case_id="CASE-NEG",
            opinion=negative_opinion,
            actor_role="CRO",
        )
        self.assertNotIn("SIGN", allowed_actions)
        self.assertIn("SIGN_WITH_DIVERGENCE", allowed_actions)


if __name__ == "__main__":
    unittest.main()
