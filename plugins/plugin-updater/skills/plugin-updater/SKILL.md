---
name: plugin-updater
description: |
  外部聚合插件的更新检查工具：读市场 marketplace.json 的 github 引用式条目，
  用 git ls-remote 比对 pin SHA 与上游 head（不走 GitHub API，免匿名限流），
  附上游版本号；无 pin 条目报「无基线」并附当前 head。
  全部最新退出码 0，有更新或无基线（或查询失败）退出码 1。
  触发：用户说"检查外部插件更新"、"mattpocock 有新版吗"、"外部插件有没有新版本"、
  "pin 落后了没"、"更新外部聚合插件"，或交付前要确认市场外部条目是否落后于上游时。
  不用于：自研插件的版本号管理（手动改双清单，与上游无关）、
  skill 分发与台账核对（用 skill-distributor）、插件结构校验（用 plugin-validator）、
  marketplace 插件的安装（走各 agent 自己的 CLI）。
displayNames:
  zh-Hans: "外部插件更新检查"
---

# Plugin Updater

一件事：**check——市场外部聚合条目是否落后于上游**。pin（marketplace.json 的
`metadata.pinnedRef/pinnedSha`）是唯一基线，工具无状态、不写任何文件。

## Procedure

```bash
python "<skill目录>/scripts/plugin_updater.py" check          # 市场根从脚本位置向上推导
python "<skill目录>/scripts/plugin_updater.py" check --root <仓库根>   # 指定仓库根（或环境变量 MARKET_REPO）
```

1. 跑 `check`，向用户转述报告：每条 github 引用式条目的 pin vs 上游 head、上游版本号、结论
2. 结论有四种，处置口径：
   - **已最新**：不动
   - **有更新**：pin 落后于上游 head——人工确认后重 pin（`update` 子命令后续票交付，
     当前版本不代写；流程依据见 `docs/plugin-compatibility.md`）
   - **无基线**：条目还没纳入治理——报告附当前 head，是否 pin 由用户决定
   - **查询失败**：单条目远端不可达，不影响其余条目；重跑或检查网络
3. 退出码语义（程序化判断用）：0=全部最新；1=有更新或无基线或查询失败；2=用法/仓库根错误

## 边界

- 版本号从上游 raw 的 `.claude-plugin/plugin.json` 取，拉不到只标「版本号未知」，不算失败
- 走 `git ls-remote`，不走 GitHub API；需要网络与 `git` 在 PATH
- `update` 子命令（tarball 下载 → validator 校验门 → pin bump → 枢纽同步）是后续票，
  当前版本只有 `check`
