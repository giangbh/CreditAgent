"""Control Gate, integrity seal, audit hash chain va Decision Service.

Reference implementation cho `docs/06 v2.0`. Chi dung standard library.

Nguyen tac:
  - Gate duoc tinh lai o server tai moi request; khong tin `allowed_actions`
    ma client gui len.
  - Thu tu bat buoc: gate -> audit -> notification bat buoc -> ghi quyet dinh.
  - Fail closed voi du lieu, fail degraded voi ha tang.
  - Bang quyet dinh chi INSERT; dinh chinh bang ban ghi moi.

Dat file tai: src/credit_agent_poc/control_gate.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum, IntEnum
from typing import Dict, List, Optional, Sequence, Tuple

from .logger import audit_log

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Action(str, Enum):
    VIEW = "VIEW"
    REQUEST_INFO = "REQUEST_INFO"
    REANALYZE = "REANALYZE"
    ESCALATE = "ESCALATE"
    SIGN = "SIGN"
    SIGN_WITH_DIVERGENCE = "SIGN_WITH_DIVERGENCE"
    REJECT = "REJECT"
    WITHDRAW = "WITHDRAW"


TERMINAL_ACTIONS = frozenset(
    {Action.SIGN, Action.SIGN_WITH_DIVERGENCE, Action.REJECT}
)
SIGNING_ACTIONS = frozenset({Action.SIGN, Action.SIGN_WITH_DIVERGENCE})


class ControlState(str, Enum):
    AI_REVIEW_REQUIRED = "AI_REVIEW_REQUIRED"
    NEEDS_EVIDENCE_REVIEW = "NEEDS_EVIDENCE_REVIEW"
    AI_OPINION_READY = "AI_OPINION_READY"
    APPROVABLE = "APPROVABLE"
    DIVERGENCE_REQUIRED = "DIVERGENCE_REQUIRED"
    ESCALATED = "ESCALATED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    BLOCKED = "BLOCKED"
    SIGNED = "SIGNED"
    SIGNED_WITH_DIVERGENCE = "SIGNED_WITH_DIVERGENCE"
    SIGNED_PENDING_REVIEW = "SIGNED_PENDING_REVIEW"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


TERMINAL_STATES = frozenset(
    {
        ControlState.SIGNED,
        ControlState.SIGNED_WITH_DIVERGENCE,
        ControlState.SIGNED_PENDING_REVIEW,
        ControlState.REJECTED,
        ControlState.WITHDRAWN,
    }
)


class OpinionDecision(str, Enum):
    APPROVE_WITH_CONDITIONS = "APPROVE_WITH_CONDITIONS"
    ESCALATE_TO_CRO_RISK = "ESCALATE_TO_CRO_RISK"
    REJECT_INSUFFICIENT_EVIDENCE = "REJECT_INSUFFICIENT_EVIDENCE"


NEGATIVE_OPINIONS = frozenset(
    {
        OpinionDecision.ESCALATE_TO_CRO_RISK,
        OpinionDecision.REJECT_INSUFFICIENT_EVIDENCE,
    }
)


class OpinionStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"
    SUPERSEDED = "SUPERSEDED"


class Alignment(str, Enum):
    CONCURRENT = "CONCURRENT"
    DIVERGENT = "DIVERGENT"
    AUTHORIZED_EXCEPTION = "AUTHORIZED_EXCEPTION"
    NO_AI_OPINION = "NO_AI_OPINION"


class AuthorityLevel(IntEnum):
    RM = 10
    CREDIT_OFFICER = 20
    BRANCH_DIRECTOR = 30
    CREDIT_AUTHORITY = 40
    CRO = 50


class AckStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class Disposition(str, Enum):
    OBSERVATION = "OBSERVATION"
    SOFT_WARNING = "SOFT_WARNING"
    MANDATORY_ESCALATION = "MANDATORY_ESCALATION"
    HARD_BLOCK = "HARD_BLOCK"


class FailureKind(str, Enum):
    """Phan biet loi ha tang voi loi du lieu. Xem doc 06 muc 3.3."""

    INFRASTRUCTURE = "INFRASTRUCTURE"  # provider timeout, gateway down, cluster loi
    DATA = "DATA"  # thieu chung tu, schema invalid, evidence conflict


class ReasonDirection(str, Enum):
    LOOSEN = "LOOSEN"
    TIGHTEN = "TIGHTEN"
    BOTH = "BOTH"


# ---------------------------------------------------------------------------
# Loi nghiep vu -> ma HTTP
# ---------------------------------------------------------------------------


class ControlError(Exception):
    def __init__(self, code: str, http_status: int, detail: str = "", **extra):
        super().__init__("{}: {}".format(code, detail))
        self.code = code
        self.http_status = http_status
        self.detail = detail
        self.extra = extra


class SealPayloadError(ValueError):
    """Payload thieu field bat buoc -> khong duoc tra ve seal."""


# ---------------------------------------------------------------------------
# Bang ma ly do (co version, co rang buoc huong)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReasonCode:
    code: str
    direction: ReasonDirection
    requires_escalation: bool = False
    requires_documents: bool = False
    min_authority: AuthorityLevel = AuthorityLevel.BRANCH_DIRECTOR
    feeds_model_risk: bool = False
    allowed_with_hard_block: bool = True


REASON_CODES: Dict[str, ReasonCode] = {
    rc.code: rc
    for rc in [
        ReasonCode("NEW_EVIDENCE_PROVIDED", ReasonDirection.LOOSEN,
                   requires_documents=True),
        ReasonCode("AI_FINDING_FACTUALLY_WRONG", ReasonDirection.LOOSEN,
                   feeds_model_risk=True),
        ReasonCode("POLICY_INTERPRETATION_DISPUTE", ReasonDirection.BOTH,
                   requires_escalation=True),
        ReasonCode("COLLATERAL_EXCEPTION_REQUEST", ReasonDirection.LOOSEN,
                   requires_escalation=True,
                   min_authority=AuthorityLevel.CREDIT_AUTHORITY),
        ReasonCode("STRATEGIC_CUSTOMER_EXCEPTION", ReasonDirection.LOOSEN,
                   requires_escalation=True,
                   min_authority=AuthorityLevel.CREDIT_AUTHORITY,
                   allowed_with_hard_block=False),
        ReasonCode("ADDITIONAL_RISK_OBSERVED", ReasonDirection.TIGHTEN,
                   feeds_model_risk=True),
        ReasonCode("LOCAL_KNOWLEDGE_NEGATIVE", ReasonDirection.TIGHTEN),
        ReasonCode("OTHER_REQUIRES_REVIEW", ReasonDirection.BOTH,
                   requires_escalation=True),
    ]
}

REASON_CODE_SET_VERSION = "reason-codes-2026.08"
MIN_NARRATIVE_LENGTH = 120


# ---------------------------------------------------------------------------
# Canonical JSON + integrity seal
# ---------------------------------------------------------------------------


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError("Khong serialize duoc: {!r}".format(value))


def canonical_json(payload: dict) -> str:
    """Chuoi canonical: khoa sap xep, khong khoang trang thua, UTF-8."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


SHA256_OF_EMPTY = hashlib.sha256(b"").hexdigest()

REQUIRED_SEAL_FIELDS: Tuple[str, ...] = (
    "decision_id",
    "case_id",
    "case_revision",
    "actor_id",
    "actor_role",
    "action",
    "human_decision",
    "alignment",
    "created_at",
)


class KeyStore:
    """Thay the bang KMS/HSM o production. App khong duoc doc khoa."""

    def __init__(self, keys: Optional[Dict[str, bytes]] = None):
        self._keys = keys or {"seal-key-1": b"local-dev-key-do-not-use-in-prod"}

    def sign(self, key_id: str, message: bytes) -> str:
        if key_id not in self._keys:
            raise KeyError("Khong ton tai seal_key_id={}".format(key_id))
        return hmac.new(self._keys[key_id], message, hashlib.sha256).hexdigest()


def build_seal_payload(decision: "Decision") -> dict:
    return {
        "decision_id": decision.decision_id,
        "case_id": decision.case_id,
        "case_revision": decision.case_revision,
        "opinion_id": decision.opinion_id,
        "opinion_version": decision.opinion_version,
        "actor_id": decision.actor_id,
        "actor_role": decision.actor_role,
        "action": decision.action,
        "human_decision": decision.human_decision,
        "alignment": decision.alignment,
        "divergence_reason_code": decision.divergence_reason_code,
        "narrative_sha256": (
            hashlib.sha256(decision.divergence_narrative.encode("utf-8")).hexdigest()
            if decision.divergence_narrative
            else None
        ),
        "approved_amount": decision.approved_amount,
        "approved_currency": decision.approved_currency,
        "approved_tenor_months": decision.approved_tenor_months,
        "approved_rate_pct": decision.approved_rate_pct,
        "acknowledgement_id": decision.acknowledgement_id,
        "warning_hash": decision.warning_hash,
        "created_at": decision.created_at,
    }


def compute_integrity_seal(payload: dict, key_store: KeyStore, key_id: str) -> str:
    """HMAC-SHA256 tren canonical payload.

    KHONG phai chu ky so. Xem doc 06 muc 6.
    Thieu bat ky field bat buoc nao -> nem loi, khong tra ve seal.
    """
    missing = [
        f
        for f in REQUIRED_SEAL_FIELDS
        if f not in payload or payload[f] is None or payload[f] == ""
    ]
    if missing:
        raise SealPayloadError(
            "Payload thieu field bat buoc: {}".format(", ".join(sorted(missing)))
        )
    return key_store.sign(key_id, canonical_json(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# Audit log co chuoi bam
# ---------------------------------------------------------------------------


GENESIS_HASH = "0" * 64


@dataclass
class AuditEntry:
    seq: int
    event_id: str
    event_type: str
    case_id: Optional[str]
    actor_id: str
    payload: dict
    prev_hash: str
    entry_hash: str
    occurred_at: datetime


class AuditWriteError(RuntimeError):
    pass


class AuditLog:
    """Append-only, hash-chained. O production: thu hoi UPDATE/DELETE o cap DB."""

    def __init__(self):
        self._entries: List[AuditEntry] = []
        self._lock = threading.Lock()

    @staticmethod
    def _hash(prev_hash: str, payload: dict, seq: int) -> str:
        material = "{}|{}|{}".format(prev_hash, canonical_json(payload), seq)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def append(
        self,
        event_type: str,
        payload: dict,
        actor_id: str = "SYSTEM",
        case_id: Optional[str] = None,
    ) -> AuditEntry:
        with self._lock:
            seq = len(self._entries) + 1
            prev_hash = self._entries[-1].entry_hash if self._entries else GENESIS_HASH
            entry = AuditEntry(
                seq=seq,
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                case_id=case_id,
                actor_id=actor_id,
                payload=payload,
                prev_hash=prev_hash,
                entry_hash=self._hash(prev_hash, payload, seq),
                occurred_at=datetime.now(timezone.utc),
            )
            self._entries.append(entry)
            return entry

    @property
    def entries(self) -> Sequence[AuditEntry]:
        return tuple(self._entries)

    def verify(self) -> Tuple[bool, Optional[int]]:
        """Tra ve (hop_le, seq_dau_tien_bi_lech)."""
        prev_hash = GENESIS_HASH
        for entry in self._entries:
            expected = self._hash(prev_hash, entry.payload, entry.seq)
            if entry.prev_hash != prev_hash or entry.entry_hash != expected:
                return False, entry.seq
            prev_hash = entry.entry_hash
        return True, None


class FailingAuditLog(AuditLog):
    """Dung de kiem thu fail-closed."""

    def __init__(self, fail_on: Sequence[str] = ()):
        super().__init__()
        self.fail_on = frozenset(fail_on)

    def append(self, event_type, payload, actor_id="SYSTEM", case_id=None):
        if not self.fail_on or event_type in self.fail_on:
            raise AuditWriteError("Khong ghi duoc audit event: {}".format(event_type))
        return super().append(event_type, payload, actor_id, case_id)


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


class NotificationTier(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    DAILY_DIGEST = "DAILY_DIGEST"
    WEEKLY_DIGEST = "WEEKLY_DIGEST"


@dataclass
class Notification:
    notification_id: str
    case_id: str
    trigger_type: str
    tier: NotificationTier
    recipient_role: str
    mandatory: bool
    idempotency_key: str
    status: str = "QUEUED"


class NotificationError(RuntimeError):
    pass


class Notifier:
    def __init__(self, fail_triggers: Sequence[str] = ()):
        self.fail_triggers = frozenset(fail_triggers)
        self.sent: List[Notification] = []
        self.failed: List[Notification] = []

    def send(self, notification: Notification) -> None:
        if notification.trigger_type in self.fail_triggers:
            notification.status = "FAILED"
            self.failed.append(notification)
            raise NotificationError(notification.trigger_type)
        notification.status = "SENT"
        self.sent.append(notification)


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    finding_id: str
    severity: str
    disposition: Disposition
    code: str = ""


@dataclass(frozen=True)
class Condition:
    condition_id: str
    owner: Optional[str] = None
    due_point: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        return bool(self.owner) and bool(self.due_point)


@dataclass(frozen=True)
class Opinion:
    opinion_id: str
    opinion_version: int
    case_revision: int
    decision: OpinionDecision
    status: OpinionStatus
    source_snapshot_hash: str
    policy_snapshot_id: str
    ruleset_version: str
    issued_at: datetime
    decisive_finding_ids: Tuple[str, ...] = ()
    findings: Tuple[Finding, ...] = ()
    conditions: Tuple[Condition, ...] = ()

    @property
    def hard_blocks(self) -> Tuple[Finding, ...]:
        return tuple(
            f for f in self.findings if f.disposition == Disposition.HARD_BLOCK
        )


@dataclass
class Case:
    case_id: str
    case_revision: int
    source_snapshot_hash: str
    policy_snapshot_id: str
    ruleset_version: str
    required_authority: AuthorityLevel = AuthorityLevel.BRANCH_DIRECTOR
    control_state: ControlState = ControlState.AI_REVIEW_REQUIRED
    evidence_review_required: bool = False
    ai_availability: str = "AVAILABLE"  # AVAILABLE | UNAVAILABLE


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: str
    authority_level: AuthorityLevel
    branch_id: str
    has_exception_authority: bool = False


@dataclass
class Acknowledgement:
    acknowledgement_id: str
    case_id: str
    opinion_id: str
    opinion_version: int
    actor_id: str
    warning_hash: str
    acknowledged_finding_ids: Tuple[str, ...]
    status: AckStatus = AckStatus.ACTIVE
    superseded_reason: Optional[str] = None


@dataclass
class Decision:
    decision_id: str
    case_id: str
    case_revision: int
    run_id: str
    opinion_id: Optional[str]
    opinion_version: Optional[int]
    ai_decision: Optional[str]
    ai_availability: str
    policy_snapshot_id: str
    ruleset_version: str
    source_snapshot_hash: str
    actor_id: str
    actor_role: str
    actor_authority_level: int
    branch_id: str
    action: str
    human_decision: str
    alignment: str
    divergence_reason_code: Optional[str]
    divergence_narrative: Optional[str]
    acknowledgement_id: Optional[str]
    warning_hash: Optional[str]
    approved_amount: Optional[Decimal]
    approved_currency: Optional[str]
    approved_tenor_months: Optional[int]
    approved_rate_pct: Optional[Decimal]
    integrity_seal: str
    seal_key_id: str
    audit_event_id: str
    notification_ids: Tuple[str, ...]
    post_review_required: bool
    idempotency_key: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Warning hash
# ---------------------------------------------------------------------------


def compute_warning_hash(case: Case, opinion: Opinion) -> str:
    """Bam tren tap finding quyet dinh cua dung mot opinion_version."""
    material = {
        "case_revision": case.case_revision,
        "opinion_id": opinion.opinion_id,
        "opinion_version": opinion.opinion_version,
        "decisive_finding_ids": sorted(opinion.decisive_finding_ids),
        "policy_snapshot_id": opinion.policy_snapshot_id,
    }
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Gate policy + ControlDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GatePolicy:
    ruleset_version: str = "gate-rules-2026.08"
    hard_block_min_authority: AuthorityLevel = AuthorityLevel.CREDIT_AUTHORITY
    non_overridable_hard_block_codes: frozenset = frozenset({"HB_AML_SANCTION"})
    opinion_validity_days: int = 15
    ai_unavailable_threshold_minutes: int = 60
    post_review_sla_days: int = 5


@dataclass
class ControlDecision:
    case_id: str
    case_revision: int
    opinion_id: Optional[str]
    opinion_version: Optional[int]
    control_state: ControlState
    allowed_actions: Tuple[Action, ...]
    blocked_reasons: Tuple[str, ...]
    pending_requirements: Tuple[str, ...]
    warning_hash: Optional[str]
    required_finding_ids: Tuple[str, ...]
    required_authority: AuthorityLevel
    actor_authority: AuthorityLevel
    authority_sufficient: bool
    post_review_required: bool
    computed_at: datetime
    ruleset_version: str

    def allows(self, action: Action) -> bool:
        return action in self.allowed_actions


class ControlGate:
    def __init__(self, policy: Optional[GatePolicy] = None):
        self.policy = policy or GatePolicy()

    def evaluate(
        self,
        case: Case,
        opinion: Optional[Opinion],
        actor: Actor,
        acknowledgement: Optional[Acknowledgement] = None,
        now: Optional[datetime] = None,
    ) -> ControlDecision:
        now = now or datetime.now(timezone.utc)
        allowed = {Action.VIEW}
        blocked: List[str] = []
        pending: List[str] = []
        post_review = False
        warning_hash: Optional[str] = None
        required_findings: Tuple[str, ...] = ()

        # --- Trang thai ket thuc: chi con doc ---
        if case.control_state in TERMINAL_STATES:
            return self._build(
                case, opinion, actor, ControlState(case.control_state),
                (Action.VIEW,), ("CASE_CLOSED",), (), None, (), False, now
            )

        allowed |= {Action.REQUEST_INFO, Action.WITHDRAW, Action.ESCALATE}

        # --- Che do suy giam: fail degraded voi ha tang ---
        if case.ai_availability == "UNAVAILABLE":
            blocked.append("AI_UNAVAILABLE")
            post_review = True
            allowed |= {Action.SIGN, Action.REJECT, Action.REANALYZE}
            # Khong duoc di vong qua HARD_BLOCK cua mot opinion truoc con hieu luc.
            if opinion is not None and opinion.hard_blocks and self._is_fresh(
                case, opinion, now
            ):
                allowed -= {Action.SIGN}
                blocked.append("UNRESOLVED_HARD_BLOCK")
            state = ControlState.AI_UNAVAILABLE
            if not self._authority_ok(case, actor):
                allowed -= TERMINAL_ACTIONS
                blocked.append("INSUFFICIENT_AUTHORITY")
            return self._build(
                case, opinion, actor, state, tuple(sorted(allowed, key=lambda a: a.value)),
                tuple(blocked), tuple(pending), None, (), post_review, now
            )

        # --- Khong co opinion hop le ---
        if opinion is None or opinion.status != OpinionStatus.VALIDATED:
            blocked.append("NO_VALID_OPINION")
            allowed.add(Action.REANALYZE)
            allowed.add(Action.REJECT)
            return self._build(
                case, opinion, actor, ControlState.AI_REVIEW_REQUIRED,
                tuple(sorted(allowed, key=lambda a: a.value)),
                tuple(blocked), tuple(pending), None, (), False, now
            )

        # --- Opinion stale ---
        if not self._is_fresh(case, opinion, now):
            blocked.append("STALE_OPINION")
            allowed.add(Action.REANALYZE)
            allowed.add(Action.REJECT)
            return self._build(
                case, opinion, actor, ControlState.AI_REVIEW_REQUIRED,
                tuple(sorted(allowed, key=lambda a: a.value)),
                tuple(blocked), tuple(pending), None, (), False, now
            )

        # --- Du lieu toi han chua review: fail closed voi du lieu ---
        if case.evidence_review_required:
            blocked.append("EVIDENCE_REVIEW_REQUIRED")
            allowed.add(Action.REANALYZE)
            return self._build(
                case, opinion, actor, ControlState.NEEDS_EVIDENCE_REVIEW,
                tuple(sorted(allowed, key=lambda a: a.value)),
                tuple(blocked), tuple(pending), None, (), False, now
            )

        warning_hash = compute_warning_hash(case, opinion)
        required_findings = tuple(sorted(opinion.decisive_finding_ids))
        allowed |= {Action.REANALYZE, Action.REJECT}

        hard_blocks = opinion.hard_blocks
        non_overridable = [
            f for f in hard_blocks
            if f.code in self.policy.non_overridable_hard_block_codes
        ]

        if non_overridable:
            blocked.append("NON_OVERRIDABLE_HARD_BLOCK")
            state = ControlState.ESCALATED
        elif hard_blocks:
            blocked.append("UNRESOLVED_HARD_BLOCK")
            state = ControlState.DIVERGENCE_REQUIRED
            if actor.authority_level >= self.policy.hard_block_min_authority:
                allowed.add(Action.SIGN_WITH_DIVERGENCE)
            else:
                blocked.append("HARD_BLOCK_AUTHORITY_REQUIRED")
        elif opinion.decision == OpinionDecision.APPROVE_WITH_CONDITIONS:
            incomplete = [c for c in opinion.conditions if not c.is_complete]
            if incomplete:
                blocked.append("CONDITION_INCOMPLETE")
                state = ControlState.AI_OPINION_READY
            else:
                allowed.add(Action.SIGN)
                state = ControlState.APPROVABLE
        else:
            # Opinion tieu cuc: khong bao gio co duong di thang toi SIGNED.
            state = ControlState.DIVERGENCE_REQUIRED
            allowed.add(Action.SIGN_WITH_DIVERGENCE)

        # --- Tham quyen ---
        if not self._authority_ok(case, actor):
            allowed -= TERMINAL_ACTIONS
            blocked.append("INSUFFICIENT_AUTHORITY")

        # --- Acknowledgement ---
        if not self._ack_valid(acknowledgement, opinion, warning_hash):
            pending.append("ACKNOWLEDGE_WARNINGS")
            allowed -= SIGNING_ACTIONS

        return self._build(
            case, opinion, actor, state,
            tuple(sorted(allowed, key=lambda a: a.value)),
            tuple(blocked), tuple(pending), warning_hash, required_findings,
            post_review, now
        )

    # -- helpers ------------------------------------------------------------

    def _is_fresh(self, case: Case, opinion: Opinion, now: datetime) -> bool:
        if opinion.case_revision != case.case_revision:
            return False
        if opinion.source_snapshot_hash != case.source_snapshot_hash:
            return False
        if opinion.policy_snapshot_id != case.policy_snapshot_id:
            return False
        if opinion.ruleset_version != case.ruleset_version:
            return False
        age = now - opinion.issued_at
        return age <= timedelta(days=self.policy.opinion_validity_days)

    def _authority_ok(self, case: Case, actor: Actor) -> bool:
        return actor.authority_level >= case.required_authority

    @staticmethod
    def _ack_valid(
        ack: Optional[Acknowledgement], opinion: Opinion, warning_hash: str
    ) -> bool:
        if ack is None:
            return False
        return (
            ack.status == AckStatus.ACTIVE
            and ack.opinion_id == opinion.opinion_id
            and ack.opinion_version == opinion.opinion_version
            and ack.warning_hash == warning_hash
        )

    def _build(self, case, opinion, actor, state, allowed, blocked, pending,
               warning_hash, required_findings, post_review, now) -> ControlDecision:
        return ControlDecision(
            case_id=case.case_id,
            case_revision=case.case_revision,
            opinion_id=opinion.opinion_id if opinion else None,
            opinion_version=opinion.opinion_version if opinion else None,
            control_state=state,
            allowed_actions=allowed,
            blocked_reasons=blocked,
            pending_requirements=pending,
            warning_hash=warning_hash,
            required_finding_ids=required_findings,
            required_authority=case.required_authority,
            actor_authority=actor.authority_level,
            authority_sufficient=self._authority_ok(case, actor),
            post_review_required=post_review,
            computed_at=now,
            ruleset_version=self.policy.ruleset_version,
        )


# ---------------------------------------------------------------------------
# Che do suy giam: phan loai loi pipeline
# ---------------------------------------------------------------------------


def classify_pipeline_failure(
    kind: FailureKind,
    minutes_elapsed: int,
    policy: Optional[GatePolicy] = None,
) -> ControlState:
    """Loi ha tang qua nguong -> AI_UNAVAILABLE. Loi du lieu -> NEEDS_EVIDENCE_REVIEW."""
    policy = policy or GatePolicy()
    if kind == FailureKind.DATA:
        return ControlState.NEEDS_EVIDENCE_REVIEW
    if minutes_elapsed >= policy.ai_unavailable_threshold_minutes:
        return ControlState.AI_UNAVAILABLE
    return ControlState.AI_REVIEW_REQUIRED


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------


class DecisionStore:
    """Chi INSERT. Unique terminal decision tren (case_id, case_revision)."""

    def __init__(self):
        self._rows: List[Decision] = []
        self._by_idempotency: Dict[Tuple[str, str, str], Decision] = {}
        self.lock = threading.Lock()

    @property
    def rows(self) -> Sequence[Decision]:
        return tuple(self._rows)

    def find_by_idempotency(self, case_id, actor_id, key) -> Optional[Decision]:
        return self._by_idempotency.get((case_id, actor_id, key))

    def has_terminal(self, case_id: str, case_revision: int) -> bool:
        return any(
            r.case_id == case_id
            and r.case_revision == case_revision
            and Action(r.action) in TERMINAL_ACTIONS
            for r in self._rows
        )

    def insert(self, decision: Decision) -> None:
        if Action(decision.action) in TERMINAL_ACTIONS and self.has_terminal(
            decision.case_id, decision.case_revision
        ):
            raise ControlError(
                "CONFLICT_TERMINAL_DECISION", 409,
                "Da ton tai quyet dinh ket thuc cho case_revision nay",
            )
        self._rows.append(decision)
        self._by_idempotency[
            (decision.case_id, decision.actor_id, decision.idempotency_key)
        ] = decision


class AcknowledgementStore:
    def __init__(self):
        self._rows: Dict[str, Acknowledgement] = {}

    def add(self, ack: Acknowledgement) -> Acknowledgement:
        self._rows[ack.acknowledgement_id] = ack
        return ack

    def get(self, ack_id: str) -> Optional[Acknowledgement]:
        return self._rows.get(ack_id)

    def active_for(self, case_id: str, actor_id: str) -> Optional[Acknowledgement]:
        for ack in self._rows.values():
            if (
                ack.case_id == case_id
                and ack.actor_id == actor_id
                and ack.status == AckStatus.ACTIVE
            ):
                return ack
        return None

    def supersede_all(self, case_id: str, reason: str) -> int:
        count = 0
        for ack in self._rows.values():
            if ack.case_id == case_id and ack.status == AckStatus.ACTIVE:
                ack.status = AckStatus.SUPERSEDED
                ack.superseded_reason = reason
                count += 1
        return count


class ModelRiskBacklog:
    def __init__(self):
        self.items: List[dict] = []

    def add(self, case_id: str, reason_code: str, narrative: str, actor_id: str):
        self.items.append(
            {
                "item_id": str(uuid.uuid4()),
                "case_id": case_id,
                "reason_code": reason_code,
                "narrative": narrative,
                "reported_by": actor_id,
                "created_at": datetime.now(timezone.utc),
            }
        )


# ---------------------------------------------------------------------------
# Decision request + service
# ---------------------------------------------------------------------------


@dataclass
class DecisionRequest:
    action: Action
    human_decision: str
    idempotency_key: str
    acknowledgement_id: Optional[str] = None
    divergence_reason_code: Optional[str] = None
    divergence_narrative: Optional[str] = None
    supporting_document_ids: Tuple[str, ...] = ()
    approved_amount: Optional[Decimal] = None
    approved_currency: Optional[str] = None
    approved_tenor_months: Optional[int] = None
    approved_rate_pct: Optional[Decimal] = None


@dataclass
class DecisionResult:
    decision: Decision
    http_status: int
    idempotent_replay: bool = False


class DecisionService:
    """Thu tu bat buoc: gate -> audit -> notification bat buoc -> ghi quyet dinh."""

    def __init__(
        self,
        gate: ControlGate,
        decisions: DecisionStore,
        acks: AcknowledgementStore,
        audit: AuditLog,
        notifier: Notifier,
        key_store: KeyStore,
        model_risk: Optional[ModelRiskBacklog] = None,
        seal_key_id: str = "seal-key-1",
    ):
        self.gate = gate
        self.decisions = decisions
        self.acks = acks
        self.audit = audit
        self.notifier = notifier
        self.key_store = key_store
        self.model_risk = model_risk or ModelRiskBacklog()
        self.seal_key_id = seal_key_id

    # -- public -------------------------------------------------------------

    def acknowledge(
        self, case: Case, opinion: Opinion, actor: Actor, warning_hash: str,
        finding_ids: Sequence[str],
    ) -> Acknowledgement:
        expected = compute_warning_hash(case, opinion)
        if warning_hash != expected:
            raise ControlError(
                "STALE_WARNING_SET", 409,
                "warning_hash khong khop tap finding hien hanh",
                expected_warning_hash=expected,
                expected_finding_ids=tuple(sorted(opinion.decisive_finding_ids)),
            )
        return self.acks.add(
            Acknowledgement(
                acknowledgement_id=str(uuid.uuid4()),
                case_id=case.case_id,
                opinion_id=opinion.opinion_id,
                opinion_version=opinion.opinion_version,
                actor_id=actor.actor_id,
                warning_hash=warning_hash,
                acknowledged_finding_ids=tuple(finding_ids),
            )
        )

    def submit(
        self,
        case: Case,
        opinion: Optional[Opinion],
        actor: Actor,
        request: DecisionRequest,
        run_id: str = "RUN-LOCAL",
        now: Optional[datetime] = None,
    ) -> DecisionResult:
        now = now or datetime.now(timezone.utc)

        existing = self.decisions.find_by_idempotency(
            case.case_id, actor.actor_id, request.idempotency_key
        )
        if existing is not None:
            return DecisionResult(existing, http_status=200, idempotent_replay=True)

        ack = (
            self.acks.get(request.acknowledgement_id)
            if request.acknowledgement_id
            else None
        )

        # 1. Gate tinh lai o server
        control = self.gate.evaluate(case, opinion, actor, ack, now=now)
        if not control.allows(request.action):
            self._audit_rejection(case, actor, request, control)
            code = self._rejection_code(control)
            raise ControlError(
                code, 403 if code == "INSUFFICIENT_AUTHORITY" else 409,
                "Action {} khong nam trong allowed_actions".format(request.action.value),
                blocked_reasons=control.blocked_reasons,
                pending_requirements=control.pending_requirements,
                allowed_actions=control.allowed_actions,
            )

        # 2. Rang buoc nghiep vu
        alignment = self._resolve_alignment(opinion, request, control)
        self._validate_reason(case, opinion, request, alignment, actor)

        decision_id = str(uuid.uuid4())
        audit_payload = {
            "decision_id": decision_id,
            "case_id": case.case_id,
            "case_revision": case.case_revision,
            "actor_id": actor.actor_id,
            "action": request.action.value,
            "alignment": alignment.value,
            "opinion_version": control.opinion_version,
            "warning_hash": control.warning_hash,
            "reason_code": request.divergence_reason_code,
            "ruleset_version": control.ruleset_version,
        }

        # 3. Audit truoc — loi thi fail closed
        try:
            audit_entry = self.audit.append(
                "human_decision_submitted", audit_payload,
                actor_id=actor.actor_id, case_id=case.case_id,
            )
        except AuditWriteError as exc:
            case.control_state = ControlState.BLOCKED
            raise ControlError(
                "AUDIT_WRITE_FAILED", 503, str(exc)
            )

        # 4. Notification bat buoc truoc — loi thi fail closed
        notifications = self._build_notifications(case, opinion, request, alignment, control)
        sent_ids: List[str] = []
        for notification in notifications:
            try:
                self.notifier.send(notification)
                sent_ids.append(notification.notification_id)
            except NotificationError as exc:
                if notification.mandatory:
                    case.control_state = ControlState.BLOCKED
                    raise ControlError(
                        "NOTIFICATION_FAILED", 503,
                        "Notification bat buoc that bai: {}".format(exc),
                    )
                # Digest that bai khong chan.

        # 5. Ghi quyet dinh
        decision = Decision(
            decision_id=decision_id,
            case_id=case.case_id,
            case_revision=case.case_revision,
            run_id=run_id,
            opinion_id=control.opinion_id,
            opinion_version=control.opinion_version,
            ai_decision=opinion.decision.value if opinion else None,
            ai_availability=case.ai_availability,
            policy_snapshot_id=case.policy_snapshot_id,
            ruleset_version=case.ruleset_version,
            source_snapshot_hash=case.source_snapshot_hash,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            actor_authority_level=int(actor.authority_level),
            branch_id=actor.branch_id,
            action=request.action.value,
            human_decision=request.human_decision,
            alignment=alignment.value,
            divergence_reason_code=request.divergence_reason_code,
            divergence_narrative=request.divergence_narrative,
            acknowledgement_id=ack.acknowledgement_id if ack else None,
            warning_hash=control.warning_hash,
            approved_amount=request.approved_amount,
            approved_currency=request.approved_currency,
            approved_tenor_months=request.approved_tenor_months,
            approved_rate_pct=request.approved_rate_pct,
            integrity_seal="",
            seal_key_id=self.seal_key_id,
            audit_event_id=audit_entry.event_id,
            notification_ids=tuple(sent_ids),
            post_review_required=control.post_review_required,
            idempotency_key=request.idempotency_key,
            created_at=now,
        )
        decision.integrity_seal = compute_integrity_seal(
            build_seal_payload(decision), self.key_store, self.seal_key_id
        )

        with self.decisions.lock:
            self.decisions.insert(decision)
            case.control_state = self._next_state(request.action, control)

        audit_log(
            "HUMAN_DECISION_SIGNED",
            "CONTROL_GATE",
            f"tr-{run_id}",
            case.case_id,
            "CONTROL",
            details={
                "decision_id": decision_id,
                "action": request.action.value,
                "actor_id": actor.actor_id,
                "alignment": alignment.value,
                "integrity_seal": decision.integrity_seal,
            },
        )

        # 6. Phan hoi nguoc ve Model Risk
        code = REASON_CODES.get(request.divergence_reason_code or "")
        if code is not None and code.feeds_model_risk:
            self.model_risk.add(
                case.case_id, code.code, request.divergence_narrative or "",
                actor.actor_id,
            )

        return DecisionResult(decision, http_status=201)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _rejection_code(control: ControlDecision) -> str:
        if "STALE_OPINION" in control.blocked_reasons:
            return "STALE_OPINION"
        if "INSUFFICIENT_AUTHORITY" in control.blocked_reasons:
            return "INSUFFICIENT_AUTHORITY"
        if "ACKNOWLEDGE_WARNINGS" in control.pending_requirements:
            return "ACK_SUPERSEDED"
        return "ACTION_NOT_ALLOWED"

    def _audit_rejection(self, case, actor, request, control) -> None:
        try:
            self.audit.append(
                "human_decision_rejected",
                {
                    "case_id": case.case_id,
                    "actor_id": actor.actor_id,
                    "action": request.action.value,
                    "blocked_reasons": list(control.blocked_reasons),
                    "pending_requirements": list(control.pending_requirements),
                },
                actor_id=actor.actor_id,
                case_id=case.case_id,
            )
        except AuditWriteError:
            pass  # Tu choi van la tu choi; khong tao ban ghi quyet dinh nao.

    @staticmethod
    def _resolve_alignment(
        opinion: Optional[Opinion], request: DecisionRequest,
        control: ControlDecision,
    ) -> Alignment:
        if opinion is None:
            return Alignment.NO_AI_OPINION
        if request.action == Action.SIGN_WITH_DIVERGENCE:
            if "UNRESOLVED_HARD_BLOCK" in control.blocked_reasons:
                return Alignment.AUTHORIZED_EXCEPTION
            return Alignment.DIVERGENT
        if request.action == Action.SIGN:
            return Alignment.CONCURRENT
        if request.action == Action.REJECT:
            return (
                Alignment.CONCURRENT
                if opinion.decision in NEGATIVE_OPINIONS
                else Alignment.DIVERGENT
            )
        return Alignment.CONCURRENT

    def _validate_reason(self, case, opinion, request, alignment, actor) -> None:
        if alignment == Alignment.CONCURRENT or alignment == Alignment.NO_AI_OPINION:
            return
        code_str = request.divergence_reason_code
        if not code_str:
            raise ControlError(
                "REASON_CODE_REQUIRED", 422,
                "Quyet dinh khac y kien AI phai co ma ly do",
            )
        code = REASON_CODES.get(code_str)
        if code is None:
            raise ControlError("UNKNOWN_REASON_CODE", 422, code_str)

        narrative = request.divergence_narrative or ""
        if len(narrative.strip()) < MIN_NARRATIVE_LENGTH:
            raise ControlError(
                "NARRATIVE_TOO_SHORT", 422,
                "Giai trinh toi thieu {} ky tu".format(MIN_NARRATIVE_LENGTH),
            )

        direction = self._request_direction(opinion, request)
        if code.direction != ReasonDirection.BOTH and code.direction != direction:
            raise ControlError(
                "REASON_DIRECTION_MISMATCH", 422,
                "Ma ly do {} co huong {}, khong dung cho quyet dinh huong {}".format(
                    code.code, code.direction.value, direction.value
                ),
            )
        if code.requires_documents and not request.supporting_document_ids:
            raise ControlError(
                "SUPPORTING_DOCUMENTS_REQUIRED", 422, code.code
            )
        if actor.authority_level < code.min_authority:
            raise ControlError(
                "INSUFFICIENT_AUTHORITY", 403,
                "Ma ly do {} yeu cau cap {}".format(
                    code.code, code.min_authority.name
                ),
            )
        if opinion is not None and opinion.hard_blocks and not code.allowed_with_hard_block:
            raise ControlError(
                "REASON_NOT_ALLOWED_WITH_HARD_BLOCK", 422, code.code
            )

    @staticmethod
    def _request_direction(
        opinion: Optional[Opinion], request: DecisionRequest
    ) -> ReasonDirection:
        if request.action in SIGNING_ACTIONS:
            return ReasonDirection.LOOSEN
        return ReasonDirection.TIGHTEN

    @staticmethod
    def _build_notifications(
        case, opinion, request, alignment, control
    ) -> List[Notification]:
        out: List[Notification] = []

        def make(trigger, tier, recipient, mandatory):
            return Notification(
                notification_id=str(uuid.uuid4()),
                case_id=case.case_id,
                trigger_type=trigger,
                tier=tier,
                recipient_role=recipient,
                mandatory=mandatory,
                idempotency_key="{}|{}|{}|{}".format(
                    case.case_id, trigger, control.opinion_version, recipient
                ),
            )

        if alignment == Alignment.AUTHORIZED_EXCEPTION:
            out.append(make("DIVERGENCE_ON_HARD_BLOCK",
                            NotificationTier.IMMEDIATE, "CRO", True))
            out.append(make("DIVERGENCE_ON_HARD_BLOCK_AUDIT",
                            NotificationTier.IMMEDIATE, "INTERNAL_AUDIT", True))
        elif alignment == Alignment.DIVERGENT:
            out.append(make("DIVERGENCE_STANDARD",
                            NotificationTier.WEEKLY_DIGEST, "RISK", False))
        if request.action == Action.ESCALATE:
            out.append(make("ESCALATION_RAISED",
                            NotificationTier.IMMEDIATE, "CREDIT_AUTHORITY", True))
        if control.post_review_required:
            out.append(make("POST_REVIEW_QUEUED",
                            NotificationTier.DAILY_DIGEST, "OPERATIONS", False))
        return out

    @staticmethod
    def _next_state(action: Action, control: ControlDecision) -> ControlState:
        if action == Action.SIGN:
            return (
                ControlState.SIGNED_PENDING_REVIEW
                if control.post_review_required
                else ControlState.SIGNED
            )
        if action == Action.SIGN_WITH_DIVERGENCE:
            return ControlState.SIGNED_WITH_DIVERGENCE
        if action == Action.REJECT:
            return ControlState.REJECTED
        if action == Action.WITHDRAW:
            return ControlState.WITHDRAWN
        if action == Action.ESCALATE:
            return ControlState.ESCALATED
        return control.control_state


# ---------------------------------------------------------------------------
# Kiem tra toan ven ban ghi quyet dinh (job hang ngay)
# ---------------------------------------------------------------------------


def verify_decision_seal(decision: Decision, key_store: KeyStore) -> bool:
    try:
        expected = compute_integrity_seal(
            build_seal_payload(decision), key_store, decision.seal_key_id
        )
    except SealPayloadError:
        return False
    return hmac.compare_digest(expected, decision.integrity_seal)


def apply_case_revision(
    case: Case, acks: AcknowledgementStore, new_source_hash: str
) -> Case:
    """Tang case_revision -> vo hieu hoa moi acknowledgement dang ACTIVE."""
    case.case_revision += 1
    case.source_snapshot_hash = new_source_hash
    acks.supersede_all(case.case_id, "NEW_CASE_REVISION")
    return case
