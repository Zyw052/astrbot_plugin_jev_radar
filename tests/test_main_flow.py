"""main.py 指令流程离线回归测试：打桩 Jev 调用与 KV，不联网。

验证：/jev dry 回显、/jev 正常输出、/jev 无参提示、被动模式默认关闭时不打扰。
"""

import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT)  # 使 radar_core/jev_client 可直接导入
sys.path.insert(0, os.path.dirname(_PROJECT))  # 使 astrbot_plugin_jev_radar 作为包导入


from astrbot_plugin_jev_radar.main import JevRadarPlugin  # noqa: E402
from astrbot_plugin_jev_radar.radar_core import parse_answers  # noqa: E402


class FakeEvent:
    def __init__(self, text, group_id="123"):
        self.message_str = text
        self._gid = group_id
        self.unified_msg_origin = "umo"

    def get_sender_name(self):
        return "tester"

    def get_sender_id(self):
        return "10001"

    def get_self_id(self):
        return "10000"

    def get_group_id(self):
        return self._gid

    def get_messages(self):
        return []

    def plain_result(self, t):
        return ("PLAIN", t)


CANON = {
    "intent": {"choice": "推销", "confidence": 0.91, "probabilities": {}},
    "emotion": {"choice": "中性", "confidence": 0.68, "probabilities": {}},
    "risk": {"choice": "高危", "confidence": 0.80, "probabilities": {}},
}
SAFE = {
    "intent": {"choice": "中性信息", "confidence": 0.99, "probabilities": {}},
    "emotion": {"choice": "中性", "confidence": 0.99, "probabilities": {}},
    "risk": {"choice": "安全", "confidence": 0.99, "probabilities": {}},
}


def _make_plugin(answers=CANON, **cfg):
    config = {
        "enable": True,
        "confidence_threshold": 0.75,
        "risk_alert_threshold": 2,
        "result_style": "详细",
        "daily_call_limit": 100,
        "desensitize": True,
        "max_chars_per_msg": 800,
        "passive_enabled": False,
    }
    config.update(cfg)
    p = JevRadarPlugin(context=None, config=config)

    async def fake_analyze(text):
        r = parse_answers(answers)
        r["usage"] = {"input_tokens": 100}
        return r

    p._analyze = fake_analyze

    async def nop(*a, **k):
        return None

    async def gk(key, default=None):
        return default

    p.put_kv_data = nop
    p.get_kv_data = gk
    return p


async def _collect(agen):
    out = []
    async for item in agen:
        out.append(item[1])
    return out


def test_cmd_dry_run_echo_only():
    p = _make_plugin()
    lines = asyncio.run(_collect(p.jev_cmd(FakeEvent("/jev dry 测试文本"))))
    joined = "\n".join(lines)
    assert "dry run" in joined
    assert "命中提醒策略" in joined


def test_cmd_normal_output():
    p = _make_plugin()
    lines = asyncio.run(_collect(p.jev_cmd(FakeEvent("/jev 借钱五千"))))
    joined = "\n".join(lines)
    assert "意图：推销" in joined
    assert "风险：高危" in joined


def test_cmd_alias_radar():
    p = _make_plugin()
    lines = asyncio.run(_collect(p.jev_cmd(FakeEvent("/雷达 测试"))))
    assert any("Jev 意图雷达" in x for x in lines)


def test_cmd_no_arg_usage_hint():
    p = _make_plugin()
    lines = asyncio.run(_collect(p.jev_cmd(FakeEvent("/jev"))))
    assert "用法" in lines[0]


def test_cmd_disabled():
    p = _make_plugin(enable=False)
    lines = asyncio.run(_collect(p.jev_cmd(FakeEvent("/jev 测试"))))
    assert "已关闭" in lines[0]


def test_cmd_quota_exceeded():
    p = _make_plugin(daily_call_limit=0)  # 0 表示不限，改用它测正常
    lines = asyncio.run(_collect(p.jev_cmd(FakeEvent("/jev 测试"))))
    assert any("意图" in x for x in lines)

    p2 = _make_plugin()
    p2._check_quota = lambda: _async_false()
    lines2 = asyncio.run(_collect(p2.jev_cmd(FakeEvent("/jev 测试"))))
    assert "上限" in lines2[0]


async def _async_false():
    return False


def test_passive_disabled_by_default():
    p = _make_plugin()
    lines = asyncio.run(_collect(p.on_message(FakeEvent("普通消息"))))
    assert lines == []


def test_passive_enabled_alerts_on_high_risk():
    p = _make_plugin(passive_enabled=True, scope_group=True, group_whitelist=[])
    lines = asyncio.run(_collect(p.on_message(FakeEvent("姐，面膜最后一天"))))
    assert lines and "提醒" in lines[0]


def test_passive_silent_when_safe():
    p = _make_plugin(answers=SAFE, passive_enabled=True)
    lines = asyncio.run(_collect(p.on_message(FakeEvent("会议改到下午三点"))))
    assert lines == []


def test_passive_skips_commands():
    p = _make_plugin(passive_enabled=True)
    lines = asyncio.run(_collect(p.on_message(FakeEvent("/jev 测试"))))
    assert lines == []


def test_passive_group_whitelist_filter():
    p = _make_plugin(passive_enabled=True, group_whitelist=["999"])
    lines = asyncio.run(_collect(p.on_message(FakeEvent("姐，面膜最后一天", group_id="123"))))
    assert lines == []
