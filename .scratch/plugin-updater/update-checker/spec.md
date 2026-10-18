Plugin: plugin-updater
Status: ready-for-agent
Category: enhancement

# plugin-updater：外部聚合插件的更新检查与一键升级

## Problem Statement

市场里有外部聚合插件（引用式 + pin），但「pin 之后的生命周期」没有工具管：上游 mattpocock/skills 的 main 已经从 pin 的 `484efcbe`（v1.2.4）走到了 `49dd158d`（v1.3.1），没有机制能发现这件事，更没有机制把新版本安全地铺下去。今天三处消费线各漂各的——仓库 pin 落后、ZCode 装的官方市场副本停在 v1.2.3、枢纽 `~/.agents/skills/` 里 31 个族实体是 8 月 6 日装的旧版且无任何版本记录。手动更新流程（compat 文档写的「重取 SHA → 重跑校验 → 更新 pin」）从未被执行过，因为步骤多、易漏、还要处理 31 个实体的覆盖问题。

## Solution

新插件 **plugin-updater**：一个工具、两个子命令。

- `check`——只报告：每条外部聚合条目的 pin SHA vs 上游 head（附上游版本号）、枢纽族实体相对 pin 基线的同步状态（已同步 / 落后 / 与基线不一致）、无 pin 条目（报「无基线」）、其他市场来源的已装插件副本（附刷新命令）。退出码 0 = 全部最新且同步，1 = 有更新或漂移。
- `update`——六步链：下载新 SHA tarball → `plugin-validator --standalone` 校验门（非 0 error 中止、不写任何文件）→ bump marketplace.json 的 pin 并同步 compat 文档表格 → 枢纽族实体按三方分类同步 → 调 skill-distributor 的 link 同步链接层 → 打印各 agent 插件副本的刷新命令。

升级时用户只操作这一个插件；skill-distributor 被它内部代为调用，不是第二个要手动开的工具。

## User Stories

1. As a 个人市场维护者, I want 一条命令查所有外部聚合插件是否落后于上游, so that 不用手工逐个 `git ls-remote` 比对 SHA
2. As a 个人市场维护者, I want 报告同时给出上游版本号而不只是 SHA, so that 一眼看出落后了几个功能版本
3. As a 个人市场维护者, I want check 同时报告枢纽族实体相对 pin 基线的同步状态, so that 知道各 agent 实际跑的 skill 是不是批准过的版本
4. As a 个人市场维护者, I want 无 pin 条目被报告为「无基线」并附上游当前 head, so that 知道哪些条目还没纳入治理
5. As a 多 agent 用户, I want check 对来自其他市场的已装插件副本给出刷新命令, so that 三条消费线的状态一眼全清
6. As a 个人市场维护者, I want update 在写入前强制过 plugin-validator --standalone 校验, so that 未经校验的上游版本永远进不了我的市场
7. As a 个人市场维护者, I want 校验不过时中止且不留下任何写入, so that 失败的更新不留半成品
8. As a 个人市场维护者, I want update 自动 bump marketplace.json 的 pin 并同步 compat 文档表格, so that 不用手改两处还会漏
9. As a 个人市场维护者, I want 干净落后（枢纽内容与旧 pin 完全一致）的族实体被直接覆盖, so that 常规升级不用逐个确认三十多个 skill
10. As a 可能手改过 skill 的用户, I want 与 pin 基线不一致的实体默认保留并标出, so that 我的手改不会被静默覆盖
11. As a 可能手改过 skill 的用户, I want 交互模式下对不一致实体逐个选择 覆盖/保留/看 diff, so that 精细控制每个 skill 的去向
12. As a 首次使用的用户, I want 用 --adopt 显式声明「枢纽无手改」让首次收敛一键完成, so that 不用为几十个旧实体逐个按确认
13. As a 个人市场维护者, I want 上游新增的族 skill 自动装入枢纽, so that 新能力不用手动发现手动装
14. As a 个人市场维护者, I want 上游已移除的 skill 交互确认后连同枢纽实体和链接层一起删除, so that 死 skill 不残留也不误删
15. As a 会无人值守运行的用户, I want 非交互环境下删除动作必须显式 --delete-removed, so that 自动化永远不会删我的正本
16. As a 只要稳定版的用户, I want deprecated 与 in-progress 分类永不装入枢纽, so that 上游 WIP 不混进我的稳定集
17. As a 个人市场维护者, I want 族成员由 pin 处上游目录清单动态派生而非硬编码, so that 上游调整分类或增删 skill 时工具不用跟着改
18. As a Claude Code 用户, I want update 完成后自动跑链接层同步, so that 新增/删除的 skill 在 Claude Code 侧自动可见
19. As a 个人市场维护者, I want update 结束打印各 agent 插件副本的刷新命令, so that 剩余的手工动作有明确清单
20. As a 要在新机器复现的用户, I want pin 是唯一基线、无额外状态文件, so that clone 下来就能判定同步状态，复现流程不变
21. As a 同时用多个 agent 的用户, I want 升级只操作枢纽一份实体, so that ZCode / MiniMax / OpenCode / DeepSeek 全部自动生效
22. As a 会话里的 agent, I want check 用退出码区分「全部最新」与「有更新或漂移」, so that 我能程序化判断是否该提示用户升级
23. As a 会话里的 agent, I want 非交互模式无 --yes 时拒绝执行任何变更, so that 误触发不会改任何东西
24. As a 台账维护者, I want 工具永不回写 PROMPT-INSTALL.md 的安装状态, so that 台账保持声明式语义
25. As a Windows 用户, I want 输出中文且 UTF-8 安全, so that 终端不乱码
26. As a 个人市场维护者, I want update 能为无 pin 条目建立首个基线（pin 到当时 head 并过校验门）, so that obsidian-skills 这类休眠条目一次纳入治理

## Implementation Decisions

- **独立插件**，不挂 skill-distributor 子命令：分发/台账与上游新鲜度治理是两个职责；与 skill-distributor 的唯一衔接是更新链末尾调用其 link 子命令。
- **双消费线模型**：工具只直接管「仓库 pin」与「枢纽族实体」两条线；对其他市场来源的已装插件副本只打印刷新命令，不代跑（版本线独立，且 ZCode/MiniMax 等本就原生读枢纽，插件副本日常冗余）。
- **判定方式**：`git ls-remote` 取上游 pinnedRef 的 head SHA 与 pinnedSha 比对；版本号从上游 plugin.json（raw）取。不用 GitHub API（匿名限流）。无 pin 条目无基线可比，check 报「无基线」，update 可 pin 到当时 head 建基线（照走校验门）。
- **tarball 复用**：codeload 任意 SHA 下载 tarball，一次下载同时服务校验门（解包后校验）与实体同步（拷贝来源）。
- **族派生规则**：族成员 = pin 处上游 `skills/` 下 engineering、productivity、misc 三个分类的目录清单，动态派生；deprecated 与 in-progress 永不装入。
- **三方分类语义**（枢纽实体 × 旧 pin × 新 pin）：
  - 枢纽 == 旧 pin 内容 → 干净落后，`--yes` 下直接覆盖；
  - 枢纽 ≠ 旧 pin 内容（手改或未知状态）→ 默认保留并标出；交互逐个问「覆盖/保留/看 diff」，`--adopt` 显式声明枢纽无手改后才允许批量覆盖；
  - 仅新 pin 有 → 上游新增，装入（交互批量确认一次）；
  - 仅旧 pin 有 → 上游已移除，交互逐个确认后连枢纽实体与链接层一起删；非交互必须显式 `--delete-removed`，否则保留并报告。
- **交互矩阵**：非交互环境（检测 tty）无 `--yes` 拒绝一切变更；`--entry <名>` 限定单条目；`--root` 指定 market 仓库根（对齐 skill-distributor 的惯例）。
- **校验门**：解包的新版本树必须过 plugin-validator 的 standalone 校验且 0 error，否则中止且无任何写入（校验门也是测试接缝的注入点之一）。
- **外部访问收敛为可注入函数**：远端 head 查询、tarball 获取、validator 调用三个 effect 函数与纯决策层分离——这是唯一的测试接缝。
- **无状态**：不写任何 sidecar 状态文件；pin（marketplace.json）即唯一基线。
- **台账纪律**：核对与同步结果不回写 PROMPT-INSTALL.md；pin bump 时同步 compat 文档的外部聚合插件表格。
- **仓库规范**：UTF-8 输出重配置；Windows + Git Bash 环境；纯标准库（urllib / tarfile / subprocess / json），不引第三方依赖。

## Testing Decisions

- 好测试只测外部行为：给假件、断言决策结果与产物文件，不断言内部调用细节。
- 被测模块：外部条目解析、pin 比对、族成员派生、三方分类、pin bump 后的清单产物、check 报告生成、tmp 目录下的实体落地语义（覆盖 / 保留 / 新增 / 删除）。
- 接缝：外部全假件——假的上游（固定 SHA + 预置目录树）、假的 validator runner（可返回通过/失败）、假仓库根与假枢纽搭在 tmp 目录。真实网络与真 validator 不进回归测试，靠真跑一次 check 验证。
- 先例：word-frequency 的回归测试——sys.path 注入被测脚本、内存接缝、中文 docstring 说明覆盖面、退出码 0（全过）/ 1（有失败）。

## Out of Scope

- PROMPT-INSTALL.md 里单名第三方 skill（apifox、git-guardrails 等已归族的除外）的更新——它们无 pin 机制，另立需求再说
- 代跑各 agent 的插件刷新命令（只打印，设计定的边界）
- 自研插件的版本号管理（手动改双清单，与上游无关）
- 状态文件 / 缓存层（无状态设计，嫌慢了再议）
- ADR（决策已记录在 compat 文档与 CONTEXT.md 术语表，不满足「难逆转」标准）
- 首次真实升级的执行本身（工具交付后单独跑，见 Further Notes）

## Further Notes

- 本 spec 由 2026-10-18 的 grilling 会话产出（grill-with-docs + domain-modeling），设计树全部分支已与维护者对齐；术语（外部聚合插件 / pin / skill 族）已入 CONTEXT.md。
- **基线变更（2026-10-18 spec 发布后）**：维护者已手动走完整条更新链——pin 重 pin 到 `49dd158d`（v1.3.1）、枢纽实体同步、resolving-merge-conflicts 删除、implement-spec/pr/retro 装入、校验按「缺 .minimax-plugin 对外部条目 N/A」特判通过。**工具交付时真机初始状态 = 已收敛**：check 应报「全部族实体已同步」，`--adopt` 保留用于未来漂移而非首次收敛。ZCode 副本仍为 v1.2.3 @ `3cca18b3`（官方市场来源）。
- 现实案例已验证分类规则的必要性：上游新增 implement-spec / pr / retro（已手动装入）；上游已移除 resolving-merge-conflicts（已手动删除）；台账四条「来源待补」实为 misc 族（spec 交付时一并修正 PROMPT-INSTALL.md，族行计数已由并行升级改为 27，归族仍待补）。
- 交付物清单：插件本体（双清单 + 明暗图标 + 单 skill + 脚本 + 回归测试 + references 契约）、市场注册条目、PROMPT-INSTALL.md 族归属修正、compat 文档更新政策、plugin-validator 0 error。
