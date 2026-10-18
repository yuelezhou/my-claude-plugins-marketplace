# plugin-updater

外部聚合插件的更新检查：市场 `marketplace.json` 里 `source` 为 github 引用式的条目
（如 mattpocock-skills）靠 `metadata.pinnedRef/pinnedSha` pin 在固定基线，
`check` 一条命令看三条消费线的全貌。

```bash
python plugins/plugin-updater/skills/plugin-updater/scripts/plugin_updater.py check
```

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
- `update` 子命令（validator 校验门 → pin bump → 枢纽三方同步）后续票交付

设计：外部访问收敛为可注入 effect 函数（远端 head / 版本号 / tarball / validator），
与纯决策逻辑分离；回归测试（`test_plugin_updater.py`）只走内存与 tmp 接缝，
不碰网络。
