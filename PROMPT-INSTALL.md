# Skill 台账（声明式）

本文件只声明**我常用的 skill** 和它们的安装方式，不记录安装状态。
定期核对：让 agent 逐条检查各发现目录（`~/.agents/skills/`、`~/.claude/skills/`、各 agent 私有目录），缺的按「安装方式」补装即可。

复现顺序（新机器）：

1. clone 本仓库
2. `python scripts/link_skills.py` —— 自研 skill 自动链接进枢纽与 Claude Code 层
3. 按下表补装第三方 skill
4. 各 agent 开一次会话确认 skill 已被识别

## 自研 skill（正本 = 本仓库，无需安装）

| skill | 说明 |
|---|---|
| anki-card-from-notes | 笔记/讲义 → markdown_sync_to_anki 格式 Anki 卡片 |
| mineru-book-ocr | 书籍 PDF → MinerU 云端 OCR → 读书笔记流水线 |
| word-frequency | 英文词频统计（等级标注 + COCA 排名），HTML / Anki / CSV |
| plugin-validator | 插件发布前校验（check_plugin.py，0 error 才能发布） |
| skill-distributor | 本地 skill 分发（link）与台账核对（audit / status） |
| hello-greeting / demo-case | 演示插件与个人工具集 |

## 第三方 skill（正本 = `~/.agents/skills/` 安装实体）

| skill | 安装方式 |
|---|---|
| mattpocock 工程套件（grilling、tdd、implement、to-spec、to-tickets、triage、wayfinder、code-review 等约 26 个） | 安装 mattpocock-skills 插件，或跑 `/setup-matt-pocock-skills` |
| git-guardrails-claude-code | 来源待补 |
| migrate-to-shoehorn | 来源待补 |
| scaffold-exercises | 来源待补 |
| setup-pre-commit | 来源待补 |
| apifox | `npx -y skills add https://github.com/apifox/apifox-cli-skills` |
| obsidian-skills | 经 marketplace 外部插件（github: kepano/obsidian-skills），不入枢纽 |
| computer-interface-controller、openclaw-self-evolution-pack | MiniMax 云端 skill-hub 安装，仅 MiniMax 可用 |

## 市场源

```
/plugin marketplace add anthropics/claude-plugins-official
/plugin marketplace add anthropics/claude-plugins-community
```

个人市场：<https://gitee.com/yuelezhou/my_claude_code_market>
