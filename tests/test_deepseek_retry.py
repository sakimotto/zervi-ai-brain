import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.main import (
    _deepseek_post_with_retry,
    _deepseek_stream_with_retry,
    _is_retryable_deepseek_error,
)


class TestIsRetryableDeepseekError:
    def test_timeout_is_retryable(self):
        assert _is_retryable_deepseek_error(httpx.TimeoutException("timed out")) is True

    def test_connect_error_is_retryable(self):
        assert _is_retryable_deepseek_error(httpx.ConnectError("connection failed")) is True

    def test_502_status_error_is_retryable(self):
        response = MagicMock()
        response.status_code = 502
        assert _is_retryable_deepseek_error(httpx.HTTPStatusError("502", request=MagicMock(), response=response)) is True

    def test_429_status_error_is_retryable(self):
        response = MagicMock()
        response.status_code = 429
        assert _is_retryable_deepseek_error(httpx.HTTPStatusError("429", request=MagicMock(), response=response)) is True

    def test_400_status_error_is_not_retryable(self):
        response = MagicMock()
        response.status_code = 400
        assert _is_retryable_deepseek_error(httpx.HTTPStatusError("400", request=MagicMock(), response=response)) is False

    def test_random_exception_is_not_retryable(self):
        assert _is_retryable_deepseek_error(ValueError("boom")) is False


class TestDeepseekPostWithRetry:
    async def test_returns_success_on_first_attempt(self):
        client = MagicMock()
        expected_response = MagicMock()
        expected_response.raise_for_status = MagicMock()
        client.post = AsyncMock(return_value=expected_response)

        response = await _deepseek_post_with_retry(
            client, "https://api.example.com/chat", {}, {"model": "x"}, 60.0
        )

        assert response is expected_response
        assert client.post.call_count == 1

    async def test_retries_on_502_and_succeeds(self):
        client = MagicMock()
        bad_response = MagicMock()
        bad_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("502", request=MagicMock(), response=bad_response)
        )
        bad_response.status_code = 502

        good_response = MagicMock()
        good_response.raise_for_status = MagicMock()

        client.post = AsyncMock(side_effect=[bad_response, good_response])

        with patch("app.main._DEEPSEEK_RETRY_BACKOFF", 0.0):
            response = await _deepseek_post_with_retry(
                client, "https://api.example.com/chat", {}, {"model": "x"}, 60.0
            )

        assert response is good_response
        assert client.post.call_count == 2

    async def test_raises_after_exhausting_retries(self):
        client = MagicMock()
        bad_response = MagicMock()
        bad_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("503", request=MagicMock(), response=bad_response)
        )
        bad_response.status_code = 503
        client.post = AsyncMock(return_value=bad_response)

        with patch("app.main._DEEPSEEK_RETRY_ATTEMPTS", 2), patch("app.main._DEEPSEEK_RETRY_BACKOFF", 0.0):
            with pytest.raises(httpx.HTTPStatusError):
                await _deepseek_post_with_retry(
                    client, "https://api.example.com/chat", {}, {"model": "x"}, 60.0
                )

        assert client.post.call_count == 2

    async def test_no_retry_on_400(self):
        client = MagicMock()
        bad_response = MagicMock()
        bad_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("400", request=MagicMock(), response=bad_response)
        )
        bad_response.status_code = 400
        client.post = AsyncMock(return_value=bad_response)

        with pytest.raises(httpx.HTTPStatusError):
            await _deepseek_post_with_retry(
                client, "https://api.example.com/chat", {}, {"model": "x"}, 60.0
            )

        assert client.post.call_count == 1


class TestDeepseekStreamWithRetry:
    async def test_stream_returns_success_on_first_attempt(self):
        client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = AsyncMock(return_value=[])
        client.stream = MagicMock()
        client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        client.stream.return_value.__aexit__ = AsyncMock(return_value=None)

        async with _deepseek_stream_with_retry(
            client, "https://api.example.com/chat", {}, {"model": "x", "stream": True}, 60.0
        ) as response:
            assert response is mock_response

    async def test_stream_retries_on_timeout(self):
        client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = AsyncMock(return_value=[])

        # First attempt times out, second succeeds.
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(side_effect=[httpx.TimeoutException("timeout"), mock_response])
        stream_ctx.__aexit__ = AsyncMock(return_value=None)
        client.stream = MagicMock(return_value=stream_ctx)

        with patch("app.main._DEEPSEEK_RETRY_BACKOFF", 0.0):
            async with _deepseek_stream_with_retry(
                client, "https://api.example.com/chat", {}, {"model": "x", "stream": True}, 60.0
            ) as response:
                assert response is mock_response

        assert client.stream.call_count == 2
