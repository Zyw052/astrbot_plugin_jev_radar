# 更新日志 · Changelog

本文件记录 `astrbot_plugin_jev_radar`（Jev 意图雷达）的版本变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2026-09-22

### 新增 Added
- **回复副驾（Reply Copilot）**：新模块，Jev 当裁判、宿主 LLM 出稿，为需要回复的消息起草 2~3 条候选回复（各附一句“为什么这么回”）；风格可配（`concise` / `polite` / `firm`）。
- **触发式设计 · 绝不无差别推送**：
  - `explicit`（默认）：只有主人主动发送 `/reply`（可引用消息）才起草；
  - `risk`：仅 `copilot_whitelist` 白名单会话内，且 Jev 判定「关注意图 / 高风险」**且** 置信度达标时才起草；
  - 总开关 `reply_copilot_enabled` **默认关闭**，从配置层面杜绝任何全量自动推送。
- **费用分层保护**：Jev 判定（便宜）与 LLM 起草（贵）**分开计数**；LLM 起草仅在触发时调用，并受 `cooldown_minutes`（同会话冷却，默认 10）+ `max_drafts_per_day`（默认 20）+ 既有 `daily_call_limit` 三重闸门保护。
- **只推主人，永不代发**：候选回复只投递给 `notify_target`（主人会话）；代码层面不存在任何向原消息会话发送草稿的路径；风险触发在原会话**零感知**。

### 说明 Notes
- 起草调用 AstrBot 内部 LLM Provider（新式 `llm_generate`，v4.5.7+）；失败时透明降级为“起草失败 + 错误摘要”，不影响原功能。
- 隐私：担任副驾时，脱敏后的消息文本会发往宿主 LLM；Jev 判定依旧走 TypeSafe（详见 README 隐私声明）。
- 兼容性：1.0.x 全部功能与配置不变，历史 38 项单测保留并通过。

## [1.0.1] - 2026-09-21

### 新增 Added
- 补充 **文档 / 更新日志**（CHANGELOG.md），记录版本变更历史。
- **README 增补**：完善使用说明与更新日志章节、隐私声明。

### 说明 Notes
- 本版本为 **市场同步准备发版**：以正式 tag + GitHub Release 形式对外发布，便于 AstrBot 插件市场与网页端抓取「更新日志」。
- 功能与 1.0.0 一致，无破坏性变更。

## [1.0.0] - 2026-09-21

### 新增 Added
- **被动模式**：自动监听群聊 / 私聊消息，基于 TypeSafe SystemOne（Jev）typed decision 判定「意图标签 + 情绪倾向 + 风险等级 + 置信度」；仅在「低置信 / 高风险 / 关注意图」时提醒，默认关闭，绝不刷屏。
- **主动模式**：`/jev <文本>` 或引用一条消息后发送 `/jev`，即时输出意图 + 情绪 + 风险 + 置信度。
- **试运行**：`/jev dry <文本>` 只回显将要发送的内容，便于调试与费用评估。
- **费用保护**：支持每日调用上限（`daily_call_limit`）、群白名单、范围开关。
- **隐私合规**：本地脱敏（手机号 / 邮箱 / 身份证 / 银行卡）；默认只记录判定结果与消息哈希，不落原文。

### 说明 Notes
- 依赖上游模型 **`jev-latest`**（TypeSafe SystemOne，`api.typesafe.ai`）。
- 被判定消息文本会发送至第三方 TypeSafe AI 进行判定，请自行评估数据敏感度与合规要求（详见 README 隐私声明）。
- 灵感来源：TypeSafe SystemOne / Jev（<https://typesafe.ai>），本插件为独立实现。

### 许可 License
- MIT © 2026 **YongWei**

[1.1.0]: https://github.com/Zyw052/astrbot_plugin_jev_radar/releases/tag/v1.1.0
[1.0.1]: https://github.com/Zyw052/astrbot_plugin_jev_radar/releases/tag/v1.0.1
[1.0.0]: https://github.com/Zyw052/astrbot_plugin_jev_radar/releases/tag/v1.0.0
