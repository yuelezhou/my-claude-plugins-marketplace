---
name: plugin-updater
description: |
  外部聚合插件的更新检查工具，check 一条命令看三条线：
  ① pin 线——读市场 marketplace.json 的 github 引用式条目，用 git ls-remote
  比对 pin SHA 与上游 head（不走 GitHub API，免匿名限流），附上游版本号，
  无 pin 条目报「无基线」并附当前 head；
  ② 枢纽同步线——下载 pin 处 tarball，动态派生族成员（engineering/productivity/misc
  三分类，deprecated/in-progress 永不装入），报 ~/.agents/skills/ 里每个族实体
  相对 pin 基线的状态（已同步 / 与基线不一致（落后或手改）/ 缺失）；
  ③ 其他市场副本线——读 ZCode / Claude Code 的插件安装记录，对装自其他市场的
  外部条目副本报版本/来源市场/上游 sha 并打印刷新命令（只打印不代跑）。
  全部最新且枢纽同步退出码 0，有更新/无基线/枢纽有差异（或查询失败）退出码 1。
  触发：用户说"检查外部插件更新"、"mattpocock 有新版吗"、"外部插件有没有新版本"、
  "pin 落后了没"、"枢纽里的 skill 和 pin 一致吗"、"更新外部聚合插件"，
  或交付前要确认市场外部条目与各 agent 消费线是否落后于基线时。
  不用于：自研插件的版本号管理（手动改双清单，与上游无关）、
  skill 分发与台账核对（用 skill-distributor）、插件结构校验（用 plugin-validator）、
  marketplace 插件的安装（走各 agent 自己的 CLI）、代跑插件刷新命令（只打印）。
displayNames:
  zh-Hans: "外部插件更新检查"
---

# Plugin Updater

一件事：**check——三条消费线相对 pin 基线的全貌**。pin（marketplace.json 的
`metadata.pinnedRef/pinnedSha`）是唯一基线，工具无状态、不写任何文件。

## Procedure

```bash
python "<skill目录>/scripts/plugin_updater.py" check          # 市场根从脚本位置向上推导
python "<skill目录>/scripts/plugin_updater.py" check --root <仓库根>   # 指定仓库根（或环境变量 MARKET_REPO）
python "<skill目录>/scripts/plugin_updater.py" check --hub <skills目录> # 指定枢纽（默认 ~/.agents/skills）
```

1. 跑 `check`，向用户转述三段报告
2. **pin 线**结论四种，处置口径：
   - **已最新**：不动
   - **有更新**：pin 落后于上游 head——人工确认后重 pin（`update` 子命令后续票交付，
     当前版本不代写；流程依据见 `docs/plugin-compatibility.md`）
   - **无基线**：条目还没纳入治理——报告附当前 head，是否 pin 由用户决定
   - **查询失败**：单条目远端不可达，不影响其余条目；重跑或检查网络
3. **枢纽同步线**（只有带 pin 条目参与；无 pin 条目注明跳过）结论三种：
   - **已同步**：枢纽实体与 pin tarball 内容逐字节一致
   - **与基线不一致（落后或手改）**：不做进一步区分——那是 `update` 用旧 pin
     做三方分类的事；当前版本只报告
   - **缺失**：枢纽缺该族实体
   - 枢纽线查询失败（多为 tarball 下载被网络抖动挡住）：可读错误逐条给出，重跑即可
4. **其他市场副本线**：对装自其他市场的外部条目副本报已装版本/来源市场/上游 sha，
   并打印该 agent 的刷新命令——**只打印不代跑**，是否刷新由用户执行；
   未装的 agent（含无独立安装记录的 MiniMax）报「未安装」，不是错误
5. 退出码语义（程序化判断用）：0=全部最新且枢纽同步；1=有更新/无基线/枢纽有差异/
   查询失败；2=用法/仓库根错误。副本线不影响退出码

## 边界

- 版本号从上游 raw 的 `.claude-plugin/plugin.json` 取，拉不到只标「版本号未知」，不算失败
- 走 `git ls-remote` 与 codeload tarball，不走 GitHub API；需要网络与 `git` 在 PATH
- 族成员由 pin 处上游 `skills/` 目录清单动态派生（engineering/productivity/misc 一级
  子目录），上游增删 skill 工具不用改；`deprecated`/`in-progress` 永不装入
- 枢纽比对是逐字节内容比对：不一致即报，不区分落后与手改（update 的事）
- `update` 子命令（validator 校验门 → pin bump → 枢纽三方同步）是后续票，
  当前版本只有 `check`
