"""Tieu chi nghiem thu Control Gate — docs/06 v2.0 muc 10.

Moi test class tuong ung mot nhom tieu chi; ten test co tien to AC<n> khop
so thu tu trong tai lieu de truy nguoc khi review.

Chay:
    PYTHONPATH=src python3 -m unittest tests.test_control_gate -v
"""

from __future__ import annotations

import hashlib
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from credit_agent_poc.control_gate import (
    SHA256_OF_EMPTY,
    AckStatus,
    Acknowledgement,
    AcknowledgementStore,
    Action,
    Actor,
    AuditLog,
    AuthorityLevel,
    Case,
    Condition,
    ControlError,
    ControlGate,
    ControlState,
    Decision,
    DecisionRequest,
    DecisionService,
    DecisionStore,
    Disposition,
    FailingAuditLog,
    FailureKind,
    Finding,
    GatePolicy,
    KeyStore,
    ModelRiskBacklog,
    Notifier,
    Opinion,
    OpinionDecision,
    OpinionStatus,
    SealPayloadError,
    apply_case_revision,
    build_seal_payload,
    classify_pipeline_failure,
    compute_integrity_seal,
    compute_warning_hash,
    verify_decision_seal,
)

NOW = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)
NARRATIVE = (
    "Khach hang da bo sung sao ke quy 2 lay truc tiep tu kenh host-to-host, "
    "the hien dong tien ve tai khoan tai ngan hang chiem 71 phan tram doanh thu "
    "khai bao, khac voi du lieu ma he thong da danh gia truoc do."
)
SHORT_NARRATIVE = "Khach hang tot, dong y cap."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_case(**overrides) -> Case:
    defaults = dict(
        case_id="CASE-001",
        case_revision=1,
        source_snapshot_hash="src-hash-1",
        policy_snapshot_id="policy-2026Q3",
        ruleset_version="rules-1.4",
        required_authority=AuthorityLevel.BRANCH_DIRECTOR,
    )
    defaults.update(overrides)
    return Case(**defaults)


def make_opinion(**overrides) -> Opinion:
    defaults = dict(
        opinion_id="OP-001",
        opinion_version=1,
        case_revision=1,
        decision=OpinionDecision.APPROVE_WITH_CONDITIONS,
        status=OpinionStatus.VALIDATED,
        source_snapshot_hash="src-hash-1",
        policy_snapshot_id="policy-2026Q3",
        ruleset_version="rules-1.4",
        issued_at=NOW - timedelta(hours=2),
        decisive_finding_ids=("F-011", "F-014"),
        findings=(
            Finding("F-011", "MEDIUM", Disposition.SOFT_WARNING),
            Finding("F-014", "HIGH", Disposition.MANDATORY_ESCALATION),
        ),
        conditions=(Condition("C-1", owner="RM-01", due_point="PRE_DISBURSEMENT"),),
    )
    defaults.update(overrides)
    return Opinion(**defaults)


def hard_block_opinion(code: str = "HB_REPAYMENT_UNPROVEN", **overrides) -> Opinion:
    return make_opinion(
        decision=OpinionDecision.REJECT_INSUFFICIENT_EVIDENCE,
        decisive_finding_ids=("F-021",),
        findings=(Finding("F-021", "CRITICAL", Disposition.HARD_BLOCK, code=code),),
        conditions=(),
        **overrides
    )


DIRECTOR = Actor("USR-8821", "BRANCH_DIRECTOR", AuthorityLevel.BRANCH_DIRECTOR, "BR-01")
AUTHORITY = Actor("USR-4400", "CREDIT_AUTHORITY", AuthorityLevel.CREDIT_AUTHORITY, "HO")
CRO = Actor("USR-0001", "CRO", AuthorityLevel.CRO, "HO", has_exception_authority=True)
OFFICER = Actor("USR-9000", "CREDIT_OFFICER", AuthorityLevel.CREDIT_OFFICER, "BR-01")


class Harness:
    """Lap rap service voi cac cong co the thay the de kiem thu that bai."""

    def __init__(self, audit=None, notifier=None, policy=None):
        self.gate = ControlGate(policy or GatePolicy())
        self.decisions = DecisionStore()
        self.acks = AcknowledgementStore()
        self.audit = audit or AuditLog()
        self.notifier = notifier or Notifier()
        self.keys = KeyStore()
        self.model_risk = ModelRiskBacklog()
        self.service = DecisionService(
            self.gate, self.decisions, self.acks, self.audit,
            self.notifier, self.keys, self.model_risk,
        )

    def acknowledge(self, case, opinion, actor):
        return self.service.acknowledge(
            case, opinion, actor,
            compute_warning_hash(case, opinion),
            opinion.decisive_finding_ids,
        )


# ---------------------------------------------------------------------------
# AC1-AC5: Control gate
# ---------------------------------------------------------------------------


class TestControlGate(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def test_AC1_no_opinion_hides_all_signing_actions(self):
        control = self.h.gate.evaluate(make_case(), None, DIRECTOR, None, now=NOW)
        self.assertNotIn(Action.SIGN, control.allowed_actions)
        self.assertNotIn(Action.SIGN_WITH_DIVERGENCE, control.allowed_actions)
        self.assertIn("NO_VALID_OPINION", control.blocked_reasons)
        self.assertIn(Action.REANALYZE, control.allowed_actions)

    def test_AC2a_invalid_opinion_blocks_terminal_actions(self):
        opinion = make_opinion(status=OpinionStatus.INVALID)
        control = self.h.gate.evaluate(make_case(), opinion, DIRECTOR, None, now=NOW)
        self.assertFalse(set(control.allowed_actions) & {Action.SIGN,
                                                         Action.SIGN_WITH_DIVERGENCE})
        self.assertIn("NO_VALID_OPINION", control.blocked_reasons)

    def test_AC2b_stale_opinion_by_snapshot_hash(self):
        case = make_case(source_snapshot_hash="src-hash-2")
        control = self.h.gate.evaluate(case, make_opinion(), DIRECTOR, None, now=NOW)
        self.assertIn("STALE_OPINION", control.blocked_reasons)
        self.assertNotIn(Action.SIGN, control.allowed_actions)

    def test_AC2c_stale_opinion_by_age(self):
        opinion = make_opinion(issued_at=NOW - timedelta(days=20))
        control = self.h.gate.evaluate(make_case(), opinion, DIRECTOR, None, now=NOW)
        self.assertIn("STALE_OPINION", control.blocked_reasons)

    def test_AC2d_stale_opinion_by_policy_snapshot(self):
        case = make_case(policy_snapshot_id="policy-2026Q4")
        control = self.h.gate.evaluate(case, make_opinion(), DIRECTOR, None, now=NOW)
        self.assertIn("STALE_OPINION", control.blocked_reasons)

    def test_AC3_direct_api_call_bypassing_ui_is_rejected(self):
        """Action ngoai allowed_actions -> 409, khong ban ghi nao duoc tao."""
        case = make_case()
        opinion = hard_block_opinion()
        # Khong acknowledge, va Giam doc CN khong du tham quyen ngoai le.
        request = DecisionRequest(
            action=Action.SIGN,
            human_decision="APPROVED",
            idempotency_key="idem-1",
        )
        with self.assertRaises(ControlError) as ctx:
            self.h.service.submit(case, opinion, DIRECTOR, request, now=NOW)
        self.assertEqual(409, ctx.exception.http_status)
        self.assertEqual(0, len(self.h.decisions.rows))
        # Lan tu choi van duoc ghi audit.
        self.assertTrue(
            any(e.event_type == "human_decision_rejected" for e in self.h.audit.entries)
        )

    def test_AC4_case_revision_change_supersedes_acknowledgement(self):
        case = make_case()
        opinion = make_opinion()
        ack = self.h.acknowledge(case, opinion, DIRECTOR)
        self.assertEqual(AckStatus.ACTIVE, ack.status)

        control = self.h.gate.evaluate(case, opinion, DIRECTOR, ack, now=NOW)
        self.assertIn(Action.SIGN, control.allowed_actions)

        apply_case_revision(case, self.h.acks, "src-hash-2")
        self.assertEqual(AckStatus.SUPERSEDED, ack.status)
        self.assertEqual("NEW_CASE_REVISION", ack.superseded_reason)

        control = self.h.gate.evaluate(case, opinion, DIRECTOR, ack, now=NOW)
        self.assertNotIn(Action.SIGN, control.allowed_actions)

        request = DecisionRequest(
            action=Action.SIGN,
            human_decision="APPROVED",
            idempotency_key="idem-2",
            acknowledgement_id=ack.acknowledgement_id,
        )
        with self.assertRaises(ControlError) as ctx:
            self.h.service.submit(case, opinion, DIRECTOR, request, now=NOW)
        self.assertEqual("STALE_OPINION", ctx.exception.code)
        self.assertEqual(0, len(self.h.decisions.rows))

    def test_AC5_hard_block_requires_exception_authority(self):
        case = make_case()
        opinion = hard_block_opinion()
        ack = self.h.acknowledge(case, opinion, DIRECTOR)

        control = self.h.gate.evaluate(case, opinion, DIRECTOR, ack, now=NOW)
        self.assertNotIn(Action.SIGN_WITH_DIVERGENCE, control.allowed_actions)
        self.assertIn("HARD_BLOCK_AUTHORITY_REQUIRED", control.blocked_reasons)

        ack_authority = self.h.acknowledge(case, opinion, AUTHORITY)
        control = self.h.gate.evaluate(case, opinion, AUTHORITY, ack_authority, now=NOW)
        self.assertIn(Action.SIGN_WITH_DIVERGENCE, control.allowed_actions)

    def test_AC5b_non_overridable_hard_block_blocks_even_CRO(self):
        case = make_case(required_authority=AuthorityLevel.CRO)
        opinion = hard_block_opinion(code="HB_AML_SANCTION")
        ack = self.h.acknowledge(case, opinion, CRO)
        control = self.h.gate.evaluate(case, opinion, CRO, ack, now=NOW)
        self.assertNotIn(Action.SIGN_WITH_DIVERGENCE, control.allowed_actions)
        self.assertNotIn(Action.SIGN, control.allowed_actions)
        self.assertIn("NON_OVERRIDABLE_HARD_BLOCK", control.blocked_reasons)

    def test_AC5c_incomplete_condition_blocks_sign(self):
        case = make_case()
        opinion = make_opinion(conditions=(Condition("C-1", owner=None,
                                                     due_point="PRE_DISBURSEMENT"),))
        ack = self.h.acknowledge(case, opinion, DIRECTOR)
        control = self.h.gate.evaluate(case, opinion, DIRECTOR, ack, now=NOW)
        self.assertIn("CONDITION_INCOMPLETE", control.blocked_reasons)
        self.assertNotIn(Action.SIGN, control.allowed_actions)

    def test_AC5d_insufficient_authority_strips_terminal_actions(self):
        case = make_case(required_authority=AuthorityLevel.CREDIT_AUTHORITY)
        opinion = make_opinion()
        ack = self.h.acknowledge(case, opinion, OFFICER)
        control = self.h.gate.evaluate(case, opinion, OFFICER, ack, now=NOW)
        self.assertFalse(
            set(control.allowed_actions)
            & {Action.SIGN, Action.SIGN_WITH_DIVERGENCE, Action.REJECT}
        )
        self.assertIn("INSUFFICIENT_AUTHORITY", control.blocked_reasons)
        self.assertIn(Action.ESCALATE, control.allowed_actions)


# ---------------------------------------------------------------------------
# AC6-AC9: Toan ven
# ---------------------------------------------------------------------------


class TestIntegrity(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def _signed_decision(self) -> Decision:
        case = make_case()
        opinion = make_opinion()
        ack = self.h.acknowledge(case, opinion, DIRECTOR)
        request = DecisionRequest(
            action=Action.SIGN,
            human_decision="APPROVED_WITH_CONDITIONS",
            idempotency_key="idem-seal",
            acknowledgement_id=ack.acknowledgement_id,
            approved_amount=Decimal("8000000000.00"),
            approved_currency="VND",
            approved_tenor_months=36,
            approved_rate_pct=Decimal("9.5000"),
        )
        return self.h.service.submit(case, opinion, DIRECTOR, request, now=NOW).decision

    def test_AC6_seal_on_incomplete_payload_raises(self):
        payload = {"case_id": "CASE-001"}
        with self.assertRaises(SealPayloadError):
            compute_integrity_seal(payload, self.h.keys, "seal-key-1")

        decision = self._signed_decision()
        broken = build_seal_payload(decision)
        broken["actor_id"] = None
        with self.assertRaises(SealPayloadError):
            compute_integrity_seal(broken, self.h.keys, "seal-key-1")

    def test_AC7_seals_differ_and_never_equal_empty_sha256(self):
        """Bay cua v1.0: hash mau la SHA-256 cua chuoi rong."""
        self.assertEqual(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            SHA256_OF_EMPTY,
        )
        first = self._signed_decision()
        self.assertNotEqual(SHA256_OF_EMPTY, first.integrity_seal)

        other = Harness()
        case = make_case(case_id="CASE-002")
        opinion = make_opinion()
        ack = other.acknowledge(case, opinion, DIRECTOR)
        second = other.service.submit(
            case, opinion, DIRECTOR,
            DecisionRequest(Action.SIGN, "APPROVED_WITH_CONDITIONS", "idem-x",
                            acknowledgement_id=ack.acknowledgement_id),
            now=NOW,
        ).decision
        self.assertNotEqual(first.integrity_seal, second.integrity_seal)
        self.assertNotEqual(SHA256_OF_EMPTY, second.integrity_seal)

    def test_AC8_tampered_decision_row_fails_seal_verification(self):
        decision = self._signed_decision()
        self.assertTrue(verify_decision_seal(decision, self.h.keys))
        decision.approved_amount = Decimal("12000000000.00")
        self.assertFalse(verify_decision_seal(decision, self.h.keys))

    def test_AC9_tampered_audit_chain_is_detected_at_exact_position(self):
        log = AuditLog()
        for i in range(5):
            log.append("evt_{}".format(i), {"i": i}, case_id="CASE-001")
        ok, broken_at = log.verify()
        self.assertTrue(ok)
        self.assertIsNone(broken_at)

        log.entries[2].payload["i"] = 99
        ok, broken_at = log.verify()
        self.assertFalse(ok)
        self.assertEqual(3, broken_at)

    def test_AC9b_audit_chain_links_to_genesis(self):
        log = AuditLog()
        entry = log.append("first", {"a": 1})
        self.assertEqual("0" * 64, entry.prev_hash)
        self.assertEqual(64, len(entry.entry_hash))


# ---------------------------------------------------------------------------
# AC10-AC14: Fail closed / degraded
# ---------------------------------------------------------------------------


class TestFailClosedAndDegraded(unittest.TestCase):
    def test_AC10_audit_failure_blocks_and_creates_no_decision(self):
        h = Harness(audit=FailingAuditLog(fail_on=["human_decision_submitted"]))
        case = make_case()
        opinion = make_opinion()
        ack = h.acknowledge(case, opinion, DIRECTOR)
        request = DecisionRequest(Action.SIGN, "APPROVED", "idem-audit",
                                  acknowledgement_id=ack.acknowledgement_id)
        with self.assertRaises(ControlError) as ctx:
            h.service.submit(case, opinion, DIRECTOR, request, now=NOW)
        self.assertEqual("AUDIT_WRITE_FAILED", ctx.exception.code)
        self.assertEqual(503, ctx.exception.http_status)
        self.assertEqual(0, len(h.decisions.rows))
        self.assertEqual(ControlState.BLOCKED, case.control_state)

    def test_AC11_mandatory_notification_failure_blocks(self):
        h = Harness(notifier=Notifier(fail_triggers=["DIVERGENCE_ON_HARD_BLOCK"]))
        case = make_case(required_authority=AuthorityLevel.CREDIT_AUTHORITY)
        opinion = hard_block_opinion()
        ack = h.acknowledge(case, opinion, AUTHORITY)
        request = DecisionRequest(
            action=Action.SIGN_WITH_DIVERGENCE,
            human_decision="APPROVED_WITH_CONDITIONS",
            idempotency_key="idem-noti",
            acknowledgement_id=ack.acknowledgement_id,
            divergence_reason_code="COLLATERAL_EXCEPTION_REQUEST",
            divergence_narrative=NARRATIVE,
        )
        with self.assertRaises(ControlError) as ctx:
            h.service.submit(case, opinion, AUTHORITY, request, now=NOW)
        self.assertEqual("NOTIFICATION_FAILED", ctx.exception.code)
        self.assertEqual(0, len(h.decisions.rows))
        self.assertEqual(ControlState.BLOCKED, case.control_state)

    def test_AC12_digest_notification_failure_does_not_block(self):
        h = Harness(notifier=Notifier(fail_triggers=["DIVERGENCE_STANDARD"]))
        case = make_case()
        opinion = make_opinion(decision=OpinionDecision.ESCALATE_TO_CRO_RISK,
                               conditions=())
        ack = h.acknowledge(case, opinion, DIRECTOR)
        request = DecisionRequest(
            action=Action.SIGN_WITH_DIVERGENCE,
            human_decision="APPROVED_WITH_CONDITIONS",
            idempotency_key="idem-digest",
            acknowledgement_id=ack.acknowledgement_id,
            divergence_reason_code="NEW_EVIDENCE_PROVIDED",
            divergence_narrative=NARRATIVE,
            supporting_document_ids=("DOC-99",),
        )
        result = h.service.submit(case, opinion, DIRECTOR, request, now=NOW)
        self.assertEqual(201, result.http_status)
        self.assertEqual(1, len(h.decisions.rows))
        self.assertEqual(1, len(h.notifier.failed))

    def test_AC13_infrastructure_failure_enters_degraded_mode(self):
        state = classify_pipeline_failure(FailureKind.INFRASTRUCTURE, 75)
        self.assertEqual(ControlState.AI_UNAVAILABLE, state)

        h = Harness()
        case = make_case(ai_availability="UNAVAILABLE",
                         control_state=ControlState.AI_UNAVAILABLE)
        control = h.gate.evaluate(case, None, DIRECTOR, None, now=NOW)
        self.assertIn(Action.SIGN, control.allowed_actions)
        self.assertTrue(control.post_review_required)

        request = DecisionRequest(Action.SIGN, "APPROVED", "idem-degraded")
        result = h.service.submit(case, None, DIRECTOR, request, now=NOW)
        self.assertTrue(result.decision.post_review_required)
        self.assertEqual("NO_AI_OPINION", result.decision.alignment)
        self.assertEqual(ControlState.SIGNED_PENDING_REVIEW, case.control_state)

    def test_AC13b_degraded_mode_cannot_bypass_live_hard_block(self):
        h = Harness()
        case = make_case(ai_availability="UNAVAILABLE")
        opinion = hard_block_opinion()
        control = h.gate.evaluate(case, opinion, CRO, None, now=NOW)
        self.assertNotIn(Action.SIGN, control.allowed_actions)
        self.assertIn("UNRESOLVED_HARD_BLOCK", control.blocked_reasons)

    def test_AC14_data_failure_must_not_enter_degraded_mode(self):
        state = classify_pipeline_failure(FailureKind.DATA, 600)
        self.assertEqual(ControlState.NEEDS_EVIDENCE_REVIEW, state)

        h = Harness()
        case = make_case(evidence_review_required=True)
        opinion = make_opinion()
        ack = h.acknowledge(case, opinion, DIRECTOR)
        control = h.gate.evaluate(case, opinion, DIRECTOR, ack, now=NOW)
        self.assertEqual(ControlState.NEEDS_EVIDENCE_REVIEW, control.control_state)
        self.assertNotIn(Action.SIGN, control.allowed_actions)
        self.assertFalse(control.post_review_required)


# ---------------------------------------------------------------------------
# AC15-AC16: Idempotency va dong thoi
# ---------------------------------------------------------------------------


class TestIdempotencyAndConcurrency(unittest.TestCase):
    def test_AC15_same_idempotency_key_creates_one_row(self):
        h = Harness()
        case = make_case()
        opinion = make_opinion()
        ack = h.acknowledge(case, opinion, DIRECTOR)
        request = DecisionRequest(Action.SIGN, "APPROVED", "idem-dup",
                                  acknowledgement_id=ack.acknowledgement_id)

        first = h.service.submit(case, opinion, DIRECTOR, request, now=NOW)
        second = h.service.submit(case, opinion, DIRECTOR, request, now=NOW)

        self.assertEqual(201, first.http_status)
        self.assertEqual(200, second.http_status)
        self.assertTrue(second.idempotent_replay)
        self.assertEqual(first.decision.decision_id, second.decision.decision_id)
        self.assertEqual(1, len(h.decisions.rows))

    def test_AC16_concurrent_signers_exactly_one_succeeds(self):
        h = Harness()
        case = make_case(required_authority=AuthorityLevel.BRANCH_DIRECTOR)
        opinion = make_opinion()
        second_director = Actor("USR-7777", "BRANCH_DIRECTOR",
                                AuthorityLevel.BRANCH_DIRECTOR, "BR-01")
        ack_a = h.acknowledge(case, opinion, DIRECTOR)
        ack_b = h.acknowledge(case, opinion, second_director)

        results, errors = [], []
        barrier = threading.Barrier(2)

        def submit(actor, ack, key):
            barrier.wait()
            try:
                results.append(
                    h.service.submit(
                        case, opinion, actor,
                        DecisionRequest(Action.SIGN, "APPROVED", key,
                                        acknowledgement_id=ack.acknowledgement_id),
                        now=NOW,
                    )
                )
            except ControlError as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=submit, args=(DIRECTOR, ack_a, "k-a")),
            threading.Thread(target=submit, args=(second_director, ack_b, "k-b")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(1, len(results))
        self.assertEqual(1, len(errors))
        self.assertEqual(409, errors[0].http_status)
        # Nguoi thua cuoc bi chan o mot trong hai lop, tuy thoi diem:
        #   - gate: ho so da chuyen trang thai ket thuc  -> ACTION_NOT_ALLOWED
        #   - store: unique index tren (case_id, revision) -> CONFLICT_TERMINAL_DECISION
        # Lop store moi la bao dam tat dinh; xem test ke tiep.
        self.assertIn(
            errors[0].code, {"ACTION_NOT_ALLOWED", "CONFLICT_TERMINAL_DECISION"}
        )
        self.assertEqual(1, len(h.decisions.rows))

    def test_AC16b_store_enforces_single_terminal_decision_per_revision(self):
        """Bao dam tat dinh: unique index, khong phu thuoc thu tu thuc thi."""
        h = Harness()
        case = make_case()
        opinion = make_opinion()
        ack = h.acknowledge(case, opinion, DIRECTOR)
        h.service.submit(
            case, opinion, DIRECTOR,
            DecisionRequest(Action.SIGN, "APPROVED", "k-1",
                            acknowledgement_id=ack.acknowledgement_id),
            now=NOW,
        )
        duplicate = h.decisions.rows[0]
        clone = replace(duplicate, decision_id="D-CLONE", idempotency_key="k-2")
        with self.assertRaises(ControlError) as ctx:
            h.decisions.insert(clone)
        self.assertEqual("CONFLICT_TERMINAL_DECISION", ctx.exception.code)
        self.assertEqual(409, ctx.exception.http_status)
        self.assertEqual(1, len(h.decisions.rows))


# ---------------------------------------------------------------------------
# AC17-AC20: Rang buoc nghiep vu
# ---------------------------------------------------------------------------


class TestBusinessConstraints(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.case = make_case()
        self.opinion = make_opinion(decision=OpinionDecision.ESCALATE_TO_CRO_RISK,
                                    conditions=())
        self.ack = self.h.acknowledge(self.case, self.opinion, DIRECTOR)

    def _request(self, **overrides) -> DecisionRequest:
        defaults = dict(
            action=Action.SIGN_WITH_DIVERGENCE,
            human_decision="APPROVED_WITH_CONDITIONS",
            idempotency_key="idem-bc",
            acknowledgement_id=self.ack.acknowledgement_id,
            divergence_reason_code="NEW_EVIDENCE_PROVIDED",
            divergence_narrative=NARRATIVE,
            supporting_document_ids=("DOC-99",),
        )
        defaults.update(overrides)
        return DecisionRequest(**defaults)

    def test_AC17a_divergence_without_reason_code_is_422(self):
        with self.assertRaises(ControlError) as ctx:
            self.h.service.submit(self.case, self.opinion, DIRECTOR,
                                  self._request(divergence_reason_code=None), now=NOW)
        self.assertEqual("REASON_CODE_REQUIRED", ctx.exception.code)
        self.assertEqual(422, ctx.exception.http_status)
        self.assertEqual(0, len(self.h.decisions.rows))

    def test_AC17b_short_narrative_is_422(self):
        with self.assertRaises(ControlError) as ctx:
            self.h.service.submit(
                self.case, self.opinion, DIRECTOR,
                self._request(divergence_narrative=SHORT_NARRATIVE), now=NOW,
            )
        self.assertEqual("NARRATIVE_TOO_SHORT", ctx.exception.code)
        self.assertEqual(0, len(self.h.decisions.rows))

    def test_AC17c_missing_supporting_documents_is_422(self):
        with self.assertRaises(ControlError) as ctx:
            self.h.service.submit(
                self.case, self.opinion, DIRECTOR,
                self._request(supporting_document_ids=()), now=NOW,
            )
        self.assertEqual("SUPPORTING_DOCUMENTS_REQUIRED", ctx.exception.code)

    def test_AC18_tightening_reason_code_on_loosening_decision_is_422(self):
        """Loi cua v1.0: ma ly do va noi dung giai trinh nguoc huong nhau."""
        with self.assertRaises(ControlError) as ctx:
            self.h.service.submit(
                self.case, self.opinion, DIRECTOR,
                self._request(divergence_reason_code="ADDITIONAL_RISK_OBSERVED"),
                now=NOW,
            )
        self.assertEqual("REASON_DIRECTION_MISMATCH", ctx.exception.code)
        self.assertEqual(422, ctx.exception.http_status)
        self.assertEqual(0, len(self.h.decisions.rows))

    def test_AC18b_reason_code_below_required_authority_is_403(self):
        with self.assertRaises(ControlError) as ctx:
            self.h.service.submit(
                self.case, self.opinion, DIRECTOR,
                self._request(divergence_reason_code="STRATEGIC_CUSTOMER_EXCEPTION"),
                now=NOW,
            )
        self.assertEqual("INSUFFICIENT_AUTHORITY", ctx.exception.code)
        self.assertEqual(403, ctx.exception.http_status)

    def test_AC19_model_risk_feedback_is_created(self):
        result = self.h.service.submit(
            self.case, self.opinion, DIRECTOR,
            self._request(divergence_reason_code="AI_FINDING_FACTUALLY_WRONG",
                          supporting_document_ids=()),
            now=NOW,
        )
        self.assertEqual(201, result.http_status)
        self.assertEqual(1, len(self.h.model_risk.items))
        self.assertEqual("AI_FINDING_FACTUALLY_WRONG",
                         self.h.model_risk.items[0]["reason_code"])

    def test_AC19b_ordinary_reason_code_creates_no_feedback(self):
        self.h.service.submit(self.case, self.opinion, DIRECTOR,
                              self._request(), now=NOW)
        self.assertEqual(0, len(self.h.model_risk.items))

    def test_AC20_no_path_from_negative_opinion_to_SIGNED(self):
        """Opinion tieu cuc chi co the toi SIGNED_WITH_DIVERGENCE."""
        for decision in (OpinionDecision.ESCALATE_TO_CRO_RISK,
                         OpinionDecision.REJECT_INSUFFICIENT_EVIDENCE):
            for actor in (DIRECTOR, AUTHORITY, CRO):
                h = Harness()
                case = make_case(required_authority=AuthorityLevel.BRANCH_DIRECTOR)
                opinion = make_opinion(decision=decision, conditions=())
                ack = h.acknowledge(case, opinion, actor)
                control = h.gate.evaluate(case, opinion, actor, ack, now=NOW)
                self.assertNotIn(
                    Action.SIGN, control.allowed_actions,
                    "SIGN khong duoc phep voi opinion {} cho {}".format(
                        decision.value, actor.role
                    ),
                )
                with self.assertRaises(ControlError):
                    h.service.submit(
                        case, opinion, actor,
                        DecisionRequest(Action.SIGN, "APPROVED", "k",
                                        acknowledgement_id=ack.acknowledgement_id),
                        now=NOW,
                    )
                self.assertEqual(0, len(h.decisions.rows))

    def test_AC20b_divergent_sign_reaches_signed_with_divergence(self):
        result = self.h.service.submit(self.case, self.opinion, DIRECTOR,
                                       self._request(), now=NOW)
        self.assertEqual(201, result.http_status)
        self.assertEqual(ControlState.SIGNED_WITH_DIVERGENCE,
                         self.case.control_state)
        self.assertEqual("DIVERGENT", result.decision.alignment)

    def test_AC20c_terminal_case_is_read_only(self):
        self.h.service.submit(self.case, self.opinion, DIRECTOR,
                              self._request(), now=NOW)
        control = self.h.gate.evaluate(self.case, self.opinion, CRO, None, now=NOW)
        self.assertEqual((Action.VIEW,), control.allowed_actions)
        self.assertIn("CASE_CLOSED", control.blocked_reasons)


# ---------------------------------------------------------------------------
# Bo sung: warning hash va acknowledgement
# ---------------------------------------------------------------------------


class TestWarningHash(unittest.TestCase):
    def test_stale_warning_set_is_rejected_at_acknowledge(self):
        h = Harness()
        case = make_case()
        opinion = make_opinion()
        with self.assertRaises(ControlError) as ctx:
            h.service.acknowledge(case, opinion, DIRECTOR,
                                  hashlib.sha256(b"sai").hexdigest(),
                                  opinion.decisive_finding_ids)
        self.assertEqual("STALE_WARNING_SET", ctx.exception.code)
        self.assertEqual(409, ctx.exception.http_status)

    def test_warning_hash_changes_when_decisive_findings_change(self):
        case = make_case()
        a = compute_warning_hash(case, make_opinion())
        b = compute_warning_hash(
            case, make_opinion(decisive_finding_ids=("F-011", "F-014", "F-020"))
        )
        self.assertNotEqual(a, b)

    def test_warning_hash_is_order_independent(self):
        case = make_case()
        a = compute_warning_hash(case, make_opinion(decisive_finding_ids=("F-011", "F-014")))
        b = compute_warning_hash(case, make_opinion(decisive_finding_ids=("F-014", "F-011")))
        self.assertEqual(a, b)

    def test_acknowledgement_of_another_actor_is_not_reusable(self):
        h = Harness()
        case = make_case()
        opinion = make_opinion()
        ack = h.acknowledge(case, opinion, DIRECTOR)
        ack.status = AckStatus.SUPERSEDED
        control = h.gate.evaluate(case, opinion, DIRECTOR, ack, now=NOW)
        self.assertIn("ACKNOWLEDGE_WARNINGS", control.pending_requirements)
        self.assertNotIn(Action.SIGN, control.allowed_actions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
