# 插件发布前验证清单

check_plugin.py 覆盖 A 组（0 error 必达）；B、C 是脚本之外的人工项。
验证对象是「插件目录」（含 `.claude-plugin/plugin.json` 的那一层）。

## A. 静态校验（check_plugin.py 自动）

| 检查项 | 级别 |
|---|---|
| `.claude-plugin/plugin.json` 存在且为合法 JSON 对象 | error |
| name / version / description 必填 | error |
| version 是 x.y.z 格式 | error |
| name 与插件目录名一致 | error |
| `skills/*/` 每个目录都有 SKILL.md | error |
| SKILL.md frontmatter 有 name 且与 skill 目录名一致 | error |
| SKILL.md frontmatter description 非空 | error |
| `agents/*.md` 有 frontmatter 且含 name | error |
| `.mcp.json`、`hooks/hooks.json`、`.lsp.json`、`monitors/monitors.json`、`settings.json`（存在哪个查哪个）是合法 JSON | error |
| 所有 `*.py`（递归）UTF-8 且语法可编译 | error |
| 已注册进最近的 marketplace.json 且 source 指向本目录（`--standalone` 跳过） | error |
| 插件名 / skill 名是 kebab-case | warning |
| SKILL.md description 足够长（≥30 字，它是触发依据） | warning |
| SKILL.md 正文非空 | warning |
| SKILL.md 引用的 `references/ scripts/ data/ assets/` 相对路径存在 | warning |
| `.mcp.json` 有 mcpServers、`hooks.json` 有 hooks | warning |
| agents/*.md 有 description | warning |
| plugin.json 与 marketplace.json 的 description 一致 | warning |
| README.md 存在 | warning |

## B. 交叉验证（本机有 claude CLI 就做）

1. `claude plugin validate <插件目录>` —— 官方校验器，结果以它为准
2. `claude --plugin-dir <插件目录>` 启动冒烟：skills / commands / agents 能被列出、能触发

## C. 仓库规则收尾（见根目录 AGENTS.md）

- [ ] marketplace.json 的 `plugins` 数组已加本插件条目
- [ ] plugin.json 与 marketplace.json 的 description / version 两处一致
- [ ] SKILL.md description 写清了触发场景与「不用于」边界（相邻 skill 的边界显式划清）
- [ ] 交付说明里注明校验结果（0 error；warning 如何处置）
