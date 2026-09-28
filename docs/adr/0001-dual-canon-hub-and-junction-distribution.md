# Skill 双正本制：仓库自研 / 枢纽第三方，junction 分发

skill 曾散落在各 agent 的私有目录（`~/.zcode/skills`、`~/.minimax/skills`、`~/.claude/skills`），同一 skill 多份实拷贝且已发生漂移（word-frequency 枢纽拷贝落后仓库 v1.1.0、anki-card-from-notes 三份拷贝），而本机同时使用 Claude Code / ZCode / MiniMax Code / OpenCode / DeepSeek Deep Code 五类 agent。决定采用双正本制：自研 skill 正本在本仓库 `plugins/<名>/skills/<名>/`（享受 git 版本与 marketplace 发布流程），第三方 skill 正本即 `~/.agents/skills/` 的安装实体；`~/.agents/skills/` 作为运行时枢纽——ZCode、MiniMax Code、OpenCode、Deep Code 原生扫描它（MiniMax 经本机 runtime 源码 `roots.ts` 确认默认开启），自研 skill 由 `scripts/link_skills.py` 以 NTFS junction 从枢纽链回仓库；Claude Code 不读枢纽，由同一脚本在 `~/.claude/skills/` 建第二层链接。换装或新装 agent 零重装 skill。

## Considered Options

- 所有正本放 `~/.agents/skills/`：脱离 git 版本管理与远端备份，自研 skill 的变更历史丢失——否决
- 各 agent 目录各放拷贝 + 同步脚本修补：正是已观察到漂移的根源——否决
- 只用 vercel-labs/skills CLI 分发：Windows symlink 权限受限且只能安装已推送内容——留作补充，不作主体

## Consequences

- 枢纽里的自研条目永远是链接：在枢纽"改"自研 skill 实际是改仓库；直接编辑第三方条目则合法（那本来就是它的正本）
- 链接层（`~/.claude/skills/`）禁止放置与枢纽不同内容的实体——MiniMax 的 cc 根（优先级 40）高于 agents 根（30），同名不同内容会被静默择优
- 新机器复现 = clone 本仓库 → `python scripts/link_skills.py` → 按 PROMPT-INSTALL.md 台账补装第三方
