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
  ② update 走完仓库写半链——对有新版的条目下载新 SHA tarball → plugin-validator
  --standalone 校验门（非 0 阻断 error 全链中止、零写入；「缺 .minimax-plugin」
  对外部引用式条目特判 N/A）→ bump marketplace.json 的 pinnedSha/pinnedAt
  （note 只同步内嵌旧 SHA/日期的文字）→ 同步 docs/plugin-compatibility.md
  「外部聚合插件」表格的 pin 列；无 pin 条目可 pin 到当时 head 建基线（照走同一
  校验门，写齐 pinnedRef/pinnedSha/pinnedAt）。全部条目先计划后写入（全或无），
  --dry-run 预览、--entry 限定单条目、非交互必须 --yes。
  触发：用户说"检查外部插件更新"、"mattpocock 有新版吗"、"外部插件有没有新版本"、
  "pin 落后了没"、"枢纽里的 skill 和 pin 一致吗"、"更新外部聚合插件"、
  "把 mattpocock 升到最新"、"给 obsidian-skills 建 pin 基线"，
  或交付前要确认市场外部条目与各 agent 消费线是否落后于基线时。
  不用于：自研插件的版本号管理（手动改双清单，与上游无关）、
  skill 分发与台账核对（用 skill-distributor）、插件结构校验（用 plugin-validator）、
  marketplace 插件的安装（走各 agent 自己的 CLI）、代跑插件刷新命令（只打印）。
displayNames:
  zh-Hans: "外部插件更新检查"
---

# Plugin Updater

两个子命令：**check——三条消费线相对 pin 基线的全貌**（只报告）；**update——
仓库写半链**（校验门 + pin bump + compat 表格同步）。pin（marketplace.json 的
`metadata.pinnedRef/pinnedSha`）是唯一基线，工具无状态、不写 sidecar 文件。

## Procedure

```bash
python "<skill目录>/scripts/plugin_updater.py" check          # 市场根从脚本位置向上推导
python "<skill目录>/scripts/plugin_updater.py" check --root <仓库根>   # 指定仓库根（或环境变量 MARKET_REPO）
python "<skill目录>/scripts/plugin_updater.py" check --hub <skills目录> # 指定枢纽（默认 ~/.agents/skills）

python "<skill目录>/scripts/plugin_updater.py" update --yes            # 全部有新版条目走更新链
python "<skill目录>/scripts/plugin_updater.py" update --entry mattpocock-skills --yes
python "<skill目录>/scripts/plugin_updater.py" update --dry-run        # 预览将做的变更，不写文件
python "<skill目录>/scripts/plugin_updater.py" update --entry obsidian-skills --yes   # 无 pin 条目建基线
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
   - **与基线不一致（落后或手改）**：不做进一步区分——三方分类与覆盖是
     update 的枢纽线（后续票交付），当前版本只报告
   - **缺失**：枢纽缺该族实体
   - 枢纽线查询失败（多为 tarball 下载被网络抖动挡住）：可读错误逐条给出，重跑即可
4. **其他市场副本线**：对装自其他市场的外部条目副本报已装版本/来源市场/上游 sha，
   并打印该 agent 的刷新命令——**只打印不代跑**，是否刷新由用户执行；
   未装的 agent（含无独立安装记录的 MiniMax）报「未安装」，不是错误
5. 退出码语义（程序化判断用）：0=全部最新且枢纽同步；1=有更新/无基线/枢纽有差异/
   查询失败；2=用法/仓库根错误。副本线不影响退出码

### update（仓库写半链；先 --dry-run 预览，确认后 --yes 执行）

对有新版的条目（或 `--entry` 指定条目）依序：

1. **下载新 SHA tarball**（与 check 枢纽线共用一次下载）
2. **校验门**：对解包树跑 `plugin-validator --standalone`；非 0 阻断 error
   **全链中止、零写入**。「缺 .minimax-plugin/plugin.json」对外部引用式条目
   特判 N/A 不阻断（本地无源码、不分发给 MiniMax——2026-10-18 手动重 pin 先例），
   其余 error 照常阻断；validator 输出无「结果:」汇总行时视为不可识别，保守拦截
3. **bump**：该条目 `pinnedSha` → 新 head、`pinnedAt` → 当天；`note` 只同步
   内嵌旧 SHA/日期的文字，其余原样保留；保持 JSON 2 空格缩进与行尾排版
4. **同步 compat 表格**：`docs/plugin-compatibility.md`「外部聚合插件」节的
   pin 列（`` main `49dd158`（2026-10-18，v1.3.1） `` 格式），精准行替换
5. **无 pin 条目建基线**：pin 到当时 head，照走同一校验门，写齐
   pinnedRef（`git ls-remote --symref` 取默认分支）/pinnedSha/pinnedAt；
   compat 表里没有该条目行时跳过表格同步（不算失败）
6. **守卫**：全部条目先计划后写入（全或无——任一条目失败就不写任何文件）；
   已最新条目直接跳过（重跑零改动）；非交互环境（非 tty）缺 `--yes` 拒绝执行
   任何变更（`--dry-run` 不写文件所以豁免）；退出码 0=成功或无需更新，
   1=失败全链中止，2=用法错误

## 边界

- check 版本号从上游 raw 的 `.claude-plugin/plugin.json` 取，拉不到只标
  「版本号未知」，不算失败
- 走 `git ls-remote` 与 codeload tarball，不走 GitHub API；需要网络与 `git` 在 PATH；
  真机网络间歇性抖动是已知情况，失败重跑即可
- 族成员由 pin 处上游 `skills/` 目录清单动态派生（engineering/productivity/misc 一级
  子目录），上游增删 skill 工具不用改；`deprecated`/`in-progress` 永不装入
- update 当前只覆盖**仓库写半链**（校验门 → pin bump → compat 表格）：
  枢纽族实体三方同步、链接层 link、副本刷新命令打印是后续票（04），
  pin bump 后如需同步枢纽，暂按 compat 文档的更新流程手动走
- update 会改 marketplace.json 与 docs/plugin-compatibility.md 两处，
  提交前照常过 plugin-validator；`.minimax-plugin` 等其余清单不受影响
