# 各 Agent 的 Skill 发现目录（调研定稿）

分发与核对的事实依据。置信度从高到低：**runtime 源码 ≈ 官方文档 > 本机实测 > 第三方安装器文档 > 社区 SEO**。调研日期 2026-09-28。

## 用户级（全局）发现目录

| Agent | 扫描根 | 原生读枢纽 `~/.agents/skills/` | 证据 |
|---|---|---|---|
| ZCode | `~/.zcode/skills/`、`~/.agents/skills/` | ✓ | 本机实测（两个目录的 skill 同时出现在会话列表）+ 社区文档交叉 |
| MiniMax Code | `~/.claude/skills/`(优先级40)、`~/.codex/skills/`(35)、`~/.agents/skills/`(30)；另有 skill-hub 云端通道（装到 `~/.minimax/skills`，不在 external roots 里） | ✓ 默认开启 | 本机 runtime 源码：local-runtime-v2 `src/skills/roots.ts` 的 `readExternalUserSkillRoots()` + `src/skills-config.ts` 默认表 |
| OpenCode | `~/.config/opencode/skills/`、`~/.agents/skills/`、`~/.claude/skills/` | ✓ | 官方文档 opencode.ai/docs/skills |
| Deep Code（DeepSeek） | `~/.agents/skills/` | ✓ | 官方文档 api-docs.deepseek.com（quick_start/agent_integrations/deepcode） |
| Claude Code | `~/.claude/skills/` | ✗ 唯一需要链接层的 | 官方文档 code.claude.com/docs/en/skills |

## 项目级（worktree）发现目录

| Agent | 目录 |
|---|---|
| ZCode | `.agents/skills/` |
| MiniMax Code | `.minimax/skills/`(65)、`.claude/skills/`(60)、`.agents/skills/`(55) |
| OpenCode | `.opencode/skills/`、`.claude/skills/`、`.agents/skills/` |
| Deep Code | `.deepcode/skills/` |
| Claude Code | `.claude/skills/` |

## 分发含义

- 枢纽一个实体目录即可覆盖 ZCode / MiniMax / OpenCode / Deep Code 四家
- Claude Code 必须由 `skill_distributor.py link` 在 `~/.claude/skills/` 建第二层 junction
- MiniMax 同名 skill 会同时从 cc 根(40) 与 agents 根(30) 可见——链接层禁放与枢纽异内容的实体，否则同名异内容被静默择优
- 工作在某个仓库内时，把 skill 放该仓库 `.agents/skills/` 即对 MiniMax / OpenCode / ZCode 项目级可见，无需安装
