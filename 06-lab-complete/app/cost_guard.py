"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402
"""

from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r


# Giá mô phỏng theo bản khung, không phải giá được tra cứu hiện tại.
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def budget_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"budget:{day}"


def check_budget() -> None:
    """Kiểm tra ngân sách trước khi gọi LLM."""
    try:
        spent = float(r.get(budget_key()) or 0)
    except redis.RedisError:
        raise HTTPException(
            status_code=503,
            detail="Budget storage is unavailable",
        ) from None

    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Daily budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Cộng chi phí vào Redis và trả về chi phí request."""
    cost = (
        input_tokens / 1000 * PRICE_INPUT_PER_1K
        + output_tokens / 1000 * PRICE_OUTPUT_PER_1K
    )

    try:
        with r.pipeline(transaction=True) as pipe:
            pipe.incrbyfloat(budget_key(), cost)
            pipe.expire(budget_key(), 48 * 3600)
            pipe.execute()
    except redis.RedisError:
        raise HTTPException(
            status_code=503,
            detail="Budget storage is unavailable",
        ) from None

    return cost