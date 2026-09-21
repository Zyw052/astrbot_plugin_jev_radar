"""真实连通性验证脚本（可选，会消耗极小额度）。

用法（key 从环境变量读取，绝不落盘、绝不明文写入任何文件）::

    JEVKEY=<你的key> python3 tests/real_connectivity.py

行为：
  - 仅发起 1 次真实请求；失败最多重试 1 次（由 JevClient 控制），绝不额外多打。
  - 只打印「判定结果 + token 用量 + 耗时」，不打印 key。
  - 未设置 JEVKEY 时安全退出（exit code 2），不发起任何请求。
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jev_client import JevClient, JevError  # noqa: E402
from radar_core import build_questions, build_state, parse_answers  # noqa: E402

SAMPLE = "姐，我们这款面膜都是纯天然成分，今天活动最后一天，前50名下单送面膜仪，错过就没啦！"


async def main() -> int:
    key = os.environ.get("JEVKEY")
    if not key:
        print("[skip] 未设置环境变量 JEVKEY，跳过真实连通性验证（不发起任何请求）。")
        return 2

    base_url = os.environ.get("JEV_BASE_URL", "https://api.typesafe.ai")
    model = os.environ.get("JEV_MODEL", "jev-latest")

    client = JevClient(base_url=base_url, api_key=key, model=model, timeout=30, retries=1)
    state = build_state(SAMPLE, max_chars=800, redact=True)
    try:
        t0 = time.time()
        answers, usage = await client.judge(state, build_questions())
        dt = time.time() - t0
    except JevError as e:
        print(f"[fail] 真实调用失败：{e}")
        return 1
    finally:
        await client.close()

    result = parse_answers(answers)
    print("[ok] 真实连通性验证成功")
    print(f"  model   = {model}")
    print(f"  latency = {dt:.2f}s")
    print(f"  usage   = {usage}")
    print(f"  intent  = {result['intent']} (conf={result['intent_confidence']:.2f})")
    print(f"  emotion = {result['emotion']} (conf={result['emotion_confidence']:.2f})")
    print(f"  risk    = {result['risk']} (level={result['risk_level']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
