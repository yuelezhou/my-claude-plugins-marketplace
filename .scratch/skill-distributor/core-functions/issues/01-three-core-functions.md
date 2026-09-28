Plugin: skill-distributor
Status: resolved

# skill-distributor 应支持分发、重名检查、清理三个功能

## 需求

skill-distributor 插件要支持三个功能：

1. **分发** —— 把仓库自研 skill 分发到各 agent 的 skill 发现目录
2. **重名检查** —— 检查同名 skill 在多个目录的重复/冲突
3. **清理** —— 处理掉多余的重复拷贝

## 现状对照（记录时已实现，2026-09-28）

| 需求 | 对应实现 | 实测 |
|---|---|---|
| 分发 | `link` 子命令：仓库正本 → 枢纽 `~/.agents/skills/` junction → `~/.claude/skills/` junction，幂等 | 9 个自研 skill 两层就绪 |
| 重名检查 | `status` 的同名多拷贝漂移检测 + `dupes` 清单（[正本]/[清]/[留]/[?]分级） | 合成重复用例通过 |
| 清理 | `clean` 子命令：删私有目录里与正本一致的拷贝，删前逐项确认（非交互需 `--yes`），内容不一致默认保留 `--force` 才清 | 一致/不一致两种用例通过 |

## 待裁决

- 若本票意图 = 验收上述功能：改 `Status: ready-for-human`，逐条实测后关闭
- 若意图 = 还缺的行为（比如想要不同的分发目标、更严的重名策略）：补充说明，转 `needs-info`

## Comments

- 2026-09-28 验收通过（用户确认）。复验记录：`link` 8 个自研 skill 两层就绪（幂等）；`status` 各层一致无漂移；`dupes` 无重复拷贝；`clean` 空场正常；plugin-validator 0 error。复验同时修复两个衍生问题：枢纽 junction 路径触发找不到仓库根（realpath + `--root`/`MARKET_REPO`）、悬空链接检测盲区（status 报告 + `link --prune` 放宽）。
- 备注：本票记录期间自研 skill 数从 9 变 8——cs-book-study 经用户决定撤销收编并已注销（原副本在 skills-migration-backup-20260928）。
