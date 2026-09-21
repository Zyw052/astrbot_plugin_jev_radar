"""Jev 意图雷达 —— AstrBot 插件主类。

定位：用 TypeSafe SystemOne（Jev）的 typed decision 能力，把消息判定为
「意图标签 + 情绪 + 风险等级 + 置信度」，仅在低置信 / 高风险 / 关注意图时提醒。

开发规范依据（AstrBot 插件开发规范）：
  - §3.1  文件必须命名 main.py，主类继承 Star，__init__ 收 Context
  - §4.1  新式指令注册 @filter.command("xxx", alias={...})
  - §4.3  事件过滤 @filter.event_message_type(...)
  - §4.4  事件钩子不与 command 混用
  - §5.1  被动回复 yield event.plain_result(...)
  - §6    配置 _conf_schema.json，__init__(self, context, config: AstrBotConfig)
  - §9.2  持久化数据放 data/plugin_data/{plugin_name}/
  - §10.1 日志用 from astrbot.api import logger，禁止 import logging
  - §10.2 网络用 aiohttp（见 jev_client.py）
  - §10.4 良好错误处理，不让插件因单个错误崩溃

作者：YongWei
许可：MIT（见 LICENSE）
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .jev_client import (
    JevAuthError,
    JevClient,
    JevError,
    JevRateLimitError,
    JevTimeoutError,
)
from .radar_core import (
    DEFAULT_WATCH_INTENTS,
    build_questions,
    build_state,
    dry_run_preview,
    format_result,
    message_hash,
    parse_answers,
    should_alert,
)

# 指令别名（§4.1 alias）
_COMMAND_ALIASES = {"雷达", "radar"}

# dry run 触发词（方案 §4.2：/雷达 test <文本> 或 /jev dry <文本>）
_DRY_FLAGS = {"dry", "dryrun", "dry-run", "--dry", "test"}


class JevRadarPlugin(Star):
    """Jev 意图雷达插件主类。"""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._client: JevClient | None = None
        self._client_sig: tuple = ()  # 用于配置变更时重建客户端
        self._lock = asyncio.Lock()
        # 内存态每日计数（KV 持久化兜底），{"date": "YYYY-MM-DD", "count": int}
        self._usage_cache: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 配置与生命周期
    # ------------------------------------------------------------------

    def _cfg(self, key: str, default: Any = None) -> Any:
        """安全读取配置项（Dict 兼容 + 异常兜底）。"""
        try:
            return self.config.get(key, default)
        except Exception:  # noqa: BLE001
            return default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("enable", True))

    @property
    def passive_enabled(self) -> bool:
        return bool(self._cfg("passive_enabled", False))

    async def initialize(self) -> None:
        """插件启用时调用（Star 生命周期）。"""
        logger.info("[Jev雷达] 插件已加载；被动模式=%s", self.passive_enabled)

    async def terminate(self) -> None:
        """插件卸载/停用时调用：释放 HTTP 会话。"""
        if self._client is not None:
            await self._client.close()
            self._client = None
        logger.info("[Jev雷达] 插件已卸载，HTTP 会话已释放。")

    async def _get_client(self) -> JevClient:
        """按当前配置获取（并在必要时重建）HTTP 客户端。"""
        sig = (
            str(self._cfg("base_url", "https://api.typesafe.ai")),
            str(self._cfg("api_key", "")),
            str(self._cfg("model", "jev-latest")),
            int(self._cfg("timeout_sec", 20) or 20),
            int(self._cfg("retries", 1) if self._cfg("retries", 1) is not None else 1),
        )
        if self._client is None or self._client_sig != sig:
            if self._client is not None:
                await self._client.close()
            self._client = JevClient(
                base_url=sig[0],
                api_key=sig[1],
                model=sig[2],
                timeout=sig[3],
                retries=sig[4],
            )
            self._client_sig = sig
        return self._client

    # ------------------------------------------------------------------
    # 费用保护：每日调用计数（KV 优先，内存兜底）
    # ------------------------------------------------------------------

    async def _get_usage(self) -> dict[str, Any]:
        today = date.today().isoformat()
        data: dict[str, Any] = {}
        try:
            data = await self.get_kv_data("daily_usage", {}) or {}
        except Exception:  # noqa: BLE001 - 旧版本无 KV 则退回内存
            data = self._usage_cache
        if not isinstance(data, dict) or data.get("date") != today:
            data = {"date": today, "count": 0}
        self._usage_cache = data
        return data

    async def _incr_usage(self) -> int:
        async with self._lock:
            data = await self._get_usage()
            data["count"] = int(data.get("count", 0)) + 1
            self._usage_cache = data
            try:
                await self.put_kv_data("daily_usage", data)
            except Exception:  # noqa: BLE001
                pass
            return data["count"]

    async def _check_quota(self) -> bool:
        """额度检查：未超限返回 True。"""
        limit = int(self._cfg("daily_call_limit", 2000) or 0)
        if limit <= 0:
            return True
        data = await self._get_usage()
        return int(data.get("count", 0)) < limit

    # ------------------------------------------------------------------
    # 判定核心：调用 Jev → 解析 → 返回统一结果
    # ------------------------------------------------------------------

    async def _analyze(self, text: str) -> dict[str, Any]:
        """对文本执行一次意图判定。返回 parse_answers 结构；失败返回 {"ok": False, "error": ...}。"""
        max_chars = int(self._cfg("max_chars_per_msg", 800) or 800)
        redact = bool(self._cfg("desensitize", True))
        state = build_state(text, max_chars=max_chars, redact=redact)
        questions = build_questions()

        try:
            client = await self._get_client()
            answers, usage = await client.judge(state, questions)
        except JevAuthError as e:
            logger.warning("[Jev雷达] 鉴权失败：%s", e)
            return {"ok": False, "error": "鉴权失败：请检查 API Key 配置（api_key）。"}
        except JevTimeoutError as e:
            logger.warning("[Jev雷达] 超时：%s", e)
            return {"ok": False, "error": "调用超时，请稍后重试。"}
        except JevRateLimitError as e:
            logger.warning("[Jev雷达] 限流：%s", e)
            return {"ok": False, "error": "接口限流/过载，请稍后重试。"}
        except JevError as e:
            logger.error("[Jev雷达] 调用失败：%s", e)
            return {"ok": False, "error": f"调用失败：{e}"}
        except Exception as e:  # noqa: BLE001 - 兜底，绝不让插件崩溃
            logger.error("[Jev雷达] 未预期异常：%s", e)
            return {"ok": False, "error": f"未预期错误：{type(e).__name__}"}

        result = parse_answers(answers)
        result["usage"] = usage
        return result

    # ------------------------------------------------------------------
    # 记录落盘（只落结果 + 消息哈希，不落原文；方案 §6.3）
    # ------------------------------------------------------------------

    def _data_dir(self) -> Path:
        """持久化目录：data/plugin_data/{plugin_name}/（§9.2）。"""
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            base = Path(get_astrbot_data_path())
        except Exception:  # noqa: BLE001
            # 极少数脱离 AstrBot 运行时的场景（如单测导入）：退到系统临时目录，
            # 绝不写入插件自身目录，避免污染仓库与覆盖插件文件。
            import tempfile

            base = Path(tempfile.gettempdir()) / "astrbot_plugin_jev_radar_data"
        name = getattr(self, "name", None) or "astrbot_plugin_jev_radar"
        d = base / "plugin_data" / name
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return d

    def _log_decision(self, result: dict[str, Any], original_text: str) -> None:
        """按配置记录判定日志（仅哈希，不落原文）。"""
        if not bool(self._cfg("log_decisions", False)):
            return
        try:
            record = {
                "hash": message_hash(original_text),
                "intent": result.get("intent"),
                "confidence": result.get("confidence"),
                "emotion": result.get("emotion"),
                "risk": result.get("risk"),
                "risk_level": result.get("risk_level"),
            }
            path = self._data_dir() / "decisions.jsonl"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            logger.debug("[Jev雷达] 写判定日志失败：%s", e)

    # ------------------------------------------------------------------
    # 主动指令
    # ------------------------------------------------------------------

    @filter.command("jev", alias=_COMMAND_ALIASES)
    async def jev_cmd(self, event: AstrMessageEvent):
        """Jev 意图雷达：/jev <文本>，或引用一条消息后 /jev。加 dry 前缀可试运行。"""
        if not self.enabled:
            yield event.plain_result("Jev 意图雷达当前已关闭（enable=false）。")
            return

        raw = (event.message_str or "").strip()
        # 去掉首个 "/" 与指令词，取剩余文本
        body = raw.lstrip("/")
        parts = body.split(maxsplit=1)
        rest = parts[1].strip() if len(parts) > 1 else ""

        # dry run 前缀识别
        dry = False
        if rest:
            head = rest.split(maxsplit=1)
            if head[0].lower() in _DRY_FLAGS:
                dry = True
                rest = head[1].strip() if len(head) > 1 else ""

        text = rest
        if not text:
            text = self._extract_reply_text(event)

        if not text:
            yield event.plain_result(
                "用法：/jev <文本>，或引用一条消息后发送 /jev。\n"
                "试运行：/jev dry <文本>（只回显，不发送、不计额度）。"
            )
            return

        # 额度检查（dry run 也消耗真实调用，故同样计入；如需彻底免费请勿触发）
        if not await self._check_quota():
            limit = int(self._cfg("daily_call_limit", 2000) or 0)
            yield event.plain_result(f"已达今日调用上限（{limit}），为保护费用暂不判定。")
            return

        result = await self._analyze(text)
        if result.get("ok"):
            await self._incr_usage()

        style = str(self._cfg("result_style", "详细"))

        if not result.get("ok"):
            err = result.get("error", "未知错误")
            if dry:
                yield event.plain_result(f"【dry run】调用失败：{err}")
            else:
                yield event.plain_result(f"🎯 Jev 意图雷达\n{err}")
            return

        alerted, reasons = should_alert(
            result,
            confidence_threshold=float(self._cfg("confidence_threshold", 0.75) or 0.75),
            risk_alert_threshold=int(self._cfg("risk_alert_threshold", 2) or 2),
            watch_intents=self._cfg("watch_intents", DEFAULT_WATCH_INTENTS),
        )

        if dry:
            yield event.plain_result(dry_run_preview(result, style=style, alerted=alerted))
            return

        self._log_decision(result, text)
        yield event.plain_result(format_result(result, style=style))

    # ------------------------------------------------------------------
    # 被动模式（默认关闭；仅低置信/高风险/关注意图时提醒）
    # ------------------------------------------------------------------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """被动监听：判定意图，命中提醒策略才推送。默认关闭，避免打扰与耗钱。"""
        try:
            if not self.enabled or not self.passive_enabled:
                return
            # 跳过指令消息（避免与 /jev 重复触发）
            msg = (event.message_str or "").strip()
            if msg.startswith("/") or msg.startswith("／"):
                return
            if msg.startswith(("雷达", "radar")):
                return
            # 跳过机器人自己 / 空消息
            try:
                if event.get_sender_id() == event.get_self_id():
                    return
            except Exception:  # noqa: BLE001
                pass
            if not msg:
                return

            # 范围控制
            group_id = None
            try:
                group_id = event.get_group_id()
            except Exception:  # noqa: BLE001
                group_id = None
            is_private = not group_id
            if is_private and not bool(self._cfg("scope_private", False)):
                return
            if not is_private and not bool(self._cfg("scope_group", True)):
                return

            # 群白名单（空 = 全部群）
            whitelist: list[Any] = list(self._cfg("group_whitelist", []) or [])
            if group_id and whitelist and str(group_id) not in {str(x) for x in whitelist}:
                return

            # 费用保护
            if not await self._check_quota():
                logger.debug("[Jev雷达] 被动判定已达每日上限，跳过。")
                return

            result = await self._analyze(msg)
            if result.get("ok"):
                await self._incr_usage()
            else:
                return

            alerted, reasons = should_alert(
                result,
                confidence_threshold=float(self._cfg("confidence_threshold", 0.75) or 0.75),
                risk_alert_threshold=int(self._cfg("risk_alert_threshold", 2) or 2),
                watch_intents=self._cfg("watch_intents", DEFAULT_WATCH_INTENTS),
            )
            self._log_decision(result, msg)

            if not alerted:
                return  # 静默：只记录，不打扰

            style = str(self._cfg("result_style", "详细"))
            head = "🎯 Jev 意图雷达 · 提醒（" + "、".join(reasons) + "）"
            yield event.plain_result(head + "\n" + format_result(result, style=style))
        except Exception as e:  # noqa: BLE001 - 被动路径绝不能崩
            logger.error("[Jev雷达] 被动处理异常：%s", e)

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_reply_text(event: AstrMessageEvent) -> str:
        """从引用消息中提取纯文本（Reply.message_str；部分适配器可能为空）。"""
        try:
            for comp in event.get_messages():
                if isinstance(comp, Comp.Reply):
                    txt = (getattr(comp, "message_str", "") or "").strip()
                    if txt:
                        return txt
                    chain = getattr(comp, "chain", None)
                    if chain:
                        joined = "".join(getattr(c, "text", "") or "" for c in chain).strip()
                        if joined:
                            return joined
        except Exception as e:  # noqa: BLE001
            logger.debug("[Jev雷达] 提取引用文本失败：%s", e)
        return ""
