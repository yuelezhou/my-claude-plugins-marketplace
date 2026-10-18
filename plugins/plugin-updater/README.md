# plugin-updater

外部聚合插件的更新检查与升级：市场 `marketplace.json` 里 `source` 为 github
引用式的条目（如 mattpocock-skills）靠 `metadata.pinnedRef/pinnedSha` pin 在
固定基线，`check` 一条命令看三条消费线的全貌，`update` 走完仓库写半链。

```bash
python plugins/plugin-updater/skills/plugin-updater/scripts/plugin_updater.py check
python plugins/plugin-updater/skills/plugin-updater/scripts/plugin_updater.py update --entry mattpocock-skills --dry-run
python plugins/plugin-updater/skills/plugin-updater/scripts/plugin_updater.py update --entry mattpocock-skills --yes
```

## check（只报告，不写任何文件）

- **pin 线**：`git ls-remote` 取上游 head 与 pin 比对（不走 GitHub API），附上游
  版本号；无 pin 条目报「无基线」并附当前 head
- **枢纽同步线**：下载 pin 处 codeload tarball，动态派生族成员（`skills/` 下
  engineering/productivity/misc 一级子目录，deprecated/in-progress 永不装入），
  报 `~/.agents/skills/` 里每个族实体的状态：已同步 / 与基线不一致（落后或手改，
  不做进一步区分）/ 缺失
- **其他市场副本线**：读 ZCode（`~/.zcode/cli/plugins/`）与 Claude Code
  （`~/.claude/plugins/`）的安装记录，对装自其他市场的外部条目副本报
  版本/来源市场/上游 sha 并打印刷新命令（只打印不代跑）；未装的 agent 报
  「未安装」不报错（MiniMax 无独立安装记录，恒报未安装）
- 退出码：0=全部最新且枢纽同步；1=有更新/无基线/枢纽有差异/查询失败；
  2=用法/仓库根错误（副本线只报告，不影响退出码）
- `--root <仓库根>` 指定市场根；`--hub <skills目录>` 指定枢纽（默认 `~/.agents/skills`）

## update（仓库写半链）

对有新版的条目（或 `--entry <名>` 指定条目）依序：下载新 SHA tarball →
`plugin-validator --standalone` 校验门 → bump `marketplace.json` 的
`pinnedSha`/`pinnedAt` → 同步 `docs/plugin-compatibility.md`「外部聚合插件」
表格的 pin 列。

- **校验门**：非 0 阻断 error 全链中止、零写入；「缺 .minimax-plugin」对外部
  引用式条目特判 N/A（本地无源码、不分发给 MiniMax），其余 error 照常阻断；
  validator 输出无「结果:」汇总行视为不可识别，保守拦截
- **bump**：`note` 只同步内嵌旧 SHA/日期的文字，其余原样保留；JSON 2 空格缩进
  与行尾排版保持；已最新条目直接跳过，重跑零改动
- **建基线**：无 pin 条目（如 obsidian-skills）update 时 pin 到当时 head，
  照走同一校验门，写齐 pinnedRef（`git ls-remote --symref` 取默认分支）/
  pinnedSha/pinnedAt
- **守卫**：全部条目先计划后写入（全或无——任一条目失败就不写任何文件）；
  `--dry-run` 只打印将做的变更不写文件；非交互环境（非 tty）缺 `--yes`
  拒绝执行任何变更
- 退出码：0=成功或无需更新；1=失败全链中止；2=用法错误
- 枢纽族实体三方同步、链接层 link、副本刷新命令打印是后续票（04）

设计：外部访问收敛为可注入 effect 函数（远端 head / 版本号 / tarball /
默认分支 / validator），与纯决策逻辑分离；回归测试（`test_plugin_updater.py`）
只走内存与 tmp 接缝，不碰网络。
