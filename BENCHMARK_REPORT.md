# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Trần Xuân Trường
**Ngày chạy:** 25/11/2026 (GMT+7)
**Môi trường:** Ubuntu 26.04.1 LTS trong WSL2, kernel 6.18.58.1-microsoft-standard-WSL2; Python 3.11.18; WSL nhìn thấy 12 logical CPU và khoảng 7.64 GiB RAM. CP7 chạy trực tiếp bằng Python, một process agent mỗi lần đo; model `mock-llm-small`, v1 ở cổng 8001, v2 ở cổng 8002.

Bằng chứng cấu hình, lệnh, thời gian và exit code: [manifest baseline](reports/cp7/manifest-baseline.json), [manifest sau sửa](reports/cp7/manifest-fixed.json). Mọi load test dùng 300 request, có warm-up riêng không tính vào 300; `MOCK_ERROR_RATE=0.01`, latency cơ bản 120 ms, jitter 60 ms, retrieval 20 ms, slow thêm 1500 ms. Eval dùng `MOCK_ERROR_RATE=0` như ví dụ CI để đo chất lượng thay vì fault ngẫu nhiên; giữ slow rate 0.03. Đây là mock LLM, chi phí mô phỏng, không phải hóa đơn nhà cung cấp.

Đối chiếu artifact/wiring CP7: [verification.txt](reports/cp7/verification.txt), kết quả PASSED. Kiểm tra hash report, đủ số request, bảng số liệu, dataset không đổi, chất lượng final và đóng agent local; không tính phần CP8 chưa chạy là đã đạt.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Theo ngưỡng mặc định của load_test.py; theo dõi phần lớn người dùng thay vì chỉ average |
| Error rate `/ask` | ≤ 2% | Theo ngưỡng mặc định của load_test.py; phát hiện lỗi vượt mức mock 1% dự kiến |
| Accuracy trên golden dataset | ≥ 100% sau sửa KB, không regression | Theo CP7 K5: đạt 23/23 trên bộ câu hỏi được cung cấp; không suy rộng thành accuracy ngoài dataset |

Script dùng phép so sánh `<=` cho latency/error rate. Job CI của Exercise 7.3 dùng ngưỡng accuracy 85% và kiểm tra regression; lần eval cuối CP7 dùng ngưỡng nghiêm hơn 100%.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.87 | 193.9 | 227.3 | 1712.4 | 0.33% | PASS |
| 10 | 38.62 | 201.3 | 235.8 | 1714.0 | 1.67% | PASS |
| 50 | 84.69 | 310.9 | 418.7 | 1776.8 | 1.33% | PASS |
| 100 | 53.65 | 697.1 | 3981.0 | 4348.7 | 1.33% | FAIL (p95) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

RPS tăng gần 10 lần từ concurrency 1 lên 10, nhưng tăng ít hơn khi lên 50 và giảm khi lên 100. p95 ở concurrency 100 đạt 3981.0 ms, vượt SLO dù error rate vẫn dưới 2%. Điều này cho thấy tăng số request đồng thời không bảo đảm throughput tăng tuyến tính. Scheduling, xử lý HTTP/log và tài nguyên máy có thể góp phần vào độ trễ ở tải cao; chưa có profiling để khẳng định nút thắt cụ thể. Giữ nguyên lượt đo FAIL thay vì chỉnh ngưỡng hoặc chạy chọn kết quả đẹp.

Nguồn: [c1](reports/load_v2_c1.json), [c10](reports/load_v2_c10.json), [c50](reports/load_v2_c50.json), [c100](reports/load_v2_c100.json). Các lượt này đo v2 trước khi sửa KB, cùng slow rate 0.03. Latency trong script chỉ tổng hợp request HTTP 200; error rate tính trên toàn bộ 300 request.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 223.0 | 290.3 | 312.2 |
| 0.03 (mặc định) | 246.2 | 298.7 | 1704.1 |
| 0.1 | 372.5 | 1706.2 | 1735.2 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

p99 nhạy rõ nhất khi tăng slow rate từ 0 lên 0.03: tăng từ 312.2 lên 1704.1 ms, trong khi average chỉ tăng từ 223.0 lên 246.2 ms và p95 gần như không đổi. Khi slow rate lên 0.1, p95 cũng tăng tới 1706.2 ms. Vì vậy average có thể che nhóm người dùng gặp request rất chậm; nên đặt SLO bằng percentile và theo dõi thêm p99. Các số có nhiễu ngẫu nhiên và sai số lấy mẫu nên không đòi hỏi mọi chỉ số phải tăng đều.

Cả ba lượt dùng concurrency 20, 300 request/lượt, khởi động lại v2 để thay slow rate, giữ các cấu hình khác. Nguồn: [slow 0](reports/load_v2_slow_0.json), [slow 0.03](reports/load_v2_slow_0.03.json), [slow 0.1](reports/load_v2_slow_0.1.json). Lượt slow 0.1 FAIL SLO p95; hai lượt còn lại PASS.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100% (23/23) |
| Avg tokens / câu | 56.7 | 108.8 | 113.7 |
| Tổng cost (USD) | 0.000399 | 0.000757 | 0.000790 |
| Cost / câu đúng (USD) | 0.00039915 | 0.00003607 | 0.00003436 |
| Quality gate | FAIL (ngưỡng 80%) | PASS (ngưỡng 80%, baseline v1) | PASS (ngưỡng 100%, baseline v2) |

Nguồn: [eval v1](reports/eval_v1.json), [eval v2](reports/eval_v2.json), [eval v2 fixed](reports/eval_v2_fixed.json). Cả ba không có lỗi HTTP/connection; final không có regression. Giữ nguyên golden_dataset.jsonl và run_eval.py. Cost/câu đúng được chép từ trường `cost_per_correct_usd` của tool; tổng cost được tool làm tròn đến 6 chữ số thập phân.

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | token, hết hạn, chữ ký | Thêm tài liệu JWT và từ khóa kích hoạt jwt vào KNOWLEDGE_BASE, giải thích token có chữ ký/thời hạn và khác API key cố định |
| scaling-03 | cpu, memory, custom metrics | Thêm tài liệu Kubernetes HPA với các từ khóa hpa/kubernetes/autoscal, giải thích scale pod theo CPU, memory hoặc custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Retrieval giúp v2 đạt nhiều câu đúng hơn nhưng tăng token trung bình và tổng chi phí. Cost/câu đúng của v2 thấp hơn v1 nhiều vì v1 rẻ mỗi lần gọi nhưng chỉ đúng 1/23. Sau bổ sung KB, tổng chi phí tăng nhẹ còn cost/câu đúng giảm vì trả lời đúng cả hai câu thiếu. Phép chấm dựa trên keyword, ngưỡng mỗi câu 0.6; 23 câu chưa đủ để khẳng định chất lượng tổng quát.

p95 eval quan sát được: v1 187.9 ms, v2 225.1 ms, v2 fixed 208.3 ms. Chỉ ghi nhận như output eval; không kết luận sửa KB làm nhanh hơn từ mẫu nhỏ và mock có jitter. Đánh giá latency phải dựa vào load test ở mục 2.

Job yêu cầu Exercise 7.3 nằm tại [.github/workflows/eval.yml](.github/workflows/eval.yml). Job chạy trên pull_request, bật v2 với MOCK_ERROR_RATE=0, gọi run_eval.py với `--min-accuracy 0.85` và baseline eval_v2_fixed.json. Tool trả exit code 1 nếu dưới ngưỡng hoặc có câu baseline đúng nay sai; shell fail job. Muốn chặn merge thật phải đặt job eval là required status check trong branch protection/ruleset; chưa cấu hình quyền GitHub trong phiên này. Đã chạy lệnh gate tương đương local: [eval_ci.txt](reports/cp7/eval_ci.txt), kết quả 23/23, exit code 0. Chưa chạy workflow trên GitHub.

---

## 4. Observability stack (production)

Đã có Grafana, trace chậm/lỗi, unit test alert SUCCESS, bằng chứng API và ảnh hai alert cùng firing; đã đo lại scaling đúng 1/3 instances. Câu trả lời Exercise 7.4 nằm trong MISSION_ANSWERS.md: dashboard hai instances có p95 295.75 ms, avg xấp xỉ 230 ms; tải mỗi instance khoảng 9–9.5 req/s; input/output khoảng 1400/2150 tokens/s. Các số đọc từ đường biểu đồ là xấp xỉ; đây là workload UI 30 users, khác benchmark headless 100 users. Đã dọn stack local sau khi lưu bằng chứng: [cleanup.txt](reports/cp8/cleanup.txt), [after-cleanup.txt](reports/cp8/after-cleanup.txt) chỉ còn tiêu đề, không còn container của project. Còn kiểm tra cuối và nộp bài.

### 4.1 Screenshot

- [x] [Dashboard Grafana khi đang có tải](screenshots/grafana-dashboard.png) — ảnh có traffic 18.4 req/s, error rate 0.99%, p95 296.56 ms, in-flight 6 và 1 instance; đây là số tại thời điểm chụp, không phải CSV benchmark scaling.
- [x] [Một trace chậm trong Jaeger](screenshots/jaeger-slow-trace.png) — span LLM chiếm khoảng 97.03% tổng thời gian, có trace JSON và log khớp ID.
- [x] [Một trace lỗi trong Jaeger](screenshots/jaeger-error-trace.png) — HTTP 503, span LLM có error=true và event exception; log khớp trace ID.
- [x] [Trang Alerts của Prometheus với hai alert cùng firing](screenshots/prometheus-alert-firing.png) — AgentHighErrorRate khoảng 22.14% và AgentHighLatencyP95 khoảng 1.888 giây tại thời điểm chụp (theo CHECKPOINTS K5).

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2`, giữ slow rate 0.03 | AgentHighErrorRate | 88.0 giây tới lần đầu quan sát firing | Error rate /ask |
| B | `MOCK_SLOW_RATE=0.3`, giữ error rate 0.2 từ A | AgentHighLatencyP95; AgentHighErrorRate tiếp tục firing | 141.5 giây tới lần đầu quan sát latency firing và cả hai cùng firing | Latency p95/p99; Error rate /ask xác nhận lỗi vẫn cao |
| C | `LLM_MODEL=mock-llm-large` | Không thực hiện | Không đo | Không ghi kết quả |
| D | `docker pause` 1 instance | Không thực hiện | Không đo | Không ghi kết quả |
| E | `AGENT_VERSION=v1` | Không thực hiện | Không đo | Trả lời câu hỏi lý thuyết bên dưới |

Unit test theo Exercise 7.6: [alert-rules-test.txt](reports/cp8/alert-rules-test.txt) có SUCCESS. Bằng chứng thí nghiệm: [A](reports/cp8/alert-A-observation.json), [B](reports/cp8/alert-B-observation.json), kèm các file alert-A-start.txt/alert-B-start.txt. Thời gian là lần đầu script quan sát firing trừ thời điểm bắt đầu áp dụng cấu hình; polling 5 giây, có sai số lấy mẫu và độ trễ API, không nhận là thời điểm chuyển trạng thái chính xác tuyệt đối.

A bắt đầu 14:24:08 UTC và được quan sát firing lúc 14:25:36.029767 UTC; error rate ở mẫu đó khoảng 20.92%. B bắt đầu 14:31:19 UTC; lúc 14:33:40.456136 UTC đã có đồng thời AgentHighErrorRate và AgentHighLatencyP95 firing, p95 ở mẫu latency khoảng 1.895 giây. Script B thấy error alert sau 11.1 giây vì alert này đã firing từ A; không diễn giải đó là thời gian kích hoạt mới. B là thí nghiệm cộng dồn, giữ lỗi cao để chụp hai alert cùng firing; không sửa rule/for để rút ngắn thời gian chờ.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đây là câu trả lời lý thuyết, không phải kết quả chạy E: metric hạ tầng có thể vẫn tốt khi nội dung trả lời sai. Cần eval định kỳ/trước release trên golden dataset với baseline và regression gate, đồng thời đánh giá mẫu câu trả lời thực tế hoặc phản hồi người dùng. Trong CP7 đã có ví dụ trực tiếp: v1 chỉ đúng 1/23 dù process vẫn phục vụ API; không thể suy chất lượng từ HTTP 200, latency hoặc cost riêng lẻ.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `9321d64ebc70e6873d6a626874f82bc4`
- Tổng thời gian: 1742.496 ms, lấy từ duration của root span `POST /ask` trong [trace JSON](reports/cp8/jaeger-slow-trace.json), đơn vị gốc microsecond.
- Span xử lý con chiếm nhiều thời gian nhất: `chat mock-llm-small` (1690.822 ms, 97.03% thời gian root span). Không tính các span cha bao ngoài như `agent.run` là một bước xử lý độc lập. Retrieval mất 21.485 ms; độ trễ chủ yếu nằm ở bước LLM trong trace này.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts":"2026-11-25T14:00:55.709309+00:00","level":"INFO","service":"observable-agent","instance":"f58eefdebd89","event":"llm_call","trace_id":"9321d64ebc70e6873d6a626874f82bc4","span_id":"6e43ad39262526e1","request_id":"98785cb15416","model":"mock-llm-small","agent_version":"v2","input_tokens":73,"output_tokens":35,"cost_usd":3.2e-05,"llm_ms":1689.6}
{"ts":"2026-11-25T14:00:55.735483+00:00","level":"INFO","service":"observable-agent","instance":"f58eefdebd89","event":"http_request","trace_id":"9321d64ebc70e6873d6a626874f82bc4","span_id":"6e43ad39262526e1","request_id":"98785cb15416","method":"POST","route":"/ask","status":200,"ms":1741.2}
```

Nguồn log đầy đủ: [jaeger-slow-trace.log](reports/cp8/jaeger-slow-trace.log). Log ms và span duration đo ở các ranh giới khác nhau nên không hoàn toàn trùng số; phần phân tích dùng duration trong trace JSON, không dùng số 1.7s đã làm tròn trên UI.

Trace lỗi đã đối chiếu thêm: `8a09b4fe56d47e2cc51825d05924cf50`, root `POST /ask` duration 848.318 ms, HTTP 503. Span `chat mock-llm-small` duration 825.073 ms, có error=true, error.type=upstream_unavailable và event exception loại `utils.mock_llm.LLMError`, thông báo `Upstream LLM error: 503 Service Unavailable (mock)`.

Nguồn: [trace lỗi JSON](reports/cp8/jaeger-error-trace.json), [log khớp ID](reports/cp8/jaeger-error-trace.log). Trích dòng JSON trong log, bỏ tiền tố Docker Compose:

```json
{"ts":"2026-11-25T14:09:18.516815+00:00","level":"INFO","service":"observable-agent","instance":"f58eefdebd89","event":"llm_error","trace_id":"8a09b4fe56d47e2cc51825d05924cf50","span_id":"b1e721e72996783d","request_id":"b338ec3b0cf0","error":"Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts":"2026-11-25T14:09:18.517657+00:00","level":"INFO","service":"observable-agent","instance":"f58eefdebd89","event":"http_request","trace_id":"8a09b4fe56d47e2cc51825d05924cf50","span_id":"b1e721e72996783d","request_id":"b338ec3b0cf0","method":"POST","route":"/ask","status":503,"ms":847.0}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Đã chạy lại đủ hai lượt hợp lệ với `run --rm --no-deps locust`, 100 users, ramp-up 10 users/giây, thời lượng 2 phút. Cấu hình v2, mock-llm-small, error rate 0.01, slow rate 0.03. Hai lượt đầu thiếu --no-deps bị Compose đưa về mặc định 2 replicas, đã lưu riêng tại [invalid-scaling-default-replicas](reports/cp8/invalid-scaling-default-replicas) và không dùng cho bảng so sánh. Bảng dưới dùng dòng Aggregated của CSV, gồm /ask và /health.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 63.23 | 210 | 790 | 1700 | 67/7531 (0.89%) |
| 3 | 65.85 | 200 | 260 | 1700 | 57/7837 (0.73%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Lượt 1: [trạng thái agent](reports/cp8/scale-1-agent-status.txt) xác nhận chỉ agent-1 healthy. Lượt 3: [trước](reports/cp8/scale-3-agent-status-before.txt) và [sau](reports/cp8/scale-3-agent-status-after.txt) đều có 3 agent healthy; log Locust không tạo/xóa agent. CSV gốc được sao chép vào [scale_1_stats.csv](benchmark-results/scale_1_stats.csv) và [scale_3_stats.csv](benchmark-results/scale_3_stats.csv). CSV và log cuối có snapshot khác thời điểm (tổng request lần 1: 7531/7573; lần 3: 7837/7880); dùng CSV nhất quán để so sánh.

Riêng /ask, 1 → 3 instances: RPS 57.62 → 59.94 (tăng khoảng 4.0%), trung bình 305.10 → 241.25 ms, p95 840 → 270 ms (giảm khoảng 67.9%), p99 giữ 1700 ms. Dòng Aggregated có p95 790 → 260 ms, RPS tăng khoảng 4.1%. Lỗi /ask là 67/6862 (0.98%) và 57/7133 (0.80%); error report là HTTP 503 từ mock upstream. Không quy mức giảm lỗi này cho scaling vì mock có lỗi ngẫu nhiên.

Scale cải thiện p95 trong lần đo này nhưng throughput không tăng ba lần. Locust giữ cố định 100 users và mỗi user nghỉ 0.5–2 giây giữa các lượt; đây không phải phép đo công suất tối đa. p99 gần 1.7 giây phù hợp slow-path của mock LLM vẫn tồn tại khi tăng instance; trace chậm đã cho thấy LLM chiếm khoảng 97% thời gian. Chưa đo CPU/throttling nên chưa khẳng định nút thắt CPU. Bằng chứng log: [lượt 1](reports/cp8/scale-1.txt), [lượt 3](reports/cp8/scale-3.txt).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Average không phản ánh đầy đủ tail latency: slow rate 0.03 làm p99 tăng mạnh dù average thay đổi ít.
  2. Concurrency cao hơn không luôn tạo throughput cao hơn: c100 chậm hơn và RPS thấp hơn c50 trong lần đo này.
  3. Eval cần xét chất lượng cùng cost/câu đúng và regression; final v2 đạt 23/23 với cost/câu đúng thấp hơn v1.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

Sẽ theo dõi thêm độ mới của dữ liệu retrieval và kiểm tra chất lượng định kỳ trên dataset mở rộng; metric hit ratio hiện có chỉ mô tả truy xuất, không bảo đảm câu trả lời đúng. Giữ label ít giá trị, không đưa question/user_id thành label. Dashboard/trace phát hiện tail latency và lỗi upstream; hai alert error/latency đã firing, nhưng chất lượng ngữ nghĩa cần eval riêng. Scale 1 → 3 giảm p95 /ask 840 → 270 ms trong lần đo này, p99 vẫn 1700 ms; không suy ra mức tăng công suất tối đa từ workload cố định 100 users.
