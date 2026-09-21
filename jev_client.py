"""Jev 意图雷达 —— TypeSafe SystemOne 异步 HTTP 客户端。

规范依据：
  - §10.2 网络请求：仅用 aiohttp/httpx（异步），禁止 requests
  - §10.4 工程原则：良好错误处理，不让插件因单个错误崩溃

接口（依据 /AstrBot/data/reports/Jev-API调研_20260921.md 与实测报告）：
  POST {base_url}/v1/systemone
  Header: Authorization: Bearer <key>, Content-Type: application/json
  Body:   {"state": "<文本>", "model": "<model>", "questions": {...}}
  响应:   {"model": "...", "answers": {...}, "usage": {...}}

错误码：401 未授权 / 422 校验失败 / 429 限流 / 529 过载
  - 429 / 503 / 529 → 按配置重试（默认最多重试 1 次）
  - 其余 → 直接抛 JevError，由调用方降级为提示，不崩

作者：YongWei
许可：MIT（见 LICENSE）
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS = {429, 503, 529}

# 默认端点后缀（与 base_url 拼接）
SYSTEMONE_PATH = "/v1/systemone"


class JevError(Exception):
    """Jev 调用通用异常基类。"""


class JevAuthError(JevError):
    """401 鉴权失败（key 无效 / 缺失）。"""


class JevRateLimitError(JevError):
    """429/503/529 限流或过载（已重试仍失败）。"""


class JevTimeoutError(JevError):
    """请求超时。"""


class JevClient:
    """Jev（TypeSafe SystemOne）异步客户端。

    使用示例::

        client = JevClient(base_url=..., api_key=..., model="jev-latest")
        answers, usage = await client.judge(state="...", questions={...})
        await client.close()

    也可通过 async with 使用::

        async with JevClient(...) as client:
            answers, usage = await client.judge(...)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "jev-latest",
        timeout: int = 20,
        retries: int = 1,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "jev-latest"
        self.timeout = int(timeout) if timeout else 20
        self.retries = max(0, int(retries) if retries is not None else 1)
        self._session: aiohttp.ClientSession | None = None

    # -- 生命周期 ---------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        """惰性创建共享 ClientSession（复用连接，降低握手开销）。"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """关闭底层会话；重复调用安全。"""
        if self._session is not None and not self._session.closed:
            try:
                await self._session.close()
            except Exception:  # noqa: BLE001
                pass
        self._session = None

    async def __aenter__(self) -> JevClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # -- 核心调用 ---------------------------------------------------------

    @property
    def endpoint(self) -> str:
        """完整端点 URL。"""
        return self.base_url + SYSTEMONE_PATH

    async def judge(
        self, state: str, questions: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """执行一次判定请求。

        返回 ``(answers, usage)``；失败抛 JevError 子类。
        绝不在此处吞掉异常 —— 由 main.py 统一降级为面向用户的提示。
        """
        if not self.api_key:
            raise JevAuthError("未配置 TypeSafe API Key（api_key 为空）")

        payload = {
            "state": state,
            "model": self.model,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_err: Exception | None = None
        # retries=1 表示「最多重试 1 次」= 最多请求 2 次（首次 + 1 次重试）
        for attempt in range(self.retries + 1):
            try:
                session = await self._get_session()
                async with session.post(self.endpoint, json=payload, headers=headers) as resp:
                    raw = await resp.text()
                    if resp.status == 200:
                        data = json.loads(raw)
                        return data.get("answers", {}) or {}, data.get("usage", {}) or {}
                    if resp.status == 401:
                        raise JevAuthError("鉴权失败(401)：API Key 无效或已过期")
                    if resp.status in _RETRYABLE_STATUS:
                        last_err = JevRateLimitError(f"限流/过载({resp.status})：{raw[:200]}")
                        if attempt < self.retries:
                            await asyncio.sleep(1.5 * (attempt + 1))
                            continue
                        raise last_err
                    # 422 及其它错误：不重试
                    raise JevError(f"请求失败({resp.status})：{raw[:300]}")
            except JevError:
                raise
            except asyncio.TimeoutError as e:
                last_err = JevTimeoutError(f"请求超时（>{self.timeout}s）")
                if attempt < self.retries:
                    await asyncio.sleep(1.0)
                    continue
                raise last_err from e
            except aiohttp.ClientError as e:
                last_err = JevError(f"网络错误：{type(e).__name__}: {e}")
                if attempt < self.retries:
                    await asyncio.sleep(1.0)
                    continue
                raise last_err from e
            except json.JSONDecodeError as e:
                raise JevError(f"响应非合法 JSON：{e}") from e

        # 理论不可达；兜底
        raise last_err or JevError("未知调用失败")


__all__ = [
    "JevClient",
    "JevError",
    "JevAuthError",
    "JevRateLimitError",
    "JevTimeoutError",
    "SYSTEMONE_PATH",
]
