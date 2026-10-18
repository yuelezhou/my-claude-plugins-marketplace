# plugin-updater

外部聚合插件的更新检查：市场 `marketplace.json` 里 `source` 为 github 引用式的条目
（如 mattpocock-skills）靠 `metadata.pinnedRef/pinnedSha` pin 在固定基线，本插件用
`git ls-remote` 取上游 head 与 pin 比对（不走 GitHub API），版本号从上游 raw 的
`.claude-plugin/plugin.json` 取。

```bash
python plugins/plugin-updater/skills/plugin-updater/scripts/plugin_updater.py check
```

- 退出码：0=全部最新；1=有更新或无基线或查询失败；2=用法/仓库根错误
- 无 pin 条目报「无基线」并附当前 head
- `update` 子命令（tarball 下载 → validator 校验门 → pin bump → 枢纽同步）后续票交付

设计：外部访问收敛为可注入 effect 函数（远端 head / 版本号 / tarball / validator），
与纯决策逻辑分离；回归测试（`test_plugin_updater.py`）只走内存接缝，不碰网络。
