# Jev 意图雷达 · astrbot_plugin_jev_radar

<p align="center">
  <img src="assets/logo.png" alt="Jev 意图雷达 Logo" width="180" height="180">
</p>

> **帮你看懂消息背后的意图。**

用 [TypeSafe SystemOne（Jev）](https://typesafe.ai) 的 typed decision 能力，把群聊 / 私聊消息实时判定为
**「意图标签 + 情绪倾向 + 风险等级 + 置信度」**，只在**低置信度或高风险**时提醒，绝不刷屏。

> 一句话：**AstrBot 有了官方的 Jev「闸门」，我们做了 Jev 的「眼睛」。**
> 官方 `reply_gate` 决定「Bot 要不要回」，本插件输出「**人怎么理解这条消息**」。二者定位不同，可共存。

- 作者：**YongWei**
- 许可：**MIT**（见 [LICENSE](LICENSE)）
- 版本：1.2.0

---

## ⚠️ 隐私声明（务必先读）

1. **消息内容会发送至第三方**：启用后，被判定消息的**文本**会通过 HTTPS 发送至 **TypeSafe AI**（`api.typesafe.ai`）进行判定。启用前请自行评估数据敏感度。
2. **数据出境提示**：TypeSafe 为境外服务，请遵守所在地的数据合规要求。
3. **本地脱敏（默认开启）**：发送前会本地替换手机号 / 邮箱 / 身份证 / 银行卡 / 超长数字串，并对超长文本截断。
4. **不落原文**：默认只记录「判定结果 + 消息哈希」，不保存原始消息文本；`log_decisions` 默认关闭。
5. **可退出**：`enable=false` 即完全停用；`scope_group` / `scope_private` / `group_whitelist` 可精确控制生效范围。
6. **密钥安全**：`api_key` 仅保存在本机 `data/config/` 下，**不硬编码、不入库、不随仓库分发**。
7. **回复副驾（v1.1.0）额外披露**：启用副驾后，脱敏后的消息文本会①随判定发往 TypeSafe、②在起草时发往宿主 AstrBot 配置的 LLM Provider；副驾候选回复**只推送给主人**，永不向原会话发送。

---

## ✨ 功能

### 被动模式（默认关闭）
自动监听消息并判定意图。**仅当命中以下任一条件才提醒**，其余情况静默记录：
- 意图置信度 `< confidence_threshold`（默认 0.75）
- 风险等级 `>= risk_alert_threshold`（默认 2 = 高危）
- 命中「关注意图」白名单（默认：推销 / 引战 / 诈骗 / 拉人）

> 默认关闭的原因：避免打扰群聊、避免产生不必要的 API 费用。

### 主动模式
- `/jev <文本>` — 判定一段文本
- 引用一条消息后发送 `/jev` — 判定被引用的消息
- `/jev dry <文本>` 或 `/jev test <文本>` — **试运行**，只回显「将要发送的内容」，不发送、不写记录（仍消耗一次真实判定调用）
- `/jev_stats`（别名：`雷达统计`）— 查看今日额度使用与历史判定意图/风险分布（v1.2.0）

### 其他控制
- 群白名单 `group_whitelist`、群/私聊范围开关
- 每日调用上限 `daily_call_limit`（费用保护）

### 回复副驾（v1.1.0，默认关闭）
Jev 当裁判、宿主 LLM 出稿：对需要回复的消息起草 2~3 条候选回复（各附一句“为什么这么回”），**只推给主人参考，永不代发到任何会话**。
- `/reply <文本>` 或引用一条消息后发 `/reply` — 立即起草（explicit 触发，默认模式）；
- `risk` 触发模式：仅白名单会话内，Jev 判定「关注意图 / 高风险」且置信度达标时起草并推主人，原会话零感知；
- 费用分层：Jev 判定与 LLM 起草分开计数，起草受冷却 + 每日起草上限 + 总额度三重闸门；
- 失败降级：LLM 不可用 / Jev 超时 → 提示“起草失败”并带错误摘要，不崩、不刷屏。

---

## 📦 安装

1. 将本插件目录放入 AstrBot 的 `data/plugins/` 下（目录名 `astrbot_plugin_jev_radar`）。
2. 在 WebUI「插件管理」中重载插件。
3. 在插件配置中填入 **TypeSafe API Key**（在 <https://console.typesafe.ai> 获取）。
4. （可选）开启被动模式。

依赖：`aiohttp`（见 `requirements.txt`）。

---

## ⚙️ 配置表

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enable` | bool | `true` | 总开关 |
| `api_key` | string | `""` | TypeSafe API Key（仅存本机） |
| `base_url` | string | `https://api.typesafe.ai` | 接口地址（请求 `POST {base_url}/v1/systemone`） |
| `model` | string | `jev-latest` | Jev 模型名 |
| `timeout_sec` | int | `20` | 请求超时（秒） |
| `retries` | int | `1` | 429/503/529 重试次数 |
| `confidence_threshold` | float | `0.75` | 低于此置信度标记「存疑」 |
| `risk_alert_threshold` | int | `2` | 风险提醒阈值（0 安全 / 1 关注 / 2 高危） |
| `daily_call_limit` | int | `2000` | 每日调用上限（0=不限） |
| `passive_enabled` | bool | `false` | 被动模式开关 |
| `scope_group` | bool | `true` | 被动模式作用于群聊 |
| `scope_private` | bool | `false` | 被动模式作用于私聊 |
| `group_whitelist` | list | `[]` | 群白名单（空=全部群） |
| `watch_intents` | list | `["推销","引战","诈骗","拉人"]` | 命中即提醒的意图 |
| `desensitize` | bool | `true` | 发送前本地脱敏 |
| `max_chars_per_msg` | int | `800` | 单条消息裁剪长度 |
| `result_style` | string | `详细` | 结果样式：`详细` / `简洁` |
| `log_decisions` | bool | `false` | 记录判定日志（仅哈希，无原文） |
| `reply_copilot_enabled` | bool | `false` | 回复副驾总开关（默认关闭） |
| `trigger_mode` | string | `explicit` | 触发模式：`explicit`=仅 /reply；`risk`=白名单内 Jev 触发 |
| `draft_count` | int | `3` | 候选回复条数（2~3） |
| `draft_style` | string | `concise` | 风格：`concise` / `polite` / `firm` |
| `cooldown_minutes` | int | `10` | 同会话起草冷却（分钟，0=不冷却） |
| `max_drafts_per_day` | int | `20` | 每日 LLM 起草上限（0=不限） |
| `notify_target` | string | `""` | 副驾推送目标（主人 UMO）；risk 模式留空则只记录不推送 |
| `copilot_whitelist` | list | `[]` | risk 模式白名单（UMO / 群号；空=risk 完全不触发） |
| `llm_provider_id` | string | `""` | 起草用 LLM Provider（留空=会话默认） |

---

## 🧪 使用示例

**主动判定**
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

**试运行**
```
/jev dry 兄弟在吗？先借我五千，下个月还你。
```
输出：
```
【dry run · 仅回显】
🎯 Jev 意图雷达
意图：借钱（置信 1.00）
...
（命中提醒策略，正常模式会推送）
```

---

## 💰 费用说明

- TypeSafe 按 **input token** 计费（约 **$0.042 / Mtok**），output 免费。
- 每条判定约数百 input token，实测约 **$0.000027 / 条**（每千条约 ¥0.2 量级）。
- 本插件提供 `daily_call_limit` 做费用兜底；被动模式默认关闭，避免非预期花费。
- 具体价格以 [TypeSafe 官方](https://docs.typesafe.ai/models) 为准。

> 注意：**Jev 只做判定、不生成回复**，其文本**不支持图片/音频/视频**（仅文本）。

---

## 🗺️ Roadmap

- [ ] 上架 AstrBot 插件市场（需先推送到 GitHub 公开仓库并在 <https://cloud.astrbot.app/publish> 发布）
- [ ] 补充插件 Logo（`logo.png`，1:1，推荐 256×256）
- [ ] 支持自定义意图标签集（通过配置传入 criteria）
- [x] 支持接入宿主 AstrBot 的 LLM 对高风险消息做「解释/建议」（v1.1.0 回复副驾已实现）
- [ ] 扩样到 100~200 条真实脱敏中文语料复测并与 LLM 基线对照
- [ ] 支持多意图加权（利用 `probabilities` 全分布）

---

## 🔧 技术说明

- 网络：`aiohttp`（异步，遵循 AstrBot 规范，禁止 `requests`）。
- 请求体（TypeSafe SystemOne 三段式）：
  ```json
  {
    "state": "先说上下文，再说消息",
    "model": "jev-latest",
    "questions": {
      "intent":  {"type": "choice", "instructions": "...", "criteria": {"标签": "说明"}},
      "emotion": {"type": "choice", "instructions": "...", "criteria": {"标签": "说明"}},
      "risk":    {"type": "choice", "instructions": "...", "criteria": {"标签": "说明"}}
    }
  }
  ```
- 选用 `choice` 原语（而非 `score`）的原因：`choice` 的返回字段（`choice` / `probabilities` / `confidence`）经实测确认，解析稳定。
- 模块划分：`main.py`（AstrBot 集成）/ `jev_client.py`（异步 HTTP）/ `radar_core.py`（纯逻辑）/ `reply_copilot.py`（回复副驾纯逻辑，均可离线单测）。

---

## 🙏 灵感来源

- TypeSafe SystemOne / Jev — <https://typesafe.ai> ，<https://docs.typesafe.ai>
- 参考了 AstrBot 官方生态中 Jev 相关插件的技术路径思路（直连 `api.typesafe.ai/v1/systemone`）。

---

## 📝 更新日志

- **v1.2.0（2026-09-23）· 判定统计 + 持久化健壮性** — 新增 `/jev_stats` 统计命令；KV 额度持久化读写失败改为记录警告日志（不再静默丢失）。
- **v1.1.0（2026-09-22）· 回复副驾** — 新增 Reply Copilot：触发式（explicit /risk）起草候选回复、只推主人、永不代发、费用分层与三重闸门；不含任何无差别推送。
- **v1.0.0（2026-09-21）· 首发** — 被动监听 + 主动 `/jev` 判定、`/jev dry` 试运行、费用保护、本地脱敏。
- 完整变更记录见 [`CHANGELOG.md`](./CHANGELOG.md)。

---

## 📄 License

MIT © 2026 **YongWei**
