import json
import unittest
from unittest.mock import MagicMock

from credit_agent_poc.claim_check import (
    InMemoryClaimCheckStore,
    RedisClaimCheckStore,
    TieredClaimCheckStore,
    get_claim_check_store,
)
from credit_agent_poc.db import StateRepository
from credit_agent_poc.models import AuditEvent, CreditState


class ClaimCheckStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state1 = CreditState(
            case_id="CASE-TEST-001",
            scenario_id="approve_conditions",
            run_id="run-001",
            state_version=1,
            case_file={"cif": "CIF-001", "requested_amount": 500000000},
        )
        self.state2 = CreditState(
            case_id="CASE-TEST-002",
            scenario_id="escalate_policy_exception",
            run_id="run-002",
            state_version=2,
            case_file={"cif": "CIF-002", "requested_amount": 1000000000},
        )

    def test_in_memory_store_put_get_delete(self) -> None:
        store = InMemoryClaimCheckStore(max_entries=10)
        self.assertFalse(store.contains("CASE-TEST-001"))
        self.assertIsNone(store.get("CASE-TEST-001"))

        store.put("CASE-TEST-001", self.state1)
        self.assertTrue(store.contains("CASE-TEST-001"))
        self.assertIn("CASE-TEST-001", store)

        retrieved = store.get("CASE-TEST-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.case_id, "CASE-TEST-001")
        self.assertEqual(retrieved.case_file["cif"], "CIF-001")

        # Test deepcopy isolation
        retrieved.case_file["cif"] = "MODIFIED"
        fresh = store.get("CASE-TEST-001")
        self.assertEqual(fresh.case_file["cif"], "CIF-001")

        # Test delete
        store.delete("CASE-TEST-001")
        self.assertFalse(store.contains("CASE-TEST-001"))

    def test_in_memory_store_lru_eviction(self) -> None:
        store = InMemoryClaimCheckStore(max_entries=2)
        s1 = CreditState(case_id="C1", scenario_id="s1", run_id="r1")
        s2 = CreditState(case_id="C2", scenario_id="s2", run_id="r2")
        s3 = CreditState(case_id="C3", scenario_id="s3", run_id="r3")

        store.put("C1", s1)
        store.put("C2", s2)
        self.assertTrue(store.contains("C1"))
        self.assertTrue(store.contains("C2"))

        # Access C1 so C2 becomes oldest
        _ = store.get("C1")
        store.put("C3", s3)

        # C2 should be evicted, C1 and C3 remain
        self.assertTrue(store.contains("C1"))
        self.assertFalse(store.contains("C2"))
        self.assertTrue(store.contains("C3"))

    def test_redis_store_with_mock_client(self) -> None:
        mock_redis = MagicMock()
        fake_redis_dict = {}

        def fake_get(key: str) -> str:
            return fake_redis_dict.get(key)

        def fake_set(key: str, val: str, ex: int = None) -> bool:
            fake_redis_dict[key] = val
            return True

        def fake_delete(*keys: str) -> int:
            cnt = 0
            for k in keys:
                if k in fake_redis_dict:
                    del fake_redis_dict[k]
                    cnt += 1
            return cnt

        def fake_ping() -> bool:
            return True

        mock_redis.get.side_effect = fake_get
        mock_redis.set.side_effect = fake_set
        mock_redis.delete.side_effect = fake_delete
        mock_redis.ping.side_effect = fake_ping
        mock_redis.keys.return_value = ["credit_claim_check:CASE-TEST-001"]

        redis_store = RedisClaimCheckStore(redis_client=mock_redis, key_prefix="credit_claim_check:")
        self.assertTrue(redis_store.is_available())

        # Test put
        redis_store.put("CASE-TEST-001", self.state1, ttl_seconds=3600)
        self.assertIn("credit_claim_check:CASE-TEST-001", fake_redis_dict)

        # Test get
        loaded = redis_store.get("CASE-TEST-001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.case_id, "CASE-TEST-001")
        self.assertEqual(loaded.case_file["cif"], "CIF-001")

        # Test delete
        redis_store.delete("CASE-TEST-001")
        self.assertNotIn("credit_claim_check:CASE-TEST-001", fake_redis_dict)

    def test_redis_store_graceful_connection_failure(self) -> None:
        # Invalid redis URL with no actual server running
        redis_store = RedisClaimCheckStore(redis_url="redis://127.0.0.1:9999/0")
        self.assertFalse(redis_store.is_available())
        self.assertIsNone(redis_store.get("CASE-NONEXISTENT"))

    def test_tiered_store_multi_layer_resolution(self) -> None:
        l1 = InMemoryClaimCheckStore()
        db_repo = StateRepository(db_path=":memory:")

        # Initialize Tiered store with L1 and L3 (no L2 redis active)
        tiered_store = TieredClaimCheckStore(l1_memory=l1, l2_redis=None, l3_repository=db_repo)

        # 1. Put into Tiered Store -> writes through to L1 and L3 DB
        tiered_store.put("CASE-TEST-001", self.state1)
        self.assertIsNotNone(l1.get("CASE-TEST-001"))
        self.assertIsNotNone(db_repo.load_case("CASE-TEST-001"))

        # 2. Clear L1 memory -> L1 is empty
        l1.clear()
        self.assertIsNone(l1.get("CASE-TEST-001"))

        # 3. Get from Tiered store -> Fallback to L3 DB and backfills L1
        recovered = tiered_store.get("CASE-TEST-001")
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.case_id, "CASE-TEST-001")

        # Verify L1 was backfilled
        self.assertIsNotNone(l1.get("CASE-TEST-001"))

    def test_get_claim_check_store_factory(self) -> None:
        mem_store = get_claim_check_store(store_type="MEMORY", force_new=True)
        self.assertIsInstance(mem_store, InMemoryClaimCheckStore)

        tiered_store = get_claim_check_store(store_type="TIERED", db_path=":memory:", force_new=True)
        self.assertIsInstance(tiered_store, TieredClaimCheckStore)


if __name__ == "__main__":
    unittest.main()
