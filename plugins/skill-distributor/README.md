# skill-distributor

本地 skill 分发与台账核对：把本仓库自研 skill 分发进各 agent 的 skill 发现目录，按台账核对装没装，检测漂移。

## 用法

```bash
python skills/skill-distributor/scripts/skill_distributor.py <子命令>
```

| 子命令 | 作用 |
|---|---|
| `link` | 分发：仓库自研 skill → 枢纽 `~/.agents/skills/` junction → `~/.claude/skills/` junction（幂等）。`--also 名1,名2` 追加第三方进 cc 层；`--prune` 清悬空链接 |
| `status` | 盘点：各层条目类型、自研链接一致性、同名多拷贝漂移（退出码 0/1） |
| `audit` | 核对：status + 按 PROMPT-INSTALL.md 台账逐行给「装了/没装」 |
| `dupes` | 查看：重复拷贝清单（位置、内容一致否、正本是谁） |
| `clean` | 清理：删除私有目录里与正本一致的残留拷贝；删前逐项确认，非交互需 `--yes`；内容不一致默认保留（`--force` 强制） |
| `link-plugins` | 插件分发矩阵：Claude/ZCode 市场注册 + MiniMax 物理拷贝（`--agents` 选目标）；`status`/`audit` 报告 MiniMax 副本新鲜度 |

架构依据见仓库 ADR-0001；各 agent 发现目录与优先级见 `skills/skill-distributor/references/agent-roots.md`。

## 三条不变量

1. 枢纽里的自研条目永远是 junction → 仓库正本（改枢纽=改仓库）
2. Claude Code 层禁放实体，一律 junction → 枢纽
3. 第三方正本 = 枢纽安装实体，其他 agent 私有目录不应再有拷贝
