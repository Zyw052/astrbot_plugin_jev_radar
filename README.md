# Jev 意图雷达 · astrbot_plugin_jev_radar

**中文** | [English](README.en.md) | [日本語](README.ja.md)

<p align="center">
  <img src="assets/logo.png" alt="Jev 意图雷达 Logo" width="180" height="180">
</p>

> **帮你看懂消息背后的意图。**

- 作者：**YongWei**
- 许可：**MIT**（见 [LICENSE](LICENSE)）
- 当前版本：**1.2.0**（完整变更见 [CHANGELOG.md](CHANGELOG.md)）

---

## ⚠️ 隐私与合规（务必先读）

1. **消息内容会发送至第三方**：启用后，被判定消息的**文本**会通过 HTTPS 发送至 **TypeSafe AI**（`api.typesafe.ai`）进行意图判定。启用前请自行评估数据敏感度。
2. **数据出境提示**：TypeSafe 为境外服务，请遵守所在地的数据合规要求。
3. **本地脱敏（默认开启）**：发送前会本地替换手机号 / 邮箱 / 身份证 / 银行卡 / 超长数字串为占位符，并对超长文本截断（`max_chars_per_msg`）。
4. **不落原文**：默认只记录「判定结果 + 消息哈希」，绝不保存原始消息文本；`log_decisions` 默认关闭。
5. **可退出**：`enable=false` 即完全停用（不监听、不调用、不提醒）；`scope_group` / `scope_private` / `group_whitelist` 可精确控制生效范围。
6. **密钥安全**：`api_key` 仅保存在本机 `data/config/` 下，**不硬编码、不入库、不随仓库分发**，请勿泄露。
7. **回复副驾额外披露**：启用副驾后，脱敏后的消息文本会①随判定发往 TypeSafe、②在起草时发往宿主 AstrBot 配置的 LLM Provider；副驾候选回复**只推送给主人**，永不向原会话发送。

---

## ① 插件简介与定位

用 [TypeSafe SystemOne（Jev）](https://typesafe.ai) 的 typed decision 能力，把群聊 / 私聊消息实时判定为
**「意图标签 + 情绪倾向 + 风险等级 + 置信度」**。插件默认**极其克制**：只在低置信度或高风险时提醒，绝不刷屏。

> 一句话：**AstrBot 有了官方的 Jev「闸门」，我们做了 Jev 的「眼睛」。**
> 官方 `reply_gate` 决定「Bot 要不要回」；本插件输出「**人怎么理解这条消息**」。二者定位不同，可共存。

- **被动模式**（默认关闭）：自动监听消息，仅在高风险/低置信/命中关注意图时提醒。
- **主动模式**：`/jev` 按需判定，`/jev dry` 试运行预览。
- **回复副驾**（默认关闭）：Jev 当裁判、宿主 LLM 出稿，为主人起草候选回复，永不代发。

---

## ② 安装

1. 将本插件目录放入 AstrBot 的 **`data/plugins/`** 下（目录名 `astrbot_plugin_jev_radar`）。
2. 依赖为 **`aiohttp>=3.9`**（见 `requirements.txt`），AstrBot 安装插件时会自动安装；如未安装可 `pip install aiohttp>=3.9`。
3. 在 WebUI「插件管理」中**启用 / 重载**插件。
4. 在插件配置中填入 **TypeSafe API Key**（在 <https://console.typesafe.ai> 获取）。
5. （可选）开启被动模式 `passive_enabled=true`。

> Jev 仅支持**文本**判定，不支持图片 / 音频 / 视频。

---

## ③ 配置项逐条说明

对照 `_conf_schema.json`（27 项）。「**作用**」解释该项影响什么，「建议值」为一般推荐。

| 配置项 | 类型 | 默认值 | 作用 | 建议值 |
|---|---|---|---|---|
| `enable` | bool | `true` | 总开关；关闭后插件完全停用，不监听、不调用、不提醒 | 保持默认 |
| `api_key` | string | `""` | TypeSafe API Key，仅存本机；**留空则无法调用** | 必填 |
| `base_url` | string | `https://api.typesafe.ai` | 接口地址，实际请求 `POST {base_url}/v1/systemone` | 保持默认 |
| `model` | string | `jev-latest` | Jev 模型名（另有 `jev-preview`） | `jev-latest` |
| `timeout_sec` | int | `20` | 单次请求超时秒数；网络不佳可调大 | 20~30 |
| `retries` | int | `1` | 仅对 429 / 503 / 529（限流/过载）重试；其它错误不重试 | 1 |
| `confidence_threshold` | float | `0.75` | 意图置信度低于此值时标为「存疑」，被动模式且触发提醒 | 0.75 |
| `risk_alert_threshold` | int | `2` | 风险等级 0=安全 / 1=关注 / 2=高危；达到即触发提醒 | 1（更敏感）或 2 |
| `daily_call_limit` | int | `2000` | 每日最多调用次数，0=不限；费用保护兜底 | 2000 |
| `passive_enabled` | bool | `false` | 被动模式总开关（默认关闭，避免打扰与费用） | 需要自动监听才开 |
| `scope_group` | bool | `true` | 被动模式是否处理群聊消息 | 保持默认 |
| `scope_private` | bool | `false` | 被动模式是否处理私聊消息 | 保持默认 |
| `group_whitelist` | list | `[]` | 被动模式群白名单；**填入群号，留空=所有群生效** | 群多时建议填白名单收敛范围 |
| `watch_intents` | list | `["推销","引战","诈骗","拉人"]` | 「关注意图」清单，被动模式下命中即提醒（即使置信度高） | 按需增删 |
| `desensitize` | bool | `true` | 发送前本地脱敏（手机号/邮箱/证件/银行卡/超长数字） | **务必开启** |
| `max_chars_per_msg` | int | `800` | 超长文本截断后再发送（控费 + 降敏感） | 800 |
| `result_style` | string | `详细` | 结果样式：`详细`=多行含置信度；`简洁`=单行摘要 | 按喜好 |
| `log_decisions` | bool | `false` | 将判定结果写入本地 `decisions.jsonl`（仅含消息哈希，**不含原文**）；开启后 `/jev_stats` 才有历史统计 | 想看统计再开 |
| `reply_copilot_enabled` | bool | `false` | 回复副驾总开关，默认关闭；开启后仍仅按 `trigger_mode` 触发 | 需要时再开 |
| `trigger_mode` | string | `explicit` | `explicit`=仅主人 `/reply` 触发（最保守）；`risk`=仅白名单会话内、Jev 判定关注意图/高风险且置信度达标时起草并推主人 | 建议 `explicit` |
| `draft_count` | int | `3` | 每次起草生成候选回复条数（2~3） | 3 |
| `draft_style` | string | `concise` | `concise`=简洁直接 / `polite`=礼貌得体 / `firm`=明确坚定 | 按需 |
| `cooldown_minutes` | int | `10` | risk 模式下同会话两次 LLM 起草最短间隔，0=不冷却（不建议）；费用保护 | 10 |
| `max_drafts_per_day` | int | `20` | 每日 LLM 起草上限（0=不限）；注意 Jev 判定**不占**此额度，单独计数 | 20 |
| `notify_target` | string | `""` | risk 模式下候选回复**只推送**到主人的会话标识（UMO，如 `aiocqhttp:FriendMessage:xxxx`）；留空则 risk 模式只记录不推送 | 用 risk 模式必填 |
| `copilot_whitelist` | list | `[]` | risk 模式仅在这些会话内生效（UMO 或群号）；**留空 = risk 模式完全不触发**（最保守） | 用 risk 模式必填 |
| `llm_provider_id` | string | `""` | 起草用 LLM Provider；留空=使用主人当前会话的默认 Provider | 保持默认 |

---

## ④ 命令手册

### `/jev` — 手动判定
- **用途**：判定一段文本的「意图 / 情绪 / 风险 / 置信度」。
- **参数**：`dry`（可选，试运行）+ 待判定文本；或**引用一条消息**后不带参数发送 `/jev`（判定被引用消息）。
- **示例**：
  ```
  /jev 姐，我们这款面膜纯天然成分，今天最后一天，前50名下单送面膜仪！
  ```
  输出：
  ```
  🎯 Jev 意图雷达
  意图：推销（置信 1.00）
  情绪：中性（0.90）
  风险：高危 ⚠️（0.95）
  ```
- **`dry` 试运行**：`/jev dry 兄弟在吗？先借我五千，下个月还你。` 只回显「将要发送的内容」，不发送、不写记录（**仍消耗一次真实判定调用**）。别名 `/jev test`。
- `/jev stats` 会提示请在用 `/jev_stats`。

### `/jev_stats` — 判定统计（别名：`雷达统计` / `radar_stats`）
- **用途**：查看**今日判定调用额度**（含副驾起草额度使用）、**历史判定记录总数**、**意图分布 Top5** 与**风险分布**（v1.2.0 新增）。
- **参数**：无。
- **示例**：`/jev_stats`
- 注意：`log_decisions` 未开启时没有历史分布数据，命令会给出开启提示（今日额度仍可见）。

### `/reply` — 回复副驾起草
- **用途**：让宿主 LLM 按当前上下文起草 2~3 条候选回复（各附一句「为什么这么回」），供主人参考，**绝不代发到任何会话**。
- **参数**：可选文本；或**引用一条消息**后发送 `/reply`（按该消息起草）。
- **示例**：
  ```
  /reply 对方又来催发货了，语气很冲
  ```
- 前提：`reply_copilot_enabled=true`（默认关闭）。`risk` 模式下无需手动发 `/reply`，由白名单会话内的判定自动触发并推送到 `notify_target`。

---

## ⑤ 被动监听机制

- 实现方式：AstrBot `@filter.event_message_type(EventMessageType.ALL)`，监听全部消息后经 `on_llm_request` 钩子按需判定。
- **默认关闭**（`passive_enabled=false`）：避免打扰群聊、避免产生非预期 API 费用。
- **开启方式**：在插件配置中把 `passive_enabled` 设为 `true` 并重载插件。
- **生效范围**：`scope_group`（群聊，默认开）+ `scope_private`（私聊，默认关）+ `group_whitelist`（群白名单，空=全部群）共同决定；三者取交集。
- **提醒条件（三者任一才提醒，其余静默）**：
  1. 意图置信度 `< confidence_threshold`（标为「存疑」）；
  2. 风险等级 `>= risk_alert_threshold`；
  3. 命中 `watch_intents` 关注意图（即使置信度高）。
- **注意事项**：①开启即产生持续费用，请配合 `daily_call_limit`；②建议先开 `dry` 试运行或仅开群白名单小范围验证；③被动提醒只推主人会话，不在原会话刷屏。

---

## ⑥ KV 配额与统计

- **额度持久化**：今日判定调用数（`daily_usage`）与副驾起草数（`reply_draft_usage`）持久化于 AstrBot KV 存储（`data/plugin_data/`），跨重启累计。
- **两类额度分开计数**：Jev 判定（便宜）计入 `daily_call_limit`；LLM 起草（贵）计入 `max_drafts_per_day`，互不挤占。
- **读写失败告警**（v1.2.0）：KV **读写失败时输出警告日志**并临时退回内存计数（重启后该日额度会重置），不再静默丢失、便于排查。
- **`/jev_stats` 展示内容**：今日判定调用 X / 上限 Y；今日副驾起草 A / 上限 B；历史判定记录总数；意图分布 Top5；风险分布。历史分布需 `log_decisions=true`。

---

## ⑦ FAQ

1. **装好了不触发 / 没反应？** 依次检查：`api_key` 是否已填 → `enable` 是否为 true → 被动模式需 `passive_enabled=true` 且 `scope_group`/`scope_private` 至少开启一个、群号是否在 `group_whitelist`；主动判定可直接试 `/jev 你好` 验证连通。
2. **为什么没有任何提醒？** 设计如此：被动模式只在低置信 / 高风险 / 命中关注意图时提醒，普通闲聊静默。若想更敏感，可将 `risk_alert_threshold` 降为 1、`confidence_threshold` 调高。
3. **如何控制额度 / 费用？** `daily_call_limit`（默认 2000）兜底判定；`max_drafts_per_day`（默认 20）与 `cooldown_minutes`（默认 10）限制 LLM 起草；用量在 `/jev_stats` 随时查看；被动模式默认关闭防止意外花费。TypeSafe 仅按 input token 计费（约 $0.042/Mtok），单条判定成本广泛远低于一分钱，具体价格以官方文档为准。
4. **日志 / 记录在哪里？** 插件运行日志在 AstrBot 控制台；判定记录（仅结果与消息哈希，无原文）在开启 `log_decisions` 后写入 `data/plugin_data/` 下的 `decisions.jsonl`；KV 额度读写失败会在日志中输出警告。
5. **如何完全关闭 / 卸载？** 完全停用：配置中 `enable=false`（不监听、不调用、不提醒）；卸载：WebUI 插件管理中卸载并删除 `data/plugins/astrbot_plugin_jev_radar` 目录。被动的所有监听均随开关即时停止。
6. **`/reply` 报「起草失败」？** 说明 LLM Provider 调用失败（超时 / 未配置 / 额度用尽），命令会回显错误摘要且不影响其它功能；可检查宿主 LLM Provider 或 `llm_provider_id`。
7. **支持图片 / 语音判定吗？** 不支持，Jev 仅判定文本；图片 / 音频 / 视频消息会被忽略或按无文本处理。

---

## ⑧ 隐私与合规建议

- 消息文本（脱敏后）发往 TypeSafe（境外）参与判定；启用副驾后另发往宿主 LLM。**不会**上传至本插件作者的任何服务器，作者不收集任何数据。
- 建议保持 `desensitize=true`、`max_chars_per_msg=800`、`log_decisions=false`（如非统计需要），并在群白名单内限定被动模式范围。
- 请依照当地数据保护法规（如个人信息出境规定）评估使用场景。

---

## ⑨ 版本与更新日志

- **v1.2.0（2026-09-23）** — 新增 `/jev_stats` 判定统计；KV 额度持久化读写失败改为记录警告日志（不再静默丢失）。
- **v1.1.0（2026-09-22）** — 新增回复副驾 Reply Copilot（explicit/risk 触发、只推主人、永不代发、费用分层三重闸门）。
- **v1.0.0（2026-09-21）** — 首发：被动监听 + 主动 `/jev` 判定、`/jev dry` 试运行、费用保护、本地脱敏。

完整变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## ⑩ 许可

[MIT](LICENSE) © 2026 **YongWei**
