from __future__ import annotations

from typing import Any, Optional
from ...scenarios import Scenario


class ScenarioDataGenerator:
    """Generates realistic, rich backend JSON responses for all 25 credit tools based on scenario context."""

    @staticmethod
    def get_document_inventory(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        docs = [
            {
                "document_id": "DOC-001",
                "document_type": "application",
                "filename": "Loan_Application_Form.pdf",
                "status": "VALID",
                "pages": 4,
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            },
            {
                "document_id": "DOC-002",
                "document_type": "company_registration",
                "filename": "Business_Registration_Certificate.pdf",
                "status": "VALID",
                "pages": 2,
                "sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
            },
            {
                "document_id": "DOC-003",
                "document_type": "bank_statement",
                "filename": "Bank_Statement_12M.pdf",
                "status": "VALID",
                "pages": 36,
                "sha256": "3e23e8160039594a33894f6564e1b1348bbd7a0088d42c4acb73eee7935b2041",
            },
        ]
        if s.documents_complete:
            docs.append({
                "document_id": "DOC-004",
                "document_type": "financial_statement",
                "filename": "Audited_Financial_Statement_2025.pdf",
                "status": "VALID",
                "pages": 18,
                "sha256": "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
            })
        return {
            "application_id": f"APP-{s.scenario_id.upper()}",
            "total_documents": len(docs),
            "documents": docs,
            "system": "DMS_ECM",
        }

    @staticmethod
    def get_classify_document(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        doc_id = args.get("document_id", "DOC-001")
        doc_type_map = {
            "DOC-001": "LOAN_APPLICATION",
            "DOC-002": "BUSINESS_REGISTRATION",
            "DOC-003": "BANK_STATEMENT",
            "DOC-004": "FINANCIAL_STATEMENT",
        }
        classified_type = doc_type_map.get(doc_id, "GENERAL_CREDIT_DOCUMENT")
        return {
            "document_id": doc_id,
            "classification": classified_type,
            "confidence": 0.992,
            "verification_status": "CONFIRMED",
            "extracted_attributes": {"language": "vi", "ocr_quality": "HIGH"},
            "system": "DMS_IDP_ENGINE",
        }

    @staticmethod
    def get_extract_document_fields(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        req = dict(s.request)
        req["requested_amount"] = req.get("amount", 2_000_000_000)
        return {
            "document_id": args.get("document_id", "DOC-001"),
            "borrower": {
                "entity_id": s.borrower.get("entity_id", "ENT-001"),
                "tax_id": f"03{abs(hash(s.scenario_id)) % 100000000:08d}",
                "company_name": f"Cong Ty TNHH {s.scenario_id.replace('_', ' ').title()}",
                "segment": s.borrower.get("segment", "SME"),
                "industry": s.borrower.get("industry", "general"),
            },
            "request": req,
            "declared_revenue": s.declared_revenue,
            "extraction_confidence": 0.975,
            "system": "IDP_OCR_EXTRACT",
        }

    @staticmethod
    def get_parse_bank_statement(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        months = s.statement_months
        total_inflow = s.observed_inflow
        total_outflow = int(total_inflow * 0.85)
        return {
            "artifact_ref": f"artifact://{s.scenario_id}/transactions",
            "statement_months": months,
            "coverage_start": "2025-01-01",
            "coverage_end": f"2025-{months:02d}-28",
            "reconciled": True,
            "opening_balance": 150_000_000,
            "closing_balance": 280_000_000,
            "total_inflow": total_inflow,
            "total_outflow": total_outflow,
            "transaction_count": months * 120,
            "system": "STATEMENT_PARSER_ENGINE",
        }

    @staticmethod
    def get_resolve_borrower_identity(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "entity_id": s.borrower.get("entity_id", "ENT-001"),
            "cif_number": f"CIF-{abs(hash(s.scenario_id)) % 1000000:06d}",
            "legal_name": f"Cong Ty TNHH {s.scenario_id.replace('_', ' ').title()}",
            "status": "MATCHED",
            "confidence": 1.0,
            "blacklisted": False,
            "pep_status": False,
            "tax_code_valid": True,
            "system": "CORE_BANKING_CIF",
        }

    @staticmethod
    def get_validate_case_completeness(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        missing = []
        if not s.documents_complete:
            missing.append("financial_statement")
        if s.statement_months < 6:
            missing.append("minimum_6_month_bank_statement")
        return {
            "case_id": f"CASE-{s.scenario_id.upper()}",
            "complete": len(missing) == 0,
            "missing": missing,
            "checklist": {
                "application_form": True,
                "business_license": True,
                "bank_statement_6m": s.statement_months >= 6,
                "financial_statement": s.documents_complete,
            },
            "system": "LOS_ORIGINATION",
        }

    @staticmethod
    def get_query_transactions(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        limit = args.get("limit", 50)
        sample_transactions = [
            {
                "transaction_id": f"TX-{i:04d}",
                "date": f"2025-06-{(i % 28) + 1:02d}",
                "amount": (i + 1) * 25_000_000,
                "direction": "IN" if i % 2 == 0 else "OUT",
                "counterparty": f"Doi Tac {chr(65 + (i % 6))}",
                "narrative": f"Thanh toan tien hang hop dong #{100 + i}",
            }
            for i in range(min(limit, 10))
        ]
        return {
            "artifact_ref": f"artifact://{s.scenario_id}/transaction-query",
            "record_count": s.statement_months * 120,
            "coverage_months": s.statement_months,
            "sample_transactions": sample_transactions,
            "currency": "VND",
            "system": "CORE_BANKING_TRANSACTIONS",
        }

    @staticmethod
    def get_compute_cashflow_metrics(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        avg_monthly_inflow = round(s.observed_inflow / max(1, s.statement_months), 2)
        return {
            "metric_id": f"METRIC-CASH-{s.scenario_id}",
            "observed_inflow": s.observed_inflow,
            "avg_monthly_inflow": avg_monthly_inflow,
            "inflow_concentration": s.inflow_concentration,
            "top_counterparty_share": s.inflow_concentration,
            "coverage_months": s.statement_months,
            "net_cashflow": int(s.observed_inflow * 0.15),
            "system": "CASHFLOW_ANALYTICS_SERVICE",
        }

    @staticmethod
    def get_detect_cashflow_anomalies(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        anomalies = []
        if s.inflow_concentration >= 0.45:
            anomalies.append("high_customer_concentration")
        if s.observed_inflow < s.declared_revenue * 0.7:
            anomalies.append("revenue_mismatch_gap")
        return {
            "anomalies": anomalies,
            "evidence_id": f"EVD-CASH-{s.scenario_id}",
            "risk_score": 0.65 if anomalies else 0.05,
            "system": "CASHFLOW_AI_ENGINE",
        }

    @staticmethod
    def get_reconcile_declared_revenue(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        ratio = round(s.observed_inflow / s.declared_revenue, 4) if s.declared_revenue else 0.0
        discrepancy = s.declared_revenue - s.observed_inflow
        return {
            "calculation_ref": f"CALC-REV-{s.scenario_id}",
            "declared_revenue": s.declared_revenue,
            "observed_inflow": s.observed_inflow,
            "match_ratio": ratio,
            "discrepancy_amount": discrepancy,
            "reconciled": ratio >= 0.85,
            "system": "FINANCIAL_SPREADING_ENGINE",
        }

    @staticmethod
    def get_calculate_credit_capacity(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        req_amount = s.request.get("amount", 2_000_000_000)
        supported = req_amount if s.dscr >= 1.2 else max(0, int(req_amount * s.dscr / 1.2))
        return {
            "calculation_ref": f"CALC-CAP-{s.scenario_id}",
            "dscr": s.dscr,
            "min_required_dscr": 1.20,
            "requested_amount": req_amount,
            "supported_amount": supported,
            "primary_repayment_viable": s.dscr >= 1.2 and s.statement_months >= 6,
            "system": "FINANCIAL_RATING_CAPACITY_ENGINE",
        }

    @staticmethod
    def get_stress_repayment_capacity(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        revenue_drop_pct = args.get("revenue_drop_pct", 0.22)
        stressed_dscr = round(s.dscr * (1.0 - revenue_drop_pct), 2)
        return {
            "calculation_ref": f"CALC-STRESS-{s.scenario_id}",
            "base_dscr": s.dscr,
            "stressed_dscr": stressed_dscr,
            "revenue_stress_applied": f"-{int(revenue_drop_pct * 100)}%",
            "passes": stressed_dscr >= 1.0,
            "system": "RISK_STRESS_TEST_ENGINE",
        }

    @staticmethod
    def get_assess_refinancing_pattern(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        refinancing_detected = s.dscr < 0.8 and s.collateral_coverage > 2.0
        return {
            "finding": "REFINANCING_RISK_SUSPECTED" if refinancing_detected else "NONE_DETECTED",
            "evidence_id": f"EVD-REFI-{s.scenario_id}",
            "repayment_source_verified": not refinancing_detected,
            "system": "EARLY_WARNING_SYSTEM",
        }

    @staticmethod
    def get_build_entity_transaction_graph(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "graph_ref": f"graph://{s.scenario_id}",
            "nodes_count": 12,
            "edges_count": 34,
            "related_party_coverage": s.related_party_coverage,
            "target_entity": s.borrower.get("entity_id", "ENT-001"),
            "system": "GRAPH_DB_NEO4J",
        }

    @staticmethod
    def get_detect_transaction_cycles(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        has_cycle = s.circular_funds_score >= 0.7
        cycles = []
        if has_cycle:
            cycles.append({
                "cycle_id": f"CYCLE-{s.scenario_id}",
                "nodes": ["ENT-004", "PARTNER-X", "SHELL-COMPANY-Y", "ENT-004"],
                "flow_amount": 1_800_000_000,
                "confidence": s.circular_funds_score,
            })
        return {
            "cycle_score": s.circular_funds_score,
            "cycle_ids": [c["cycle_id"] for c in cycles],
            "detected_cycles": cycles,
            "evidence_id": f"EVD-INTEGRITY-{s.scenario_id}",
            "risk_level": "HIGH" if has_cycle else "LOW",
            "system": "ANTI_FRAUD_GRAPH_ANALYTICS",
        }

    @staticmethod
    def get_trace_funds(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "path_ref": f"path://{s.scenario_id}/material-flow",
            "status": "TRACED",
            "hops_analyzed": 4,
            "origin_account": "ACC-001-BORROWER",
            "destination_account": "ACC-999-BENEFICIARY",
            "system": "AML_FUNDS_TRACE_ENGINE",
        }

    @staticmethod
    def get_search_policy(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query", "working_capital tenor limit")
        return {
            "query": query,
            "candidate_clause_ids": ["POL-WC-001", "POL-WC-017", "POL-RISK-009"],
            "policy_snapshot_id": "POLICY-SME-2025-v2.1",
            "top_match_score": 0.94,
            "system": "POLICY_VECTOR_RAG",
        }

    @staticmethod
    def get_get_policy_clause(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        clause_id = args.get("clause_id", "POL-WC-001")
        return {
            "clause_id": clause_id,
            "title": "Hạn mức và Kỳ hạn Cho vay Bổ sung Vốn lưu động SME",
            "effective": True,
            "max_tenor_months": 24,
            "max_unsecured_amount": 2_000_000_000,
            "product": "working_capital",
            "source_ref": "policy://sme/v2.1/working-capital#clause-001",
            "system": "BRE_POLICY_MANAGEMENT",
        }

    @staticmethod
    def get_evaluate_policy_rule(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        if s.circular_funds_score >= 0.8:
            disposition = "MANDATORY_ESCALATION"
            rule_id = "RULE-INTEGRITY-007"
            reason = "Phát hiện dấu hiệu dòng tiền vòng tròn vượt ngưỡng cho phép (score >= 0.80)"
        elif s.policy_exception:
            disposition = "MANDATORY_ESCALATION"
            rule_id = "RULE-TENOR-003"
            reason = "Thời hạn cấp tín dụng đề xuất vượt hạn mức tối đa theo quy định"
        else:
            disposition = "ADVISORY"
            rule_id = "RULE-WC-BASE"
            reason = "Tuân thủ đầy đủ các quy tắc chính sách tín dụng hiện hành"

        return {
            "rule_id": rule_id,
            "disposition": disposition,
            "reason": reason,
            "policy_citation_id": f"CITE-{rule_id}",
            "system": "BUSINESS_RULE_ENGINE",
        }

    @staticmethod
    def get_validate_policy_citation(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        citation_id = args.get("policy_citation_id", "CITE-RULE-WC-BASE")
        return {
            "policy_citation_id": citation_id,
            "valid": True,
            "policy_snapshot_id": "POLICY-SME-2025-v2.1",
            "legal_disclaimer": "Trích dẫn chính xác theo Quyết định 1234/QĐ-NHNN.",
            "system": "LEGAL_COMPLIANCE_ENGINE",
        }

    @staticmethod
    def get_resolve_approval_authority(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        req_amount = s.request.get("amount", 2_000_000_000)
        requires_cro = s.authority_escalation or s.policy_exception or s.circular_funds_score >= 0.8 or req_amount > 3_000_000_000
        authority = "CRO_RISK" if requires_cro else "CREDIT_COMMITTEE"
        return {
            "authority": authority,
            "escalation_required": s.authority_escalation or requires_cro,
            "authority_level": "LEVEL_1_HỘI_SỞ" if requires_cro else "LEVEL_2_CHI_NHÁNH",
            "approval_threshold_amount": 3_000_000_000,
            "system": "LOS_AUTHORITY_MATRIX",
        }

    @staticmethod
    def get_calculate_amortization(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        amount = args.get("amount", s.request.get("amount", 2_000_000_000))
        tenor = args.get("tenor_months", s.request.get("tenor_months", 12))
        rate_annual = args.get("interest_rate_annual", 0.085)
        monthly_principal = round(amount / tenor, 2)
        first_month_interest = round(amount * (rate_annual / 12), 2)
        return {
            "calculation_ref": f"CALC-AMORT-{s.scenario_id}",
            "total_amount": amount,
            "tenor_months": tenor,
            "annual_interest_rate": rate_annual,
            "monthly_principal": monthly_principal,
            "first_month_interest": first_month_interest,
            "total_first_month_payment": monthly_principal + first_month_interest,
            "system": "AMORTIZATION_ENGINE",
        }

    @staticmethod
    def get_resolve_pricing_band(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        band = "RISK_ADJUSTED_B" if s.dscr >= 1.4 else "RISK_ADJUSTED_C"
        base_rate = 0.075 if band == "RISK_ADJUSTED_B" else 0.090
        spread = 0.015
        return {
            "pricing_band": band,
            "base_rate": base_rate,
            "margin_spread": spread,
            "effective_rate": round(base_rate + spread, 4),
            "source_ref": f"pricing://sme/v1/{band.lower().replace('_', '-')}",
            "system": "PRICING_TARIFF_SYSTEM",
        }

    @staticmethod
    def get_validate_deal_structure(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        violations = []
        if s.dscr < 1.2:
            violations.append("DSCR_BELOW_MINIMUM_THRESHOLD")
        if s.circular_funds_score >= 0.8:
            violations.append("CIRCULAR_FUNDS_RISK_BREACH")
        if s.policy_exception:
            violations.append("POLICY_TENOR_EXCEEDED")
        if not s.documents_complete:
            violations.append("MISSING_CRITICAL_FINANCIAL_DOCUMENTS")

        valid = len(violations) == 0
        return {
            "case_id": f"CASE-{s.scenario_id.upper()}",
            "valid": valid,
            "violations": violations,
            "collateral_coverage_ratio": s.collateral_coverage,
            "recommendation": "PROCEED" if valid else "REQUIRES_ESCALATION_OR_REJECTION",
            "system": "LOS_VALIDATION_ENGINE",
        }

    @staticmethod
    def get_retrieve_approved_memory(s: Scenario, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "query_industry": s.borrower.get("industry", "general"),
            "entries": [
                {
                    "case_ref": "CASE-HIST-2024-88",
                    "similarity_score": 0.89,
                    "approved_exception": "TENOR_EXTENSION_36M",
                    "mitigating_factor": "Strong collateral coverage 2.5x and 5-year clean repayment history",
                    "approver_role": "CRO_RISK",
                }
            ] if s.policy_exception else [],
            "note": "Historical approval memory retrieved successfully",
            "system": "KNOWLEDGE_MEMORY_STORE",
        }
