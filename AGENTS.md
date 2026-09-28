# AGENTS.md

个人 Claude Code 插件市场：本仓库是插件集合，用来记录和分发我自己的 agent 能力（skills / agents / MCP 配置）。文档与提交信息以中文为主。

## 仓库结构

- `.claude-plugin/marketplace.json` — 市场注册表：每个插件一条 `{name, description, source}`，`source` 指向 `./plugins/<name>`
- `plugins/<插件名>/` — 每个插件自包含：
  - `.claude-plugin/plugin.json` — 必需元数据（name / version / description / author）
  - `skills/<skill-name>/SKILL.md` — Agent Skill 入口；frontmatter 的 `name` + `description` 决定触发时机（description 要写清触发短语和「不用于」的排除场景）
  - `skills/<skill-name>/references/` — 详细契约/排查文档；SKILL.md 只放执行规则，细节放这里
  - `skills/<skill-name>/scripts/` — Python 辅助脚本
  - `agents/`、`commands/`、`hooks/`、`.mcp.json` — 可选组件
- 无 package.json / 构建系统；纯 markdown + Python 脚本仓库，平台 Windows + Git Bash

## 插件清单

| 插件 | 内容 |
|---|---|
| hello-greeting | 演示插件 |
| my-utils | skills（quick-deploy、code-clean）+ 自定义 agent |
| anki-card-from-notes | 笔记 → markdown_sync_to_anki 格式 Anki 卡片 |
| mineru-book-ocr | 书籍 PDF → MinerU 云端 OCR → 读书笔记流水线（拆分→提交→等待→收集→归档） |
| word-frequency | 英文词频统计，HTML / Anki / CSV 输出，自带词典数据 |
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

1. 新增插件：建 `plugins/<name>/.claude-plugin/plugin.json` + 组件，**必须同步在 `.claude-plugin/marketplace.json` 的 `plugins` 数组加一条**——漏了市场里看不到
2. 改版本号或 description 时，`plugin.json` 与 `marketplace.json` 两处保持一致（曾出现两处漂移，靠提交人工同步）
3. **任何插件提交/发布前，先用 plugin-validator 插件的 `check_plugin.py` 校验，0 error 才能交付**（warning 逐条人工确认）
4. SKILL.md 的 frontmatter `description` 是触发依据：写明「何时用 / 何时不用」，相邻 skill 的边界要显式划清（参照 anki-card-from-notes 的写法）
5. skill 自带 Python 脚本时，配套的输入输出契约写进 `references/`，SKILL.md 里给速查表和「先看后写」的执行规则即可

## Windows / Python 约定

- Python 脚本必须处理 UTF-8：脚本内 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`；命令行跑时 `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`
- mineru-book-ocr 依赖外部仓库 `D:\code\toy_and_tools\py_pdf_book_helper`（PDF 拆分脚本等）；MinerU 桌面版有 ≤200 页且 ≤200MB 的单文件硬限制，拆分按 200 页均分
- word-frequency 的 `data/`：5 个词典文件（dict/levels/lemma/coca/phrases）是运行时依赖；`known_words.txt` 是用户已会词表，属持久状态，**勿覆盖删除**；仓库 `data/` 与 skill `data/` 无自动同步，重建后要手动拷贝（步骤见 references/rebuild-data.md）

## 官方文档（怎么制作插件和市场）

- https://code.claude.com/docs/en/plugins/overview — Claude Code 插件官方文档：插件的制作、结构、市场（marketplace）的配置与发布都在这里

## 关键文档（改敏感区前先读）

- `plugins/anki-card-from-notes/skills/anki-card-from-notes/references/card-format.md` — Anki 卡片格式契约
- `plugins/mineru-book-ocr/skills/mineru-book-ocr/references/pipeline-contracts.md` — 五段流水线的输入/输出/验收判据
- `plugins/mineru-book-ocr/skills/mineru-book-ocr/references/mineru-desktop-internals.md` — MinerU 桌面版机制与配额
- `plugins/word-frequency/skills/word-frequency/references/rebuild-data.md` — 词典数据重建步骤

## Agent skills

### Issue tracker

Issue 以本地 markdown 追踪：`.scratch/<feature>/` 目录下 `spec.md` + `issues/NN-<slug>.md`，不使用 GitHub/Gitee Issue。见 `docs/agents/issue-tracker.md`。

### Triage labels

保留五个默认标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文布局：根目录 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。
