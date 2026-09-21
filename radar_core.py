"""Jev 意图雷达 —— 纯逻辑核心模块（不依赖 AstrBot，可离线单测）。

本模块承载「与框架无关」的业务逻辑，便于单元测试：
  - 脱敏 / 截断（依据 §方案-§6 隐私合规）
  - Jev 问题定义（依据 TypeSafe SystemOne 请求体三段式 state/model/questions）
  - 响应解析（依据实测报告 answers.<q>.{choice,probabilities,confidence}）
  - 提醒策略判定（低置信 / 高风险 / 关注意图）
  - 结果格式化（简洁 / 详细）

开发规范依据（AstrBot 插件开发规范）
  - §10.4 工程原则：功能需经测试、良好注释、良好错误处理
  - §10.2 网络请求禁用 requests（本模块不含网络，网络见 jev_client.py）

作者：YongWei
许可：MIT（见 LICENSE）
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# ---------------------------------------------------------------------------
# 1. 默认标签体系（criteria）
# ---------------------------------------------------------------------------

# 意图分类：choice（多选一），命中即返回单一标签 + 全概率分布
DEFAULT_INTENT_CRITERIA: dict[str, str] = {
    "中性信息": "纯粹陈述事实或日常信息交流，无下列特殊意图。",
    "真心感谢": "发自内心地表达谢意。",
    "客套敷衍": "表面应付、礼貌性回应，但无实质诚意。",
    "暗讽": "用反话或含蓄方式表达讽刺、不满或优越感。",
    "挖坑试探": "表面普通寒暄，实则设套套话或试探对方底细。",
    "推销": "推销产品或服务，引导对方购买。",
    "引战": "刻意挑起争吵、对立或群体冲突。",
    "诈骗": "以欺诈为目的骗取财物或信息。",
    "拉人": "拉人入群、引流、发展下线或拉票。",
    "借钱": "请求借贷金钱。",
    "借口": "编造理由掩饰真实原因（可能撒谎）。",
    "情绪勒索": "以情绪或道德压力迫使对方就范。",
}

# 情绪倾向：choice，用于给人看的情绪标签
DEFAULT_EMOTION_CRITERIA: dict[str, str] = {
    "正面": "表达愉悦、赞同、感谢等积极情绪。",
    "中性": "情绪平淡，无显著倾向。",
    "负面": "表达不满、失望、抱怨等消极情绪。",
    "愤怒": "明显的愤怒、敌意或强烈对抗情绪。",
    "焦虑": "表达着急、担忧、不安或催促。",
}

# 风险等级：choice，映射为 0/1/2 数值用于阈值比较
DEFAULT_RISK_CRITERIA: dict[str, str] = {
    "安全": "正常交流，无明显风险。",
    "关注": "存在可疑倾向，建议留意但不必立即处理。",
    "高危": "明显涉及诈骗、引战、骚扰、违规推广等，建议人工介入。",
}

# 风险标签 → 数值等级
RISK_LEVEL: dict[str, int] = {"安全": 0, "关注": 1, "高危": 2}

# 默认「关注意图」：命中即提醒（与方案 §4.1 一致）
DEFAULT_WATCH_INTENTS: list[str] = ["推销", "引战", "诈骗", "拉人"]


# ---------------------------------------------------------------------------
# 2. 脱敏与截断（隐私合规，方案 §6）
# ---------------------------------------------------------------------------

# 常见敏感信息的正则（顺序敏感：先长后短，避免身份证被手机号规则切碎）
_REDACT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("[邮箱]", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("[身份证]", re.compile(r"\b\d{17}[\dXx]\b")),
    ("[银行卡]", re.compile(r"\b\d{16,19}\b")),
    ("[手机号]", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("[长数字]", re.compile(r"(?<!\d)\d{11,}(?!\d)")),
]


def desensitize(text: str) -> str:
    """本地脱敏：替换手机号 / 邮箱 / 身份证 / 银行卡 / 超长数字串。

    依据方案 §6「本地脱敏策略（默认开）」。任何异常都吞掉并返回原文，
    保证脱敏失败不阻断主流程（§10.4 良好错误处理）。
    """
    if not text:
        return text or ""
    try:
        for placeholder, pattern in _REDACT_PATTERNS:
            text = pattern.sub(placeholder, text)
    except Exception:  # noqa: BLE001 - 脱敏失败绝不能崩
        return text
    return text


def trim_text(text: str, max_chars: int) -> str:
    """超长裁剪（方案 §6 max_chars_per_msg），避免把超长文本整段发往第三方。"""
    text = text or ""
    if max_chars and max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + "…[已截断]"
    return text


def build_state(text: str, max_chars: int = 800, redact: bool = True) -> str:
    """构造发往 Jev 的 state 字段：先裁剪、再按需脱敏。"""
    text = trim_text(text, max_chars)
    if redact:
        text = desensitize(text)
    return text


def message_hash(text: str) -> str:
    """消息指纹（BLAKE2），用于「只落结果不落原文」的记录方式（方案 §6.3）。"""
    return hashlib.blake2b((text or "").encode("utf-8"), digest_size=8).hexdigest()


# ---------------------------------------------------------------------------
# 3. 请求体构造（依据 TypeSafe SystemOne 三段式规格）
# ---------------------------------------------------------------------------


def build_questions(
    intent_criteria: dict[str, str] | None = None,
    emotion_criteria: dict[str, str] | None = None,
    risk_criteria: dict[str, str] | None = None,
) -> dict[str, Any]:
    """构造 questions 段：三个 choice 问题（意图 / 情绪 / 风险）。

    选用 `choice` 原语的理由（诚实说明）：实测报告「存疑③」指出 `score`
    原语的返回字段结构未经真实验证，为避免解析不确定性，本插件统一使用
    字段已确证的 `choice`（返回 choice / probabilities / confidence）。
    """
    return {
        "intent": {
            "type": "choice",
            "instructions": "根据上下文，判断【最后一条消息】发送者的真实意图，只从 criteria 中选一项。",
            "criteria": intent_criteria or DEFAULT_INTENT_CRITERIA,
        },
        "emotion": {
            "type": "choice",
            "instructions": "判断【最后一条消息】发送者当前主导的情绪倾向，只从 criteria 中选一项。",
            "criteria": emotion_criteria or DEFAULT_EMOTION_CRITERIA,
        },
        "risk": {
            "type": "choice",
            "instructions": "评估【最后一条消息】的风险等级（诈骗/引战/骚扰/违规推广等），只从 criteria 中选一项。",
            "criteria": risk_criteria or DEFAULT_RISK_CRITERIA,
        },
    }


# ---------------------------------------------------------------------------
# 4. 响应解析（依据实测 answers.<q>.{choice,probabilities,confidence}）
# ---------------------------------------------------------------------------


def parse_answers(answers: dict[str, Any] | None) -> dict[str, Any]:
    """把 Jev 原始 answers 解析为统一结构。

    返回形如::

        {
          "intent": "推销", "intent_confidence": 0.91, "intent_probabilities": {...},
          "emotion": "负面", "emotion_confidence": 0.68,
          "risk": "高危", "risk_confidence": 0.80, "risk_level": 2,
          "confidence": 0.91,          # 顶层置信度 = 意图置信度
          "ok": True,
        }

    任何缺失 / 异常字段都做兜底，不抛异常（§10.4）。
    """
    answers = answers or {}

    def _pick(key: str) -> tuple[str, float, dict[str, float]]:
        node = answers.get(key) or {}
        if not isinstance(node, dict):
            return "", 0.0, {}
        choice = node.get("choice") or ""
        try:
            conf = float(node.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        probs = node.get("probabilities") or {}
        if not isinstance(probs, dict):
            probs = {}
        return str(choice), conf, probs

    intent, intent_conf, intent_probs = _pick("intent")
    emotion, emotion_conf, _ = _pick("emotion")
    risk, risk_conf, _ = _pick("risk")

    return {
        "ok": bool(intent),
        "intent": intent,
        "intent_confidence": intent_conf,
        "intent_probabilities": intent_probs,
        "emotion": emotion,
        "emotion_confidence": emotion_conf,
        "risk": risk,
        "risk_confidence": risk_conf,
        "risk_level": RISK_LEVEL.get(risk, 0),
        # 顶层 confidence 采用意图置信度（意图是主判定维度）
        "confidence": intent_conf,
    }


# ---------------------------------------------------------------------------
# 5. 提醒策略（方案 §4.1：仅低置信 / 高风险 / 关注意图才提醒）
# ---------------------------------------------------------------------------


def should_alert(
    result: dict[str, Any],
    confidence_threshold: float = 0.75,
    risk_alert_threshold: int = 2,
    watch_intents: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """判断是否应发出提醒，返回 (是否提醒, 命中的原因列表)。"""
    reasons: list[str] = []
    try:
        if not result.get("ok"):
            # 判定失败不算「需要打扰」，交由调用方决定是否记日志
            return False, reasons

        if result.get("confidence", 0.0) < float(confidence_threshold):
            reasons.append(f"低置信({result.get('confidence', 0.0):.2f}<{confidence_threshold})")

        if int(result.get("risk_level", 0)) >= int(risk_alert_threshold):
            reasons.append(f"高风险({result.get('risk')}≥阈值{risk_alert_threshold})")

        if watch_intents and result.get("intent") in watch_intents:
            reasons.append(f"关注意图({result.get('intent')})")
    except Exception:  # noqa: BLE001
        return False, reasons
    return (len(reasons) > 0), reasons


# ---------------------------------------------------------------------------
# 6. 结果格式化（方案 §4.5）
# ---------------------------------------------------------------------------


def format_result(result: dict[str, Any], style: str = "详细") -> str:
    """把解析结果格式化为可发送文本。style: 详细 / 简洁。"""
    if not result.get("ok"):
        return "🎯 Jev 意图雷达\n判定失败：未能从响应中解析出有效意图。"

    intent = result.get("intent") or "未知"
    iconf = result.get("intent_confidence", 0.0)
    emotion = result.get("emotion") or "未知"
    econf = result.get("emotion_confidence", 0.0)
    risk = result.get("risk") or "未知"
    rconf = result.get("risk_confidence", 0.0)
    level = int(result.get("risk_level", 0))

    risk_mark = {0: "✅", 1: "👀", 2: "⚠️"}.get(level, "")

    if style == "简洁":
        return f"🎯 Jev｜意图 {intent}({iconf:.2f})｜情绪 {emotion}｜风险 {risk}{risk_mark}"

    lines = [
        "🎯 Jev 意图雷达",
        f"意图：{intent}（置信 {iconf:.2f}）",
        f"情绪：{emotion}（{econf:.2f}）",
        f"风险：{risk} {risk_mark}（{rconf:.2f}）",
    ]
    if iconf < 0.75:
        lines.append("—— 存疑 · 建议人工复核")
    return "\n".join(lines)


def dry_run_preview(result: dict[str, Any], style: str = "详细", alerted: bool = False) -> str:
    """dry run 预览：只回显「将会发送的内容」，不发真消息、不写记录、不计额度。"""
    body = format_result(result, style)
    flag = "（命中提醒策略，正常模式会推送）" if alerted else "（未命中提醒策略，正常模式会静默）"
    return f"【dry run · 仅回显】\n{body}\n{flag}"


__all__ = [
    "DEFAULT_INTENT_CRITERIA",
    "DEFAULT_EMOTION_CRITERIA",
    "DEFAULT_RISK_CRITERIA",
    "DEFAULT_WATCH_INTENTS",
    "RISK_LEVEL",
    "desensitize",
    "trim_text",
    "build_state",
    "message_hash",
    "build_questions",
    "parse_answers",
    "should_alert",
    "format_result",
    "dry_run_preview",
]
