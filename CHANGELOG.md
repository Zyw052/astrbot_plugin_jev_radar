# 更新日志 · Changelog

本文件记录 `astrbot_plugin_jev_radar`（Jev 意图雷达）的版本变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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

[1.0.1]: https://github.com/Zyw052/astrbot_plugin_jev_radar/releases/tag/v1.0.1
[1.0.0]: https://github.com/Zyw052/astrbot_plugin_jev_radar/releases/tag/v1.0.0
