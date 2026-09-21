"""jev_client 离线单测：mock aiohttp，不发真实网络请求，不消耗额度。

覆盖：正常 200 解析、401 鉴权、422 不重试、429 重试后成功、429 重试耗尽、超时。
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from jev_client import (  # noqa: E402
    JevAuthError,
    JevClient,
    JevError,
    JevRateLimitError,
)


# --------------------------------------------------------------------------
# 假 aiohttp 会话
# --------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload if isinstance(payload, str) else json.dumps(payload)

    async def text(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakePostContext:
    """模拟 session.post(...) 返回的异步上下文管理器，按序吐出预设响应。"""

    def __init__(self, scripted):
        self._scripted = scripted  # list[FakeResponse 或 Exception]

    async def __aenter__(self):
        item = self._scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        self._resp = item
        return item

    async def __aexit__(self, *a):
        return False


class FakeSession:
    def __init__(self, scripted):
        self.closed = False
        self._scripted = scripted
        self.posts = []

    def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return FakePostContext(self._scripted)

    async def close(self):
        self.closed = True


def _make_client(session, retries=1):
    c = JevClient(
        base_url="https://api.typesafe.ai",
        api_key="test-key",
        model="jev-latest",
        timeout=5,
        retries=retries,
    )
    c._session = session
    return c


QUESTIONS = {"intent": {"type": "choice", "instructions": "x", "criteria": {"a": "b"}}}

OK_PAYLOAD = {
    "model": "jev-1.13.0",
    "answers": {
        "intent": {
            "type": "choice",
            "choice": "推销",
            "probabilities": {"推销": 1.0},
            "confidence": 1.0,
        }
    },
    "usage": {"input_tokens": 100, "output_tokens": 10},
}


def test_judge_success():
    session = FakeSession([FakeResponse(200, OK_PAYLOAD)])
    client = _make_client(session)

    answers, usage = asyncio.run(client.judge("state", QUESTIONS))
    assert answers["intent"]["choice"] == "推销"
    assert usage["input_tokens"] == 100
    # 校验请求构造：Bearer 鉴权 + 端点 + 模型
    assert session.posts[0]["url"].endswith("/v1/systemone")
    assert session.posts[0]["headers"]["Authorization"] == "Bearer test-key"
    assert session.posts[0]["json"]["model"] == "jev-latest"


def test_judge_no_api_key():
    client = JevClient("https://api.typesafe.ai", "", "jev-latest")
    with pytest.raises(JevAuthError):
        asyncio.run(client.judge("state", QUESTIONS))


def test_judge_401_auth_error_no_retry():
    session = FakeSession([FakeResponse(401, "unauthorized")])
    client = _make_client(session, retries=1)
    with pytest.raises(JevAuthError):
        asyncio.run(client.judge("state", QUESTIONS))
    assert len(session.posts) == 1  # 401 不重试


def test_judge_422_no_retry():
    session = FakeSession([FakeResponse(422, "validation error")])
    client = _make_client(session, retries=1)
    with pytest.raises(JevError):
        asyncio.run(client.judge("state", QUESTIONS))
    assert len(session.posts) == 1  # 422 不重试


def test_judge_429_then_success():
    session = FakeSession([FakeResponse(429, "rate limited"), FakeResponse(200, OK_PAYLOAD)])
    client = _make_client(session, retries=1)
    answers, _ = asyncio.run(client.judge("state", QUESTIONS))
    assert answers["intent"]["choice"] == "推销"
    assert len(session.posts) == 2  # 首次 + 1 次重试


def test_judge_429_exhausted():
    session = FakeSession([FakeResponse(429, "rate limited"), FakeResponse(529, "overloaded")])
    client = _make_client(session, retries=1)
    with pytest.raises(JevRateLimitError):
        asyncio.run(client.judge("state", QUESTIONS))
    assert len(session.posts) == 2


def test_judge_retries_zero_no_retry():
    session = FakeSession([FakeResponse(429, "rate limited")])
    client = _make_client(session, retries=0)
    with pytest.raises(JevRateLimitError):
        asyncio.run(client.judge("state", QUESTIONS))
    assert len(session.posts) == 1  # retries=0 → 只请求 1 次


def test_judge_timeout():
    session = FakeSession([asyncio.TimeoutError()])
    client = _make_client(session, retries=0)
    from jev_client import JevTimeoutError

    with pytest.raises(JevTimeoutError):
        asyncio.run(client.judge("state", QUESTIONS))


def test_endpoint_property():
    client = JevClient("https://api.typesafe.ai/", "k")
    assert client.endpoint == "https://api.typesafe.ai/v1/systemone"
