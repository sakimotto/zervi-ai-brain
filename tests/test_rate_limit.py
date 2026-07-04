import pytest
from fastapi import HTTPException, Request

from app.rate_limit import check_rate_limit


def _fake_request(ip: str = "127.0.0.1") -> Request:
    return Request({"type": "http", "client": (ip, 12345)})


class TestRateLimiter:
    async def test_under_limit_passes(self):
        await check_rate_limit(_fake_request(), user_id=1, limit=3)
        await check_rate_limit(_fake_request(), user_id=1, limit=3)

    async def test_exceeding_limit_raises_429(self):
        for _ in range(3):
            await check_rate_limit(_fake_request(), user_id=2, limit=3)
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(_fake_request(), user_id=2, limit=3)
        assert exc_info.value.status_code == 429

    async def test_different_users_are_isolated(self):
        for _ in range(3):
            await check_rate_limit(_fake_request(), user_id=3, limit=3)
        # A different user should still be allowed even though user 3 hit its limit.
        await check_rate_limit(_fake_request(), user_id=4, limit=3)

    async def test_limit_zero_disables_check(self):
        for _ in range(10):
            await check_rate_limit(_fake_request(), user_id=5, limit=0)

    async def test_ip_fallback(self):
        for _ in range(2):
            await check_rate_limit(_fake_request(ip="10.0.0.1"), user_id=None, limit=2)
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(_fake_request(ip="10.0.0.1"), user_id=None, limit=2)
        assert exc_info.value.status_code == 429
