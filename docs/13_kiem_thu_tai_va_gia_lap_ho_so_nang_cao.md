# Hướng Dẫn Kiểm Thử Tải (Load Testing) & Giả Lập Hồ Sơ Tín Dụng Nâng Cao (Synthetic Dossier)

Tài liệu này hướng dẫn chi tiết quy trình kiểm thử hiệu năng, đo đạc thông lượng (Throughput), phân vị độ trễ (Latency Percentiles) và phương pháp sinh ngẫu nhiên hàng nghìn bộ hồ sơ doanh nghiệp phục vụ thẩm định tín dụng tự động trong CreditAgent POC.

---

## 🎯 1. Mục Tiêu Kiểm Thử Tải (Load Testing Objectives)

1. **Đo đạc Năng lực Xử lý (System Throughput - TPS)**: Số lượng bộ hồ sơ thẩm định trọn vòng 13 Agents hoàn tất thành công trên mỗi giây.
2. **Phân tích Phân vị Độ trễ (End-to-End Latency Percentiles)**:
   - **P50 (Median)**: Thời gian xử lý trung vị của hệ thống khi chịu tải.
   - **P90 / P95 / P99**: Đánh giá độ trễ biên dưới tác động nghẽn hàng đợi (Queue Contention) hoặc tắc nghẽn tài nguyên.
3. **Kiểm tra Tính Toàn vẹn Dữ liệu (State & Audit Integrity)**:
   - Đảm bảo mỗi lượt chạy sinh một mã hồ sơ duy nhất `case_id` (`CASE-{SCENARIO}-{UUID}`).
   - Kiểm tra việc ghi vết đầy đủ vào bảng `credit_cases` và `audit_events` trong SQLite/PostgreSQL.
4. **Kiểm tra Cơ chế Bộ đệm Phân tán Multi-Tier Claim Check Store**:
   - Đảm bảo cơ chế L1 RAM $\rightarrow$ L2 Redis $\rightarrow$ L3 Database hoạt động ổn định, cách ly bộ nhớ hoàn toàn giữa các luồng chạy song song.

---

## 🚀 2. Hướng Dẫn Sử Dụng Công Cụ Load Test (`scripts/load_test.py`)

Công cụ benchmark được xây dựng chuyên dụng, hỗ trợ 2 chế độ kiểm thử chính:

### Chế độ A: Kiểm thử qua HTTP REST API (`--mode api`)
Mô phỏng hành vi thực tế của nhiều Cán bộ Tín dụng / Trình duyệt hoặc hệ thống LOS bắn request đồng thời vào Web Server:

```bash
# Chạy 20 hồ sơ với 5 luồng đồng thời qua HTTP API:
PYTHONPATH=src python3 scripts/load_test.py -n 20 -c 5 -m api

# Chạy 50 hồ sơ ĐỘNG với 10 luồng song song:
PYTHONPATH=src python3 scripts/load_test.py -n 50 -c 10 -m api -d
```

### Chế độ B: Kiểm thử trực tiếp vào Temporal Engine (`--mode temporal`)
Bắn tải trực tiếp vào Temporal Server Cluster để đo lường công suất tối đa của cụm Temporal Workers:

```bash
# Chạy 30 hồ sơ với 6 luồng trực tiếp vào Temporal:
PYTHONPATH=src python3 scripts/load_test.py -n 30 -c 6 -m temporal

# Chạy 20 hồ sơ động thuộc nhóm rủi ro rửa tiền (AML):
PYTHONPATH=src python3 scripts/load_test.py -n 20 -c 4 -m temporal -d -a SUSPICIOUS_AML -o report_aml.json
```

### Chạy qua Lệnh CLI Dự án
```bash
PYTHONPATH=src python3 -m credit_agent_poc load-test -n 20 -c 4 -d
```

---

## 🏭 3. Bộ Sinh Hồ Sơ Động (Synthetic Dossier Generator)

Module `SyntheticDossierGenerator` trong `src/credit_agent_poc/dossier_generator.py` mô phỏng các doanh nghiệp SME/Mid-Corp Việt Nam với các trường thông tin thực tế:

### Các Tham Số Biến Thiên
- **Tên Doanh nghiệp**: Sinh ngẫu nhiên từ tiền tố pháp lý (`Công ty TNHH`, `Công ty Cổ phần`, `Tập đoàn`) và tên thương mại thực tế.
- **Mã số thuế (MST)**: Định dạng 10 chữ số chuẩn Việt Nam (`010...`, `030...`, `360...`).
- **Ngành nghề**: `wholesale`, `manufacturing`, `construction`, `services`, `retail`, `logistics`, `agriculture`, `pharmaceuticals`, `technology`.
- **Doanh thu & Dòng tiền**: Doanh thu khai báo từ 5 tỷ - 120 tỷ VNĐ; dòng tiền vào quan sát qua sao kê từ 40% - 120% doanh thu.
- **Nhu cầu vay**: 1 tỷ - 50 tỷ VNĐ với các mục đích thực tế (`working_capital`, `import_raw_materials`, `machinery_upgrade`,...).

### 5 Nhóm Hồ Sơ Đặc Trưng (Risk Archetypes)

| Archetype | Đặc Điểm Dữ Liệu | Expected Outcome | Quyết Định Control Gate |
|---|---|---|---|
| `HEALTHY_PRIME` | DSCR ≥ 1.5, TSBĐ ≥ 1.3, Hồ sơ đủ 12 tháng, AML sạch | `APPROVE_WITH_CONDITIONS` | `READY_FOR_HUMAN_REVIEW` |
| `POLICY_EXCEPTION_TENOR` | Tài chính tốt nhưng thời hạn vay 36 tháng (vượt trần quy định) | `ESCALATE_TO_CRO_RISK` | `ESCALATED_FOR_HUMAN_REVIEW` |
| `SUSPICIOUS_AML` | Điểm giao dịch lòng vòng ≥ 0.88, tập trung dòng tiền bất thường | `ESCALATE_TO_CRO_RISK` | `ESCALATED_FOR_HUMAN_REVIEW` |
| `WEAK_CASHFLOW` | DSCR < 0.85, dòng tiền sao kê yếu dù TSBĐ cao (TSBĐ không chữa lỗi dòng tiền) | `REJECT_INSUFFICIENT_EVIDENCE` | `HUMAN_REVIEW_RECOMMENDED_REJECT` |
| `INCOMPLETE_DOCS` | Chỉ có 2-4 tháng sao kê ngân hàng, thiếu chứng từ gốc | `REJECT_INSUFFICIENT_EVIDENCE` | `HUMAN_REVIEW_RECOMMENDED_REJECT` |

---

## 🔌 4. API Nạp Hồ Sơ Tùy Biến (Custom Dossier Injection)

### Endpoint 1: Nạp và Thẩm định Hồ sơ Tùy biến (`POST /api/run-custom`)
Hệ thống cho phép nạp trực tiếp hồ sơ dạng JSON từ LOS / Core Banking:

```bash
curl -X POST http://127.0.0.1:8080/api/run-custom \
  -H "Content-Type: application/json" \
  -d '{
    "borrower": {
      "name": "Công ty TNHH Xuất Nhập Khẩu Nam Á",
      "tax_code": "0301234567",
      "segment": "SME",
      "industry": "logistics"
    },
    "request": {
      "amount": 8000000000,
      "tenor_months": 12,
      "purpose": "working_capital"
    },
    "declared_revenue": 50000000000,
    "observed_inflow": 48000000000,
    "dscr": 1.82,
    "collateral_coverage": 1.6,
    "documents_complete": true,
    "statement_months": 12
  }'
```

**Response**:
```json
{
  "run_id": "f8a12bc4-8931-4c12-b1d9-5a1e809f4567",
  "scenario_id": "custom_a1b2c3d4",
  "company_name": "Công ty TNHH Xuất Nhập Khẩu Nam Á",
  "status": "RUNNING"
}
```

### Endpoint 2: Sinh hàng loạt Hồ sơ Thử nghiệm (`POST /api/generate-synthetic`)
```bash
curl -X POST http://127.0.0.1:8080/api/generate-synthetic \
  -H "Content-Type: application/json" \
  -d '{"count": 5, "archetype": "HEALTHY_PRIME"}'
```

---

## 📊 5. Mẫu Báo Cáo Kết Quả Benchmark

```text
======================================================================
 🚀 CREDITAGENT POC LOAD & STRESS TEST BENCHMARK
======================================================================
 • Mode:             API (http://127.0.0.1:8080)
 • Target:           Web Server Async Runner
 • Total Requests:   12
 • Concurrency:      4 concurrent workers
 • Dossier Mode:     ⚡ DYNAMIC SYNTHETIC (Archetype: RANDOM_MIX)
======================================================================

Progress: |██████████████████████████████| 12/12 (100.0%) 

======================================================================
 📊 LOAD TEST EXECUTION SUMMARY REPORT
======================================================================
 • Total Completed:  12 cases (12 passed, 0 failed)
 • Success Rate:     100.0%
 • Total Wall Clock: 9.75s
 • System TPS:       1.23 loans/sec
----------------------------------------------------------------------
 ⏱️  LATENCY PERCENTILES (Thời gian thẩm định qua 13 AI Agents):
   - Min Latency:    2832.2 ms
   - Mean Latency:   3146.2 ms
   - P50 (Median):   3244.0 ms
   - P90:            3258.8 ms
   - P95:            3258.8 ms
   - P99:            3262.8 ms
   - Max Latency:    3262.8 ms
----------------------------------------------------------------------
 ⚖️  CREDIT OUTCOMES BREAKDOWN:
   - APPROVE_WITH_CONDITIONS            :    2 cases
   - ESCALATE_TO_CRO_RISK               :    4 cases
   - REJECT_INSUFFICIENT_EVIDENCE       :    6 cases
----------------------------------------------------------------------
 🛡️  CONTROL GATE DECISIONS:
   - Control Gate Status 'ESCALATED_FOR_HUMAN_REVIEW':    4 cases
   - Control Gate Status 'HUMAN_REVIEW_RECOMMENDED_REJECT':    6 cases
   - Control Gate Status 'READY_FOR_HUMAN_REVIEW':    2 cases
----------------------------------------------------------------------
 💾 DATABASE PERSISTENCE STATUS:
   - Rows in `credit_cases`:  331
   - Rows in `audit_events`:  10867
======================================================================
```
