# 外部聚合插件更新契约（check / update 全量对外行为）

`plugin_updater.py` 的完整行为规范。`SKILL.md` 里的 Procedure 与六步链摘要是本文的速查版；这里写全量口径，供执行前对照、出错排查和后续改代码时定位测试点。与实现不一致时**以脚本为准**（事实来源：脚本模块 docstring + `--help` + `test_plugin_updater.py`）。成文基准：feature/plugin-updater @ 70a7309 之后、票 05 交付前。

## 治理对象与三线消费模型

市场里 `source.source == "github"` 的引用式条目（当前：mattpocock-skills、obsidian-skills）是治理对象；本地路径条目（source 为字符串）直接过滤，不是治理对象。同一条上游在三条消费线上各有一份状态，工具全都要报：

| 线 | 状态载体 | 工具动作 | 数据来源 |
|---|---|---|---|
| pin 线 | `marketplace.json` 条目的 `metadata.pinnedRef/pinnedSha/pinnedAt` | 比对 + bump / 建基线（update 可写） | `git ls-remote <github-url> <ref>` 取上游 head；版本号取 raw `raw.githubusercontent.com/<repo>/<sha>/.claude-plugin/plugin.json` 的 `version` |
| 枢纽线 | `~/.agents/skills/` 里的族实体（安装正本） | 比对（check）/ 三方同步（update 可写） | pin 处 codeload tarball（`codeload.github.com/<repo>/tar.gz/<sha>`）解包出的基线树 |
| 副本线 | ZCode / Claude Code 各自安装的**插件**副本 | 只报告 + 打印刷新命令，**永不代跑** | `~/.zcode/cli/plugins/` 与 `~/.claude/plugins/` 下的 `installed_plugins.json` + `known_marketplaces.json` |

- pin 线**不走 GitHub API**（匿名限流），全部走 `git ls-remote` 与 codeload；需要 `git` 在 PATH 与网络。`main` 这类短 ref 会同时命中 `refs/heads/changeset-release/main`，解析只认精确行（`refs/heads/<ref>` / `refs/tags/<ref>` / 原样），没有精确匹配就报错——静默取首行会把发布分支误当 head。
- 版本号拉取失败只标「版本号未知」，不算失败、不影响判定。
- 副本线「本仓库市场」的识别：`known_marketplaces.json` 里 source 路径（ZCode `source.path`；Claude Code `source.path` 或 `installLocation`）归一化后等于市场仓库根。无法确认属于本仓库时按**其他市场**报告（保守，宁报不漏）；MiniMax 无插件安装记录，恒报「未安装」并注明原生读枢纽。

## check 语义（只报告，不写任何文件）

三段报告依次输出：

1. **pin 线**——逐条目给 ref / pin / head / 版本 / 结论。结论四种：
   - **已最新**：pin==head（SHA 大小写不敏感）。不动。
   - **有更新**：pin 落后于上游 head。人工确认后 `update`（先 `--dry-run` 预览）。
   - **无基线**：`marketplace.json` 无 `pinnedSha`。报告附上游当前 head，用户点头后 `update --entry <名>` pin 到当时 head 建基线。
   - **查询失败**：单条目远端不可达。不影响其余条目，重跑或查网络。
   - 汇总行：`已最新 X / 有更新 X / 无基线 X / 查询失败 X`。
2. **枢纽同步线**——只有带 pin 的条目参与（无 pin 条目在段首注明跳过：无基线无族）。逐条目下载 pin tarball、动态派生族成员、逐成员报三方状态：
   - **已同步**：枢纽实体与 pin 基线内容逐字节一致（行尾差异不算，见 CRLF 归一）。
   - **与基线不一致（落后或手改）**：check **不做**落后/手改区分——那是 update 用旧 pin 树三方分类的事。
   - **缺失**：枢纽缺该族实体（update 会补装入）。
   - 条目级失败（下载/解包/派生）记「枢纽线查询失败」附可读错误后继续其余条目。
3. **副本线**——逐条目 × 逐 agent（ZCode / Claude Code / MiniMax）报：未安装 / 已装（本仓库市场，无需处理）/ 已装（其他市场）+ 已装版本、来源市场、上游 sha + 刷新命令（`zcode plugins marketplace update <市场>` + `zcode plugins plugin update <id>`；`claude plugin update <id>`）。

退出码只看前两条线：**0**=全部已最新且枢纽全同步；**1**=有更新/无基线/查询失败/枢纽有差异或枢纽线查询失败；**2**=仓库根定位失败。副本线不影响退出码（外部市场副本是常驻消费线，不是 check 能消除的漂移）。

## update 语义（六步链；全部条目先计划后写入）

对有新版的条目（`--entry` 限定时对指定条目）依序六步。两阶段**全或无**：阶段一（步骤①②）对全部目标条目做计划，任一条目在任一环节失败（head 查询 / 默认分支解析 / tarball 下载解包 / 校验门）就整链不进写盘阶段——失败的更新不留半成品。已最新（skip）条目跳过且**不进枢纽同步**（真机 pin==head 时 update 零动作，幂等）。

1. **下载新旧 SHA tarball**：旧 pin 树在 bump 前先落地（三方分类需要旧基线；bump 完旧 SHA 就从 marketplace.json 消失了）。解包后把树根目录名规范成 plugin.json 的 `name`——codeload 顶层目录是 `<repo>-<sha>`，而 validator 校验 name 与目录名一致，不解齐会出假阻断。
2. **校验门**（详见下节）。
3. **bump + compat 表格**：`pinnedSha` → 新 head、`pinnedAt` → 当天（`pinnedRef` 原样；`note` 只同步内嵌旧 SHA（全串→12 位→7 位，长串优先防前缀截断）/ 旧日期的文字，其余内容不代拟）；同步 `docs/plugin-compatibility.md`「外部聚合插件」表格该条目行的 pin 列（第 3 列精准行替换，其余行列不动；表里没该行则跳过并注明，不算失败）。**建基线**（无 pin 条目）：pin 到当时 head，写齐 `pinnedRef`（`git ls-remote --symref` 取上游默认分支）/`pinnedSha`/`pinnedAt`，照走同一校验门。写盘前与原字节比对，无变化不写（重复 apply 字节级零改动）；marketplace.json 的 BOM / CRLF / 缩进 / 末尾换行跟随原文件。
4. **枢纽族实体三方同步**（详见下节）。
5. **链接层同步**：有实际结构变化（装入/删除）时调 skill-distributor 的 `link` 子命令（`sys.executable`，cwd 与 `--root` 都指仓库根）。失败**不回滚**已写入，报告给手动补救命令：`python plugins/skill-distributor/skills/skill-distributor/scripts/skill_distributor.py link`。
6. **收尾报告**：逐条目计划（bump 旧→新 / 建基线 / 已最新跳过）、失败明细（阶段 + 阻断 error 清单）、写入结果、覆盖/保留/新增/删除清单（保留带原因）、副本线刷新命令。

## 三方分类（枢纽实体 × 旧 pin 树 × 新 pin 树）

族成员 = pin 处上游 `skills/` 下 **engineering / productivity / misc** 三个分类的一级子目录，**动态派生**（上游增删 skill 工具不用改）；`deprecated` / `in-progress` 不在分类清单里，结构上就进不了族——「永不装入」由派生规则保证而非运行时过滤。建基线（无旧树）时不存在「干净落后/已移除」概念：枢纽==新树不动；枢纽!=新树保守保留（无基线可证清白）；枢纽缺则装入。五个动作：

| 动作 | 判定 | 处置 |
|---|---|---|
| 干净落后覆盖 | 枢纽==旧 pin 且 != 新 pin | **直接覆盖，不问**（内容=批准过的旧基线，覆盖不丢东西；三十多个成员逐个问违背升级本意）。覆盖=删旧树拷新树，无自动备份（无状态设计） |
| 与基线不一致 | 枢纽 != 旧 pin（手改或未知状态） | 默认**保留**并在报告标注；交互终端逐个问「覆盖/保留/看 diff」（o/k/d，diff 为文件级差异摘要：仅枢纽有/仅基线有/内容不同）；`--adopt` 显式声明枢纽无手改后全部按干净落后覆盖 |
| 上游新增 / 枢纽缺失 | 仅新 pin 有 | **装入**枢纽；`--yes` 自动，交互下批量确认一次（可拒，拒则保留并标注） |
| 上游已移除 | 仅旧 pin 有而新 pin 没有，且枢纽还在 | 交互终端**逐个**确认后连枢纽实体与链接层条目一起删；非交互必须显式 `--delete-removed`，否则保留并在报告标注原因 |
| 已同步 | 枢纽==新 pin | 不动 |

链接层安全纪律（绝对红线）：枢纽目标是 junction/symlink 时**拒绝覆盖并报错**（绝不写穿链接改到链接目标——枢纽里自研 skill 的正本链接就在其中）；删已移除成员的链接层条目用 `os.rmdir` 只摘链接本身，**绝不递归删穿 junction 的目标**。单项失败（如 junction 拒覆盖）不中断其余成员，但会使该条目带错误项 → update 退出码 1。

## 校验门

对解包的新版本树跑 `check_plugin.py <树> --standalone`（仓库内相对路径 `plugins/plugin-validator/skills/plugin-validator/scripts/check_plugin.py`）：

- 放行判据是**输出内容**而非退出码：收集全部 `ERROR ` 行；无阻断 error 且输出可识别才放行。
- **「缺少 .minimax-plugin/plugin.json」对外部引用式条目特判 N/A 不阻断**（本地无源码、不分发给 MiniMax——2026-10-18 手动重 pin 先例），其余 error 照常阻断；豁免项在报告注明数量。
- 输出里没有「结果:」汇总行 = 不可识别（脚本缺失/崩溃），**保守按未通过处理**；validator 脚本本身不存在直接报错——门没有证据时绝不放行。
- 未通过 → 该条目进失败通道 → 全链中止、零写入。

## 交互矩阵

| 旗标 | 适用 | 语义 | 缺省 |
|---|---|---|---|
| `--root <仓库根>` | check / update | 指定 market 仓库根 | `MARKET_REPO` 环境变量 → 从脚本真实位置向上推导（realpath 会把枢纽 junction 解析回仓库，经枢纽触发也能找到）；找不到退出码 2 |
| `--hub <目录>` | check / update | 枢纽 skills 目录 | `~/.agents/skills` |
| `--link <目录>` | update | 链接层 skills 目录（仅删上游已移除成员时清理用） | `~/.claude/skills` |
| `--entry <名>` | update | 限定单条目；只接受 github 引用式条目名 | 全部外部条目；名字不存在退出码 2 |
| `--yes` | update | 确认执行变更；**非交互环境（stdin 非 tty）缺它拒绝一切变更**（退出码 2） | 交互 tty 下可缺；给了它则跳过全部 prompt |
| `--dry-run` | update | 只打印将做的变更，不写任何文件 | 唯一豁免 `--yes` 的动作；不触发 prompt、不计结构变化、不调链接层 |
| `--adopt` | update | 声明枢纽无手改：与基线不一致实体按干净落后覆盖 | 不一致默认保留 |
| `--delete-removed` | update | 非交互删除上游已移除实体（连链接层） | 非交互保留并标注；交互模式逐个确认即可，无需此旗标 |

运行形态与决策默认（三方分类落到 prompt 的方式）：

| 形态 | 不一致实体 | 新增装入 | 已移除删除 |
|---|---|---|---|
| 交互 tty、无 `--yes` | 逐个问 覆盖/保留/看 diff | 批量问一次（y/n） | 逐个问（y/n） |
| `--yes`（含非交互 + `--yes`） | 保留（`--adopt` 则覆盖） | 自动装入 | 仅 `--delete-removed` 才删 |
| `--dry-run` | 按计划展示，不问 | 按计划展示 | 按计划展示 |

## 退出码

| 码 | check | update |
|---|---|---|
| 0 | 全部已最新且枢纽全同步 | 更新成功，或无需更新（全部已最新零动作） |
| 1 | 有更新 / 无基线 / 查询失败 / 枢纽有差异 / 枢纽线查询失败 | 任一条目失败全链中止（零写入）；枢纽同步有错误项；链接层同步失败 |
| 2 | 仓库根定位失败 | 用法/输入错误：非交互缺 `--yes`、`--entry` 条目不存在、仓库根定位失败 |

副本线三种状态都不影响退出码。

## 无状态基线设计

- **pin 即基线**：`marketplace.json` 的 `metadata.pinnedRef/pinnedSha/pinnedAt` 是唯一基线，不写任何 sidecar 状态/缓存文件。clone 下来即可判定同步状态，复现流程不变；枢纽比对每次现下载 pin tarball，无本地缓存可失效。
- 核对与同步结果**不回写** PROMPT-INSTALL.md（台账保持声明式语义，只记用什么和怎么装，不记安装状态）；pin bump 时同步的只有 compat 文档表格。
- `pinnedAt` 用运行当天日期（注入点见下），`note` 是人工备注，工具只同步其中内嵌的旧 SHA/日期文字。

## CRLF 归一

所有内容比对（check 枢纽线、update 三方分类、diff 摘要）读文件后先把 `\r\n` 归一为 `\n` 再比。codeload 基线是 LF，Windows 安装链（git clone / 解压）落盘常是 CRLF——行尾差异是安装链的产物不是内容漂移，拉平后真正的手改/落后仍然可见。文件集合不同（增删文件）照常算漂移。

## 注入接缝（改代码前先读：测试点定位）

外部访问收敛为**effect 函数**（唯一出入口，回归测试在这里注入假件），与纯决策层、编排层分离——改行为先确认改的是哪层：

| 层 | 函数 | 测试方式 |
|---|---|---|
| effect（外部访问） | `fetch_remote_head` / `fetch_upstream_version` / `fetch_tarball`（+`download_to_file`）/ `fetch_remote_default_ref` / `run_validator` / `run_link_sync` | 假函数注入；`download_to_file` 有 file:// 离线路径 |
| 纯决策 | `parse_external_entries` / `parse_ls_remote_output` / `parse_symref_output` / `parse_upstream_plugin_json` / `judge_entry` / `derive_family_members` / `judge_hub_members` / `compare_tree`（CRLF 归一在这）/ `classify_family_sync` / `diff_tree_summary` / `judge_validator_output` / `apply_pin_bump` / `render_pin_cell` / `sync_compat_table` / `serialize_marketplace_bytes` / `collect_copy_line`（+来源市场识别）/ `decide_exit_code` / 各 build_*_report | 直接断言输入→输出 |
| 交互 | `prompt_mismatch`（o/k/d 循环）/ `prompt_batch_install` / `prompt_removals` | 收 `input_fn`，注入应答序列 |
| 编排 | `run_check` / `run_hub_check` / `plan_updates` / `apply_updates` / `sync_hub_families` / `cmd_update` | 逐参注入决策函数（`decide_mismatch` / `confirm_installs` / `decide_removals` / `run_link` / `validator` / `get_tarball` / `today` 等）；假仓库根与假枢纽搭在 tmp 目录 |

回归测试 `test_plugin_updater.py`（同目录，73 用例，退出码 0=全过 / 1=有失败）：接缝全在内存与 tmp，**网络不进测试**；真实网络路径靠真跑一次 `check` 覆盖。给假件、断言决策结果与产物文件，不断言内部调用细节。`plan_updates` 的 `today` 参数注入固定日期——涉及 `pinnedAt` 的断言不要依赖系统时钟。

## 已知真机口径（2026-10-18 交付时，会随时间漂移，仅作对照）

- mattpocock-skills pin `49dd158d`（v1.3.1）== 上游 head，check 报「已最新」；枢纽 31 个族成员 29 已同步、2 个已知措辞漂移实体与基线不一致（见下条），要等下次上游更新（或手工 `--adopt`）才收敛——首次真实升级已于 2026-10-18 手动完成，`--adopt` 留给未来漂移。
- 族规模两种口径：插件清单（`.claude-plugin/plugin.json` 的 `skills` 数组）只注册 engineering+productivity 共 27 个；plugin-updater 按三类目录全口径派生 31 个（含 misc 4 个）。见 PROMPT-INSTALL.md 族行。
- ZCode 副本已随手动重 pin 升到 v1.3.1 @ `49dd158d`（官方市场来源，spec 里的 v1.2.3 @ `3cca18b3` 是升级前旧况）；obsidian-skills 无 pin，check 报「无基线」。
- 2 个已知措辞漂移实体（git-guardrails-claude-code、setup-pre-commit）等下次上游更新（或手工 `--adopt`）才收敛。
