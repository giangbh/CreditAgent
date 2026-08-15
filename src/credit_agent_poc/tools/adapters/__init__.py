from __future__ import annotations

from .base_adapter import BaseBankAdapter
from .cic_adapter import CICAdapter
from .collateral_adapter import CollateralAdapter
from .core_banking_adapter import CoreBankingAdapter
from .idp_ocr_adapter import IDPOCRAdapter

__all__ = [
    "BaseBankAdapter",
    "CICAdapter",
    "CollateralAdapter",
    "CoreBankingAdapter",
    "IDPOCRAdapter",
]
