# Jev 意图雷达 · astrbot_plugin_jev_radar

> **帮你看懂消息背后的意图。**

用 [TypeSafe SystemOne（Jev）](https://typesafe.ai) 的 typed decision 能力，把群聊 / 私聊消息实时判定为
**「意图标签 + 情绪倾向 + 风险等级 + 置信度」**，只在**低置信度或高风险**时提醒，绝不刷屏。

> 一句话：**AstrBot 有了官方的 Jev「闸门」，我们做了 Jev 的「眼睛」。**
> 官方 `reply_gate` 决定「Bot 要不要回」，本插件输出「**人怎么理解这条消息**」。二者定位不同，可共存。

- 作者：**YongWei**
- 许可：**MIT**（见 [LICENSE](LICENSE)）
- 版本：1.0.0

---

## ⚠️ 隐私声明（务必先读）

1. **消息内容会发送至第三方**：启用后，被判定消息的**文本**会通过 HTTPS 发送至 **TypeSafe AI**（`api.typesafe.ai`）进行判定。启用前请自行评估数据敏感度。
2. **数据出境提示**：TypeSafe 为境外服务，请遵守所在地的数据合规要求。
3. **本地脱敏（默认开启）**：发送前会本地替换手机号 / 邮箱 / 身份证 / 银行卡 / 超长数字串，并对超长文本截断。
4. **不落原文**：默认只记录「判定结果 + 消息哈希」，不保存原始消息文本；`log_decisions` 默认关闭。
5. **可退出**：`enable=false` 即完全停用；`scope_group` / `scope_private` / `group_whitelist` 可精确控制生效范围。
6. **密钥安全**：`api_key` 仅保存在本机 `data/config/` 下，**不硬编码、不入库、不随仓库分发**。

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
- `/jev dry <文本>` 或 `/jev test <文本>` — **试运行**，只回显「将要发送的内容」，不发送、不写记录

### 其他控制
- 群白名单 `group_whitelist`、群/私聊范围开关
- 每日调用上限 `daily_call_limit`（费用保护）

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
- [ ] 支持接入宿主 AstrBot 的 LLM 对高风险消息做「解释/建议」
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
- 模块划分：`main.py`（AstrBot 集成）/ `jev_client.py`（异步 HTTP）/ `radar_core.py`（纯逻辑，可离线单测）。

---

## 🙏 灵感来源

- TypeSafe SystemOne / Jev — <https://typesafe.ai> ，<https://docs.typesafe.ai>
- 参考了 AstrBot 官方生态中 Jev 相关插件的技术路径思路（直连 `api.typesafe.ai/v1/systemone`）。

---

## 📄 License

MIT © 2026 **YongWei**
