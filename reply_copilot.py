"""Jev 意图雷达 · 回复副驾（Reply Copilot）—— 纯逻辑核心模块（不依赖 AstrBot，可离线单测）。

设计要点（吸收对比报告：Jev 当裁判、LLM 出稿、**永不代发**、最小权限）：
  - 触发式：仅 explicit（主人 /reply 指令）或 risk（白名单会话内 Jev 判定命中且置信度达标）；
    默认 trigger_mode=explicit，绝不无差别推送。
  - 费用分层：Jev 判定（便宜）可白名单内常开；LLM 起草（贵）仅在真正触发时调用，
    且两类调用分别计数，互不挤占。
  - 冷却与日限：同会话 cooldown_minutes（默认 10）+ max_drafts_per_day（默认 20），
    并复用 daily_call_limit 总额度。
  - 永不代发：本模块只产出"给主人看的候选文案"，不持有任何发送到原会话的能力；
    投递只允许发往 notify_target（主人会话）。

开发规范依据（AstrBot 插件开发规范）：
  - §7   LLM 调用框架约定（本模块只负责 prompt 构造与产物解析，实际调用在 main.py）
  - §10.4 良好注释与错误处理；纯逻辑可离线单测

作者：YongWei
许可：MIT（见 LICENSE）
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# 1. 风格与 prompt 构造
# ---------------------------------------------------------------------------

# 支持的回复风格（draft_style 配置项）
DEFAULT_STYLES: dict[str, str] = {
    "concise": "简洁直接，一两句话说清，不寒暄不铺垫。",
    "polite": "礼貌得体，给对方面子，语气柔和但立场清晰。",
    "firm": "明确坚定，划清边界，不妥协不失礼。",
}

_VALID_STYLES = set(DEFAULT_STYLES)


def normalize_style(style: Any) -> str:
    """把风格配置归一化为合法风格名；非法值回退 concise（最保守）。"""
    s = str(style or "").strip().lower()
    return s if s in _VALID_STYLES else "concise"


def build_draft_prompt(
    message: str,
    style: str = "concise",
    draft_count: int = 2,
    judge_summary: str | None = None,
) -> str:
    """构造发往 LLM 的起草 prompt。

    只包含脱敏后的消息文本与判定摘要，不夹带任何会话标识。LLM 只产出文案，
    绝不知道也不会要求发送任何内容（永不代发的第一层保障）。
    """
    style = normalize_style(style)
    try:
        n = max(1, min(int(draft_count), 3))
    except (TypeError, ValueError):
        n = 2
    style_desc = DEFAULT_STYLES[style]

    lines = [
        "你是一条消息的回复文案副驾。任务：根据下面的消息，拟几条给消息接收者参考的回复。",
        f"风格要求：{style_desc}",
        f"共拟 {n} 条，措辞各不相同。",
        "",
    ]
    if judge_summary:
        lines.append(f"判定参考（来自意图雷达）：{judge_summary}")
        lines.append("")
    lines += [
        "消息原文：",
        "【开始】",
        message.strip() or "（空消息）",
        "【结束】",
        "",
        "输出格式（严格遵守，不要多余说明）：",
        "1. 草稿：<回复文案>",
        "   理由：<一句话说明为什么这么回>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. LLM 产出解析（宽松解析，缺字段不崩）
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"^\s*[【\[]?(\d+)[】\]\.．、:：]\s*(.*)$")


def parse_drafts(text: str, style: str = "concise") -> list[dict[str, str]]:
    """解析 LLM 输出为候选列表 [{draft, reason, style}]。

    宽松解析：接受编号行 + 后续「理由：」行；解析不到任何草稿时返回空列表。
    """
    style = normalize_style(style)
    drafts: list[dict[str, str]] = []
    cur: dict[str, str] | None = None

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _NUM_RE.match(line)
        if m:
            body = m.group(2).strip()
            # 草稿行：可能带「草稿：」「草稿:」前缀
            head = re.compile(r"^(?:草稿|draft|回复|文案)\s*[:：]\s*", re.IGNORECASE)
            body = head.sub("", body)
            if cur is not None:
                drafts.append(cur)
            cur = {"draft": body, "reason": "", "style": style}
        elif cur is not None:
            rm = re.match(r"^(?:理由|说明|reason)\s*[:：]\s*(.*)$", line, re.IGNORECASE)
            if rm:
                cur["reason"] = rm.group(1).strip()

    if cur is not None and (cur.get("draft") or cur.get("reason")):
        drafts.append(cur)

    # 兜底：整段没按格式时，把全文拆段当作一条草稿
    if not drafts and (text or "").strip():
        drafts = [{"draft": text.strip(), "reason": "", "style": style}]
    return drafts


def format_drafts(
    drafts: list[dict[str, str]],
    judge_summary: str | None = None,
    source: str = "explicit",
) -> str:
    """把候选列表格式化为推送给主人的只读文案。

    尾注会明确标注「仅供参考、未发送到任何会话」，杜绝误用为代发。
    """
    if not drafts:
        return "🧭 回复副驾｜未能解析出候选草稿。"
    lines = ["🧭 回复副驾 · 候选回复"]
    if judge_summary:
        lines.append(f"判定：{judge_summary}")
    for i, d in enumerate(drafts, 1):
        lines.append(f"【选{i}·{d.get('style', 'concise')}】{d.get('draft', '')}")
        if d.get("reason"):
            lines.append(f"　理由：{d['reason']}")
    lines.append("（仅供参考 · 不会发送到任何会话，请自行手动回复）")
    return "\n".join(lines)


def build_judge_summary(result: dict[str, Any] | None) -> str:
    """从 Jev 判定结果生成一句话摘要，用于给 LLM 与主人展示。"""
    if not result or not result.get("ok"):
        return ""
    return (
        f"意图={result.get('intent', '?')}(置信{float(result.get('intent_confidence', 0.0)):.2f})"
        f" 情绪={result.get('emotion', '?')}"
        f" 风险={result.get('risk', '?')}(等级{result.get('risk_level', 0)})"
    )


# ---------------------------------------------------------------------------
# 3. 风险触发判定（risk 模式闸门）
# ---------------------------------------------------------------------------


def should_copilot_trigger(
    result: dict[str, Any],
    risk_alert_threshold: int = 2,
    confidence_threshold: float = 0.6,
    watch_intents: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """risk 模式触发闸门：Jev 判定「关注意图（need_reply 代理）或高风险」且置信度达标。

    返回 (是否触发, 命中原因)。一切异常兜底为不触发（宁可不出，绝不误触发）。
    """
    try:
        if not result.get("ok"):
            return False, []
        if float(result.get("confidence", 0.0)) < float(confidence_threshold):
            return False, []
        reasons: list[str] = []
        if int(result.get("risk_level", 0)) >= int(risk_alert_threshold):
            reasons.append(f"高风险({result.get('risk')})")
        if watch_intents and result.get("intent") in watch_intents:
            reasons.append(f"关注意图({result.get('intent')})")
        return (len(reasons) > 0), reasons
    except Exception:  # noqa: BLE001
        return False, []


def session_in_whitelist(umo: Any, whitelist: list[Any] | None) -> bool:
    """risk 模式仅允许 copilot_whitelist 中的会话（UMO 或群号）。空名单=全部拒绝。"""
    wl = {str(x).strip() for x in (whitelist or []) if str(x).strip()}
    if not wl or umo is None or str(umo).strip() == "":
        return False
    s = str(umo)
    return any(s == w or w in s for w in wl)


# ---------------------------------------------------------------------------
# 4. 费用保护：冷却 + 每日起草上限
# ---------------------------------------------------------------------------


def check_budget(
    last_draft_ts: float | None,
    now: float | None,
    cooldown_minutes: int = 10,
    drafts_today: int = 0,
    max_drafts_per_day: int = 20,
) -> tuple[bool, str]:
    """检查是否允许本次 LLM 起草，返回 (允许, 原因说明)。

    - cooldown_minutes=0 表示同会话无冷却（仅建议显式关闭时）
    - max_drafts_per_day=0 表示每日不限（不建议）
    """
    try:
        lm = max(0, int(cooldown_minutes))
    except (TypeError, ValueError):
        lm = 10
    try:
        mx = int(max_drafts_per_day)
    except (TypeError, ValueError):
        mx = 20

    now = float(now) if now is not None else 0.0
    if last_draft_ts is None:
        pass
    else:
        try:
            elapsed_min = (now - float(last_draft_ts)) / 60.0
            if lm > 0 and elapsed_min < lm:
                wait = lm - elapsed_min
                return False, f"冷却中（同会话还需等待约 {wait:.0f} 分钟，当前 {lm} 分钟/次）"
        except (TypeError, ValueError):
            pass

    if mx > 0 and int(drafts_today) >= mx:
        return False, f"已达今日起草上限（{int(drafts_today)}/{mx}）"
    return True, ""


__all__ = [
    "DEFAULT_STYLES",
    "normalize_style",
    "build_draft_prompt",
    "parse_drafts",
    "format_drafts",
    "build_judge_summary",
    "should_copilot_trigger",
    "session_in_whitelist",
    "check_budget",
]
