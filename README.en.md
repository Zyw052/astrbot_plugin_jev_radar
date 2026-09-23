# Jev Intent Radar · astrbot_plugin_jev_radar

[中文](README.md) | **English** | [日本語](README.ja.md)

<p align="center">
  <img src="assets/logo.png" alt="Jev Intent Radar Logo" width="180" height="180">
</p>

> **Understand what a message really means.**

- Author: **YongWei**
- License: **MIT** (see [LICENSE](LICENSE))
- Current version: **1.2.0** (full history in [CHANGELOG.md](CHANGELOG.md))

---

## ⚠️ Privacy & Compliance (read this first)

1. **Message text goes to a third party**: once enabled, the **text** of each analyzed message is sent over HTTPS to **TypeSafe AI** (`api.typesafe.ai`) for intent classification. Assess data sensitivity before enabling.
2. **Cross-border data**: TypeSafe is an overseas service; comply with local data-regulation requirements.
3. **Local redaction (on by default)**: phone numbers, emails, ID numbers, bank cards and long digit runs are replaced with placeholders before sending; long texts are truncated (`max_chars_per_msg`).
4. **No raw text stored**: by default only "verdict + message hash" is kept, never the original text; `log_decisions` is off by default.
5. **Fully opt-out**: set `enable=false` to disable everything (no listening, no API calls, no alerts); `scope_group` / `scope_private` / `group_whitelist` control the exact scope.
6. **API key safety**: `api_key` lives only in local `data/config/` — never hard-coded, never committed, never distributed. Keep it secret.
7. **Extra disclosure for the Reply Copilot**: when enabled, redacted message text is sent ① to TypeSafe for classification and ② to the host AstrBot LLM Provider for drafting. Draft replies are delivered **only to the owner**, never to the original conversation.

---

## ① What is this?

Using the typed-decision capability of [TypeSafe SystemOne (Jev)](https://typesafe.ai), the plugin classifies group/private chat messages in real time into an **intent label + sentiment + risk level + confidence score**, and is deliberately restrained: it only alerts on low confidence or high risk — never spam.

> In one sentence: **AstrBot already ships an official Jev "gate"; this plugin is Jev's "eyes."**
> The official `reply_gate` decides whether the bot *should reply*; this plugin tells a human *how to read the message*. Different jobs — they can coexist.

Three capabilities:

- **Passive mode** (off by default): listens automatically, alerts only on high risk / low confidence / flagged intents.
- **Active mode**: classify on demand with `/jev`, or dry-run with `/jev dry`.
- **Reply Copilot** (off by default): Jev judges, the host LLM drafts candidate replies for the owner — it never sends anything to any conversation.

---

## ② Installation

1. Copy this plugin folder into AstrBot's **`data/plugins/`** directory (folder name `astrbot_plugin_jev_radar`).
2. The single dependency is **`aiohttp>=3.9`** (see `requirements.txt`); AstrBot installs it automatically when adding the plugin. If missing: `pip install aiohttp>=3.9`.
3. **Enable / reload** the plugin in the WebUI plugin manager.
4. Enter your **TypeSafe API Key** in the plugin config (obtain it at <https://console.typesafe.ai>).
5. (Optional) enable passive mode with `passive_enabled=true`.

> Jev classifies **text only** — images, audio and video are not supported.

---

## ③ Configuration Reference

Mirrors `_conf_schema.json` (27 keys). "**Effect**" explains what each key actually changes; "Recommended" is a general suggestion.

| Key | Type | Default | Effect | Recommended |
|---|---|---|---|---|
| `enable` | bool | `true` | Master switch; when off the plugin does nothing at all (no listening, no calls, no alerts) | keep |
| `api_key` | string | `""` | TypeSafe API key, stored locally only; **empty = no calls possible** | required |
| `base_url` | string | `https://api.typesafe.ai` | API endpoint; actual request is `POST {base_url}/v1/systemone` | keep |
| `model` | string | `jev-latest` | Jev model name (`jev-preview` also available) | `jev-latest` |
| `timeout_sec` | int | `20` | Per-request timeout in seconds; raise on slow networks | 20–30 |
| `retries` | int | `1` | Retries for 429 / 503 / 529 (rate limit / overload) only; other errors fail fast | 1 |
| `confidence_threshold` | float | `0.75` | Intents below this confidence are flagged "doubtful" and trigger passive alerts | 0.75 |
| `risk_alert_threshold` | int | `2` | Risk level 0 = safe / 1 = attention / 2 = high; alerts fire at or above this | 1 (sensitive) or 2 |
| `daily_call_limit` | int | `2000` | Hard daily cap on classification calls, 0 = unlimited; cost guard | 2000 |
| `passive_enabled` | bool | `false` | Master switch for passive listening (off by default to avoid noise and cost) | enable only if needed |
| `scope_group` | bool | `true` | Whether passive mode processes group messages | keep |
| `scope_private` | bool | `false` | Whether passive mode processes private messages | keep |
| `group_whitelist` | list | `[]` | Group whitelist for passive mode; **empty = all groups** | restrict with IDs if you're in many groups |
| `watch_intents` | list | `["推销","引战","诈骗","拉人"]` (spam, trolling, scam, recruiting) | Watched intents trigger an alert in passive mode even at high confidence | tune to taste |
| `desensitize` | bool | `true` | Local redaction before sending (phone/email/ID/bank-card/digit runs) | **always keep on** |
| `max_chars_per_msg` | int | `800` | Truncate long texts before sending (cost + privacy) | 800 |
| `result_style` | string | `详细` ("detailed") | `详细` = multi-line with confidence; `简洁` = one-line summary | preference |
| `log_decisions` | bool | `false` | Persist verdicts to local `decisions.jsonl` (hash only, **no raw text**); required for `/jev_stats` history | enable if you want stats |
| `reply_copilot_enabled` | bool | `false` | Master switch for the Reply Copilot; even when on, it fires only per `trigger_mode` | enable only if needed |
| `trigger_mode` | string | `explicit` | `explicit` = only the owner's `/reply` command (most conservative); `risk` = only inside whitelisted chats, only when Jev flags a watched intent / high risk with sufficient confidence, drafts pushed to the owner | `explicit` |
| `draft_count` | int | `3` | Candidate replies generated per drafting run (2–3) | 3 |
| `draft_style` | string | `concise` | `concise` = direct / `polite` = courteous / `firm` = assertive | as needed |
| `cooldown_minutes` | int | `10` | Minimum gap between two LLM drafting runs in the same chat under `risk` mode; 0 = none (not recommended); cost guard | 10 |
| `max_drafts_per_day` | int | `20` | Daily cap on LLM draft runs (0 = unlimited); note Jev classifications do **not** count against this, they are tracked separately | 20 |
| `notify_target` | string | `""` | Owner's session identifier (UMO, e.g. `aiocqhttp:FriendMessage:xxxx`) that `risk`-mode drafts are pushed to; empty = record only, no push | required for risk mode |
| `copilot_whitelist` | list | `[]` | Chats allowed in `risk` mode (UMO or group ID); **empty = risk mode never fires** (most conservative) | required for risk mode |
| `llm_provider_id` | string | `""` | LLM Provider used for drafting; empty = the chat's default provider | keep |

---

## ④ Command Manual

### `/jev` — Classify manually
- **Purpose**: classify a text into intent / sentiment / risk / confidence.
- **Arguments**: optional `dry` followed by the text; or **reply-quote a message** and send bare `/jev` to classify the quoted message.
- **Example**:
  ```
  /jev Hey girl, our face mask is all-natural, today only, first 50 orders get a free device!
  ```
  Output:
  ```
  🎯 Jev Intent Radar
  Intent: Sales pitch (confidence 1.00)
  Sentiment: neutral (0.90)
  Risk: HIGH ⚠️ (0.95)
  ```
- **Dry run**: `/jev dry Buddy, lend me five grand, I'll pay you back next month.` just echoes what *would* be sent — nothing is sent or logged (but **it still consumes one real classification call**). Alias `/jev test`. Bare `/jev stats` points you to `/jev_stats`.

### `/jev_stats` — Usage & statistics (aliases: `雷达统计` / `radar_stats`)
- **Purpose**: view today's classification quota (including Copilot drafting usage), total historical verdict count, top-5 intent distribution and risk distribution (new in v1.2.0).
- **Arguments**: none.
- **Example**: `/jev_stats`
- Note: without `log_decisions=true` there is no historical distribution; the command tells you how to enable it (today's quotas remain visible).

### `/reply` — Draft candidate replies
- **Purpose**: have a host LLM draft 2–3 candidate replies for the current context (each with a one-line rationale), for the owner's reference. **It never sends to any conversation.**
- **Arguments**: optional text; or **reply-quote a message** and send `/reply` to draft for that message.
- **Example**:
  ```
  /reply the buyer is pressing for shipment again, quite angry
  ```
- Prerequisite: `reply_copilot_enabled=true` (off by default). In `risk` mode no command is needed — a flagged message auto-triggers a draft pushed to `notify_target`.

---

## ⑤ Passive Listening

- Implementation: AstrBot `@filter.event_message_type(EventMessageType.ALL)`; every message flows through the `on_llm_request` hook, which consults the config before firing an API call.
- **Off by default** (`passive_enabled=false`): keeps group chats quiet and avoids unexpected API spend.
- **How to enable**: set `passive_enabled=true` in the plugin config and reload.
- **Scope control**: `scope_group` (groups, default on) × `scope_private` (privates, default off) × `group_whitelist` (empty = all groups); the effective scope is their intersection.
- **Alert conditions (any ONE suffices; everything else stays silent)**:
  1. intent confidence `< confidence_threshold` (flagged "doubtful");
  2. risk level `>= risk_alert_threshold`;
  3. the intent is in `watch_intents` (even at high confidence).
- **Caveats**: ① enabling incurs continuous per-message cost — respect `daily_call_limit`; ② start small via `dry` runs or a short whitelist; ③ passive alerts go to the owner's session only, never displayed in the original chat.

---

## ⑥ KV Quota & Statistics

- **Persistent quotas**: today's classification count (`daily_usage`) and drafting count (`reply_draft_usage`) are persisted in AstrBot's KV store (under `data/plugin_data/`) and survive restarts.
- **Two separate budgets**: cheap Jev classifications count toward `daily_call_limit`; expensive LLM drafts count toward `max_drafts_per_day`. Neither eats the other's quota.
- **Read/write failure warnings** (v1.2.0): when a KV read/write fails, a **warning log is emitted** and the plugin temporarily falls back to in-memory counting (a restart would reset that day's counter) — no more silent loss, easier troubleshooting.
- **What `/jev_stats` shows**: today's classifications X / limit Y; today's drafts A / limit B; total historical verdicts; top-5 intent distribution; risk distribution. History requires `log_decisions=true`.

---

## ⑦ FAQ

1. **Installed but nothing happens?** Check in order: is `api_key` set → is `enable` true → for passive mode, is `passive_enabled=true` and at least one of `scope_group`/`scope_private` on, and is the group in `group_whitelist`? Test connectivity with a quick `/jev hello`.
2. **Why do I never get alerts?** By design: passive mode alerts only on low confidence / high risk / watched intents; normal chatter stays silent. To be more sensitive, lower `risk_alert_threshold` to 1 and/or raise `confidence_threshold`.
3. **How do I control quota / cost?** `daily_call_limit` (default 2000) caps classifications; `max_drafts_per_day` (default 20) and `cooldown_minutes` (default 10) cap LLM drafting; usage is visible anytime via `/jev_stats`; passive mode is off by default to prevent surprise spend. TypeSafe bills input tokens only (≈ $0.042/Mtok), a single classification costs a tiny fraction of a cent — see the official docs for exact pricing.
4. **Where are the logs / records?** Runtime logs go to the AstrBot console; verdict records (results + message hashes only, no raw text) are written to `decisions.jsonl` under `data/plugin_data/` when `log_decisions=true`; KV quota read/write failures produce warning lines in the log.
5. **How do I disable or uninstall?** Disable entirely: set `enable=false` (no listening, no calls, no alerts). Uninstall: remove via the WebUI plugin manager and delete `data/plugins/astrbot_plugin_jev_radar`. All passive listeners stop immediately with the switch.
6. **`/reply` says "drafting failed"?** The host LLM call failed (timeout / not configured / quota exhausted). The reply includes the error summary and other features are unaffected; check the LLM Provider or `llm_provider_id`.
7. **Does it classify images / voice?** No. Jev handles text only; image/audio/video messages are ignored.

---

## ⑧ Privacy Notes & Advice

- Redacted message text goes to TypeSafe (overseas) for classification and, with the Copilot enabled, additionally to the host LLM provider — **never** to any server of the plugin author; the author collects nothing.
- Keep `desensitize=true`, `max_chars_per_msg=800`, `log_decisions=false` unless you need stats, and restrict passive mode to a whitelist.
- Evaluate your use case against local data protection laws (e.g. cross-border transfer rules).

---

## ⑨ Versioning & Changelog

- **v1.2.0 (2026-09-23)** — Added `/jev_stats`; KV quota persistence now logs warnings on read/write failure instead of failing silently.
- **v1.1.0 (2026-09-22)** — Reply Copilot (explicit/risk triggers, owner-only delivery, layered cost guard).
- **v1.0.0 (2026-09-21)** — Initial release: passive listening + `/jev`, `/jev dry`, cost guard, local redaction.

Full history: [`CHANGELOG.md`](CHANGELOG.md).

---

## ⑩ License

[MIT](LICENSE) © 2026 **YongWei**
