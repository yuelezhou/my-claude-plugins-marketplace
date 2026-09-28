---
name: skill-distributor
description: |
  本地 skill 分发与台账核对工具。把 market 仓库的自研 skill 以 junction 分发进
  ~/.agents/skills 运行时枢纽（ZCode / MiniMax / OpenCode / DeepSeek Deep Code 原生读）
  与 ~/.claude/skills 链接层（Claude Code 专用），按 PROMPT-INSTALL.md 台账核对
  "哪个装了哪个没装"，盘点各层条目类型，检测同名多拷贝漂移、悬空链接与链接层违规实体。
  触发：用户说"同步/分发 skill"、"核对台账 / 检查哪些 skill 没装"、"skill 装到哪了"、
  "盘点本地 skill"、"查看/清理重复 skill"、"有重复的 skill 帮我处理掉"，
  或在本仓库新建插件后要暴露给各 agent 时。
  不用于：编写新 skill（用 skill-creator）、校验插件结构（用 plugin-validator）、
  marketplace 插件的安装（走各 agent 自己的 CLI）。
displayNames:
  zh-Hans: "Skill 分发与台账核对"
---

# Skill Distributor

本地 skill 分发三件事：**分发（link）→ 盘点（status）→ 核对（audit）**。架构依据见仓库 ADR-0001，各 agent 的发现目录与优先级见 `references/agent-roots.md`。

## 不变量（违反即漂移，修复时以此为准）

1. 枢纽 `~/.agents/skills/` 里自研条目永远是 junction，指向仓库正本——在枢纽"改"自研 skill 就是改仓库
2. Claude Code 层 `~/.claude/skills/` 禁止放实体，一律 junction → 枢纽条目（MiniMax 的 cc 根优先级 40 高于 agents 根 30，同名异内容会被静默择优）
3. 第三方 skill 的正本 = 枢纽里的安装实体；其他 agent 私有目录不应再出现第三方拷贝

## Procedure

1. **分发**（新建插件后、新机器上）：

   ```bash
   python "<skill目录>/scripts/skill_distributor.py" link
   ```

   幂等可重跑：已就绪跳过、目标错误重建。`--also 名1,名2` 把枢纽里的第三方 skill 追加进 Claude Code 层；`--prune` 清理指向本仓库的悬空链接。

2. **盘点**：

   ```bash
   python "<skill目录>/scripts/skill_distributor.py" status
   ```

   输出枢纽 / Claude Code 层 / 其他 agent 私有目录的条目类型（JUNCTION→目标 或 实体）、自研链接一致性、同名多拷贝漂移。退出码 0=一致，1=有缺失或漂移。

3. **核对台账**（用户问"哪个装了哪个没装"时）：

   ```bash
   python "<skill目录>/scripts/skill_distributor.py" audit
   ```

   - 自研行：以仓库插件为事实源核对两层链接
   - 第三方单名行：核对枢纽实体，附台账里的「安装方式」
   - 族条目（如 mattpocock 套件）：脚本标「族——按成员核对」，由 agent 对照枢纽实际清单判断

4. **缺什么补什么**：自研缺链接 → 重跑 `link`；第三方缺 → 按 PROMPT-INSTALL.md 该行的「安装方式」安装（`npx skills add -g` / 插件安装 / agent 云端市场），装完重跑 `audit` 确认；发现漂移 → 按上面三条不变量修复（实体拷贝迁出，改用链接）

5. **查看与清理重复拷贝**：

   ```bash
   python "<skill目录>/scripts/skill_distributor.py" dupes   # 查看：位置/内容一致否/正本是谁
   python "<skill目录>/scripts/skill_distributor.py" clean   # 处理掉
   ```

   - `clean` 只删**私有目录里与正本内容一致**的实体拷贝；内容不一致的默认保留并标出，`--force` 才清
   - **删除前必须经用户确认**：交互终端逐项 y/n/a；非交互环境（agent 跑脚本）无 `--yes` 会拒绝执行——流程是先跑 `dupes` 给用户看，用户同意后 `clean --yes`
   - 永不触碰：枢纽正本实体、所有 junction 链接、单一私有目录独占的合法 skill（如 MiniMax 云端装的）

6. 交付说明里给结果表：装了 / 没装 / 修复了什么；核对结果**不回写**台账（台账是声明式的）
