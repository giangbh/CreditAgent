from __future__ import annotations

from .base_adapter import BaseBankAdapter
from .mock import (
    CICAdapter,
    CollateralAdapter,
    CoreBankingAdapter,
    IDPOCRAdapter,
    RESTBackendAdapter,
)
from .production import (
    BaseProductionHTTPAdapter,
    ProductionCoreBankingAdapter,
    ProductionIDPOCREngineAdapter,
    ProductionCICAdapter,
    ProductionGraphFraudAdapter,
    ProductionPolicyBREAdapter,
    ProductionLOSStructuringAdapter,
    ProductionEnterpriseBackend,
)

__all__ = [
    "BaseBankAdapter",
    "CICAdapter",
    "CollateralAdapter",
    "CoreBankingAdapter",
    "IDPOCRAdapter",
    "RESTBackendAdapter",
    "BaseProductionHTTPAdapter",
    "ProductionCoreBankingAdapter",
    "ProductionIDPOCREngineAdapter",
    "ProductionCICAdapter",
    "ProductionGraphFraudAdapter",
    "ProductionPolicyBREAdapter",
    "ProductionLOSStructuringAdapter",
    "ProductionEnterpriseBackend",
]
