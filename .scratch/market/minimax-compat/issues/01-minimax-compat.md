Plugin: market
Status: resolved

# market 兼容 MiniMax Code 插件格式

## 需求

本项目以 Claude Code plugin 为基础，要求兼容 MiniMax Code 与 ZCode 的插件体系。

## 调研结论（2026-09-28）

- ZCode：原生读取 `.claude-plugin/marketplace.json` 与 `.claude-plugin/plugin.json`（本机缓存 claude-plugins-official 佐证）——零改动兼容
- MiniMax Code（mcode 0.4.0+）：首选形态即 Claude 兼容形态 `.claude-plugin/plugin.json`；支持 skills（≤64，frontmatter name 须与目录一致）与 MCP（根目录 `mcp.json`，≤8 服务器）；不支持自定义 agents/commands/LSP；无市场清单概念
- 依据：MiniMax-Code-Plugins docs/plugin-compatibility.md + 本机 runtime/缓存结构实测

## 实施记录

1. gitee-mcp 新增根目录 `mcp.json`（与 `.mcp.json` 内容相同）——Claude/ZCode 读点文件、MiniMax 读无点文件
2. plugin-validator 新增 `check_minimax_compat`：agents 不支持警告、双 MCP 文件一致性（error 级）、缺 `.mcp.json` 警告、64 skill 上限（error）、8 MCP 上限（warning）、根 plugin.json 残留警告；`mcp.json` 纳入 JSON 组件合法性检查
3. 新建 `docs/plugin-compatibility.md` 三平台兼容矩阵，AGENTS.md 关键文档区挂链接
4. 决定不兼容 mcode 0.3.x 便携格式（根目录 plugin.json），只目标 0.4.0+；暂不向 MiniMax-Code-Plugins 社区仓库贡献 PR

## Comments

- 2026-09-28 全量验证：8 插件 0 error；demo-case 因 debug-helper agent 带一条预期的 MiniMax 警告（接受降级，已在兼容矩阵注明）。
