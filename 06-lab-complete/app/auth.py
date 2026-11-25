"""
API Key authentication (tiêu chí 6).

Yêu cầu:
  • Client gửi header  X-API-Key: <key>
  • Key phải trùng biến môi trường AGENT_API_KEY
  • Thiếu hoặc sai key → HTTP 401 (không phải 403 hay 422)
"""


from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings


api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


def verify_api_key(
    api_key: str = Security(api_key_header),
) -> str:
    if (
        not api_key
        or not settings.agent_api_key
        or api_key != settings.agent_api_key
    ):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
        )
    return api_key
