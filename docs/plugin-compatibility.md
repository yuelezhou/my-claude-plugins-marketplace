# 三平台插件兼容性矩阵

本仓库插件面向 Claude Code / ZCode / MiniMax Code 三个运行时。本文记录各平台的能力差异与本项目逐插件的兼容状态。调研日期 2026-09-28；MiniMax 规则依据 [MiniMax-Code-Plugins docs/plugin-compatibility.md](https://github.com/minimax-ai/minimax-code-plugins/blob/main/docs/plugin-compatibility.md)，ZCode/Claude 依据官方文档与本机缓存结构实测。

## 组件支持矩阵

| 组件 | Claude Code | ZCode | MiniMax Code Desktop |
|---|---|---|---|
| skills/（SKILL.md） | ✅ | ✅ | ✅ 自动扫描 `skills/*/SKILL.md`（frontmatter name 须与目录一致，≤64 字符；每插件 ≤64 个） |
| 自定义 agents/ | ✅ | ✅ | ❌ 不支持（静默不可用） |
| commands/ | ✅ | ✅ | ❌ 不支持 |
| hooks | ✅ hooks/hooks.json | ✅（本机样例未见，待验证） | ✅ 内联在 `.minimax-plugin` 清单的 `hooks` 字段 |
| MCP | ✅ `.mcp.json` | ✅ `.mcp.json` | ✅ `mcp.json`（≤8 服务器；stdio / streamable-http / sse） |
| LSP | ✅ `.lsp.json` | 待验证 | ❌ |
| 市场清单 | ✅ `.claude-plugin/marketplace.json` | ✅ 原生读取 Claude 格式（兼容层已证实） | ⚠️ 桌面端有「从 Git 仓库导入」（公开 git 仓库 + GitHub 子目录，不经审核）；托管市场走飞书表单提交 |

## 清单形态规则（MiniMax Code Desktop）

运行时探测顺序（依据 Desktop `app.asar` 内 `detectLocalPluginPackage`）：

1. 根目录 `plugin.json`（Agent Plugins 1.0）——**仅当被该读取器完整接受时上位**；非法或畸形则自动穿透，不遮蔽后续清单
2. `.minimax-plugin/plugin.json`（MiniMax Plugin V1）
3. `.claude-plugin/plugin.json`（兼容 vendor 方言，源码中以 unicode 转义书写）
4. `.codex-plugin/plugin.json`

> 关键推论：根 `plugin.json` 合法时会压过 `.minimax-plugin/`，使 MiniMax 的 `icon`/`category`/`exampleQueries` 全部失效——Agent Plugins 1.0 路径下这三项被运行时硬编码为 `category: 'Other'`、`exampleQueries: []`、`displayName: name`。**本仓库已统一删除根 `plugin.json`**，只保留 `.minimax-plugin/`。

- MiniMax V1 清单字段为**封闭集**：`$schema`/`schemaVersion`/`name`/`displayName`/`version`/`description`/`author`/`icon`/`darkIcon`/`category`/`exampleQueries`/`apps`/`mcpServers`/`skills`/`hooks`/`hostBindings`，多一个字段即拒
- `apps` 必须为 `[]`；`icon` 必填且需实际存在；`category` 取自固定 10 项枚举
- MCP 方言：`.mcp.json` 用 `type: "http"`（Claude Code 习惯），`mcp.json` 用 `type: "streamable-http"`（V1 唯一接受的 http 类传输）
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
| gitee-mcp | ✅ 读 `.mcp.json` | ✅ 读 `.mcp.json` | ✅ 读 `mcp.json` | **两份 MCP 文件方言不同**（`.mcp.json` = `type:http` 给 Claude Code；`mcp.json` = `schemaVersion:1` + `type:streamable-http` 给 MiniMax）。validator 强制校验两者**服务器集合与 url 一致**，transport 差异只告警；`${GITEE_ACCESS_TOKEN}` 在 MiniMax 侧的展开未验证 |

## 维护规则

1. 新增组件前先查本矩阵；MiniMax 不支持的组件只做「Claude/ZCode 可用 + 注明降级」
2. gitee-mcp 改 MCP 配置时，`.mcp.json` 与 `mcp.json` **都要改**（各自保持本客户端方言），但服务器名与 url 必须相同；跑 plugin-validator 会校验
3. **不要新增根目录 `plugin.json`**——它会压过 `.minimax-plugin/` 使 MiniMax 元数据失效
4. 本矩阵有误或平台规则变更时直接更新本文件并改 ADR 引用（分发架构见 ADR-0001）

## 插件分发矩阵（plugin 层，与 skill 层 junction 机制区分）

| Agent | 插件分发动作 | 链接可用？ |
|---|---|---|
| Claude Code | 一次性注册本地目录市场（`claude plugin marketplace add <仓库>`）+ install——**原位加载**，改源码 `/reload-plugins` 生效；异地机器用 GitHub 源 `marketplace add yuelezhou/my-claude-plugins-marketplace` | 原位（优于链接） |
| ZCode | `zcode plugins marketplace add` + `install`（副本制双登记）；更新 = `marketplace update` + `plugin update` 两步 | ✗ 副本 |
| MiniMax Code | **物理拷贝**到 `~/.minimax/plugins/<名>/`（drop-in 免登记自动启用、热感知）；junction/symlink/hardlink 一律被拒（`PLUGIN_ROOT_SYMLINK`） | ✗ 只能拷贝 |
| DeepSeek / OpenCode | 无插件机制，走 skill 通道 | — |

由 skill-distributor 的 `link-plugins` 子命令统一执行（`status`/`audit` 报告 MiniMax 副本新鲜度，`clean` 可删过期副本）。

## 目标标准与落地格式

本仓库同时服务两端，清单按目标各写一份，**不做 Agent Plugins 1.0 便携格式**：

| 目标 | 清单 | 位置 |
|---|---|---|
| Claude Code / ZCode | Claude Code 插件清单 | `.claude-plugin/plugin.json` |
| MiniMax Code | MiniMax Plugin V1 清单 | `.minimax-plugin/plugin.json` |

取舍依据：Agent Plugins 1.0 虽是跨端标准，但 MiniMax 运行时在该路径下把 `displayName` 强制为 `name`、`category` 硬编码为 `Other`、`exampleQueries` 固定为空——插件在市场/插件面板里没有任何元数据。改用 `.minimax-plugin/` 后图标、分类、示例查询才全部生效。放弃的代价是失去 agent-plugins.org 生态的自动发现，需要跨端的第三方客户端需自行补一份根 `plugin.json`（但注意：在本仓库形态下补回会让 MiniMax 侧元数据再次失效）。

## 外部聚合插件（引用式 + pin SHA）

| 插件 | 上游 | pin | 三平台 |
|---|---|---|---|
| mattpocock-skills | [mattpocock/skills](https://github.com/mattpocock/skills) | main `49dd158`（2026-10-18，v1.3.1） | ✅✅✅ 纯 skills |

入库流程：clone → `plugin-validator --standalone` 0 error → 本表标注 → marketplace.json 加条目（github source + metadata.pinnedSha）。更新流程：重取 SHA → 重跑校验 → 更新 pin。
