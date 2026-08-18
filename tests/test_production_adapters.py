from __future__ import annotations

import unittest
from credit_agent_poc.config import CONFIG
from credit_agent_poc.scenarios import SCENARIOS
from credit_agent_poc.models import ToolExecutionError
from credit_agent_poc.tools import ToolGateway
from credit_agent_poc.tools.adapters.production_adapters import (
    ProductionCoreBankingAdapter,
    ProductionIDPOCREngineAdapter,
    ProductionCICAdapter,
    ProductionGraphFraudAdapter,
    ProductionPolicyBREAdapter,
    ProductionLOSStructuringAdapter,
    ProductionEnterpriseBackend,
)


class ProductionAdapterTests(unittest.TestCase):
    def test_config_contains_production_urls(self) -> None:
        self.assertTrue(CONFIG.CBS_ENDPOINT_URL.startswith("http"))
        self.assertTrue(CONFIG.DMS_OCR_ENDPOINT_URL.startswith("http"))
        self.assertTrue(CONFIG.CIC_ENDPOINT_URL.startswith("http"))
        self.assertTrue(CONFIG.GRAPH_FRAUD_ENDPOINT_URL.startswith("http"))
        self.assertTrue(CONFIG.POLICY_BRE_ENDPOINT_URL.startswith("http"))
        self.assertTrue(CONFIG.LOS_STRUCTURING_ENDPOINT_URL.startswith("http"))

    def test_production_adapters_instantiation_uses_config_defaults(self) -> None:
        cbs = ProductionCoreBankingAdapter()
        self.assertEqual(cbs.endpoint_url, CONFIG.CBS_ENDPOINT_URL)

        dms = ProductionIDPOCREngineAdapter()
        self.assertEqual(dms.endpoint_url, CONFIG.DMS_OCR_ENDPOINT_URL)

        cic = ProductionCICAdapter()
        self.assertEqual(cic.endpoint_url, CONFIG.CIC_ENDPOINT_URL)

        graph = ProductionGraphFraudAdapter()
        self.assertEqual(graph.endpoint_url, CONFIG.GRAPH_FRAUD_ENDPOINT_URL)

        bre = ProductionPolicyBREAdapter()
        self.assertEqual(bre.endpoint_url, CONFIG.POLICY_BRE_ENDPOINT_URL)

        los = ProductionLOSStructuringAdapter()
        self.assertEqual(los.endpoint_url, CONFIG.LOS_STRUCTURING_ENDPOINT_URL)

    def test_production_enterprise_backend_instantiation_and_gateway(self) -> None:
        backend = ProductionEnterpriseBackend()
        gateway = ToolGateway(backend=backend)
        self.assertIsInstance(gateway.backend, ProductionEnterpriseBackend)

        # Invalid tool execution raises ToolExecutionError
        with self.assertRaises(ToolExecutionError):
            backend.execute("non_existent_tool", SCENARIOS["approve_conditions"], {})
