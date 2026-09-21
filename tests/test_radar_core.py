"""radar_core 离线单测（不依赖 AstrBot、不发起网络请求、不消耗额度）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radar_core import (  # noqa: E402
    DEFAULT_WATCH_INTENTS,
    RISK_LEVEL,
    build_questions,
    build_state,
    desensitize,
    dry_run_preview,
    format_result,
    message_hash,
    parse_answers,
    should_alert,
    trim_text,
)


def test_desensitize_phone_email_id_bank():
    text = "联系我 13812345678 或 a@b.com，身份证 11010119900307123X，卡号 6222021234567890123"
    out = desensitize(text)
    assert "13812345678" not in out
    assert "a@b.com" not in out
    assert "11010119900307123X" not in out
    assert "6222021234567890123" not in out
    assert "[手机号]" in out and "[邮箱]" in out and "[身份证]" in out


def test_desensitize_empty_and_none():
    assert desensitize("") == ""
    assert desensitize(None) == ""


def test_trim_text():
    assert trim_text("abc", 10) == "abc"
    long_text = "x" * 50
    out = trim_text(long_text, 10)
    assert out.startswith("x" * 10)
    assert "已截断" in out


def test_build_state_trim_then_redact():
    out = build_state("我的电话是13812345678", max_chars=800, redact=True)
    assert "13812345678" not in out
    out2 = build_state("我的电话是13812345678", max_chars=800, redact=False)
    assert "13812345678" in out2


def test_message_hash_stable_and_no_plaintext():
    h1 = message_hash("你好")
    h2 = message_hash("你好")
    assert h1 == h2
    assert "你好" not in h1


def test_build_questions_three_choice():
    q = build_questions()
    assert set(q.keys()) == {"intent", "emotion", "risk"}
    for key in ("intent", "emotion", "risk"):
        assert q[key]["type"] == "choice"
        assert isinstance(q[key]["criteria"], dict) and q[key]["criteria"]


def test_parse_answers_normal():
    answers = {
        "intent": {
            "type": "choice",
            "choice": "推销",
            "confidence": 0.91,
            "probabilities": {"推销": 0.91, "中性信息": 0.09},
        },
        "emotion": {
            "type": "choice",
            "choice": "中性",
            "confidence": 0.68,
            "probabilities": {"中性": 0.68},
        },
        "risk": {
            "type": "choice",
            "choice": "高危",
            "confidence": 0.80,
            "probabilities": {"高危": 0.80},
        },
    }
    r = parse_answers(answers)
    assert r["ok"] is True
    assert r["intent"] == "推销"
    assert abs(r["confidence"] - 0.91) < 1e-6
    assert r["risk_level"] == 2
    assert r["emotion"] == "中性"


def test_parse_answers_missing_fields_graceful():
    r = parse_answers({})
    assert r["ok"] is False
    assert r["intent"] == ""
    assert r["risk_level"] == 0
    r2 = parse_answers(None)
    assert r2["ok"] is False


def test_parse_answers_bad_types():
    r = parse_answers({"intent": "not-a-dict", "risk": {"choice": None}})
    assert r["ok"] is False
    assert r["confidence"] == 0.0


def test_risk_level_mapping():
    assert RISK_LEVEL["安全"] == 0
    assert RISK_LEVEL["关注"] == 1
    assert RISK_LEVEL["高危"] == 2


def test_should_alert_low_confidence():
    r = parse_answers(
        {
            "intent": {"choice": "中性信息", "confidence": 0.60, "probabilities": {}},
            "risk": {"choice": "安全", "confidence": 0.9, "probabilities": {}},
        }
    )
    alerted, reasons = should_alert(
        r, confidence_threshold=0.75, risk_alert_threshold=2, watch_intents=DEFAULT_WATCH_INTENTS
    )
    assert alerted is True
    assert any("低置信" in x for x in reasons)


def test_should_alert_high_risk():
    r = parse_answers(
        {
            "intent": {"choice": "中性信息", "confidence": 0.99, "probabilities": {}},
            "risk": {"choice": "高危", "confidence": 0.9, "probabilities": {}},
        }
    )
    alerted, reasons = should_alert(r, 0.75, 2, DEFAULT_WATCH_INTENTS)
    assert alerted is True
    assert any("高风险" in x for x in reasons)


def test_should_alert_watch_intent():
    r = parse_answers(
        {
            "intent": {"choice": "诈骗", "confidence": 0.99, "probabilities": {}},
            "risk": {"choice": "安全", "confidence": 0.9, "probabilities": {}},
        }
    )
    alerted, reasons = should_alert(r, 0.75, 2, DEFAULT_WATCH_INTENTS)
    assert alerted is True
    assert any("关注意图" in x for x in reasons)


def test_should_alert_silent_when_normal():
    r = parse_answers(
        {
            "intent": {"choice": "中性信息", "confidence": 0.99, "probabilities": {}},
            "risk": {"choice": "安全", "confidence": 0.99, "probabilities": {}},
        }
    )
    alerted, reasons = should_alert(r, 0.75, 2, DEFAULT_WATCH_INTENTS)
    assert alerted is False
    assert reasons == []


def test_should_alert_not_alert_on_failed():
    alerted, _ = should_alert({"ok": False}, 0.75, 2, DEFAULT_WATCH_INTENTS)
    assert alerted is False


def test_format_result_detailed_and_simple():
    r = parse_answers(
        {
            "intent": {"choice": "推销", "confidence": 0.91, "probabilities": {}},
            "emotion": {"choice": "中性", "confidence": 0.68, "probabilities": {}},
            "risk": {"choice": "高危", "confidence": 0.80, "probabilities": {}},
        }
    )
    detailed = format_result(r, "详细")
    assert "意图：推销" in detailed and "风险：高危" in detailed
    simple = format_result(r, "简洁")
    assert "\n" not in simple
    assert "推销" in simple


def test_format_result_on_failure():
    out = format_result({"ok": False}, "详细")
    assert "失败" in out


def test_dry_run_preview():
    r = parse_answers(
        {
            "intent": {"choice": "借钱", "confidence": 1.0, "probabilities": {}},
            "risk": {"choice": "关注", "confidence": 0.9, "probabilities": {}},
        }
    )
    out = dry_run_preview(r, "详细", alerted=True)
    assert "dry run" in out
    assert "命中提醒策略" in out
