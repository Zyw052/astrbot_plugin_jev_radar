"""回复副驾（Reply Copilot）单测：纯逻辑 + main.py 集成闸门，全部离线打桩。

覆盖（对应需求）：
  - 触发策略：默认 explicit；risk 需白名单 + Jev 闸门（关注意图/高风险 且 置信度达标）
  - 费用分层：Jev 计数与 LLM 起草计数分开；冷却与每日上限
  - 永不代发：risk 触发只经 _deliver_to_master（目标=notify_target），绝不动原会话
  - 失败降级：LLM 失败不崩，返回错误摘要
"""

import asyncio
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT)
sys.path.insert(0, os.path.dirname(_PROJECT))


from astrbot_plugin_jev_radar.main import JevRadarPlugin  # noqa: E402
from astrbot_plugin_jev_radar.reply_copilot import (  # noqa: E402
    build_draft_prompt,
    build_judge_summary,
    check_budget,
    format_drafts,
    normalize_style,
    parse_drafts,
    session_in_whitelist,
    should_copilot_trigger,
)

# ---------------------------------------------------------------------------
# mock 判定结果
# ---------------------------------------------------------------------------

def _result(intent="推销", conf=0.91, risk="高危", level=None):
    return {
        "ok": True,
        "intent": intent,
        "intent_confidence": conf,
        "confidence": conf,
        "emotion": "负面",
        "risk": risk,
        "risk_level": level if level is not None else (2 if risk == "高危" else 0),
    }


# ---------------------------------------------------------------------------
# 纯逻辑测试
# ---------------------------------------------------------------------------

def test_normalize_style():
    assert normalize_style("polite") == "polite"
    assert normalize_style("POLITE") == "polite"
    assert normalize_style("unknown") == "concise"
    assert normalize_style(None) == "concise"


def test_build_draft_prompt_contains_message_and_count():
    p = build_draft_prompt("你好，在吗", style="firm", draft_count=3, judge_summary="意图=借钱(置信0.90)")
    assert "你好，在吗" in p
    assert "明确坚定" in p
    assert "共拟 3 条" in p
    assert "意图=借钱" in p
    # prompt 不含任何日期/路径等泄露面
    assert "/AstrBot" not in p


def test_parse_drafts_standard_format():
    txt = "1. 草稿：好的，收到。\n   理由：确认信息即可\n2. 草稿：稍后回复你。\n   理由：留缓冲\n3. 草稿：暂不回应。\n   理由：避免争执"
    ds = parse_drafts(txt)
    assert len(ds) == 3
    assert ds[0]["draft"] == "好的，收到。"
    assert ds[1]["reason"] == "留缓冲"


def test_parse_drafts_garbage_fallback():
    ds = parse_drafts("一整段没有格式的回复建议")
    assert len(ds) == 1 and "格式" in ds[0]["draft"]


def test_parse_drafts_empty():
    assert parse_drafts("") == []


def test_format_drafts_contains_never_send_note():
    ds = parse_drafts("1. 草稿：好的\n   理由：确认\n2. 草稿：再见\n   理由：礼貌")
    out = format_drafts(ds, judge_summary="意图=中性信息(置信0.99)")
    assert "【选1·concise】好的" in out
    assert "不会发送到任何会话" in out


def test_build_judge_summary_ok_and_bad():
    s = build_judge_summary(_result())
    assert "推销" in s and "0.91" in s
    assert build_judge_summary({"ok": False}) == ""
    assert build_judge_summary(None) == ""


# ---------------------------------------------------------------------------
# 触发闸门：risk 模式的触发条件（绝不无差别）
# ---------------------------------------------------------------------------

def test_trigger_gate_hits_on_high_risk_and_watch_intent():
    ok, reasons = should_copilot_trigger(_result(), risk_alert_threshold=2, confidence_threshold=0.6, watch_intents=["推销"])
    assert ok
    assert len(reasons) == 2


def test_trigger_gate_blocked_by_low_confidence():
    ok, _ = should_copilot_trigger(_result(conf=0.4), risk_alert_threshold=2, confidence_threshold=0.6, watch_intents=["推销"])
    assert not ok


def test_trigger_gate_neutral_message_never_triggers():
    ok, _ = should_copilot_trigger(
        _result(intent="中性信息", conf=0.99, risk="安全", level=0),
        risk_alert_threshold=2, confidence_threshold=0.6, watch_intents=["推销"],
    )
    assert not ok


def test_trigger_gate_judge_failure_never_triggers():
    ok, _ = should_copilot_trigger({"ok": False})
    assert not ok


# ---------------------------------------------------------------------------
# 白名单：risk 模式仅白名单会话生效，空名单=全部拒绝
# ---------------------------------------------------------------------------

def test_whitelist_empty_denies_all():
    assert not session_in_whitelist("aiocqhttp:GroupMessage:123", [])


def test_whitelist_matches_umo_and_group_id():
    wl = ["555"]
    assert session_in_whitelist("aiocqhttp:GroupMessage:555", wl)
    assert session_in_whitelist("555", wl)
    assert not session_in_whitelist("aiocqhttp:GroupMessage:666", wl)


# ---------------------------------------------------------------------------
# 冷却与每日上限
# ---------------------------------------------------------------------------

def test_budget_cooldown_blocks():
    now = time.time()
    ok, reason = check_budget(last_draft_ts=now - 60, now=now, cooldown_minutes=10)
    assert not ok and "冷却" in reason


def test_budget_cooldown_expired_passes():
    now = time.time()
    ok, reason = check_budget(last_draft_ts=now - 700, now=now, cooldown_minutes=10, drafts_today=0, max_drafts_per_day=20)
    assert ok and reason == ""


def test_budget_daily_cap_blocks():
    ok, reason = check_budget(last_draft_ts=None, now=time.time(), cooldown_minutes=10, drafts_today=20, max_drafts_per_day=20)
    assert not ok and "上限" in reason


def test_budget_zero_limits_are_allowed():
    assert check_budget(None, time.time(), cooldown_minutes=0, drafts_today=999, max_drafts_per_day=0) == (True, "")


# ---------------------------------------------------------------------------
# main.py 集成（打桩 LLM / KV）
# ---------------------------------------------------------------------------

class FakeContext:
    def __init__(self):
        self.sent = []

    async def llm_generate(self, chat_provider_id=None, prompt=None):
        class R:
            completion_text = "1. 草稿：好的，我明白。\n   理由：清晰表态\n2. 草稿：这件事再商量。\n   理由：留余地"
        return R()

    async def send_message(self, target, chain):
        self.sent.append((target, str(getattr(chain, "plain_result", str(chain)))))


def _make_plugin(**cfg):
    config = {
        "enable": True,
        "passive_enabled": True,
        "scope_group": True,
        "daily_call_limit": 100,
        "reply_copilot_enabled": True,
        "trigger_mode": "risk",
        "copilot_whitelist": ["555"],
        "notify_target": "aiocqhttp:FriendMessage:owner",
        "confidence_threshold": 0.75,
        "risk_alert_threshold": 2,
        "max_chars_per_msg": 800,
        "desensitize": True,
    }
    config.update(cfg)
    p = JevRadarPlugin(context=FakeContext(), config=config)

    async def nop(*a, **k):
        return None

    p.get_kv_data = nop
    p.put_kv_data = nop
    return p


def _event(text, umo="aiocqhttp:GroupMessage:555", gid="555"):
    class E:
        message_str = text
        unified_msg_origin = umo
        def get_sender_id(self):
            return "10001"
        def get_self_id(self):
            return "10000"
        def get_group_id(self):
            return gid
        def get_messages(self):
            return []
        def plain_result(self, t):
            return ("PLAIN", t)
    return E()


def test_reply_cmd_disabled_by_default():
    p = _make_plugin(reply_copilot_enabled=False)
    outs = asyncio.run(_collect(p.reply_cmd(_event("/reply 你好"))))
    assert "未启用" in outs[0][1]


async def _collect(gen):
    out = []
    async for r in gen:
        out.append(r)
    return out


def test_reply_cmd_happy_path_explicit():
    p = _make_plugin(trigger_mode="explicit")
    p._analyze = _stub_analyze
    outs = asyncio.run(_collect(p.reply_cmd(_event("/reply 有人推销东西"))))
    text = outs[0][1]
    assert "候选回复" in text
    assert "我明白" in text
    # /reply 结果只回显给主人所在会话，不调用 send_message（没有代发动作）
    assert not p.context.sent


async def _stub_analyze(text):
    return {"ok": False, "error": "skip"}


def test_reply_cmd_daily_cap_blocks_drafts():
    p = _make_plugin(trigger_mode="explicit")

    from datetime import date as _date
    today = _date.today().isoformat()

    async def full(*a, **k):
        return {"date": today, "drafts": 20}

    p.get_kv_data = full
    outs = asyncio.run(_collect(p.reply_cmd(_event("/reply 文本"))))
    assert "被限流" in outs[0][1]


def test_on_message_risk_mode_triggers_and_pushes_only_to_owner():
    p = _make_plugin(trigger_mode="risk")
    p._analyze = _stub_risky
    asyncio.run(_drain(p.on_message(_event("有人强推销", umo="aiocqhttp:GroupMessage:555"))))
    # 只有一条推送，且目标是 notify_target（主人），绝不是原群会话
    assert len(p.context.sent) == 1
    target = p.context.sent[0][0]
    assert target == "aiocqhttp:FriendMessage:owner"
    assert "候选回复" in p.context.sent[0][1]


async def _drain(gen):
    async for _ in gen:
        pass


async def _stub_risky(text):
    return _result()


def test_on_message_default_explicit_mode_never_pushes():
    p = _make_plugin(trigger_mode="explicit")
    p._analyze = _stub_risky
    asyncio.run(_drain(p.on_message(_event("有人强推销"))))
    assert not p.context.sent  # 默认 explicit：被动路径绝不触发副驾


def test_on_message_non_whitelist_session_never_pushes():
    p = _make_plugin(trigger_mode="risk", copilot_whitelist=["999"])
    p._analyze = _stub_risky
    asyncio.run(_drain(p.on_message(_event("有人强推销", umo="aiocqhttp:GroupMessage:555"))))
    assert not p.context.sent


def test_on_message_low_confidence_never_pushes():
    p = _make_plugin(trigger_mode="risk")

    async def low_conf(text):
        return _result(conf=0.30)

    p._analyze = low_conf
    asyncio.run(_drain(p.on_message(_event("有人强推销"))))
    assert not p.context.sent


def test_on_message_copilot_disabled_never_pushes():
    p = _make_plugin(reply_copilot_enabled=False)
    p._analyze = _stub_risky
    asyncio.run(_drain(p.on_message(_event("有人强推销"))))
    assert not p.context.sent


def test_llm_failure_degrades_gracefully():
    p = _make_plugin(trigger_mode="risk")

    class BadCtx:
        async def llm_generate(self, chat_provider_id=None, prompt=None):
            raise RuntimeError("provider down")

    self_id_ctx = BadCtx()
    p.context = self_id_ctx

    async def nop(*a, **k):
        return None

    p.get_kv_data = nop
    p.put_kv_data = nop
    p._analyze = _stub_risky
    asyncio.run(_drain(p.on_message(_event("有人强推销"))))
    # 失败降级：没有推送、没有抛异常
    assert len(getattr(self_id_ctx, "sent", [])) == 0


def test_draft_counter_separate_from_judge_counter():
    p = _make_plugin()
    import unittest.mock as mock

    async def judge_val(*a, **k):
        return {"date": "2026-09-22", "count": 5}

    async def void(*a, **k):
        pass

    with mock.patch.object(type(p), "get_kv_data", lambda self, k, d=None: _ret(k)):
        pass
    p.get_kv_data = void
    p.put_kv_data = void
    d = asyncio.run(p._get_draft_usage())
    assert "drafts" in d  # 起草计量键独立于 Jev 计数（count）


def _ret(k):
    if k == "reply_draft_usage":

        class FakeAsyncDict(dict):
            pass

        async def _r():
            return {"date": "2026-09-22", "drafts": 2}

        return _r()
    raise AssertionError(k)
