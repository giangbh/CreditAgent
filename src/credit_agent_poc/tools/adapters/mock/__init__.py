from __future__ import annotations

from .cic_adapter import CICAdapter
from .collateral_adapter import CollateralAdapter
from .core_banking_adapter import CoreBankingAdapter
from .idp_ocr_adapter import IDPOCRAdapter
from .rest_backend_adapter import RESTBackendAdapter

__all__ = [
    "CICAdapter",
    "CollateralAdapter",
    "CoreBankingAdapter",
    "IDPOCRAdapter",
    "RESTBackendAdapter",
]
