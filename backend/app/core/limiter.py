"""Per-IP rate limiting. In-memory by default; point slowapi at Redis to scale out."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[])
CHAT_LIMIT = f"{settings.rate_limit_per_minute}/minute"
