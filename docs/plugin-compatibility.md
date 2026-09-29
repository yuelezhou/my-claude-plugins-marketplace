# 三平台插件兼容性矩阵

本仓库插件面向 Claude Code / ZCode / MiniMax Code 三个运行时。本文记录各平台的能力差异与本项目逐插件的兼容状态。调研日期 2026-09-28；MiniMax 规则依据 [MiniMax-Code-Plugins docs/plugin-compatibility.md](https://github.com/minimax-ai/minimax-code-plugins/blob/main/docs/plugin-compatibility.md)，ZCode/Claude 依据官方文档与本机缓存结构实测。

## 组件支持矩阵

| 组件 | Claude Code | ZCode | MiniMax Code (mcode 0.4.0+) |
|---|---|---|---|
| skills/（SKILL.md） | ✅ | ✅ | ✅（frontmatter name 须与目录一致，≤64 字符；每插件 ≤64 个） |
| 自定义 agents/ | ✅ | ✅ | ❌ 不支持（静默不可用） |
| commands/ | ✅ | ✅ | ❌ 不支持 |
| hooks | ✅ hooks/hooks.json | ✅（本机样例未见，待验证） | ⚠️ 仅 0.4.0+ 内联在清单的 `hooks` 字段（12 个事件） |
| MCP | ✅ `.mcp.json` 或清单 `mcpServers`（≤ 建议上限无） | ✅ `.mcp.json` | ✅ 根目录 `mcp.json`（≤8 服务器；stdio / streamable-http / sse） |
| LSP | ✅ `.lsp.json` | 待验证 | ❌ |
| 市场清单 | ✅ `.claude-plugin/marketplace.json` | ✅ 原生读取 Claude 格式（兼容层已证实） | ❌ 无市场清单概念——社区仓库按 `plugins/<owner>/<name>/` 一文件夹一发布 |

## 清单形态规则（MiniMax）

- **mcode 0.4.0+（首选）**：`.claude-plugin/plugin.json`——与 Claude Code 完全同形；根目录 `plugin.json` 会被忽略
- mcode 0.3.x 便携格式：根目录 `plugin.json` + `$schema: agent-plugins.org`——本仓库**不支持**（并行发布是双倍维护）
- 保留环境变量：`PLUGIN_ROOT`、`PLUGIN_DATA` 不可自行设置；勿在环境值/headers 中内嵌 token

## 本项目逐插件状态

| 插件 | Claude | ZCode | MiniMax | 备注 |
|---|---|---|---|---|
| anki-card-from-notes | ✅ | ✅ | ✅ 纯 skills | |
| word-frequency | ✅ | ✅ | ✅ 纯 skills | |
| skill-distributor | ✅ | ✅ | ✅ 纯 skills | 需在 market 仓库 clone 内运行（或 `--root`/`MARKET_REPO`） |
| plugin-validator | ✅ | ✅ | ✅ 纯 skills | |
| hello-greeting | ✅ | ✅ | ✅ 纯 skills | |
| demo-case | ✅ | ✅ | ⚠️ 部分 | debug-helper agent 在 MiniMax 不可用（演示插件，接受降级） |
| gitee-mcp | ✅ 读 `.mcp.json` | ✅ 读 `.mcp.json` | ✅ 读根目录 `mcp.json` | **双 MCP 文件必须保持一致**，validator 强制校验；`${GITEE_ACCESS_TOKEN}` 在 MiniMax 侧的展开未验证 |

## 维护规则

1. 新增组件前先查本矩阵；MiniMax 不支持的组件只做「Claude/ZCode 可用 + 注明降级」
2. gitee-mcp 改 MCP 配置时，`.mcp.json` 与 `mcp.json` **同步改**，跑 plugin-validator 会校验一致性
3. 本矩阵有误或平台规则变更时直接更新本文件并改 ADR 引用（分发架构见 ADR-0001）

## 插件分发矩阵（plugin 层，与 skill 层 junction 机制区分）

| Agent | 插件分发动作 | 链接可用？ |
|---|---|---|
| Claude Code | 一次性注册本地目录市场（`claude plugin marketplace add <仓库>`）+ install——**原位加载**，改源码 `/reload-plugins` 生效；异地机器用 GitHub 源 `marketplace add yuelezhou/my-claude-plugins-marketplace` | 原位（优于链接） |
| ZCode | `zcode plugins marketplace add` + `install`（副本制双登记）；更新 = `marketplace update` + `plugin update` 两步 | ✗ 副本 |
| MiniMax Code | **物理拷贝**到 `~/.minimax/plugins/<名>/`（drop-in 免登记自动启用、热感知）；junction/symlink/hardlink 一律被拒（`PLUGIN_ROOT_SYMLINK`） | ✗ 只能拷贝 |
| DeepSeek / OpenCode | 无插件机制，走 skill 通道 | — |

由 skill-distributor 的 `link-plugins` 子命令统一执行（`status`/`audit` 报告 MiniMax 副本新鲜度，`clean` 可删过期副本）。

## Agent Plugins 1.0 规范符合（agent-plugins.org）

本仓库插件**符合 [Agent Plugins 1.0](https://agent-plugins.org/specification)**：每个插件根目录带便携清单 `plugin.json`（`$schema` + `name` + `version` 最小集，字段不复制——与 `.claude-plugin/plugin.json` 的同步由 plugin-validator 强制校验）。组件面天然合规（skills + 根目录 `mcp.json`；`agents/` 属规范外组件，客户端按规范忽略）。注意：mcode 0.4.0+ 会忽略根 plugin.json 优先读 `.claude-plugin/`——两份清单服务不同生态，均为有意保留。

## 外部聚合插件（引用式 + pin SHA）

| 插件 | 上游 | pin | 三平台 |
|---|---|---|---|
| mattpocock-skills | [mattpocock/skills](https://github.com/mattpocock/skills) | main `484efcbe`（2026-09-29） | ✅✅✅ 纯 skills |

入库流程：clone → `plugin-validator --standalone` 0 error → 本表标注 → marketplace.json 加条目（github source + metadata.pinnedSha）。更新流程：重取 SHA → 重跑校验 → 更新 pin。
