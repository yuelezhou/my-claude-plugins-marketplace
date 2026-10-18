---
name: plugin-updater
description: |
  外部聚合插件的更新检查与升级工具，两个子命令：
  ① check 一条命令看三条线——pin 线：读市场 marketplace.json 的 github 引用式
  条目，用 git ls-remote 比对 pin SHA 与上游 head（不走 GitHub API，免匿名限流），
  附上游版本号，无 pin 条目报「无基线」并附当前 head；枢纽同步线：下载 pin 处
  tarball，动态派生族成员（engineering/productivity/misc 三分类，
  deprecated/in-progress 永不装入），报 ~/.agents/skills/ 里每个族实体相对 pin
  基线的状态（已同步 / 与基线不一致（落后或手改）/ 缺失）；其他市场副本线：读
  ZCode / Claude Code 的插件安装记录，对装自其他市场的外部条目副本报版本/来源
  市场/上游 sha 并打印刷新命令（只打印不代跑）。
  ② update 走完六步更新链——下载新旧 SHA tarball（旧 pin 树在 bump 前落地，
  三方分类要用）→ plugin-validator --standalone 校验门（非 0 阻断 error 全链
  中止、零写入；「缺 .minimax-plugin」对外部引用式条目特判 N/A）→ bump
  marketplace.json 的 pinnedSha/pinnedAt（note 只同步内嵌旧 SHA/日期的文字）
  → 同步 docs/plugin-compatibility.md「外部聚合插件」表格的 pin 列 →
  枢纽族实体三方同步（枢纽实体×旧 pin×新 pin：干净落后直接覆盖；不一致默认
  保留并标出，交互逐个问「覆盖/保留/看 diff」，--adopt 声明无手改后批量覆盖；
  上游新增装入；上游已移除连链接层 junction 一起删，非交互须 --delete-removed）
  → 有结构变化时调 skill-distributor link 同步链接层 → 打印各 agent 插件副本
  刷新命令收尾。无 pin 条目可 pin 到当时 head 建基线（照走同一校验门）。
  全部条目先计划后写入（全或无），--dry-run 预览、--entry 限定单条目、
  非交互必须 --yes。
  触发：用户说"检查外部插件更新"、"mattpocock 有新版吗"、"外部插件有没有新版本"、
  "pin 落后了没"、"枢纽里的 skill 和 pin 一致吗"、"更新外部聚合插件"、
  "把 mattpocock 升到最新"、"给 obsidian-skills 建 pin 基线"、
  "同步枢纽里的族 skill"，
  或交付前要确认市场外部条目与各 agent 消费线是否落后于基线时。
  不用于：自研插件的版本号管理（手动改双清单，与上游无关）、
  skill 分发与台账核对（用 skill-distributor）、插件结构校验（用 plugin-validator）、
  marketplace 插件的安装（走各 agent 自己的 CLI）、代跑插件刷新命令（只打印）。
displayNames:
  zh-Hans: "外部插件更新检查"
---

# Plugin Updater

两个子命令：**check——三条消费线相对 pin 基线的全貌**（只报告）；**update——
六步更新全链**（校验门 + pin bump + compat 表格 + 枢纽族实体三方同步 + 链接层
link + 副本命令收尾）。pin（marketplace.json 的 `metadata.pinnedRef/pinnedSha`）
是唯一基线，工具无状态、不写 sidecar 文件。

## Procedure

```bash
python "<skill目录>/scripts/plugin_updater.py" check          # 市场根从脚本位置向上推导
python "<skill目录>/scripts/plugin_updater.py" check --root <仓库根>   # 指定仓库根（或环境变量 MARKET_REPO）
python "<skill目录>/scripts/plugin_updater.py" check --hub <skills目录> # 指定枢纽（默认 ~/.agents/skills）

python "<skill目录>/scripts/plugin_updater.py" update --yes            # 全部有新版条目走更新链
python "<skill目录>/scripts/plugin_updater.py" update --entry mattpocock-skills --yes
python "<skill目录>/scripts/plugin_updater.py" update --dry-run        # 预览将做的变更，不写文件
python "<skill目录>/scripts/plugin_updater.py" update --entry obsidian-skills --yes   # 无 pin 条目建基线
python "<skill目录>/scripts/plugin_updater.py" update --yes --adopt             # 声明枢纽无手改，不一致实体一并覆盖
python "<skill目录>/scripts/plugin_updater.py" update --yes --delete-removed    # 非交互删除上游已移除实体（连链接层）
```

### check（只报告，不写任何文件）

1. 跑 `check`，向用户转述三段报告
2. **pin 线**结论四种，处置口径：
   - **已最新**：不动
   - **有更新**：pin 落后于上游 head——人工确认后跑 `update`（先 `--dry-run` 预览）
   - **无基线**：条目还没纳入治理——报告附当前 head，用户点头后
     `update --entry <名>` pin 到当时 head 建基线
   - **查询失败**：单条目远端不可达，不影响其余条目；重跑或检查网络
3. **枢纽同步线**（只有带 pin 条目参与；无 pin 条目注明跳过）结论三种：
   - **已同步**：枢纽实体与 pin tarball 内容逐字节一致（行尾差异不算）
   - **与基线不一致（落后或手改）**：落后还是手改由 update 用旧 pin 三方分类
     区分处置（干净落后直接覆盖，手改默认保留）
   - **缺失**：枢纽缺该族实体（update 会补装入）
   - 枢纽线查询失败（多为 tarball 下载被网络抖动挡住）：可读错误逐条给出，重跑即可
4. **其他市场副本线**：对装自其他市场的外部条目副本报已装版本/来源市场/上游 sha，
   并打印该 agent 的刷新命令——**只打印不代跑**，是否刷新由用户执行；
   未装的 agent（含无独立安装记录的 MiniMax）报「未安装」，不是错误
5. 退出码语义（程序化判断用）：0=全部最新且枢纽同步；1=有更新/无基线/枢纽有差异/
   查询失败；2=用法/仓库根错误。副本线不影响退出码

### update（六步全链；先 --dry-run 预览，确认后 --yes 执行）

对有新版的条目（或 `--entry` 指定条目）依序：

1. **下载新旧 SHA tarball**：旧 pin 树在 bump 前先落地（三方分类需要旧基线，
   bump 完旧 SHA 就从 marketplace.json 消失了）；新树与 check 枢纽线同一套下载解包
2. **校验门**：对解包新树跑 `plugin-validator --standalone`；非 0 阻断 error
   **全链中止、零写入**。「缺 .minimax-plugin/plugin.json」对外部引用式条目
   特判 N/A 不阻断（本地无源码、不分发给 MiniMax——2026-10-18 手动重 pin 先例），
   其余 error 照常阻断；validator 输出无「结果:」汇总行时视为不可识别，保守拦截
3. **bump + compat 表格**：该条目 `pinnedSha` → 新 head、`pinnedAt` → 当天
   （`note` 只同步内嵌旧 SHA/日期的文字）；同步 `docs/plugin-compatibility.md`
   「外部聚合插件」节的 pin 列（`` main `49dd158`（2026-10-18，v1.3.1） `` 格式），
   精准行替换。无 pin 条目建基线：pin 到当时 head，照走同一校验门，写齐
   pinnedRef/pinnedSha/pinnedAt。全部条目先计划后写入（全或无——任一条目失败
   就不写任何文件）；已最新条目直接跳过（重跑零动作，也不进枢纽同步）
4. **枢纽族实体三方同步**（枢纽实体 × 旧 pin × 新 pin，CRLF 行尾差异不算漂移）：
   - **干净落后**（枢纽==旧 pin 且 != 新 pin）：直接覆盖，不逐个问（内容等于
     批准过的旧基线，覆盖不丢东西；三十多个成员逐个问违背升级本意）
   - **与基线不一致**（枢纽 != 旧 pin，可能手改）：默认**保留**并在报告标出；
     交互终端逐个问「覆盖/保留/看 diff」（diff 给文件级差异摘要）；
     `--adopt` 显式声明枢纽无手改后全部按干净落后覆盖
   - **上游新增 / 枢纽缺失**：装入枢纽；`--yes` 自动，交互下批量确认一次
   - **上游已移除**（仅旧 pin 有、枢纽还在）：交互终端逐个确认后连枢纽实体与
     `~/.claude/skills/` 链接层 junction 一起删（删链接用 os.rmdir 只摘链接，
     **绝不递归删穿 junction 的目标**）；非交互必须显式 `--delete-removed`，
     否则保留并在报告标注
   - 覆盖前不做自动备份（无状态设计），报告列全改动清单；枢纽目标是
     junction 时拒绝覆盖并报错（绝不写穿链接改到链接目标）
5. **链接层同步**：有结构变化（装入/删除）时自动调 skill-distributor 的
   `link` 子命令同步 `~/.claude/skills/`；调用失败不回滚已写入，
   报告给手动补救命令（`python plugins/skill-distributor/.../skill_distributor.py link`）
6. **收尾报告**：覆盖/保留/新增/删除清单（保留带原因）+ 各 agent 插件副本
   刷新命令（只打印不代跑）。退出码 0=成功或无需更新；1=失败全链中止、
   枢纽有错误项或链接层同步失败；2=用法错误（含非交互缺 `--yes`）

## 边界

- check 版本号从上游 raw 的 `.claude-plugin/plugin.json` 取，拉不到只标
  「版本号未知」，不算失败
- 走 `git ls-remote` 与 codeload tarball，不走 GitHub API；需要网络与 `git` 在 PATH；
  真机网络间歇性抖动是已知情况，失败重跑即可
- 族成员由 pin 处上游 `skills/` 目录清单动态派生（engineering/productivity/misc 一级
  子目录），上游增删 skill 工具不用改；`deprecated`/`in-progress` 永不装入
- update 的枢纽同步只处理 bump/建基线条目：已最新（pin==head）条目不碰枢纽，
  2 个已知措辞漂移实体（git-guardrails-claude-code、setup-pre-commit）要等下次
  上游更新（或手工 `--adopt`）才收敛
- 枢纽路径与链接层路径可用 `--hub` / `--link` 参数化（默认 `~/.agents/skills`、
  `~/.claude/skills`）；枢纽里自研条目的 junction 一律不碰
- update 会改 marketplace.json、docs/plugin-compatibility.md 与枢纽实体，
  提交前照常过 plugin-validator；`.minimax-plugin` 等其余清单不受影响
