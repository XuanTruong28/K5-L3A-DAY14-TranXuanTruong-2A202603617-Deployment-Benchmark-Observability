# Deployment Information

## Public URL

https://agent-production-a52803be.up.railway.app

## Platform

Railway — project `lab14`, environment `production`, web service `agent` và database service `Redis`.

Deploy agent Part 6 từ `06-lab-complete/` theo README K5. Lần upload trực tiếp từ ổ D qua WSL gặp lỗi build đọc requirements thành byte rỗng, trong khi file gốc không chứa byte rỗng. Đã copy source cần thiết sang thư mục Linux tạm rồi upload vào cùng project/service; build và deploy thành công. Không thay phiên bản requirements để xử lý lỗi này; chưa xác định chính xác nguyên nhân lỗi upload/build ban đầu.

## Test Commands

Các lệnh theo CP6 trong CHECKPOINTS. `AGENT_API_KEY` phải được đặt trong môi trường terminal bằng đúng key đã cấu hình trên Railway; không ghi giá trị key trong repo hoặc ảnh.

### Health Check

```bash
BASE="https://agent-production-a52803be.up.railway.app"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
```

Kết quả thực tế: `200`, `200`. Người học đã mở `/health` và `/ready` trên trình duyệt, nhận `{"status":"ok"}` và `{"ready":true}`.

### API Test (with authentication)

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'
```

Kết quả thực tế: thiếu key `401`, key đúng `200`. Bằng chứng bốn lệnh: [public-check.txt](reports/cp6/public-check.txt). Kiểm tra lại sau khi hoàn tất CP8: health `200`, ready `200`, ask thiếu key `401`, ask có key `200`, lưu tại [final-public-check.txt](reports/cp6/final-public-check.txt). Key được nhập ẩn trong terminal; file bằng chứng chỉ ghi mã HTTP.

## Environment Variables Set

- `PORT=8000`
- `ENVIRONMENT=production`
- `AGENT_API_KEY`: key ngẫu nhiên được đưa lên Railway qua stdin, không ghi giá trị ở đây.
- `REDIS_URL`: reference `${{Redis.REDIS_URL}}`, không ghi connection string chứa credential.
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

## Screenshots

Đã lưu và kiểm tra ba ảnh theo SUBMISSION:

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)

