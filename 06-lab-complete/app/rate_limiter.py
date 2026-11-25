"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)
"""


import hashlib
import math
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r


WINDOW_SECONDS = 60

# Thực hiện các thao tác trong Redis một cách nguyên tử,
# tránh hai worker đồng thời vượt qua bước kiểm tra.
RATE_LIMIT_SCRIPT = r.register_script("""
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)

if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    return math.max(1, math.ceil(tonumber(oldest[2]) + window - now))
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)
return 0
""")


def check_rate_limit(key: str) -> None:
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    redis_key = f"rate_limit:{key_hash}"

    try:
        retry_after = int(
            RATE_LIMIT_SCRIPT(
                keys=[redis_key],
                args=[
                    time.time(),
                    WINDOW_SECONDS,
                    settings.rate_limit_per_minute,
                    uuid.uuid4().hex,
                ],
            )
        )
    except redis.RedisError:
        raise HTTPException(
            status_code=503,
            detail="Rate limiter is unavailable",
        ) from None

    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )