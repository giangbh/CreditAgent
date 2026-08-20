from __future__ import annotations

import copy
import json
import logging
import threading
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Dict, Optional

from .config import CONFIG
from .db import StateRepository
from .models import AuditEvent, CreditState

logger = logging.getLogger("credit_agent_poc.claim_check")


class BaseClaimCheckStore(ABC):
    """Abstract Base Class for Claim Check State Stores."""

    @abstractmethod
    def get(self, case_id: str) -> Optional[CreditState]:
        """Retrieve CreditState by case_id."""
        raise NotImplementedError

    @abstractmethod
    def put(self, case_id: str, state: CreditState, ttl_seconds: Optional[int] = None) -> None:
        """Store CreditState by case_id with optional TTL."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, case_id: str) -> None:
        """Delete CreditState by case_id."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored states."""
        raise NotImplementedError

    def contains(self, case_id: str) -> bool:
        """Check if case_id exists in the store."""
        return self.get(case_id) is not None

    def __getitem__(self, case_id: str) -> CreditState:
        val = self.get(case_id)
        if val is None:
            raise KeyError(case_id)
        return val

    def __setitem__(self, case_id: str, state: CreditState) -> None:
        self.put(case_id, state)

    def __contains__(self, case_id: str) -> bool:
        return self.contains(case_id)


class InMemoryClaimCheckStore(BaseClaimCheckStore):
    """L1 In-Memory Thread-Safe LRU Claim Check Store for Microsecond Lookups."""

    def __init__(self, max_entries: int = 1000) -> None:
        self.max_entries = max_entries
        self._store: OrderedDict[str, CreditState] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, case_id: str) -> Optional[CreditState]:
        with self._lock:
            if case_id in self._store:
                self._store.move_to_end(case_id)
                return copy.deepcopy(self._store[case_id])
            return None

    def put(self, case_id: str, state: CreditState, ttl_seconds: Optional[int] = None) -> None:
        with self._lock:
            if case_id in self._store:
                self._store.move_to_end(case_id)
            self._store[case_id] = copy.deepcopy(state)
            if len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    def delete(self, case_id: str) -> None:
        with self._lock:
            self._store.pop(case_id, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def contains(self, case_id: str) -> bool:
        with self._lock:
            return case_id in self._store


class RedisClaimCheckStore(BaseClaimCheckStore):
    """L2 Distributed Redis Claim Check Store for Multi-Worker Temporal Clusters."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "credit_claim_check:",
        default_ttl_seconds: Optional[int] = None,
        redis_client: Optional[Any] = None,
    ) -> None:
        self.redis_url = redis_url or CONFIG.REDIS_URL or "redis://127.0.0.1:6379/0"
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl_seconds or CONFIG.CLAIM_CHECK_TTL_SECONDS
        self._client = redis_client
        self._is_connected: Optional[bool] = None

    def _get_client(self) -> Optional[Any]:
        if self._client is not None:
            return self._client
        try:
            import redis

            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self._client.ping()
            self._is_connected = True
            return self._client
        except Exception as exc:
            logger.warning(f"RedisClaimCheckStore failed to connect to {self.redis_url}: {exc}")
            self._is_connected = False
            return None

    def is_available(self) -> bool:
        """Check if Redis connection is active and responsive."""
        client = self._get_client()
        if client is None:
            return False
        try:
            return bool(client.ping())
        except Exception:
            return False

    def _make_key(self, case_id: str) -> str:
        return f"{self.key_prefix}{case_id}"

    def get(self, case_id: str) -> Optional[CreditState]:
        client = self._get_client()
        if not client:
            return None
        try:
            raw_data = client.get(self._make_key(case_id))
            if not raw_data:
                return None
            state_dict = json.loads(raw_data)
            if "audit" in state_dict and isinstance(state_dict["audit"], list):
                state_dict["audit"] = [
                    AuditEvent(**evt) if isinstance(evt, dict) else evt for evt in state_dict["audit"]
                ]
            return CreditState(**state_dict)
        except Exception as exc:
            logger.warning(f"RedisClaimCheckStore get error for {case_id}: {exc}")
            return None

    def put(self, case_id: str, state: CreditState, ttl_seconds: Optional[int] = None) -> None:
        client = self._get_client()
        if not client:
            return
        try:
            key = self._make_key(case_id)
            ttl = ttl_seconds or self.default_ttl
            raw_data = json.dumps(state.public_snapshot(), ensure_ascii=False)
            client.set(key, raw_data, ex=ttl)
        except Exception as exc:
            logger.warning(f"RedisClaimCheckStore put error for {case_id}: {exc}")

    def delete(self, case_id: str) -> None:
        client = self._get_client()
        if not client:
            return
        try:
            client.delete(self._make_key(case_id))
        except Exception as exc:
            logger.warning(f"RedisClaimCheckStore delete error for {case_id}: {exc}")

    def clear(self) -> None:
        client = self._get_client()
        if not client:
            return
        try:
            keys = client.keys(f"{self.key_prefix}*")
            if keys:
                client.delete(*keys)
        except Exception as exc:
            logger.warning(f"RedisClaimCheckStore clear error: {exc}")


class TieredClaimCheckStore(BaseClaimCheckStore):
    """Tiered Multi-Layer Claim Check Store:
    - Tier 1: Local In-Memory LRU Cache (microsecond latency)
    - Tier 2: Distributed Redis Cache (shared across multi-workers)
    - Tier 3: Persistent Database (SQLite / PostgreSQL)
    """

    def __init__(
        self,
        l1_memory: Optional[InMemoryClaimCheckStore] = None,
        l2_redis: Optional[RedisClaimCheckStore] = None,
        l3_repository: Optional[StateRepository] = None,
    ) -> None:
        self.l1 = l1_memory or InMemoryClaimCheckStore()
        self.l2 = l2_redis
        self.l3 = l3_repository or StateRepository(CONFIG.DB_PATH)

    def get(self, case_id: str) -> Optional[CreditState]:
        # 1. Check L1 Memory Cache (Fastest)
        state = self.l1.get(case_id)
        if state is not None:
            return state

        # 2. Check L2 Distributed Redis Cache
        if self.l2 is not None:
            state = self.l2.get(case_id)
            if state is not None:
                self.l1.put(case_id, state)
                return state

        # 3. Check L3 Persistent Database
        if self.l3 is not None:
            state = self.l3.load_case(case_id)
            if state is not None:
                self.l1.put(case_id, state)
                if self.l2 is not None:
                    self.l2.put(case_id, state)
                return state

        return None

    def put(self, case_id: str, state: CreditState, ttl_seconds: Optional[int] = None) -> None:
        # Write-through to all available tiers
        self.l1.put(case_id, state)
        if self.l2 is not None:
            self.l2.put(case_id, state, ttl_seconds=ttl_seconds)
        if self.l3 is not None:
            try:
                self.l3.save_case(state)
            except Exception as exc:
                logger.warning(f"Failed to persist state to L3 DB for {case_id}: {exc}")

    def delete(self, case_id: str) -> None:
        self.l1.delete(case_id)
        if self.l2 is not None:
            self.l2.delete(case_id)

    def clear(self) -> None:
        self.l1.clear()
        if self.l2 is not None:
            self.l2.clear()


# Global Singleton Store Provider
_GLOBAL_STORE: Optional[BaseClaimCheckStore] = None
_STORE_LOCK = threading.Lock()


def get_claim_check_store(
    store_type: Optional[str] = None,
    redis_url: Optional[str] = None,
    db_path: Optional[str] = None,
    force_new: bool = False,
) -> BaseClaimCheckStore:
    """Factory function providing the configured Claim Check Store instance."""
    global _GLOBAL_STORE
    with _STORE_LOCK:
        if _GLOBAL_STORE is not None and not force_new:
            return _GLOBAL_STORE

        st = (store_type or CONFIG.CLAIM_CHECK_STORE_TYPE).upper()
        effective_redis_url = redis_url or CONFIG.REDIS_URL

        if st == "MEMORY":
            store = InMemoryClaimCheckStore()
        elif st == "REDIS":
            store = RedisClaimCheckStore(redis_url=effective_redis_url)
        else:
            # Default to TIERED (L1 RAM + L2 Redis if url provided + L3 SQLite)
            l2 = RedisClaimCheckStore(redis_url=effective_redis_url) if effective_redis_url else None
            l3 = StateRepository(db_path or CONFIG.DB_PATH)
            store = TieredClaimCheckStore(l2_redis=l2, l3_repository=l3)

        if not force_new:
            _GLOBAL_STORE = store
        return store
