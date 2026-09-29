# 五大 AI Coding Agent 的 Plugin 发现/加载/登记机制调研

- **调研日期**：2026-09-29
- **调研者**：skill-distributor plugin-hub 子任务（独立调研 agent）
- **范围**：Claude Code / ZCode / MiniMax Code (mcode) / DeepSeek Deep Code / OpenCode 的 **plugin（插件包）** 发现目录与登记要求。skill（非 plugin）的发现目录不在本文重复，见 `docs/plugin-compatibility.md` 与 `plugins/skill-distributor/skills/skill-distributor/references/agent-roots.md`。
- **结论可信度总评**：**高**。五家中四家的核心结论有一手证据：MiniMax 为 runtime 源码级（从本机 app.asar 提取的 `@mavis/local-runtime-v2` TS 源码），ZCode 为本机受控实验 + CLI 源码级（zcode.cjs v0.16.9），Claude Code 与 OpenCode、DeepSeek 为官方文档直接陈述。置信度标注沿用定稿规则：runtime 源码 ≈ 官方文档 > 本机受控实验 > 第三方安装器文档 > 社区 SEO。所有「未证实」项在文中显式标出。

---

## 1. Claude Code

### 发现/加载位置

| 位置 | 作用 | 是否需要登记 |
|---|---|---|
| `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` | 市场安装插件的本体缓存（`${CLAUDE_PLUGIN_ROOT}` 指向这里），`CLAUDE_CODE_PLUGIN_CACHE_DIR` 可改根 | 需要（见下） |
| `~/.claude/plugins/marketplaces/<name>/` | 市场（GitHub/Git/URL 来源）的 clone；**本地 `file`/`directory` 市场不复制，`installLocation` 就是用户给的路径** | 需要先加市场 |
| `~/.claude/plugins/data/<plugin-id>/` | 插件持久数据（`${CLAUDE_PLUGIN_DATA}`），首次使用时创建 | — |
| `~/.claude/skills/<plugin-dir>/`、`<project>/.claude/skills/<plugin-dir>/` | **Drop-in 路径**：目录内有 `.claude-plugin/plugin.json` 即作为 `名字@skills-dir` 内联插件**原位加载，永不复制** | **不需要登记** |
| `--plugin-dir <path>` / `--plugin-url` / `CLAUDE_CODE_PLUGIN_DIRS` | 会话级 `@inline` 插件，原位加载，仅当次会话 | 不需要（但仅当次会话） |
| 项目 `.claude/plugins/` | **官方明确不扫描**："Claude Code doesn't scan a project's `.claude/plugins/` directory." | — |

### 登记要求（marketplace 正规通道）

- 已安装记录：`~/.claude/plugins/installed_plugins.json`（scope、installPath、version；会话启动只读它 + cache，不联网）。市场记录：`~/.claude/plugins/known_marketplaces.json`（本机实文件与此一致，本机 `config.json` 的 `repositories:{}` 是旧版残留 schema）。
- 启用开关：**用户 settings.json 的 `enabledPlugins` 键**（插件引用页原文："Once a user's `enabledPlugins` entry is written, it persists across plugin updates"；用户配置值存 `pluginConfigs`）。本机 `~/.claude/settings.json` 无 enabledPlugins（未装任何插件，一致）。
- 命令：`/plugin marketplace add <git|url|本地目录>` → `/plugin install 名@市场`（或 `claude plugin ...` CLI）。
- **本地目录市场的特殊待遇**：其插件**原位加载**（"loads in place from its path inside the marketplace folder"），源码改动下次会话启动或 `/reload-plugins` 生效，无需版本号变更——这是 Claude Code 唯一的「链接式」持久通道。

### `@skills-dir` drop-in 机制（关键发现）

官方 loading 页明确：把含 `.claude-plugin/plugin.json` 的插件目录放进 `~/.claude/skills/` 或项目 `.claude/skills/`，会作为 `<清单名>@skills-dir` 内联插件加载：
- 启用默认值取清单 `defaultEnabled`（settings 可覆盖为 true/false）；
- **原位加载、不复制**；
- 用户级优先于项目级；与市场插件/`--plugin-dir` 同名时 **skills-dir 优先级最低**（让位并报一行 Errors）；
- 项目级只认会话主工作目录的 `.claude/skills/`（需过 trust 对话框，不向上搜父目录）。

### 证据

- 来源类型：官方文档（2026-09-29 抓取）
  - https://code.claude.com/docs/en/plugins/loading （cache/installed_plugins.json/--plugin-dir/本地市场原位加载/@skills-dir/不扫项目 .claude/plugins）
  - https://code.claude.com/docs/en/plugins-reference （enabledPlugins 持久化、pluginConfigs、--plugin-dir 命名规则）
- 来源类型：本机安装态（`C:\Users\yuele\.claude\plugins\`：config.json=`repositories:{}` 旧 schema；known_marketplaces.json 记 claude-plugins-official 及 installLocation；marketplaces/ 内为市场 clone；repos/、blocklist.json）

---

## 2. ZCode

### 发现/加载位置

| 位置 | 作用 | 是否需要登记 |
|---|---|---|
| `~/.zcode/cli/plugins/cache/<marketplace>/<plugin>/<version>/` | 安装时**复制进来的版本化缓存本体**（实验证实，非链接） | 需要（双登记） |
| `~/.zcode/cli/plugins/installed_plugins.json` | 已安装插件注册表：id=`名@市场`、installPath（指向缓存）、scope、source、cacheTransactionId | **登记点 1** |
| `~/.zcode/cli/config.json` → `plugins.enabledPlugins` | 启用开关 map（`"名@市场": true`） | **登记点 2** |
| `~/.zcode/cli/plugins/known_marketplaces.json` | 市场注册表（含本地 directory/file 来源的 path） | 加市场时写 |
| `~/.zcode/cli/plugins/marketplaces/<id>/` | 市场清单副本 | — |
| 任意文件夹直接放入 cache | **不会被发现**：加载器遍历 `installed_plugins.json` 记录并校验记录形状，再按 `installPath`（缺省才回落拼接 cache 路径）读本体 | 不行，必须登记 |

### 登记要求与正规动作

- 官方通道（CLI，本机 v0.16.9 实测）：
  1. `zcode plugins marketplace add <本地目录|git|url>` —— 本地目录解析为 `{source:"directory", path}`（或 `.json` 文件为 `{source:"file"}`），写入 known_marketplaces.json；
  2. `zcode plugins install 名@市场` —— **把插件复制到版本化缓存**，写 installed_plugins.json 记录（installPath 指缓存），并在 `~/.zcode/cli/config.json` 写 `plugins.enabledPlugins[名@市场]=true`。
  - 其余子命令：`list|uninstall|enable|disable|update|validate`，市场侧 `marketplace add|list|remove|update`。
- 桌面端等价动作（官方捆绑开发指南）：「插件市场 → 添加 → 添加插件市场」粘贴市场根目录 → 「个人」→ 安装；且明确 **"Source edits are not hot reload. A market refresh updates the catalog; the installed plugin still needs its update action."** —— 装的是副本，改源码不热更。
- 未文档化的手工通道（源码级推断，未实测）：直接改 `installed_plugins.json` 加记录（installPath 可指任意目录）+ `config.json` enabledPlugins 置 true。加载函数 `ydn` 优先取记录里的 `installPath`，理论可行；**未证实**，不建议 plugin-hub 依赖。

### seed hash 会不会拦外部塞入的目录？

**不会成为登记通道的障碍，也拦不住也救不了裸放目录**：
- `.zcode-plugin-seed.json`（hash、marketplace、source）只在**捆绑官方插件播种**（`seedBundledOfficialPlugins`）链路使用；`isSeedCurrent` 把 seed 里的 hash 与**应用内置源**的 hash 对比，不一致就重新播种——是完整性恢复，不是加载闸门。
- 加载路径（zcode.cjs）按 installed_plugins.json 记录取本体，**未发现**对缓存内容做逐次 hash 校验的代码（多条 sha256 引用均属损坏备份/内置端点等无关逻辑；结论=未发现，非保证不存在）。
- 本机缓存佐证：从 GitHub URL 装的 mattpocock-skills 也被复制进 cache 并无 seed 文件；zcode-plugins-official 缓存（CDN filesystem 源）才有 seed。

### 证据

- 来源类型：**本机受控实验**（2026-09-29，实验后已完全清理）：临时目录建 `.claude-plugin/marketplace.json` + `demo-plug/.claude-plugin/plugin.json` → `plugins marketplace add` → `plugins install demo-plug@zc-test-mkt` → 观测到：cache/zc-test-mkt/demo-plug/0.0.1/ 出现**复制体**；installed_plugins.json 新增记录（installPath 指 cache）；config.json enabledPlugins 置 true。卸载 + remove market 后所有登记与缓存复原（残余空目录已手删）。
- 来源类型：CLI 运行时源码（`C:\Users\yuele\AppData\Local\Programs\ZCode\resources\glm\zcode.cjs`，v0.16.9，`ELECTRON_RUN_AS_NODE=1 ZCode.exe zcode.cjs` 可直接运行）：`Cdn`=cache 路径拼接、`ydn`=按 installPath 读本体、记录形状校验、`isSeedCurrent`/`isSeedUsable` 播种校验、marketplace add 的 directory/file 源解析。
- 来源类型：官方捆绑开发指南（本机 `resources/glm/packages/plugin-creator-plugin/skills/plugin-creator/references/installing-and-updating.md`）：UI 添加市场→安装流程、"source/marketplace copy/installed copy 是三个不同位置"、更新需市场刷新+插件更新。任务给的 https://github.com/zcode-plugins AGENTS.md **未证实**：GitHub 上无此 org/仓库（404），该指南的本地等价物即上述捆绑 skill。
- 注：设置 schema 另有 `plugins.extraKnownMarketplaces`（settings 声明市场，相对用户设置目录解析），是登记的第 3 条路，本机未见实例。

---

## 3. MiniMax Code（mcode）

### 发现/加载位置（runtime 源码级结论）

**唯一扫描根：`<dataDir>/plugins/`**（本机 dataDir=`C:\Users\yuele\.minimax`；`~/.mavis` 是指向它的 **junction**，同一目录两名，known_marketplaces.json 里的 `.mavis` 路径即由此解析）。dataDir 可被 `MINIMAX_DATA_DIR`/`MAVIS_DATA_DIR` 环境变量或 git-profile 开发模式移动（源码 `data-dir.js`）。

| 位置 | 作用 | 是否需要登记 |
|---|---|---|
| `<dataDir>/plugins/<name>/` | **本地插件扫描根**（`scanLocalPluginPackages(path.join(dataDir,'plugins'))`），`LocalPluginDirectoryWatcher` 监视变更并触发重新发布（热感知外部改动） | **不需要登记，默认启用** |
| `<dataDir>/v2/plugin-cache/official/sha256-tree-v1-<hash>/` | 官方（云端市场）插件的内容寻址缓存（`.minimax-plugin/plugin.json` + 树哈希键） | 云端通道登记（sqlite official state） |
| `<dataDir>/plugins/known_marketplaces.json` + `plugins/marketplaces/` | Claude 兼容市场层的注册表/克隆目录（镜像 Claude Code 文件格式，字段多 `enabled:true`；本机两项为空、无安装实例） | **加载路径未证实**（本机无样本） |
| `<dataDir>/sqlite.db` | `pluginDisabledLocalRoots` **禁用表**——启用态是黑名单不是白名单 | 仅记录"被用户禁用" |

### 本地插件的清单接受顺序（`detectLocalPluginPackage`）

`<dataDir>/plugins/<name>/` 下按优先级探测：
1. 根 `plugin.json`（`$schema: https://agent-plugins.org/schemas/1.0.0/plugin.schema.json` 便携格式，读 skills/ + mcp.json，hooks 恒空）；
2. `.minimax-plugin/plugin.json`（原生，schemaVersion 1）；
3. `.claude-plugin/plugin.json`（**Claude 兼容**：读 skills/（含清单 skills 字段指向的其他目录）、`hooks/hooks.json`、`.mcp.json` 与清单 `mcpServers`）；
4. `.codex-plugin/plugin.json`（Codex 兼容）。
四者皆无 → 记 diagnostic 跳过。与既有定稿一致：0.4.0+ 首选 `.claude-plugin/plugin.json` 形态。

### 硬性约束：必须是物理目录

- 扫描根与每个候选目录都过 `canonicalizePluginRoot(root, {rejectSymlink:true})`：`lstat().isSymbolicLink()` → 报 `PLUGIN_ROOT_SYMLINK`（"Plugin root must be a physical directory"）；候选枚举里 `childStat.isSymbolicLink() || !isDirectory()` 直接 continue。**Node 在 Windows 上把 NTFS junction 也报告为符号链接**，因此 junction/hardlink（miniapp 另有 `rejectHardlinks`）都会被跳过——**插件进 MiniMax 只能复制真实目录，不能链接**。（源码级结论；junction 在本机未做实机启动验证，标注为高置信推断。）
- 放进去即被发现、默认启用（`isLocalPluginEnabled` = 不在 sqlite 禁用表即 true；`setLocalPluginEnabled(false)` 才写表）；目录监视器使外部增删改被感知。禁用/启用动作在桌面 UI（插件管理）。

### 本机装机态佐证

- `~/.minimax/plugins/{cache,marketplaces}` 均为空、`~/.minimax/v2/plugin-cache/official/sha256-tree-v1-*/` 有两个官方插件缓存（其中一个即 mattpocock-skills 1.2.4，`.minimax-plugin/plugin.json` 为原生清单形态）——与「云端通道走 v2 内容寻址缓存、本地通道扫 dataDir/plugins」的源码结论互证。
- 桌面壳层（asar `/dist/main`）证实运行时本体是 asar 内 `@mavis/local-runtime-v2`（utility 进程动态 import），PluginSystem 由其持有。
- **未证实**：mcode headless CLI 是否有 `plugin install` 类命令（本机 `~/.minimax/bin/minimax` 是指向已不存在的 `resources/resources/daemon/cli.js` 的断链；新版本 CLI 入口缺失）。社区仓库（github.com/minimax-ai/minimax-code-plugins）README/CONTRIBUTING **不提供任何面向终端用户的安装命令或目录说明**，只讲 fork→PR 贡献流——与「本地目录即装」的源码结论不冲突。

### 证据

- 来源类型：**runtime 源码**（2026-09-29 自 `C:\Users\yuele\AppData\Local\Programs\MiniMax Code\resources\app.asar`（mtime 2026-09-27）提取 `node_modules/@mavis/local-runtime-v2/src/service/plugin-system/` 全部 96 个 TS 文件至 C:\tmp\mcode-src）：
  - `plugin/package/package-readers.ts`：scanLocalPluginPackages、清单四态探测、symlink 候选跳过
  - `plugin/package/filesystem.ts`：canonicalizePluginRoot / PLUGIN_ROOT_SYMLINK
  - `plugin/runtime/repository.ts`：isLocalPluginEnabled=非禁用表、pruneMissingLocalPlugins
  - `plugin/runtime/package-storage.ts`：扫描根 `<dataDir>/plugins`、官方包按 contentDigest 从 v2 cache 恢复
  - `plugin-system.ts`：LocalPluginDirectoryWatcher 接 `dataDir/plugins`
  - `initialize.ts`：officialCacheRoot=`<dataDir>/v2/plugin-cache/official`
  - `plugin/package/agent-plugin-reader.ts` / `compatibility-reader.ts`：两种兼容清单各自可读的组件
  - dist 侧 `dist/main/modules/local-runtime/data-dir.js`：dataDir 解析与 env 覆盖
- 来源类型：本机安装态（`~/.minimax` 目录树、junction 关系 `cmd dir` 证实）
- 来源类型：第三方安装器文档（github.com/minimax-ai/minimax-code-plugins README，2026-09-29 抓取）：无安装命令/目录说明

---

## 4. DeepSeek Deep Code

### 结论：**无插件机制**

- 官方文档（2026-09-29 抓取 https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/deepcode ）通篇只有 Agent Skills：用户级 `~/.agents/skills/<name>/SKILL.md`、项目级 `./.deepcode/skills/<name>/SKILL.md` 自动发现，`/` 键选择器调用。
- 无 plugins 目录、无安装命令、无 marketplace 概念。唯一"扩展"是独立的 VSCode 编辑器扩展（共享设置文件），非 agent 内插件系统。
- 本机安装态：`~/.deepseek`、`~/.dsh` 均不存在（仅 `~/.agents` 存在），确认未装；无本机可对照物。

| 维度 | 答案 |
|---|---|
| (a) 插件本体放哪 | 不存在此概念 |
| (b) 要不要登记 | 不适用 |

---

## 5. OpenCode

### 结论：有 plugin 机制，但**不是 Claude 式插件包**

- 官方文档（2026-09-29 抓取 https://opencode.ai/docs/plugins ）：
  - 全局 `~/.config/opencode/plugins/`、项目 `.opencode/plugins/`；**"Files in these directories are automatically loaded at startup"** —— `.js`/`.ts` 文件放进去即生效，无需登记。
  - 插件本体是导出一个或多个 async 插件函数（返回 hooks 对象）的 JS/TS 模块（事件钩子如 `tool.execute.before`、可注册自定义工具），**不读取 `.claude-plugin/plugin.json`、没有 skills/agents/commands/MCP 组件打包形态**。
  - npm 插件走 `opencode.json` 的 `"plugin": [...]` 数组登记，启动时 Bun 自动安装。
- 对 plugin-hub 的含义：Claude/ZCode/MiniMax 形态的插件包**无法**作为 OpenCode plugin 分发；OpenCode 只能靠 skill 通道（已定稿：`~/.config/opencode/skills/`、`~/.agents/skills/` 等）。

| 维度 | 答案 |
|---|---|
| (a) 插件本体放哪 | `~/.config/opencode/plugins/`（全局）或 `.opencode/plugins/`（项目），且必须是 JS/TS hook 模块 |
| (b) 要不要登记 | 本地文件不需要；npm 包需 opencode.json 登记 |

---

## 6. 对 plugin-hub 分发方案的结论（可执行答案）

| Agent | 链接/放进哪个文件夹 | 登记动作 | 判定 |
|---|---|---|---|
| **Claude Code** | 两条路：① 持久正规通道——本地目录市场：把含 `.claude-plugin/marketplace.json` 的目录 `claude plugin marketplace add`，安装后**原位加载**（源码改了 `/reload-plugins` 即生效）；② 免登记 drop-in——把插件目录放进 `~/.claude/skills/`，作为 `名@skills-dir` 内联插件原位加载（受清单 `defaultEnabled` 控制；同名时优先级最低） | ① 要（两条命令）；② 不要 | ①是唯一支持「改源码即更新」的持久通道；②是唯一零登记通道但优先级最低。`.claude/plugins` 项目目录**不扫描**，别放 |
| **ZCode** | 没有任何"放进即生效"的目录。`zcode plugins marketplace add <本地目录>` + `zcode plugins install 名@市场`（或桌面 UI 等价动作）；装的是**缓存副本**，源码更新需市场刷新 + 插件更新两步 | **必须登记**（installed_plugins.json + config.json enabledPlugins，由 CLI/UI 完成；seed hash 只用于官方捆绑插件补种，不构成障碍） | 双登记、副本制、无热更——分发器只能封装这两条命令 |
| **MiniMax Code** | **`C:\Users\yuele\.minimax\plugins\<name>\` 放物理目录**（带 `.claude-plugin/plugin.json`，其余三种清单亦可），自动发现、默认启用、目录监视热感知 | **不需要**（sqlite 只记禁用表） | 五家中最好的 drop-in 目标；但**必须复制实体目录，junction/symlink/hardlink 一律被拒**（PLUGIN_ROOT_SYMLINK）。注意 dataDir 可被 `MINIMAX_DATA_DIR`/`MAVIS_DATA_DIR` 改写 |
| **DeepSeek Deep Code** | 无插件机制 | 不适用 | 插件不可分发；只走 `~/.agents/skills/` skill 通道 |
| **OpenCode** | `~/.config/opencode/plugins/`（放进去即加载）——但格式必须是 JS/TS hook 模块 | 本地文件不需要；npm 包需 opencode.json | Claude 式插件包不兼容；插件不可复用分发，走 skill 通道 |

### 分发器设计要点（跨 agent 汇总）

1. **三种范式并存**：目录扫描免登记（MiniMax、OpenCode-JS 模块、Claude @skills-dir）／副本+双登记（ZCode）／市场注册+原位加载（Claude 本地市场）。
2. **MiniMax 不能用链接层**：与 skill 分发（agent-roots.md 用 junction 枢纽）相反，plugin 通道必须真实拷贝；同一份源需要落两份实体（或 junction 只用于 skill 侧）。这也意味着 MiniMax 侧没有"单点源"，更新需重新拷贝。
3. **Claude Code 推荐本地目录市场**为持久方案（原位加载解决更新问题），`@skills-dir` 作为免登记兜底；两者都以 `~/.claude` 下路径为根，勿把插件塞进项目 `.claude/plugins/`（不被扫描）。
4. **ZCode 更新语义**：源码版本变更后需要「市场刷新（清单）+ 插件更新（拷贝）」两个用户动作，分发器指南里必须写明，避免误判"已复制=已生效"。
5. **登记文件不手改**：ZCode 的 installed_plugins.json/config.json 虽可手工构造（源码级可行但未实测），一律走 CLI；Claude 的 enabledPlugins 在 settings.json、MiniMax 的禁用表在 sqlite，手改风险高且无文档承诺。

### 未证实事项清单（防误引）

- ZCode：手工直改 `installed_plugins.json`+`enabledPlugins` 指向任意目录能否加载（源码推断可行，未实测）。
- ZCode：加载时是否绝对没有缓存内容 hash 校验（结论是"未发现"而非"不存在"）。
- MiniMax：NTFS junction 被 `lstat().isSymbolicLink()` 判为 symlink 后跳过——Node 语义 + 源码明确，但未做实机启动复验。
- MiniMax：`~/.minimax/plugins/known_marketplaces.json` 这套 Claude 兼容市场层的加载路径（本机无安装实例，仅结构存在）。
- MiniMax：headless CLI 的插件子命令（本机 CLI 入口断链，无法验证）。
- 任务线索中的 github.com/zcode-plugins org 及其 AGENTS.md：GitHub 不可达（404），以本机捆绑 plugin-creator skill 作为官方开发指南等价物。

---

## 7. 追加调研：GitHub 仓库作为分发源（2026-09-29）

**问题**：ZCode 与 MiniMax Code 能否把用户自己的 GitHub 仓库（`https://github.com/yuelezhou/my-claude-plugins-marketplace`）直接作为插件市场源，实现「git push 即分发」。

### 0. 前置事实（本机实测）

- 该 GitHub 仓库**公开可访问**：`git ls-remote` 返回 HEAD=ec5bfaa、curl HTTP 200。本机对 github.com 间歇性连接重置（首次 ls-remote 失败，重试即成功），ZCode 的 git 下载链路内置网络错误重试（见下），与此环境吻合。
- **仓库漂移警示**：本机 `git remote -v` 显示 origin 已指向该 GitHub 仓库（gitee 为独立 remote）；本地 HEAD=0159157（新增 skill-distributor、my-utils 更名 demo-case，manifest 9 条）**尚未推送**，GitHub 端停在 ec5bfaa（manifest 8 条：hello-greeting/my-utils/anki-card-from-notes/mineru-book-ocr/word-frequency/obsidian-skills[github 外链]/plugin-validator/gitee-mcp）。「push 即分发」的第一步是先把本地 commit push 上去。
- 对照实验快照留存于 `C:\tmp\zc-exp-snap\`（known_marketplaces.json / installed_plugins.json / config.json + 两目录清单，含 md5）。

### 1. ZCode：**判定「git push 即分发」可行**

**支持形态**（CLI 源码级：zcode.cjs v0.16.9 `parseMarketplaceSourceInput`；帮助文本原文 "Add a marketplace from a URL, path, or GitHub repo"）：

| 输入形态 | 解析结果 |
|---|---|
| `owner/repo` 简写（含 `/` 无 `:`，可带 `#ref` 或 `@ref`） | `{source:"github", repo[, ref]}` |
| `https://github.com/owner/repo`（.git 可省，可带 `#ref`） | 归一为 `{source:"git", url:"…​.git"}` |
| 其他 `https://…​.git` 或含 `/_git/` 的 URL | `{source:"git", url[, ref]}` |
| 其他 http(s) URL（指向 marketplace.json） | `{source:"url", url}` |
| scp 式 `user@host:path` | `{source:"git", …}` |
| 本地目录 / 本地 `.json` 文件 | `{source:"directory"/"file", path}` |

**github/git 源抓取机制**（源码级）：github 源优先走 **codeload zip 归档**（`https://codeload.github.com/<owner>/<repo>/zip/<ref>`，stripRoot；拒绝 .gitmodules、Git LFS、zip 内 symlink 条目），失败回落 `git clone --depth 1`（可用 `ZCODE_GIT_BINARY` 换 git 二进制；对 Recv failure/ECONNRESET 等网络错误自动重试 3 次）；git 源直接 clone。抓到后整个仓库内容落到 `~/.zcode/cli/plugins/marketplaces/<清单name>/`，清单在 `.claude-plugin/marketplace.json` 查找命中。

**受控实验**（2026-09-29，全程可回滚，已恢复并逐项核对）：

1. `zcode plugins marketplace add yuelezhou/my-claude-plugins-marketplace` → `Added marketplace my-claude-market (8 plugins)`（接受 github 简写形态；id 取清单 `name` 字段）。known_marketplaces.json 新增 `my-claude-market` 条目（source={source:"github",repo:…}、pluginCount:8）；整仓库复制到 `marketplaces/my-claude-market/`。
2. `zcode plugins install hello-greeting@my-claude-market` → `Installed … (1.0.0) [enabled]`。installed_plugins.json 新记录（`source:"./plugins/hello-greeting"` 相对路径、installPath 指 cache 副本）；config.json `enabledPlugins` 增键；`cache/my-claude-market/hello-greeting/1.0.0/` 出现复制体——**插件的 Claude 形态 `.claude-plugin/plugin.json` 清单被直接接受**（源码常量表同时含 `.zcode-plugin/.claude-plugin/.codex-plugin` 三种 plugin.json 路径）。
3. 更新语义实测：`plugins marketplace update my-claude-market` → `Updated … (8 plugins)`（重新抓 GitHub 端最新内容，等价 git pull 的效果）；`plugins update hello-greeting@my-claude-market` → `already up to date (1.0.0)`（按清单版本比对；源码：版本变化时输出 "Updated plugin … Restart zcode to apply"）。即上版报告「市场刷新+插件更新」两步语义对 GitHub 源**同样成立**。
4. 清理：`uninstall`（非交互 shell 需 `--force`）+ `marketplace remove` 后，三份 JSON 与快照 **md5 完全一致**；CLI 会残留 `marketplaces/my-claude-market/`、`cache/my-claude-market/` 目录，手工删除后目录清单与快照 diff 一致。
- 旁支观察：`marketplaces/zc-test-mkt/`（含 demo-plug 内容）是第 2 节上次实验未删净的残留目录（未登记、不参与加载），本次按原状保留未动。

### 2. MiniMax Code：**判定「git push 即分发」半可行**

**核心更正（runtime 源码级，修正第 3 节）**：`~/.minimax/plugins/known_marketplaces.json`（2026-06-06 生成，Claude 格式、记 anthropics/claude-plugins-official）在**当前版本（app.asar mtime 2026-09-27）没有任何代码引用**：
- 全 asar（531MB）归一化检索 + 提取 `@mavis/local-runtime-v2/dist` 全量（2869 文件）与桌面壳层 dist（234 文件）后本地检索：`known_marketplaces`、`installLocation`、`claude-plugins-official` 均 **0 命中**（全 asar 里 "marketplaces" 仅出现在拼写检查词典数据中）。
- 检索方法注记：runtime 编译产物把 `claude` 写成 unicode 转义（如 `'.\u0063\u006c\u0061\u0075\u0064\u0065-plugin/plugin.json'`），字面 grep "claude-plugin" 会误判「不支持 Claude 形态」；实际 `.claude-plugin/plugin.json` 兼容读取仍在（compatibility-reader.js 证实）。
- 结论：第 3 节「加载路径未证实」应升级为「**当前版本已无 Claude 兼容市场层**，该文件是旧版残留」。给 MiniMax 写 marketplace.json 或按 Claude 市场方式登记**均无效**。

**当前版本真正的 GitHub 通道：按插件导入**（`plugin/import/` 模块，runtime 源码级）：
- 入口：runtime HTTP API `previewGithubPlugin` / `importGithubPlugin`（plugin.controller.js + thrift-gen bindings 注册，桌面 UI 插件管理页调用；headless CLI 入口依旧断链；UI 点按未实测，渲染层不在 asar）。
- 接受的 URL（github-source.ts）：
  - `https://github.com/<owner>/<repo>`（仓库根当作单个插件包）；
  - `https://github.com/<owner>/<repo>/tree/<ref>[/<subpath>]`——**支持子目录**，即 monorepo 单插件；ref 先经 api.github.com commits API 解析为完整 SHA，API 不可达时回落 git smart-HTTP advertised refs（`…​.git/info/refs`）；
  - 其他 HTTPS git URL（**含 gitee**）：本地 `git ls-remote --symref` 解析 HEAD + `git clone --filter=blob:none --depth 1` 检出到 pin 的 SHA（需本机装有 git）。
- 下载与校验：github 走 codeload zip（归档 ≤128MiB、包 ≤64MiB/1024 文件、拒路径穿越与 symlink 条目，自动识别 zip 根目录前缀并切 subPath）；随后按四态清单探测（根 `plugin.json` 便携格式 > `.minimax-plugin` > **`.claude-plugin`** > `.codex-plugin`），且**至少含 1 个能力**（skill/MCP/hook），否则 `PLUGIN_NO_SUPPORTED_CAPABILITY`。
- 落点：暂存 `<dataDir>/v2/plugin-import/<tmp>` → **rename 进 `<dataDir>/plugins/<name>/`**（即第 3 节的本地扫描根：自动发现、默认启用，与 drop-in 同一终点）。同名冲突（对官方安装与本地插件查重）→ `PLUGIN_ALREADY_EXISTS`。
- 更新语义：**无就地更新**——源 pin 到 commit SHA，重导入同名插件会撞 `PLUGIN_ALREADY_EXISTS`；更新 = 先删旧（UI 卸载/删目录）再重导入，两步手动、逐插件。

**对用户仓库的可用性评估**：`.claude-plugin/marketplace.json` 对 MiniMax 无意义（无市场层可解析它）；但每个插件目录可经子目录 URL 单独导入，如 `https://github.com/yuelezhou/my-claude-plugins-marketplace/tree/main/plugins/hello-greeting`（各插件均含 skills，满足能力门槛；push 前注意 GitHub 端 hello-greeting 目录为旧版内容）。批量「一次导入全仓」不可行：仓库根无插件清单，导入根 URL 会报 `PLUGIN_MANIFEST_MISSING`。

### 3. 对照组：Claude Code 合规性核对（只读，未执行任何改状态命令）

按官方文档（2026-09-29 抓取 code.claude.com/docs/en/plugin-marketplaces 与 /docs/en/plugins/marketplace-reference）逐字段核对用户仓库 `.claude-plugin/marketplace.json`：

| 核对项 | 要求（文档） | 用户清单 | 结论 |
|---|---|---|---|
| `$schema` | 可选，加载时忽略 | 有 | 合规 |
| `name` | 必填；无空格/控制字符/路径符/保留名 | `my-claude-market` | 合规 |
| `description` | 可选（缺则校验 warn） | 有 | 合规 |
| `owner` | 必填对象，`name` 必填 | `{name:"yuelezhou"}` | 合规 |
| 条目 `name` | kebab-case、无空格、市场内不重复、建议与 plugin.json name 一致 | 9 条全 kebab-case；与 8 个本地插件目录的 plugin.json 逐一比对全部一致 | 合规 |
| 条目 `source`（相对路径） | `./` 前缀、市场根相对、拒 `..` | 8 条 `./plugins/<name>` | 合规 |
| 条目 `source`（对象） | `{source:"github",repo[,ref][,sha]}` 等六种对象形态 | obsidian-skills 用 `{source:"github",repo:"kepano/obsidian-skills"}`（未 pin ref/sha，合法） | 合规 |
| `strict` | 默认 true；仅当条目自身声明组件字段且插件另有 plugin.json 时 `strict:false` 才冲突 | 未设（默认 true），条目均未声明 commands/agents/skills 等组件字段 | 合规，无冲突面 |
| 命名保留字 | 非 ASCII、保留市场名（claude-plugins-official 等）、`github/npm/…` 等词 | 无冲突 | 合规 |

**判定：零改动合规**——本地 commit push 后，`claude plugin marketplace add yuelezhou/my-claude-plugins-marketplace`（owner/repo 简写）即可用。本判定为官方文档级 schema 核对；旁证：同一份清单（8 条旧版）已被 ZCode 的 Claude 兼容解析器在受控实验中成功解析安装（Claude Code 实际 add 动作未执行，属改状态操作）。注意「Claude 市场安装 = 缓存副本」：直连 GitHub 时与 ZCode 同样是「市场刷新+插件更新」两步语义，非原位加载（原位加载仅限本地目录市场）。

### 4. 总判定表：git push 即分发

| 维度 | ZCode | MiniMax Code | （对照）Claude Code |
|---|---|---|---|
| github 仓库作市场源 | **支持**（`owner/repo` 简写等 6 种形态） | **无市场机制**（Claude 兼容市场层为旧版残留，0 代码引用） | 支持（官方通道） |
| 用户仓库实测/合规 | 实测成功（add+install+update 全链路） | 不适用；改支持**逐插件 GitHub 导入**（仓库或 /tree 子目录 URL，落 `plugins/<name>/` 自动发现） | 文档级核对零改动合规（未实测 add） |
| 安装粒度 | 市场内逐插件 | 一次一个插件 | 市场内逐插件 |
| 登记 | 双登记自动（installed_plugins.json + enabledPlugins） | 零登记文件（rename 进扫描根） | 双登记自动 |
| 更新语义 | `marketplace update`（重抓源）+ `plugin update`（版本比对重拷贝，需重启）两步 | 删旧 + 重导入（pin commit SHA，重导入撞名报错） | 市场刷新 + 插件更新两步 |
| **判定** | **可行**：分发器封装 `add` 一次性 + 两条 update 命令即可 | **半可行**：push 后仍需用户在 UI 逐插件导入，且更新为删旧装新两步手动 | **可行**（push 后 add 即用） |

### 证据

- 来源类型：**本机受控实验**（2026-09-29，快照 `C:\tmp\zc-exp-snap`，恢复后三份 JSON md5 与目录清单逐项核对一致；第 2 节上次实验残留 `zc-test-mkt` 目录按原状保留）。
- 来源类型：**ZCode CLI 源码**（zcode.cjs v0.16.9）：`parseMarketplaceSourceInput`（六形态解析）、`PJr`/`hJr`（github→codeload zip、git→clone、file/directory/url 分支）、`ndn`（归档下载，拒 LFS/submodules/symlink）、`k8s`（`git clone --depth 1`，3 次网络重试、`ZCODE_GIT_BINARY`）、`Tre`/`gdn`（add/update 落盘）、帮助文本 "URL, path, or GitHub repo"。
- 来源类型：**MiniMax runtime 源码**（app.asar 内 `@mavis/local-runtime-v2/dist` 全量提取至 `C:\tmp\mcode-dist2`，与既往 `C:\tmp\mcode-src` 的 TS 源对照）：`plugin/import/github-source.ts`、`github-archive.ts`、`github-plugin-importer.ts`、`plugin-system.ts#importGithubPlugin`（PLUGIN_ALREADY_EXISTS、落点）、`package-storage.ts#acceptImportedLocalRoot`（rename 进 plugins 根）、`package-readers.ts#readImportedPluginPackage`、`http/controllers/plugin.controller.js` + `http/routing/bindings.gen.js`（previewGithubPlugin/importGithubPlugin 注册）；unicode 转义见 `dist/.../compatibility-reader.js` 第 6 行。
- 来源类型：官方文档（2026-09-29 抓取）：code.claude.com `/docs/en/plugin-marketplaces`、`/docs/en/plugins/marketplace-reference`、`/docs/en/plugins-reference`。
- 来源类型：本机 git 实测：`git ls-remote`（HEAD=ec5bfaa，公开可访问）、本仓库 `git remote -v` / `git log`（本地 0159157 未推送，GitHub 端清单落后 1 个 commit）。

### 未证实事项（追加）

- MiniMax：桌面 UI 中「从 GitHub 导入插件」入口的实际呈现与点按流程（runtime API 面已证实，渲染层不在本机 asar 内）。
- MiniMax：导入时 `plugin.json`（便携格式）与 `.claude-plugin` 并存时的取舍已从源码确认为根 plugin.json 优先，未做实机导入复验。
- ZCode：github 源在 codeload 被墙/失败时回落 `git clone` 的实机触发路径未单独复现（实验中一次成功，未观察回落）。
- 本机对 github.com 的间歇性连接重置是否影响上述通道的日常可用性：未做长周期观测（ZCode 有重试，MiniMax github 路径依赖 api.github.com / codeload.github.com 直连，gitee 路径依赖本地 git）。

## 8. 重验补注：MiniMax「插件市场」与 GitHub 注册之辨（2026-09-29）

维护者质疑「MiniMax Code 也支持注册 GitHub 市场」，据此对 507MB app.asar（runtime 5.2.0）做全量 ASCII 标识符检索复核（ASCII 不受 unicode 转义影响，否定性命中可靠）。

**核实为真的（维护者观察有据）**：

- MiniMax **有插件市场**：桌面 UI 存在「CC Marketplace」区块（i18n `section_marketplace`，与 `section_opencode:"OpenCode Plugins"`、`from_local` 并列，按来源分组展示插件），背后是官方云端策划市场 API——`GET /minimax-desktop/api/v1/marketplace/plugins`（列表，带 Productivity/Business 等分类）、`GetMarketplacePlugin`、推荐加载（`plugin_marketplace.recommendation_load_failed`）等
- **GitHub 能力真实存在**：`ImportGithubPlugin`/`PreviewGithubPlugin`（`/plugins/github/import|preview`），接受 GitHub URL（含 `/tree/<ref>/plugins/<名>` 子路径）

**「注册自定义 GitHub 仓库为市场源」仍不成立的理由**：

1. Claude 式市场注册机制的专属标识符——`known_marketplaces` / `knownMarketplaces` / `installLocation` / `addMarketplace` / `MarketplaceRegistry` / `claude-plugins-official`——在全 asar 中 **0 命中**（上版"已无此层"结论由推测升级为可靠否定）
2. DesktopService 全部插件端点枚举（12 个）中**没有任何"添加/注册市场源"端点**：市场侧只有官方的两个只读 API；写侧是逐插件 github import 与生命周期管理
3. `importGithubPlugin` 语义是「导入单个插件目录」（仓库根无清单报 PLUGIN_MANIFEST_MISSING，更新=删旧重导），落点是本地物理目录——等价于"逐插件拉取"，不是"市场源注册"（无清单联动、无批量、无源级刷新）

**结论修正**：第 7 章「MiniMax 无市场机制」表述过强，应为——**有官方策划市场（CC Marketplace，云端固定源、用户不可注册自定义源）+ 逐插件 GitHub 导入**；对本仓库分发的可行判定不变（半可行：逐插件导入或脚本拷贝）。

**未证实**：待安装的 3.0.74 更新包是否引入市场注册能力（update-info 无 changelog）；桌面 UI 是否存在源码之外的隐藏入口（如有，维护者指出入口位置即可定向挖掘）。

### 8.1 UI 截图与 CLI 实测佐证（2026-09-29，维护者提供截图）

维护者提供插件管理页截图，与源码结论逐项对上：

- 「市场」页签 = 官方策划商店实拍（74 个插件、全部/办公/创作/代码等分类），即 `ListMarketplacePlugins` API 的 UI；页面只有「管理」「创建」按钮，**无任何"添加自定义市场源"入口**
- 「创建」菜单 = 「自定义插件」「**从 Git 仓库导入插件**（支持 Agent Plugins 1.0、MiniMax Plugin 和其他兼容格式）」及技能类三项——导入为**单插件粒度**，按钮描述自证与 `ImportGithubPlugin` 通道一致
- **CLI 实测**：`~/.minimax/bin/minimax.cmd --version` 抛 node 模块加载错误——包装器指向的 `resources\resources\daemon\cli.js` 不存在，CLI 入口断链实锤；桌面应用运行中（3 个 MiniMax Code.exe 进程）但 `/minimax-desktop/api/v1/*` 不在任何对外监听端口（抽查 127.0.0.1:2513 实为无关进程 AutoGLM）
- `local-runtime.auth.json` 为云端登录 JWT（用户身份），非本地 daemon 令牌

**定论**：MiniMax 插件添加**仅 UI 可操作**（或脚本走文件系统 drop-in 等价替代）；分发器实现维持「MiniMax = 物理拷贝」路线不变。
