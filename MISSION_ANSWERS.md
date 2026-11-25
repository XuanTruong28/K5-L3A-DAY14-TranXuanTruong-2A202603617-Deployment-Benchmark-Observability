# Day 14 — Mission Answers

## Tiến độ và quy tắc áp dụng

- Đọc theo thứ tự: README → RULES → CHECKPOINTS → SUBMISSION → RUBRIC.
- Ưu tiên các lưu ý K5 trong README khi khác CODE_LAB hoặc checklist.
- Thứ tự thực hành: CP0 → CP1 (Part 1) → CP2 (Part 2) → CP3 (Part 4) → CP4 (Part 5) → CP5 (Part 6) → CP6 (Part 3) → CP7 → CP8.
- Kết quả thực hành lấy từ output và file bằng chứng thật trên máy này. Việc sử dụng AI được khai báo tập trung tại mục AI log cuối file.

## CP0 — Môi trường

- Ubuntu/WSL2, user `twentysix`; Python 3.14.4, `os.name = posix`.
- Docker Compose v5.7.0; Docker server 29.9.3.
- Người học đã chạy `docker run --rm hello-world` thành công trong Ubuntu.
- Đã cài `python3-venv`, `python3-pip` trong Ubuntu.
- Cài thư viện vào `.venv` trên ổ D qua WSL gặp `Operation not permitted` khi ghi native extension. Môi trường dùng thực tế là `/home/twentysix/.venvs/k5-day14`; `.venv` trong repo là lần tạo chưa hoàn chỉnh, không dùng.
- Chưa xác minh repo GitHub là bản fork Public hoặc việc nộp LMS.

## Part 1 — Localhost vs Production (CP1)

### Exercise 1.1 — Anti-patterns

Các vị trí dưới đây thuộc `01-localhost-vs-production/develop/app.py`:

| Vị trí | Vấn đề | Hậu quả |
| --- | --- | --- |
| Dòng 17–18 | Key mẫu và URL database có credential được hardcode | Nếu thay bằng credential thật rồi commit, người đọc repo có thể sử dụng chúng; phải lấy secret từ môi trường |
| Dòng 21–22 | DEBUG và MAX_TOKENS cố định trong code | Thay cấu hình đòi sửa source; khó quản lý khác biệt giữa môi trường |
| Dòng 33–38 | Dùng `print` cho log, không có cấu trúc rõ ràng | Khó lọc theo mức độ, truy vấn hoặc tổng hợp log |
| Dòng 34 | In key vào log | Người có quyền xem log có thể đọc secret; log cũng có thể bị gửi sang hệ thống khác |
| Dòng 42–43 và danh sách endpoint | Không có `/health` hoặc `/ready` | Nền tảng không có endpoint để phân biệt app sống và app sẵn sàng phục vụ |
| Dòng 51 | Bind `localhost` | Khi chạy trong container, dịch vụ không nhận kết nối qua network interface bên ngoài container |
| Dòng 52 | Port cố định 8000 | Không sử dụng port được nền tảng inject qua biến môi trường |
| Dòng 53 | Luôn `reload=True` | Theo dõi source và khởi động lại tiến trình không cần thiết khi production |
| Không có lifespan riêng | Không có cleanup tài nguyên do app quản lý | Nếu sau này mở connection hoặc buffer, app cần chủ động đóng/flush chúng khi shutdown |

Uvicorn vẫn có cơ chế shutdown mặc định. Vì vậy không kết luận rằng bản develop luôn bị ngắt đột ngột: log thực tế có `Application shutdown complete.`; điểm thiếu là lifecycle cleanup riêng của app.

### Exercise 1.2 — Chạy develop và kiểm tra

Lệnh có thể tái hiện từ gốc repo, trong Ubuntu:

```bash
source /home/twentysix/.venvs/k5-day14/bin/activate
cd 01-localhost-vs-production/develop
python app.py
```

Trong một terminal Ubuntu khác:

```bash
curl -i -X POST 'http://localhost:8000/ask?question=Hello'
```

Output thực tế, trích từ [reports/cp1/results.json](reports/cp1/results.json):

```text
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Theo lưu ý K5, bản develop lấy `question` từ query. Kiểm tra gửi JSON vào `POST /ask` trả 422 với `loc: ["query", "question"]`. `GET /health` trả 404 vì không khai báo endpoint.

### Exercise 1.3 — So sánh với production

| Feature | Develop | Production | Vì sao quan trọng? |
| --- | --- | --- | --- |
| Config | Giá trị trực tiếp trong app.py | `config.py` đọc environment bằng `os.getenv`, validate khi khởi tạo | Đổi cấu hình mà không sửa source; tránh lưu credential thật trong code |
| Host/port | localhost:8000 | HOST mặc định 0.0.0.0, PORT từ môi trường | Cho container và nền tảng cloud nhận request đúng cổng |
| Debug/reload | Luôn reload | Theo DEBUG, mặc định false | Giảm hoạt động theo dõi source và restart ngoài ý muốn |
| Health | Không có, đo được 404 | `/health` trả 200 kèm uptime | Giúp hệ thống giám sát kiểm tra liveness |
| Readiness | Không có | `/ready` trả 200 sau startup, có nhánh 503 khi chưa sẵn sàng | Load balancer chỉ gửi request khi app sẵn sàng |
| Logging | print và lộ key mẫu | Có thiết kế logger/JSON, log metadata thay cho key; hạn chế thực tế ghi dưới bảng | Log có cấu trúc giúp truy vấn, đồng thời cần tránh lộ credential |
| Shutdown | Không có cleanup riêng; Uvicorn vẫn shutdown mặc định | Lifespan đặt readiness false và có đoạn cleanup sau `yield` | Là nơi đóng connection, hoàn tất công việc và flush dữ liệu |
| Request | `question` qua query | `question` qua JSON; thiếu câu hỏi trả 422 | Client phải gọi đúng contract của từng bản |

Bằng chứng chạy production:

| Request | HTTP thực tế |
| --- | ---: |
| `POST /ask`, JSON `{"question":"Hello"}` | 200 |
| `POST /ask`, JSON `{}` | 422 |
| `GET /health` | 200 |
| `GET /ready` | 200 |

Chi tiết code đã sửa một anti-pattern: develop/app.py dòng 52 đặt `port=8000`; production/app.py dòng 197 dùng `port=settings.port`, với settings đọc `PORT` trong production/config.py.

Hạn chế logging quan sát được: khi không đặt OPENAI_API_KEY (đúng mục đích dùng mock), `config.py` gọi `logging.warning` trước `logging.basicConfig` trong app.py. Root logger đã có handler và mặc định WARNING nên các log INFO riêng của app không xuất hiện trong lần chạy. Có thiết kế JSON trong code nhưng không khẳng định đã thu được JSON log của app. Log Uvicorn xác nhận `Application shutdown complete.` sau SIGTERM.

Hai bản được chạy tuần tự trên cổng 8000; đã dừng develop trước production và dừng production sau kiểm tra. Code mẫu không bị sửa.

Bằng chứng và lệnh chạy lại:

- [Kết quả HTTP đầy đủ](reports/cp1/results.json).
- [Log develop, đã che key mẫu](reports/cp1/develop.log).
- [Log production](reports/cp1/production.log).
- Chạy từ gốc repo: `/home/twentysix/.venvs/k5-day14/bin/python scripts/run_cp1.py`.

## Part 2 — Docker (CP2)

Nguồn bằng chứng trong phần này: output người học tự chạy trong terminal Ubuntu/WSL và cung cấp trong cuộc hội thoại ngày 25/11/2026. Đã lưu thêm output đầy đủ của lần gọi `/ask` qua Nginx và bằng chứng dọn stack trong `reports/cp2/` (liên kết bên dưới).

### Exercise 2.1 — Đọc Dockerfile

1. Base image của develop là `python:3.11` (bản đầy đủ), khai báo bằng `FROM`. Image cung cấp hệ điều hành nền và Python runtime.
2. `WORKDIR /app` đặt thư mục làm việc bên trong container. Đây không phải đường dẫn `/app` trên máy Windows.
3. Copy `requirements.txt` và cài dependency trước khi copy source giúp tái sử dụng layer cache khi chỉ source thay đổi. Khi requirements hoặc layer phía trước thay đổi, layer cài dependency phải được build lại.
4. `CMD` cung cấp lệnh/đối số mặc định, có thể thay bằng đối số sau tên image trong `docker run`. `ENTRYPOINT` định nghĩa chương trình chính; với exec form, đối số khi chạy thường được truyền thêm cho chương trình đó. Có thể thay ENTRYPOINT bằng `--entrypoint`. Dockerfile develop dùng `CMD ["python", "app.py"]`.

### Exercise 2.2 — Build và chạy develop

Build từ gốc repo theo lưu ý K5:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --rm --name k5-day14-cp2-dev -p 8000:8000 my-agent:develop
curl -i http://localhost:8000/health
curl -i -X POST 'http://localhost:8000/ask?question=What%20is%20Docker'
docker images my-agent:develop
```

Container ID người học nhận được: `d198f4e0ef59…`; `docker ps` báo `Up`, map cổng 8000 của host đến 8000 của container.

Kết quả thực tế:

```text
GET /health: HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":62.1,"container":true}

POST /ask?question=What%20is%20Docker: HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

Bản develop nhận query, không gửi JSON như ví dụ cũ trong CODE_LAB.

### Exercise 2.3 — Multi-stage và dung lượng image

Đã dừng container develop trước khi chạy production (cùng cổng 8000). Các lệnh build/chạy production từ gốc repo:

```bash
docker stop k5-day14-cp2-dev
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker run -d --rm --name k5-day14-cp2-prod -p 8000:8000 my-agent:advanced
curl -i http://localhost:8000/health
curl -i -X POST http://localhost:8000/ask -H 'Content-Type: application/json' -d '{"question":"What is Docker?"}'
docker images --filter 'reference=my-agent:*'
```

Production trả HTTP 200 cho cả hai request. Health có `version: "2.0.0"`; câu trả lời về Docker giống nội dung develop phía trên.

| Image | Image ID | Disk usage | Content size |
| --- | --- | ---: | ---: |
| my-agent:develop | fc65c6f94e25 | 1.67 GB | 426 MB |
| my-agent:advanced | 26d587e99e98 | 240 MB | 57.4 MB |

Theo cùng cột **Disk usage**, dùng đơn vị thập phân 1.67 GB ≈ 1670 MB: giảm `(1670 - 240) / 1670 × 100 ≈ 85.6%`. Đây là phép tính gần đúng từ số Docker đã làm tròn. Content size được ghi riêng, không dùng lẫn với Disk usage trong phép so sánh.

- Stage `builder` dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` và Python dependencies vào `/root/.local`.
- Stage `runtime` bắt đầu từ `python:3.11-slim`, copy thư viện đã cài cùng source cần chạy và dùng user `appuser`.
- Image runtime không nhận bộ công cụ build từ builder. So với develop dùng base đầy đủ, việc chọn base slim cũng đóng góp vào giảm dung lượng; không quy toàn bộ chênh lệch cho riêng multi-stage.

### Exercise 2.4 — Stack Compose và Nginx

Theo hướng dẫn đã dùng `.env.local` trống (được gitignore) và project riêng `k5-day14-docker` để tránh trùng các thư mục `production` khác:

```bash
cd 02-docker/production
touch .env.local
docker compose -p k5-day14-docker up -d --build
docker compose -p k5-day14-docker ps -a
curl -i http://localhost/health
curl -i -X POST http://localhost/ask -H 'Content-Type: application/json' -d '{"question":"Explain microservices"}'
```

Kiến trúc theo cấu hình Compose/Nginx:

```text
Client → Nginx :80 → agent :8000
                       ├── Redis :6379   (REDIS_URL, dependency)
                       └── Qdrant :6333  (QDRANT_URL, dependency)
```

- Bốn service dùng network `internal`; Nginx resolve tên `agent` qua Docker DNS và proxy request đến `agent:8000`.
- Agent không publish cổng trực tiếp trong stack này. Redis và Qdrant có named volumes; Compose chờ hai dependency healthy trước khi khởi động agent.
- Các nhánh Redis/Qdrant trên sơ đồ biểu diễn cấu hình và dependency. Code mock `main.py` hiện tại chưa thực hiện truy vấn Redis hoặc Qdrant; biến môi trường không tự tạo ra kết nối ứng dụng.
- File Nginx chỉ cấu hình HTTP `listen 80`; việc Compose map 443 chưa đồng nghĩa HTTPS đã hoạt động.

Output người học cung cấp xác nhận:

```text
GET /health
HTTP/1.1 200 OK
Server: nginx
{"status":"ok","uptime_seconds":43.7,"version":"2.0.0","timestamp":"2026-11-25T08:39:59.267775"}

POST /ask
HTTP/1.1 200 OK
Server: nginx
```

Body `/ask` của lần gọi đầu bị cắt trong tin nhắn. Người học đã gọi lại và lưu output đầy đủ vào [reports/cp2/nginx-ask.txt](reports/cp2/nginx-ask.txt). Trích từ lần gọi bổ sung này:

```text
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:55:32 GMT
Content-Type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

Header `Server: nginx`, mã 200 và body đầy đủ xác nhận request proxy thành công. Mock có thể trả lời khác nhau giữa các lần gọi; output bổ sung được ghi riêng, không gán cho lần gọi đầu.

Bảng `docker compose -p k5-day14-docker ps -a` người học cung cấp sau đó:

| Container | Trạng thái ghi nhận | Cổng |
| --- | --- | --- |
| k5-day14-docker-agent-1 | Up 6 minutes (healthy) | 8000/tcp, không publish trực tiếp |
| k5-day14-docker-nginx-1 | Up 6 minutes | Host 80 → 80, 443 → 443 |
| k5-day14-docker-qdrant-1 | Up 6 minutes (healthy) | 6333–6334/tcp |
| k5-day14-docker-redis-1 | Up 6 minutes (healthy) | 6379/tcp |

Cả bốn service chạy; ba service có healthcheck đều healthy. Nginx không khai báo healthcheck trong Compose nên chỉ xác nhận trạng thái Up và hai request proxy HTTP 200, không gọi trạng thái của Nginx là healthy.

### Dọn stack và bằng chứng CP2

Sau khi lưu kết quả gọi Nginx, người học đã chạy trong `02-docker/production/`:

```bash
docker compose -p k5-day14-docker down -v
docker compose -p k5-day14-docker ps -a
```

Đã đọc và đối chiếu các file bằng chứng:

| File | Kết quả xác nhận |
| --- | --- |
| [nginx-ask.txt](reports/cp2/nginx-ask.txt) | HTTP 200, Server nginx, body JSON đầy đủ |
| [cleanup.txt](reports/cp2/cleanup.txt) | Bốn container, network `k5-day14-docker_internal` và hai volume `k5-day14-docker_redis_data`, `k5-day14-docker_qdrant_data` đều được Removed |
| [after-cleanup.txt](reports/cp2/after-cleanup.txt) | Chỉ còn dòng tiêu đề NAME/IMAGE/COMMAND/SERVICE/CREATED/STATUS/PORTS, không còn container của project |

Dữ liệu thử nghiệm trong hai volume CP2 đã bị xóa khi chạy `down -v`; image đã build được giữ lại. CP2 đã hoàn tất phần thực hành, ghi nhận kết quả và dọn stack.

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- URL: https://agent-production-a52803be.up.railway.app
- Platform: Railway, project `lab14`, environment `production`, service `agent` và Redis cloud.
- Deploy chính agent trong `06-lab-complete/`, không deploy app mẫu Part 3. Cấu hình `AGENT_API_KEY` trên nền tảng và `REDIS_URL` tham chiếu `${{Redis.REDIS_URL}}`.
- Bốn lệnh tự kiểm theo CP6 lần lượt trả `200 / 200 / 401 / 200`, đã lưu trong [reports/cp6/public-check.txt](reports/cp6/public-check.txt). Người học xác nhận mở `/health` và `/ready` nhận status ok và ready true.
- Thông tin deploy và lệnh kiểm tra: [DEPLOYMENT.md](DEPLOYMENT.md).
- Screenshot: [dashboard](screenshots/dashboard.png) cho thấy agent và Redis Online; [running](screenshots/running.png) cho thấy deployment Active/successful và domain; [test](screenshots/test.png) có URL cùng bốn mã 200/200/401/200. Đã kiểm tra ba file ảnh thực tế.

### Exercise 3.2: So sánh railway.toml và render.yaml

Theo RUBRIC K5, chọn Railway làm nền tảng chính và so sánh config với Render để hoàn thành phần nền tảng còn lại; chưa deploy Render.

| Nội dung | Railway | Render |
| --- | --- | --- |
| Định dạng | TOML với các bảng `[build]`, `[deploy]` | YAML với danh sách `services` |
| Build/chạy | `06-lab-complete/railway.toml` chọn builder DOCKERFILE, dùng CMD của Dockerfile | Mẫu `03-cloud-deployment/render/render.yaml` dùng runtime python, buildCommand/startCommand; bản khung Part 6 gợi ý runtime docker để dùng Dockerfile |
| Health check | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Secret | Đặt variables trên Railway, Redis dùng reference giữa service | Blueprint có envVars, `generateValue: true` hoặc `sync: false` để không ghi secret thật trong source |
| Redis | Trong lần thực hành tạo service Redis riêng rồi đặt reference REDIS_URL cho agent | Cần khai báo/tạo Redis và nối URL cho agent; không giả định chỉ tạo web service là đã có Redis |

Lý do khác biệt: mỗi nền tảng có schema cấu hình riêng. Cùng mục tiêu là mô tả cách build/chạy, health check và cấp biến môi trường; không chép nguyên TOML sang YAML. File `06-lab-complete/render.yaml` vẫn là bản khung tham khảo, không ghi nhận là cấu hình Render đã triển khai.

### Exercise 3.3: Cloud Run CI/CD pipeline

1. Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml`: bước test cài requirements và chạy pytest.
2. Bước build dùng Docker tạo image với tag commit SHA và latest; bước push đẩy các tag lên registry.
3. Bước deploy chờ push, dùng gcloud triển khai image lên Cloud Run, cấu hình region, tài nguyên, số instance, biến môi trường và secret.
4. `service.yaml` mô tả service Cloud Run: image, port 8000, scaling/concurrency, tài nguyên, secret cùng liveness `/health` và startup `/ready`. Chỉ đọc và mô tả pipeline theo K5; không tạo tài khoản hoặc deploy GCP.

## Part 4: API Security

### Exercise 4.1-4.3: Test results

Thực hiện CP3 theo CHECKPOINTS và lưu ý K5 số 6: chạy code mẫu develop với `AGENT_API_KEY` từ môi trường; dừng develop trước khi bật production vì dùng chung cổng 8000. Lấy JWT tại `POST /auth/token` bằng tài khoản mẫu `student` / `demo123`, dùng token đó cho vòng lặp rate limit. Không ghi giá trị JWT vào bài.

**Exercise 4.1 — API key authentication**

- Hàm `verify_api_key` trong `04-api-gateway/develop/app.py` đọc key qua `APIKeyHeader` và được gắn vào `/ask` bằng `Depends`.
- Thiếu key trả 401; sai key trả 403; key đúng cho phép xử lý request. Đây là hành vi code mẫu Part 4, không nhầm với hợp đồng Part 6 yêu cầu cả thiếu/sai key trả 401.
- Rotate key: đổi `AGENT_API_KEY` trong môi trường chạy app, khởi động lại app để nạp giá trị mới và cập nhật key ở các client hợp lệ.

Trích output `curl -i` thực tế, không gồm thanh tiến độ curl:

```text
Không có X-API-Key:
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 09:15:16 GMT
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

Có key mẫu đúng:
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:15:31 GMT
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

Key mẫu sai:
HTTP/1.1 403 Forbidden
date: Wed, 25 Nov 2026 09:16:02 GMT
content-type: application/json

{"detail":"Invalid API key."}
```

Output đầy đủ: [thiếu key](reports/cp3/api-key-missing.txt), [key đúng](reports/cp3/api-key-valid.txt), [key sai](reports/cp3/api-key-invalid.txt).

**Exercise 4.2 — JWT authentication**

Đã lấy token tại `/auth/token` theo README K5. `auth.py` xác thực tài khoản, tạo JWT ký bằng HS256, chứa `sub`, `role`, `iat`, `exp` và hết hạn sau 60 phút. Client gửi token trong `Authorization: Bearer ...`; dependency `verify_token` kiểm tra chữ ký/thời hạn rồi lấy username và role. Không phải tự viết lại JWT trong CP3.

Output gọi `/ask` bằng token hợp lệ, trích từ [jwt-valid.txt](reports/cp3/jwt-valid.txt):

```text
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:17:02 GMT
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

Lưu ý khi đọc output mẫu: trong `app.py`, trường `usage.budget_remaining_usd` đang được gán `usage.total_cost_usd`, nên con số trên là chi phí đã dùng theo code, không diễn giải là ngân sách còn lại.

**Exercise 4.3 — Rate limiting**

- `rate_limiter.py` lưu các timestamp request trong `deque`, loại timestamp ngoài cửa sổ 60 giây trước khi đếm: sliding window theo timestamp, không phải token bucket.
- User có giới hạn 10 request/60 giây. `app.py` chọn limiter admin theo role với giới hạn 100 request/60 giây; admin có hạn mức cao hơn, không bỏ kiểm tra giới hạn hoàn toàn.
- State nằm trong RAM trong code demo; nhiều instance sẽ có bộ đếm riêng nên khi triển khai stateless cần state chung trong Redis.
- Vòng lặp 20 request thực tế có 9 phản hồi 200 (request 1–9), 11 phản hồi 429 (request 10–20). Một request JWT trước vòng lặp đã dùng một lượt trong cùng cửa sổ.

Trích request 20 từ [rate-limit.txt](reports/cp3/rate-limit.txt):

```text
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 09:17:25 GMT
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795598305
retry-after: 37
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":37}}
```

Đã quan sát được 429 bằng vòng lặp curl do người học tự chạy, đúng yêu cầu tự kiểm tra CP3.

### Exercise 4.4: Cost guard implementation

Theo CP3 K5, đọc code mẫu và giải thích cách làm cost guard, không viết lại code mẫu. Người học xác nhận đã đọc xong `04-api-gateway/production/cost_guard.py`.

Code demo hiện tại:

- `check_budget(user_id)` kiểm tra trước khi gọi mock LLM. Nếu tổng chi phí toàn hệ thống đã chạm 10 USD/ngày thì trả 503; nếu user đã chạm 1 USD/ngày thì trả 402. Khi user dùng từ 80% ngân sách, code ghi cảnh báo.
- `record_usage` cộng input/output token và chi phí theo hằng số giá mẫu sau khi nhận response. Đây là chi phí mô phỏng, không phải hóa đơn LLM thật.
- `get_usage` trả request count, token, chi phí và ngân sách còn lại. Usage lưu trong RAM; `_get_record` tạo lại record user khi ngày thay đổi. State mất khi restart và không được chia sẻ giữa các instance.

Phương án Redis với ngân sách 10 USD/tháng/user được mô tả trong Exercise 4.4 của CODE_LAB:

1. Tạo key `budget:{user_id}:{YYYY-MM}` cho user và tháng hiện tại.
2. Đọc chi phí đã dùng từ Redis, mặc định 0 nếu chưa có key.
3. So sánh `current + estimated_cost` với 10 USD: vượt thì từ chối, còn ngân sách thì cho phép.
4. Cập nhật bằng `INCRBYFLOAT` và đặt TTL 32 ngày theo ví dụ hướng dẫn. Sang tháng dùng key mới nên ngân sách tháng mới bắt đầu từ 0.

Đây là giải thích phương án theo đề; không khẳng định code demo đã dùng Redis hoặc đã kiểm thử HTTP 402/503. Bằng chứng HTTP của CP3 ở trên là 401/200/403/429.

Rate limit bảo vệ tần suất gọi, còn cost guard bảo vệ ngân sách. Hai request có thể dùng lượng token khác nhau: dù chưa vượt số request/phút, người dùng vẫn có thể vượt ngân sách. Vì vậy cần cả hai lớp kiểm tra.

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

Thực hiện CP4 theo CHECKPOINTS và README K5: chạy code mẫu trong `05-scaling-reliability/`, đọc hiểu và ghi kết quả, không viết lại code mẫu.

**Exercise 5.1 — Health checks**

- `/health` là liveness: kiểm tra process còn hoạt động để nền tảng quyết định có cần restart hay không.
- `/ready` là readiness: kiểm tra app đã sẵn sàng nhận traffic để load balancer quyết định có route request hay không. Bản develop dùng cờ `_is_ready`, đặt true sau startup và false khi shutdown; không kiểm tra Redis thật trong endpoint này.
- Request `/ready` cũng đi qua middleware đếm request, nên `in_flight_requests: 1` trong output có thể chính là request kiểm tra readiness.

Output thực tế của develop, trích từ [health.txt](reports/cp4/health.txt) và [ready.txt](reports/cp4/ready.txt):

```text
GET /health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":13.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:26:45.975746+00:00","checks":{"memory":{"status":"ok","used_percent":11.8}}}

GET /ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

**Exercise 5.2 — Graceful shutdown**

Server develop được chạy bằng `python -u app.py`; PID trong lần kiểm tra là 3442. Người học gửi `POST /ask?question=Long%20task` ở background rồi gửi `kill -TERM 3442`. Dùng query theo signature `ask_agent(question: str)` của code thực tế.

Request hoàn thành HTTP 200, lưu trong [shutdown-request.txt](reports/cp4/shutdown-request.txt):

```text
HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Trích thứ tự sự kiện trong [develop-server.txt](reports/cp4/develop-server.txt):

```text
INFO:     Shutting down
INFO:     127.0.0.1:54860 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-25 16:33:36,870 INFO 🔄 Graceful shutdown initiated...
2026-11-25 16:33:36,870 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [3442]
```

Uvicorn xử lý SIGTERM, ngừng phục vụ mới và chờ công việc đang xử lý trước khi hoàn tất lifecycle shutdown. Code cấu hình `timeout_graceful_shutdown=30`; lifespan đặt `_is_ready=False` và có vòng chờ request. Lần chạy xác nhận request mock đang xử lý hoàn thành trước khi app kết thúc; không coi tên câu hỏi "Long task" là bằng chứng tác vụ kéo dài 30 giây.

**Exercise 5.3 — Stateless design**

Nếu lưu conversation history trong dict RAM, mỗi instance có bản dữ liệu riêng: request sau đến instance khác sẽ không thấy history trước đó, restart cũng làm mất dữ liệu của instance.

Code production dùng `save_session`/`load_session` đọc ghi key `session:{session_id}` trên Redis; `append_to_history` thêm message và lưu lại. Redis là state chung, agent không phụ thuộc history nằm trong RAM riêng. Session có TTL mặc định 3600 giây và history giữ tối đa 20 message. Code có fallback RAM khi không kết nối được Redis; lần thực hành này xác nhận cả ba agent dùng Redis qua [scaling-agent-logs.txt](reports/cp4/scaling-agent-logs.txt), không dựa vào fallback.

**Exercise 5.4 — Load balancing**

Chạy trong `05-scaling-reliability/production/`, tạo `.env.local` trống trước khi bật stack, đúng README K5:

```bash
touch .env.local
docker compose -p k5-day14-scaling up -d --build --scale agent=3
docker compose -p k5-day14-scaling ps -a
```

[scaling-status.txt](reports/cp4/scaling-status.txt) xác nhận ba agent và Redis healthy, Nginx Up; host port 8080 được map đến Nginx port 80. Nginx chuyển request đến các agent trên network nội bộ; agent dùng Redis chung để lưu session.

Gọi health qua Nginx ở `http://localhost:8080/health`, trích từ [scaling-health.txt](reports/cp4/scaling-health.txt):

```text
HTTP/1.1 200 OK
X-Served-By: 172.19.0.5:8000
{"status":"ok","instance_id":"instance-42585e","uptime_seconds":34.6,"storage":"redis","redis_connected":true}
```

**Exercise 5.5 — Test stateless**

```bash
python test_stateless.py
```

Theo README K5 và script thực tế, script gửi 5 câu hỏi trong cùng session qua `POST /chat` cổng 8080 rồi đọc history; không tự kill instance. Không dùng cổng 80 hoặc endpoint `/ask` của ví dụ cũ.

Kết quả trong [stateless-test.txt](reports/cp4/stateless-test.txt):

| Request | Instance xử lý |
| --- | --- |
| 1 | instance-5d1532 |
| 2 | instance-871566 |
| 3 | instance-42585e |
| 4 | instance-5d1532 |
| 5 | instance-871566 |

```text
Total requests: 5
Instances used: {'instance-5d1532', 'instance-871566', 'instance-42585e'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Session `b65d0cd8-9507-4b0f-ae5d-f1f26e5153b6` giữ đủ 5 user message và 5 assistant message dù request được xử lý qua ba instance. Kết quả chứng minh history được chia sẻ qua Redis trong kịch bản tuần tự của script, không phải kết quả thí nghiệm kill instance.

Sau khi lưu log và kết quả, đã dọn đúng project:

```bash
docker compose -p k5-day14-scaling down
docker compose -p k5-day14-scaling ps -a
```

[cleanup.txt](reports/cp4/cleanup.txt) xác nhận xóa ba container agent, Nginx, Redis và network của stack; [after-cleanup.txt](reports/cp4/after-cleanup.txt) chỉ còn tiêu đề bảng, không còn container. Redis của stack này không có volume persistent trong Compose nên session thử nghiệm không được giữ sau khi xóa container Redis.

## Part 6: Final Project

Hoàn thiện bản khung trực tiếp trong `06-lab-complete/` theo thứ tự gợi ý của README. Các phần đã làm: health, config từ môi trường, log JSON, API key, Redis/readiness, rate limit, cost guard, lifecycle shutdown, Dockerfile multi-stage, `.dockerignore`, Compose agent + Redis và `railway.toml`.

Thực hiện kiểm tra trong Ubuntu/WSL bằng môi trường Python 3.11 tại `/home/twentysix/.venvs/k5-day14-part6`, cùng phiên bản major/minor với Dockerfile. Dùng môi trường riêng vì requirements của Part 6 ghim Pydantic 2.9.0; giữ nguyên `requirements.txt`. Không sửa `check_production_ready.py`.

Lệnh kiểm tra đầy đủ, chạy trong `06-lab-complete/` khi Docker Desktop hoạt động:

```bash
source /home/twentysix/.venvs/k5-day14-part6/bin/activate
python -m pip install -r requirements.txt
set -o pipefail
python check_production_ready.py \
  2>&1 | tee ../reports/cp5/full-check.txt
```

### Checklist Deliverable

Trích nguyên phần checklist từ [full-check.txt](reports/cp5/full-check.txt), lần chạy đầy đủ có runtime và Docker:

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 41/41 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Kết quả chi tiết trong cùng file:

- Build Docker image thành công trong 24 giây, dung lượng script đo được 273 MB, nhỏ hơn 500 MB.
- Chạy agent với hai worker; `/health` và `/ready` trả 200. Khi Redis mất kết nối, `/ready` trả 503 còn `/health` vẫn 200.
- Thiếu/sai API key trả 401, key đúng trả 200.
- Script đặt `RATE_LIMIT_PER_MINUTE=5`: nhận 429 sau 5 request thành công; restart agent vẫn nhận 429, xác nhận state Redis còn tồn tại.
- Với ngân sách gần 0 do script đặt để kiểm tra, nhận HTTP 402 ở request đầu tiên.
- Bảy dòng log app được kiểm tra đều là JSON hợp lệ.
- Gửi SIGTERM trong lúc có request: request vẫn 200, process thoát code 0. Docker stop thoát code 0 trong 0.8 giây, dưới 10 giây.
- File Railway có builder DOCKERFILE và healthcheckPath `/health`; Docker CMD đọc PORT từ môi trường.

Mục “Public URL ready” của CP5 xác nhận cấu hình sẵn sàng deploy; URL cloud hoạt động thật, Redis cloud, `DEPLOYMENT.md` và ảnh deploy được thực hiện ở CP6.

## Part 7: Benchmark & Observability

### Exercise 7.1: Đọc metrics của agent

Đã bổ sung Histogram `agent_question_length_chars` trong `benchmark-observability/develop/app.py` theo mẫu CODE_LAB; gọi `.observe(len(body.question))` trong endpoint `/ask` trước retrieval/LLM. Không dùng độ dài câu hỏi làm label.

Output thực tế lưu ở [metrics.prom](reports/cp7/metrics.prom), request mẫu ở [example-response.json](reports/cp7/example-response.json):

| Loại | Ví dụ quan sát được | Ý nghĩa |
| --- | --- | --- |
| Counter | `http_requests_total{method="POST",route="/ask",status="200"} 1.0` | Số request ask thành công chỉ tăng trong vòng đời process |
| Gauge | `agent_info{model="mock-llm-small",version="v2"} 1.0` | Giá trị mô tả agent; Gauge cho phép đặt/tăng/giảm, khác Counter |
| Histogram | `agent_question_length_chars_count 1.0`, `_sum 40.0`, bucket `le="50.0"` bằng 1 | Một câu hỏi 40 ký tự, thuộc bucket độ dài tối đa 50 ký tự |

Middleware dùng route template và `unmatched` để số label hữu hạn. Nếu dùng URL thật thì bot gọi hàng nghìn đường dẫn lạ sẽ tạo hàng nghìn tổ hợp time series, tăng RAM và chi phí lưu/truy vấn Prometheus. Đã gọi hai URL không tồn tại; output gộp thành `route="unmatched",status="404"` với counter 2, không sinh label riêng cho từng URL.

### Exercise 7.2: Load test & SLO

Đã chạy 4 mức concurrency 1/10/50/100, mỗi mức 300 request; so sánh thêm slow rate 0/0.03/0.1, mỗi mức 300 request ở concurrency 20. Đổi slow rate bằng cách dừng/bật lại v2; không sửa load_test.py hoặc nới SLO. Bảng và giải thích nằm ở mục 1–2 của [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md). Hai lượt FAIL SLO là c100 và slow 0.1; giữ exit code 1 và report thật.

### Exercise 7.3: Eval & quality gate

Eval v1 đạt 1/23, v2 ban đầu đạt 21/23. Đọc missing_keywords, chỉ bổ sung hai tài liệu JWT/Kubernetes HPA trong KNOWLEDGE_BASE; không sửa golden_dataset.jsonl, run_eval.py hoặc đáp án. Đã khởi động lại v2, chạy `--min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json`, đạt 23/23, không regression và exit code 0.

Đã đồng bộ hai tài liệu sang `benchmark-observability/production/utils/mock_llm.py` theo README K5. Sau đó đã chạy và đo stack production trong CP8: Grafana, trace, alert và scaling có bằng chứng ở `reports/cp8/`, `screenshots/` và mục 4–5 của BENCHMARK_REPORT.md. Job CI ở [.github/workflows/eval.yml](.github/workflows/eval.yml), ngưỡng 85% kèm regression check; lệnh tương đương chạy local PASS. Workflow GitHub và required status check chưa được xác minh trong lần kiểm tra này.

Mười JSON bắt buộc đã lưu trong `develop/reports/` và copy nguyên vẹn ra `reports/` ở gốc repo theo SUBMISSION. Log lệnh, cấu hình và hash dataset trước/sau nằm trong `reports/cp7/`. Các agent local phục vụ phép đo đã được dừng, service Railway vẫn được giữ nguyên.

Đã kiểm chứng lại artifact/wiring theo quy trình gsd-verifier, kết quả PASSED trong [verification.txt](reports/cp7/verification.txt). Lệnh kiểm chứng có thể chạy lại từ gốc repo bằng `/home/twentysix/.venvs/k5-day14-part6/bin/python scripts/verify_cp7.py` trong WSL.

### Exercise 7.4: Observability stack

Các câu 1–3 dùng lần đo bổ sung mới lúc **22:48:20.490177 ngày 25/11/2026 (GMT+7)**, không nhận là số tại thời điểm ảnh trước. Chạy 2 agent healthy, Locust 30 users/ramp-up 5 users/giây trong 2 phút, đọc API Prometheus ở giây thứ 100 bằng đúng PromQL trong dashboard, cửa sổ rate 1 phút, cùng timestamp. Bằng chứng gốc: [prometheus.json](reports/cp8/dashboard-exact/prometheus.json), [log Locust](reports/cp8/dashboard-exact/locust.txt), trạng thái agent [trước](reports/cp8/dashboard-exact/agent-status-before.jsonl) và [sau](reports/cp8/dashboard-exact/agent-status-after.jsonl). Đây là workload 30 users, không trộn với CSV scaling 100 users. Các số dưới được làm tròn từ giá trị API, không ước lượng từ ảnh.

1. Avg `/ask` = **227.395903 ms**, p95 = **292.563739 ms**, p99 = **1799.038462 ms**. Avg là tỷ số rate của histogram sum/count; p95/p99 là kết quả histogram_quantile của dashboard (ước tính phân vị từ bucket). p95 cao hơn avg khoảng 65.168 ms; p99 cao cho thấy nhóm nhỏ request chậm bị che khuất nếu chỉ xem trung bình.
2. Requests/s theo instance: `172.19.0.6:8000` = **9.436364 req/s**, `172.19.0.4:8000` = **9.563636 req/s**, tổng **19 req/s**. Chênh lệch khoảng 0.127273 req/s cho thấy Nginx chia tải khá đều trong cửa sổ đo; không khẳng định mọi thời điểm luôn bằng nhau.
3. Input = **1458.345455 tokens/s**, output = **761.254545 tokens/s**. Input lớn hơn output vì mock tính input từ system prompt + context truy xuất + question, còn output chỉ tính câu trả lời. Panel Tokens/s cấu hình `stacking.mode=normal`: đường vàng phía trên là input + output cộng dồn; không được đọc giá trị trục của đường vàng thành riêng output. Diễn giải trước đó rằng output lớn hơn input là đọc sai biểu đồ và đã được thay bằng số API.
4. `curl -i http://localhost:8080/metrics` trả HTTP 404 từ Nginx, đã lưu [public-metrics.txt](reports/cp8/public-metrics.txt). Đây là cấu hình chủ động: `location = /metrics { return 404; }` trong nginx/nginx.conf chặn metric qua cổng public. Prometheus vẫn scrape trực tiếp `/metrics` của từng agent ở cổng 8000 trong mạng Docker theo prometheus/prometheus.yml, không đi qua Nginx.

## Các checkpoint tiếp theo

CP2 đã hoàn tất thực hành và dọn stack. CP3 đã có output 401/200/403/429, JWT và giải thích cost guard. CP4 đã hoàn tất thực hành và dọn stack. CP5 đã đạt PASS 12/12, 41/41 checks. CP6 đã hoàn tất deploy và hồ sơ. CP7 đã hoàn tất metrics, 7 bộ load test, eval 23/23 không regression và job CI local. CP8 đã có ảnh Grafana, trace chậm và trace lỗi kèm JSON/log khớp ID, unit test alert SUCCESS, thí nghiệm A/B và ảnh hai alert cùng firing, benchmark scaling đúng 1/3 instances và câu trả lời Exercise 7.4. Đã dọn stack cuối, bằng chứng reports/cp8/cleanup.txt và after-cleanup.txt xác nhận không còn container của project. Còn kiểm tra cuối và nộp GitHub–LMS; chưa xác nhận đã nộp bài.

## AI log

Theo RULES.md, mỗi nội dung hỗ trợ được ghi đủ bốn phần: **Hỏi gì — Nhận gì — Tự sửa/thực hiện gì — Tự kiểm tra thế nào**. Các câu trả lời và tài liệu có sử dụng hỗ trợ giải thích, gợi ý code, đọc lỗi, đối chiếu kết quả và biên tập. Bằng chứng chạy bằng công cụ trợ lý được phân biệt với lần người học tự chạy.

### CP0 — Thiết lập môi trường

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Cần chuẩn bị môi trường nào cho Windows? | Hướng dẫn WSL2, Ubuntu, Docker Desktop và Python trong Linux theo K5 | Cài/mở Ubuntu và Docker Desktop | Python in `posix`, Docker Compose chạy được |
| Ubuntu tạo user báo NSS/E_UNEXPECTED, cập nhật WSL báo 403 | Giải thích lỗi và hướng dẫn tải bộ cài WSL chính thức thủ công | Cập nhật WSL, restart Windows, mở lại Ubuntu, tạo user/mật khẩu | WSL 3.0.5.0 mở Ubuntu thành công |
| Nhập mật khẩu không hiện ký tự, đang ở root | Giải thích nhập mật khẩu ẩn và code lệnh tạo user/sudo | Tạo/chuyển sang user twentysix | `whoami` trả twentysix |
| Docker không tìm thấy hoặc permission denied trong Ubuntu | Hướng dẫn WSL Integration, kiểm tra socket/group và nạp lại phiên đăng nhập | Bật tích hợp Ubuntu, thêm user vào nhóm docker, mở lại phiên WSL | `id` có nhóm docker, hello-world thành công |
| Chạy lệnh Linux trong PowerShell bị lỗi | Chỉ cách vào Ubuntu bằng wsl và phân biệt dấu nhắc terminal | Chuyển terminal sang Ubuntu, cd đúng repo | Đầu dòng Linux và đúng đường dẫn bài lab; pip/venv được bổ sung bằng công cụ trợ lý |

### CP1 — Localhost vs Production

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Bài lab yêu cầu gì và phải làm theo thứ tự nào? | Tóm tắt README/RULES/CHECKPOINTS/SUBMISSION/RUBRIC và các lưu ý K5 | Đọc lại và theo lộ trình checkpoint; không chuyển Part 6 ra ngoài thư mục quy định | Đối chiếu yêu cầu nộp và tiêu chí từng phần |
| Anti-pattern trong develop và điểm khác biệt của production là gì? | Giải thích code và hỗ trợ soạn bảng config, secret, logging, probe, shutdown | Đã tự kiểm tra CP1 theo xác nhận trong cuộc hội thoại; không sửa code mẫu | Đối chiếu code và kết quả trong Part 1; reports/cp1 là bằng chứng lượt chạy bằng công cụ trợ lý |

### CP2 — Docker

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Base image, WORKDIR, cache, CMD/ENTRYPOINT nghĩa là gì? | Giải thích từng mục theo Dockerfile thực tế | Đọc Dockerfile; không viết lại code mẫu | Đối chiếu bốn câu trả lời Exercise 2.1 |
| Build và chạy develop thế nào? | Lệnh build từ gốc repo, chạy container và gọi question qua query | Build/chạy develop và gọi curl | docker ps báo Up, health/ask trả 200 |
| Multi-stage giảm dung lượng thế nào? | Giải thích builder/runtime, base slim và cách tính chênh lệch cùng một cột | Build/chạy advanced, đo docker images | Develop 1.67 GB, advanced 240 MB Disk usage; giảm khoảng 85.6% |
| Chạy Compose và lưu bằng chứng còn thiếu thế nào? | Hướng dẫn .env.local, project riêng, Nginx cổng 80 và tee output | Chạy stack, gọi qua Nginx, lưu file và down -v | Bốn service Up, ba service có healthcheck healthy, HTTP 200 và bảng sau cleanup rỗng; reports/cp2 |
| Docker image có phải ảnh và xem ở đâu? | Giải thích image/layer/container và mục Images trong Docker Desktop | Xem hai tag develop/advanced | Phân biệt image Docker với ảnh PNG nộp bài |

### CP3 — API Security

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Terminal A/B dùng thế nào và nhập thừa dấu nháy xử lý ra sao? | Chỉ A chạy server, B chạy curl; Ctrl+C hủy dòng lệnh chưa đóng nháy | Mở Ubuntu và sửa lệnh ở B | Lệnh trở lại dấu nhắc bình thường, server A tiếp tục chạy |
| Thử API key thế nào? | Lệnh thiếu/đúng/sai key và giải thích verify_api_key | Tự gọi curl và lưu output | 401/200/403 theo code mẫu; ba file api-key-* trong reports/cp3 |
| Lấy và dùng JWT thế nào? | Endpoint /auth/token, tài khoản mẫu student/demo123 theo K5, cách giữ token trong biến | Dừng develop, chạy production, lấy token và gọi API | JWT hợp lệ trả 200; jwt-valid.txt; không đưa token vào bài |
| Tạo 429 và hiểu thuật toán rate limit thế nào? | Vòng lặp 20 request, giải thích cửa sổ timestamp và hạn mức theo role | Chạy vòng lặp và đọc rate_limiter.py | 9 phản hồi 200, 11 phản hồi 429 trong vòng lặp; rate-limit.txt |
| Cost guard bảo vệ gì, khác rate limit ra sao? | Giải thích code demo ngân sách ngày/RAM và phương án tháng/Redis trong đề | Đọc cost_guard.py và xác nhận đã đọc xong | Đối chiếu phần giải thích Exercise 4.4; không nhận là đã test 402/503 tại CP3 |

### CP4 — Scaling & Reliability

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Health và ready khác nhau thế nào? | Giải thích liveness/readiness và cờ _is_ready trong develop | Chạy app mẫu, gọi hai endpoint và lưu output | Cả hai trả 200; in_flight_requests bao gồm request kiểm tra |
| Gửi SIGTERM đúng process thế nào? | Chỉ cách lấy PID từ log và gửi request background trước kill -TERM | Gửi SIGTERM tới PID 3442 | Request hoàn thành 200, có log graceful shutdown và process kết thúc |
| State ở Redis và ba instance hoạt động ra sao? | Giải thích save/load session, hướng dẫn Compose project scaling và cổng 8080 | Đọc app.py, chạy ba agent, gọi health và test_stateless.py | Ba agent dùng Redis, 5 request qua ba instance, history đủ 10 message |
| Lưu log và dọn stack thế nào? | Lệnh logs/down/ps dùng cùng project name | Lưu log, dừng stack | after-cleanup.txt không còn container; bằng chứng tại reports/cp4 |

### CP5 — Final Project

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Bắt đầu bản khung ở đâu, dùng terminal nào? | Chỉ đúng 06-lab-complete, terminal B và static-only trước khi sửa | Chạy baseline và lưu output | static-before.txt: 0/12, 5/24 checks |
| Thêm /health đúng hợp đồng thế nào? | Code mẫu endpoint trả status ok, không phụ thuộc Redis | Thêm hàm vào main.py, lưu file | static-health.txt nhận route /health |
| Đọc cấu hình và liệt kê biến thế nào? | Code mẫu dataclass/os.getenv và nội dung .env.example | Điền config.py và .env.example | static-config.txt nhận đủ biến, không hardcode secret |
| Log JSON hợp lệ thế nào? | Code mẫu JsonFormatter dùng json.dumps và gợi ý vị trí log trong ask | Thêm formatter/handler và logger.info | static-logging.txt; full-check xác nhận 7 dòng JSON |
| Auth thiếu/sai key trả 401 và nối dependency thế nào? | Code mẫu APIKeyHeader(auto_error=False), verify_api_key, Depends | Điền auth.py và nối vào ask | static-auth.txt; full-check có thiếu/sai key 401, key đúng 200 |
| App vẫn khởi động khi Redis lỗi và ready trả 503 thế nào? | Code mẫu Redis client chưa ping lúc import, hàm redis_healthy và ready | Điền redis_client.py, thêm ready vào main.py | static-ready.txt; full-check kiểm tra Redis down: ready 503, health 200 |
| Rate limit dùng chung nhiều worker thế nào? | Giải thích/code gợi ý sorted set, script Lua nguyên tử và Retry-After | Điền rate_limiter.py, gọi check_rate_limit trong ask | static-rate-limit.txt; full-check vượt hạn mức 429, restart vẫn 429 |
| Theo dõi ngân sách Redis và trả 402 thế nào? | Code mẫu check_budget/record_cost theo ngày UTC, ước lượng token cho mock | Điền cost_guard.py, gọi trước/sau LLM trong ask | static-cost.txt; full-check ngân sách gần 0 trả 402 |
| Shutdown an toàn mà không ghi đè signal handler thế nào? | Code mẫu lifespan, đóng Redis sau yield | Thêm lifespan vào main.py | static-shutdown.txt; full-check SIGTERM hoàn thành request, exit 0 |
| Dockerfile/.dockerignore đáp ứng yêu cầu thế nào? | Mẫu multi-stage slim/non-root/healthcheck/exec/PORT và loại file không cần thiết | Sửa Dockerfile, .dockerignore | static-docker.txt; full-check image 273 MB, docker stop 0.8 giây |
| Compose và cấu hình Railway viết thế nào? | Mẫu agent + Redis, variables, depends_on, railway.toml | Điền Compose và Railway config | static-compose.txt, static-deploy.txt: toàn bộ 26 kiểm tra tĩnh qua |
| Chạy bản đầy đủ với requirements ghim phiên bản thế nào? | Hướng dẫn môi trường Python 3.11 và lệnh checker có Docker | Tạo môi trường, cài nguyên requirements, chạy bản đầy đủ | full-check.txt: PASS 12/12, 41/41 checks; giữ nguyên script chấm |

### CP6 — Cloud Deployment

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Cài CLI trong Ubuntu và đăng nhập thế nào? | Chỉ lỗi đang dùng npm Windows, hướng dẫn Node/npm Linux, CLI và browserless login | Cài công cụ, tạo mã mới khi mã cũ hết hạn, đăng nhập | /usr/bin/node và /usr/bin/npm, CLI báo signed in |
| Tạo project, Redis và nối đúng service thế nào? | Lệnh init/add/status và giải thích agent Offline trước deploy | Tạo lab14, Redis và agent, liên kết đúng service | Status xác nhận Redis Online, linked service agent |
| Đặt secret và kết nối Redis cloud thế nào? | Lệnh tạo key ngẫu nhiên, stdin và reference Redis.REDIS_URL | Đặt variables trên Railway | Các request public sau deploy xác nhận auth và readiness hoạt động |
| Build báo requirements chứa byte rỗng xử lý thế nào? | Đọc log, đối chiếu file gốc, gợi ý upload bản sao từ filesystem Linux | Copy các file cần deploy vào thư mục Linux tạm và upload cùng service | Build/deploy complete; không đổi requirements hoặc khẳng định nguyên nhân chưa chứng minh |
| Tạo URL và kiểm tra API thế nào? | Lệnh domain và bốn curl theo CP6; giải thích URL gốc 404 vì chưa có route / | Tạo domain, gọi bốn lệnh, mở health/ready | public-check.txt: 200/200/401/200, browser trả ok/true |
| Chụp ảnh ở đâu, chọn running nào, điền tài liệu thế nào? | Hướng dẫn vị trí dashboard/log/terminal, chọn running.png chính; hỗ trợ diễn giải Render/Cloud Run và biên tập tài liệu | Tự chụp/lưu ba ảnh theo tên yêu cầu, giữ ảnh log bổ sung | Đối chiếu screenshots, DEPLOYMENT.md và Part 3; không lộ secret |

### CP7 — Benchmark local

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Chuẩn bị CP7 và sửa lỗi chạy Linux command trong PowerShell thế nào? | Hướng dẫn vào WSL, kích hoạt Python 3.11, copy template một lần và cài thư viện | Mở Ubuntu, tạo báo cáo, cài requirements | Tự chạy import, nhận CP7 dependencies OK |
| Thêm metric độ dài câu hỏi ở đâu? | Code mẫu Histogram và observe trước LLM, giải thích cardinality | Đã mở file; phần metric chưa lưu được bổ sung bằng công cụ trợ lý khi yêu cầu xử lý tiếp CP7 | metrics.prom có count 1/sum 40 và hai URL lạ gộp unmatched; chưa ghi nhận người học tự đo lại |
| Hoàn tất load test, eval, sửa KB và báo cáo thế nào? | Hỗ trợ chạy công cụ lab qua WSL, bổ sung hai tài liệu JWT/HPA theo hướng dẫn, job CI và phân tích JSON thật | Đã chuẩn bị môi trường; code, phép đo và đóng gói tiếp theo được thực hiện qua công cụ trợ lý theo yêu cầu | 7 lượt × 300 request, final 23/23 không regression, verification PASSED; chưa ghi nhận người học tự chạy lại |
| Ghi nhận kết quả FAIL và CI thế nào? | Giải thích FAIL SLO là số đo cần giữ, phân biệt gate local với workflow GitHub | Chưa có thao tác tự đổi ngưỡng/số đo hoặc cấu hình GitHub được ghi nhận | Reports giữ c100/slow 0.1 FAIL; CI equivalent local PASS, không nhận đã chạy GitHub Actions |
| Điền và kiểm tra báo cáo theo mẫu thế nào? | Hỗ trợ điền mục CP7 của BENCHMARK_REPORT, câu trả lời Part 7 và đối chiếu hash/JSON | Cần tự đọc lại báo cáo/code và đối chiếu các JSON trước khi nộp; chưa ghi nhận hoàn tất bước tự kiểm tra này | reports/cp7/verification.txt là bằng chứng kiểm chứng bằng công cụ trợ lý; phần CP8 cập nhật riêng theo tiến độ và bằng chứng thực tế |

### CP8 — Observability stack và nộp bài

| Hỏi gì | Nhận gì | Tự sửa/thực hiện gì | Tự kiểm tra thế nào |
| --- | --- | --- | --- |
| Bật stack observability đúng K5 thế nào? | Hướng dẫn thư mục production, key mẫu local và project k5-day14-observability, scale agent=1 | Tạo .env và thư mục bằng chứng, bật Compose | Đã lưu trạng thái stack và log khởi động trong reports/cp8 |
| Agent restart với lỗi không import được uvicorn xử lý thế nào? | Chỉ ra home của user là /app nhưng dependencies copy vào /home/agent/.local; gợi ý sửa đúng một dòng useradd | Đổi home user agent thành /home/agent, rebuild stack | Agent healthy; sau startup, health qua Nginx trả 200. Lượt 502 ban đầu xảy ra trước khi agent startup xong |
| Chụp Grafana có dữ liệu thế nào? | Hướng dẫn Locust 30 users/ramp up 5, đọc Golden Signals và phần LLM | Tạo tải bằng UI, tự chụp grafana-dashboard.png | Ảnh đã được mở đối chiếu, có traffic/error/p95/in-flight/instance và biểu đồ LLM |
| Chọn trace chậm và lấy log khớp ID thế nào? | Hướng dẫn lọc Min Duration 1s, mở span LLM, lấy ID đầy đủ, curl trace JSON và grep log | Tự chọn trace, chụp jaeger-slow-trace.png, lưu JSON/log | ID 9321d64ebc70e6873d6a626874f82bc4 khớp ảnh/trace/log; công cụ trợ lý đối chiếu duration root 1742.496 ms, LLM 1690.822 ms và cập nhật báo cáo |
| Tìm trace lỗi và hiện event exception thế nào? | Hướng dẫn bỏ lọc duration, tìm error=true, dùng show all để hiện event ngoài vùng zoom, lưu JSON và grep log theo ID | Tự tìm/chụp trace lỗi, tải JSON và lưu log | ID 8a09b4fe56d47e2cc51825d05924cf50 khớp ảnh/JSON/log, HTTP 503 và event LLMError; công cụ trợ lý đã đối chiếu và ghi báo cáo |
| Unit test alert thực hiện thế nào? | Lệnh promtool test rules dùng image Prometheus của bài và thư mục rule read-only | Tự chạy test, lưu alert-rules-test.txt | Output SUCCESS |
| Kích hoạt error/latency alert và đo thời gian thế nào? | Hướng dẫn .env thí nghiệm A/B, giữ Locust 30 users; script chỉ đọc API Prometheus mỗi 5 giây để ghi first observed firing | Tự đặt error rate 0.2, chạy A; sau đó giữ error và tăng slow rate 0.3 cho B, áp dụng Compose và chạy watcher | A: error firing 88.0 giây; B: latency firing 141.5 giây, có snapshot hai alert cùng firing; ảnh screenshots/prometheus-alert-firing.png đã được mở kiểm tra, thấy cả hai FIRING |
| Chạy benchmark scaling 1–3 instances thế nào? | Trợ lý đưa lệnh Locust headless 100 users/ramp-up 10/2 phút nhưng ban đầu thiếu --no-deps; khi đọc log phát hiện Compose đưa agent về mặc định 2 replicas, sửa hướng dẫn thêm --no-deps | Tự chạy lại cả hai lượt với --no-deps, chờ agent healthy và lưu trạng thái; gửi output để đối chiếu | Đã lưu kết quả sai số instance trong reports/cp8/invalid-scaling-default-replicas. Lượt chạy lại xác nhận 1 và 3 agent; CSV hợp lệ được sao chép vào benchmark-results, /ask p95 840 → 270 ms; trợ lý cập nhật phân tích trong BENCHMARK_REPORT |
| Đọc dashboard và /metrics để trả lời Exercise 7.4 thế nào? | Hướng dẫn chạy 2 agent, Locust 30 users/ramp-up 5, giải thích panel và cấu hình Nginx | Tự chạy curl /metrics, tạo tải và gửi ảnh Grafana; yêu cầu hoàn thiện số chính xác sau khi kiểm tra hồ sơ | /metrics 404 đúng cấu hình. Trợ lý ban đầu đọc sai panel Tokens/s cộng dồn và dùng avg xấp xỉ; đã sửa bằng lần đo bổ sung qua công cụ theo yêu cầu, không coi số mới là số trong ảnh cũ |
| Hoàn thiện avg chính xác và sửa câu cũ chưa chạy production thế nào? | Trợ lý bổ sung script capture_cp8_dashboard.py, chạy lại 2 agent/30 users/ramp-up 5/2 phút và đọc đúng PromQL dashboard tại cùng timestamp; sửa câu mô tả CP8 cũ | Yêu cầu trợ lý thực hiện hai mục; phép đo bổ sung và cập nhật tài liệu do công cụ trợ lý thực hiện, chưa ghi nhận người học tự chạy lại | reports/cp8/dashboard-exact/prometheus.json: avg 227.395903 ms, p95 292.563739 ms; input/output 1458.345455/761.254545 tokens/s. Đã lưu log, trạng thái trước/sau và dọn stack; số mới phân biệt rõ với ảnh cũ |
| Dọn stack observability thế nào? | Hướng dẫn dừng tải rồi chạy down -v đúng project k5-day14-observability, lưu log và ps -a | Tự chạy lệnh dọn và gửi output | cleanup.txt ghi container/network Removed; after-cleanup.txt chỉ còn tiêu đề, không còn container của project |
| Kiểm tra lại cloud trước khi nộp thế nào? | Hướng dẫn curl bốn trường hợp và nhập key ẩn bằng read -rsp, chỉ lưu mã HTTP | Tự chạy health/ready/ask thiếu key, lấy key từ Railway rồi test ask có key | reports/cp6/final-public-check.txt xác nhận 200/200/401/200 sau CP8 |
| Các mục còn lại đã xong chưa? | Nhắc kiểm tra hồ sơ và phân biệt hoàn thành thực hành với nộp bài | Đã hoàn thành Locust headless scaling hợp lệ, gửi dữ liệu dashboard, dọn stack và kiểm tra lại cloud; còn đưa bài lên GitHub và nộp LMS | Chưa xác nhận toàn bộ lab đã nộp; cập nhật log khi thực hiện |
