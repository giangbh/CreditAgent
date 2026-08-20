from __future__ import annotations

import random
import uuid
from dataclasses import replace
from typing import Any, Dict, List, Optional

from .scenarios import SCENARIOS, Scenario

COMPANY_PREFIXES = ["Công ty TNHH", "Công ty Cổ phần", "Tập đoàn", "Doanh nghiệp Tư nhân"]
COMPANY_NAMES = [
    "Cơ khí Hoàng Phát", "Xuất Nhập Khẩu Hải Đăng", "Nông Nghiệp Xanh Toàn Cầu",
    "Thương Mại & Dịch Vụ Nam Á", "Bách Hóa Tổng Hợp Thăng Long", "Xây Dựng & Địa Ốc Đại Việt",
    "Công Nghệ & Tự Động Hóa VinaTech", "Dệt May & Thời Trang An Bình", "Thực Phẩm & Đồ Uống Á Châu",
    "Vận Tải & Kho Vận Biển Đông", "Dược Phẩm & Thiết Bị Y Tế Hòa Bình", "Vật Liệu Xây Dựng Tiến Bộ",
    "Chế Biến Thủy Hải Sản Cửu Long", "Bao Bì & In Ấn Minh Khang", "Khai Thác Khoáng Sản Đông Dương"
]

INDUSTRIES = [
    "wholesale", "manufacturing", "construction", "services",
    "retail", "logistics", "agriculture", "pharmaceuticals", "technology"
]

SEGMENTS = ["SME", "MICRO_SME", "MID_CORP"]
PURPOSES = [
    "working_capital", "import_raw_materials", "expand_warehouse",
    "machinery_upgrade", "seasonal_inventory", "contract_financing"
]


class SyntheticDossierGenerator:
    """Enterprise-grade Synthetic Loan Dossier Generator.

    Generates realistic corporate & SME borrowers with realistic financial
    metrics, cashflow distributions, and risk archetypes.
    """

    @classmethod
    def generate_company_name(cls) -> str:
        return f"{random.choice(COMPANY_PREFIXES)} {random.choice(COMPANY_NAMES)}"

    @classmethod
    def generate_tax_code(cls) -> str:
        # Vietnamese 10-digit tax code format
        prefix = random.choice(["010", "030", "360", "370", "040"])
        return f"{prefix}{random.randint(1000000, 9999999)}"

    @classmethod
    def generate_scenario(
        cls,
        scenario_id: Optional[str] = None,
        archetype: Optional[str] = None,
        custom_params: Optional[Dict[str, Any]] = None,
    ) -> Scenario:
        """Generates a fully formed Scenario object based on archetype or random parameters."""
        sc_id = scenario_id or f"dyn_{uuid.uuid4().hex[:8]}"
        company_name = cls.generate_company_name()
        tax_code = cls.generate_tax_code()
        segment = random.choice(SEGMENTS)
        industry = random.choice(INDUSTRIES)
        purpose = random.choice(PURPOSES)

        arch = (archetype or random.choice([
            "HEALTHY_PRIME",
            "HEALTHY_PRIME",
            "POLICY_EXCEPTION_TENOR",
            "SUSPICIOUS_AML",
            "WEAK_CASHFLOW",
            "INCOMPLETE_DOCS",
        ])).upper()

        # Base financial sizing (in VND)
        revenue = float(random.randint(5, 120) * 1_000_000_000)
        loan_amount = float(random.randint(1, max(2, int(revenue * 0.4 / 1_000_000_000))) * 1_000_000_000)
        tenor_months = random.choice([6, 9, 12, 18, 24, 36])

        # Default standard healthy parameters
        params: Dict[str, Any] = {
            "scenario_id": sc_id,
            "name": f"Hồ sơ {company_name} ({arch})",
            "description": f"Khoản vay {purpose} cho {company_name} (MST: {tax_code}, Ngành: {industry})",
            "expected_outcome": "APPROVE_WITH_CONDITIONS",
            "borrower": {
                "entity_id": f"ENT-{tax_code[:6]}",
                "name": company_name,
                "tax_code": tax_code,
                "segment": segment,
                "industry": industry,
            },
            "request": {
                "amount": loan_amount,
                "tenor_months": tenor_months,
                "purpose": purpose,
            },
            "documents_complete": True,
            "statement_months": 12,
            "declared_revenue": revenue,
            "observed_inflow": revenue * random.uniform(0.85, 1.15),
            "existing_debt_service": revenue * 0.08,
            "projected_debt_service": revenue * 0.12,
            "dscr": round(random.uniform(1.45, 2.10), 2),
            "inflow_concentration": round(random.uniform(0.15, 0.42), 2),
            "circular_funds_score": round(random.uniform(0.01, 0.12), 2),
            "related_party_coverage": round(random.uniform(0.80, 0.98), 2),
            "collateral_coverage": round(random.uniform(1.25, 2.20), 2),
            "policy_exception": False,
            "authority_escalation": False,
            "forced_tool_failures": (),
        }

        # Apply specific Risk Archetype mutations
        if arch == "HEALTHY_PRIME":
            params["expected_outcome"] = "APPROVE_WITH_CONDITIONS"
            params["request"]["amount"] = float(random.randint(1, 3) * 1_000_000_000)
            params["request"]["tenor_months"] = 12
            params["dscr"] = round(random.uniform(1.50, 2.20), 2)
            params["collateral_coverage"] = round(random.uniform(1.30, 2.50), 2)
            params["circular_funds_score"] = round(random.uniform(0.01, 0.08), 2)
            params["inflow_concentration"] = round(random.uniform(0.15, 0.35), 2)
            params["related_party_coverage"] = round(random.uniform(0.85, 0.98), 2)
            params["documents_complete"] = True
            params["policy_exception"] = False
            params["authority_escalation"] = False

        elif arch == "POLICY_EXCEPTION_TENOR":
            params["expected_outcome"] = "ESCALATE_TO_CRO_RISK"
            params["request"]["tenor_months"] = 36  # Breaches standard working capital policy limit
            params["policy_exception"] = True
            params["authority_escalation"] = True
            params["dscr"] = round(random.uniform(1.35, 1.80), 2)

        elif arch == "SUSPICIOUS_AML":
            params["expected_outcome"] = "ESCALATE_TO_CRO_RISK"
            params["circular_funds_score"] = round(random.uniform(0.88, 0.96), 2)
            params["related_party_coverage"] = round(random.uniform(0.90, 0.99), 2)
            params["inflow_concentration"] = round(random.uniform(0.70, 0.92), 2)

        elif arch == "WEAK_CASHFLOW":
            params["expected_outcome"] = "REJECT_INSUFFICIENT_EVIDENCE"
            params["observed_inflow"] = revenue * random.uniform(0.40, 0.60)
            params["dscr"] = round(random.uniform(0.55, 0.85), 2)
            params["collateral_coverage"] = round(random.uniform(2.50, 3.50), 2)  # High collateral cannot cure weak repayment

        elif arch == "INCOMPLETE_DOCS":
            params["expected_outcome"] = "REJECT_INSUFFICIENT_EVIDENCE"
            params["documents_complete"] = False
            params["statement_months"] = random.choice([2, 3, 4])
            params["dscr"] = round(random.uniform(1.10, 1.30), 2)

        # Merge custom user overrides if provided
        if custom_params:
            if "borrower" in custom_params and isinstance(custom_params["borrower"], dict):
                params["borrower"].update(custom_params["borrower"])
            if "request" in custom_params and isinstance(custom_params["request"], dict):
                params["request"].update(custom_params["request"])
            for k, v in custom_params.items():
                if k not in ("borrower", "request"):
                    params[k] = v

        return Scenario(**params)

    @classmethod
    def register_scenario(cls, scenario: Scenario) -> str:
        """Dynamically registers a Scenario into the global SCENARIOS registry."""
        SCENARIOS[scenario.scenario_id] = scenario
        return scenario.scenario_id

    @classmethod
    def generate_and_register(
        cls,
        scenario_id: Optional[str] = None,
        archetype: Optional[str] = None,
        custom_params: Optional[Dict[str, Any]] = None,
    ) -> Scenario:
        """Generates and registers a new dynamic scenario ready for immediate execution."""
        sc = cls.generate_scenario(scenario_id=scenario_id, archetype=archetype, custom_params=custom_params)
        cls.register_scenario(sc)
        return sc

    @classmethod
    def generate_batch(cls, count: int = 10, archetype: Optional[str] = None) -> List[Scenario]:
        """Generates and registers a batch of unique synthetic scenarios."""
        scenarios = []
        for i in range(count):
            sc = cls.generate_and_register(scenario_id=f"syn_{i+1:03d}_{uuid.uuid4().hex[:6]}", archetype=archetype)
            scenarios.append(sc)
        return scenarios
