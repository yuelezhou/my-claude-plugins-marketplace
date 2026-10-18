# plugin-updater

外部聚合插件的更新检查与升级：市场 `marketplace.json` 里 `source` 为 github
引用式的条目（如 mattpocock-skills）靠 `metadata.pinnedRef/pinnedSha` pin 在
固定基线，`check` 一条命令看三条消费线的全貌，`update` 走完六步更新全链
（校验门 + pin bump + compat 表格 + 枢纽族实体三方同步 + 链接层 link + 副本
命令收尾）。

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

## update（六步全链）

对有新版的条目（或 `--entry <名>` 指定条目）依序：

1. 下载**新旧** SHA tarball（旧 pin 树在 bump 前落地——三方分类需要旧基线）
2. `plugin-validator --standalone` **校验门**
3. bump `marketplace.json` 的 `pinnedSha`/`pinnedAt` + 同步
   `docs/plugin-compatibility.md`「外部聚合插件」表格的 pin 列
4. **枢纽族实体三方同步**（枢纽实体 × 旧 pin × 新 pin）
5. 有结构变化时调 skill-distributor 的 `link` **同步链接层**
6. 结束报告：覆盖/保留/新增/删除清单 + 各 agent 插件副本**刷新命令**（只打印）

要点：

- **校验门**：非 0 阻断 error 全链中止、零写入；「缺 .minimax-plugin」对外部
  引用式条目特判 N/A（本地无源码、不分发给 MiniMax），其余 error 照常阻断；
  validator 输出无「结果:」汇总行视为不可识别，保守拦截
- **bump**：`note` 只同步内嵌旧 SHA/日期的文字，其余原样保留；JSON 2 空格缩进
  与行尾排版保持；已最新条目直接跳过（重跑零动作，也不进枢纽同步）
- **建基线**：无 pin 条目（如 obsidian-skills）update 时 pin 到当时 head，
  照走同一校验门，写齐 pinnedRef（`git ls-remote --symref` 取默认分支）/
  pinnedSha/pinnedAt
- **三方分类**（CRLF 行尾差异不算漂移）：
  - 干净落后（枢纽==旧 pin 且 != 新 pin）→ 直接覆盖，不逐个问
  - 与基线不一致（枢纽 != 旧 pin，可能手改）→ 默认保留并在报告标出；
    交互逐个问「覆盖/保留/看 diff」；`--adopt` 声明枢纽无手改后批量覆盖
  - 上游新增 / 枢纽缺失 → 装入（`--yes` 自动，交互批量确认一次）
  - 上游已移除 → 交互逐个确认后连枢纽实体与 `~/.claude/skills/` 链接层
    junction 一起删（只摘链接，绝不递归删穿目标）；非交互必须
    `--delete-removed`，否则保留并报告
- **junction 安全**：覆盖枢纽实体前发现目标是 junction 一律拒绝（绝不写穿
  链接）；覆盖前不做自动备份（无状态设计），报告列全改动清单
- **链接层**：仅装入/删除（结构变化）时调用；失败不回滚已写入，
  报告给手动补救命令
- **守卫**：全部条目先计划后写入（全或无——任一条目失败就不写任何文件）；
  `--dry-run` 只打印将做的变更不写文件（枢纽同步段也只出计划）；
  非交互环境（非 tty）缺 `--yes` 拒绝执行任何变更
- 退出码：0=成功或无需更新；1=失败全链中止、枢纽有错误项或链接层同步失败；
  2=用法错误
- `--hub` / `--link` 可参数化枢纽与链接层路径（默认 `~/.agents/skills`、
  `~/.claude/skills`）

设计：外部访问收敛为可注入 effect 函数（远端 head / 版本号 / tarball /
默认分支 / validator / 链接层 link），交互决策收 input_fn 与决策函数，
与纯决策逻辑分离；回归测试（`test_plugin_updater.py`）只走内存与 tmp 接缝，
不碰网络。
