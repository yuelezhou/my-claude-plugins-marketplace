# AGENTS.md

个人 Claude Code 插件市场：本仓库是插件集合，用来记录和分发我自己的 agent 能力（skills / agents / MCP 配置）。文档与提交信息以中文为主。

## 仓库结构

- `.claude-plugin/marketplace.json` — 市场注册表：每个插件一条 `{name, description, source}`，`source` 指向 `./plugins/<name>`（另含外部聚合条目，source 为 github 形式 + metadata.pinnedSha）
- `plugins/<插件名>/` — 每个插件自包含：
  - `.claude-plugin/plugin.json` — 必需元数据（name / version / description / author）
  - `plugin.json`（根目录）— Agent Plugins 1.0 便携清单（`$schema` + `name` + `version` 最小集），与 `.claude-plugin` 清单的一致性由 validator 强制
  - `skills/<skill-name>/SKILL.md` — Agent Skill 入口；frontmatter 的 `name` + `description` 决定触发时机（description 要写清触发短语和「不用于」的排除场景）
  - `skills/<skill-name>/references/` — 详细契约/排查文档；SKILL.md 只放执行规则，细节放这里
  - `skills/<skill-name>/scripts/` — Python 辅助脚本
  - `agents/`、`commands/`、`hooks/`、`.mcp.json` — 可选组件
- 无 package.json / 构建系统；纯 markdown + Python 脚本仓库，平台 Windows + Git Bash

## 插件清单

| 插件 | 内容 |
|---|---|
| hello-greeting | 演示插件 |
| demo-case | skills（quick-deploy、code-clean）+ 自定义 agent |
| anki-card-from-notes | 笔记 → markdown_sync_to_anki 格式 Anki 卡片 |
| mineru-book-ocr | 书籍 PDF → MinerU 云端 OCR → 读书笔记流水线（拆分→提交→等待→收集→归档） |
| word-frequency | 英文词频统计，HTML / Anki / CSV 输出，自带词典数据 |
| skill-distributor | 本地 skill 分发与台账核对（link / status / audit / dupes / clean / link-plugins） |
| **mattpocock-skills**（外部） | 聚合条目，github: mattpocock/skills，pin main `484efcbe`——本地无源码 |
| gitee-mcp | Gitee 云端 Remote MCP 封装（`.mcp.json`，需 `GITEE_ACCESS_TOKEN` 环境变量） |
| plugin-validator | **其他插件发布前必须运行的验证工具**（`check_plugin.py`，0 error 才能发布） |
| obsidian-skills | 外部插件（github: kepano/obsidian-skills），本地无源码 |

## 常用命令

```bash
# anki 校验脚本的回归测试（退出码 0=全部通过）
python plugins/anki-card-from-notes/skills/anki-card-from-notes/scripts/test_check_anki_cards.py

# 校验产出的 Anki 卡片文件（0 error 才可交付）
python plugins/anki-card-from-notes/skills/anki-card-from-notes/scripts/check_anki_cards.py <文件.md>

# 本地测试插件
claude --plugin-dir ./plugins/<name>

# 注册本地市场
claude plugin marketplace add local .
```

## 添加 / 修改插件的规则

1. 新增插件：建 `plugins/<name>/.claude-plugin/plugin.json` + **根目录 `plugin.json`**（Agent Plugins 1.0：`$schema`+`name`+`version`）+ 组件，**必须同步在 `.claude-plugin/marketplace.json` 的 `plugins` 数组加一条**——漏了市场里看不到
2. 改版本号时**三处同步**：`.claude-plugin/plugin.json`、根 `plugin.json`、marketplace.json 条目；description 两处同步（`.claude-plugin` 与 marketplace），以 plugin.json 为准（曾出现两处漂移，validator 会拦）
3. **任何插件提交/发布前，先用 plugin-validator 插件的 `check_plugin.py` 校验，0 error 才能交付**（warning 逐条人工确认）
4. SKILL.md 的 frontmatter `description` 是触发依据：写明「何时用 / 何时不用」，相邻 skill 的边界要显式划清（参照 anki-card-from-notes 的写法）
5. skill 自带 Python 脚本时，配套的输入输出契约写进 `references/`，SKILL.md 里给速查表和「先看后写」的执行规则即可

## Windows / Python 约定

- Python 脚本必须处理 UTF-8：脚本内 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`；命令行跑时 `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`
- mineru-book-ocr 依赖外部仓库 `D:\code\toy_and_tools\py_pdf_book_helper`（PDF 拆分脚本等）；MinerU 桌面版有 ≤200 页且 ≤200MB 的单文件硬限制，拆分按 200 页均分
- word-frequency 的 `data/`：5 个词典文件（dict/levels/lemma/coca/phrases）是运行时依赖；`known_words.txt` 是用户已会词表，属持久状态，**勿覆盖删除**；仓库 `data/` 与 skill `data/` 无自动同步，重建后要手动拷贝（步骤见 references/rebuild-data.md）

## 官方文档（怎么制作插件和市场）

- https://code.claude.com/docs/en/plugins/overview — Claude Code 插件官方文档：插件的制作、结构、市场（marketplace）的配置与发布都在这里

## Skill 管理政策（双正本制，ADR-0001）

- **自研 skill** 正本在本仓库 `plugins/<名>/skills/<名>/`，由 skill-distributor 插件分发：`python plugins/skill-distributor/skills/skill-distributor/scripts/skill_distributor.py link`（幂等，兼容入口 `scripts/link_skills.py`）；枢纽里的自研条目永远是链接——改枢纽就是改仓库，新插件建好后重跑 link
- **第三方 skill** 正本即 `~/.agents/skills/` 安装实体；常用清单在 PROMPT-INSTALL.md（声明式，只记用什么和怎么装，不记安装状态；「哪个装了哪个没装」用 skill-distributor 的 `audit` 子命令核对）
- **插件层分发**（与 skill 层不同，三范式并存）：`link-plugins` 子命令按矩阵执行——Claude/ZCode 注册市场（本仓库 GitHub 镜像即分发源）、MiniMax 物理拷贝（拒收链接）、其余走 skill 通道；矩阵与依据见 `docs/plugin-compatibility.md`
- ZCode / MiniMax / OpenCode / DeepSeek Deep Code 原生读枢纽；Claude Code 只认 `~/.claude/skills/`，**链接层禁放与枢纽不同内容的实体**（MiniMax 的 cc 根优先级 40 > agents 根 30，同名异内容会被静默择优）
- 新机器复现：clone → `python scripts/link_skills.py` → 按 PROMPT-INSTALL.md 补装第三方
- 术语定义见 CONTEXT.md（自研/第三方、正本、运行时枢纽、复现、漂移、台账）

## 关键文档（改敏感区前先读）

- `docs/plugin-compatibility.md` — 三平台（Claude/ZCode/MiniMax）插件兼容性矩阵与维护规则

- `plugins/anki-card-from-notes/skills/anki-card-from-notes/references/card-format.md` — Anki 卡片格式契约
- `plugins/mineru-book-ocr/skills/mineru-book-ocr/references/pipeline-contracts.md` — 五段流水线的输入/输出/验收判据
- `plugins/mineru-book-ocr/skills/mineru-book-ocr/references/mineru-desktop-internals.md` — MinerU 桌面版机制与配额
- `plugins/word-frequency/skills/word-frequency/references/rebuild-data.md` — 词典数据重建步骤

## Agent skills

### Issue tracker

Issue 以本地 markdown 追踪，**按插件分域**：`.scratch/<插件名>/<feature>/`（仓库级事务用 `.scratch/market/<主题>/`），每票头部带 `Plugin:` 与 `Status:` 行，不使用 GitHub/Gitee Issue。见 `docs/agents/issue-tracker.md`。

### Triage labels

保留五个默认标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文布局：根目录 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。
