# My Claude Code Marketplace

> 个人常用的 Claude Code 插件市场

## 📁 项目结构

```
my_claude_code_market/
├── .claude-plugin/
│   └── marketplace.json       # 市场配置文件（插件注册表）
├── AGENTS.md                  # 仓库协作约定（agent 读）
├── CONTEXT.md                 # 领域术语表
├── docs/
│   ├── adr/                   # 架构决策记录（如 ADR-0001 双正本分发）
│   ├── agents/                # 工程 skill 配置（issue tracker / triage / 域文档）
│   └── plugin-compatibility.md  # 三平台兼容性矩阵
├── scripts/
│   └── link_skills.py         # skill 分发兼容入口
├── .scratch/                  # 本地 issue tracker（按插件分域）
├── plugins/                   # 各个插件（自包含，共 8 个）
│   ├── demo-case/             # 演示与个人工具集
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json    # 插件元数据
│   │   ├── skills/            # Agent Skills
│   │   │   ├── quick-deploy/
│   │   │   └── code-clean/
│   │   ├── agents/
│   │   │   └── debug-helper.md
│   │   └── README.md
│   ├── anki-card-from-notes/  # 笔记转 Anki 卡片
│   ├── skill-distributor/     # 本地 skill 分发与台账核对
│   └── …
└── README.md
```

## 🚀 快速开始

### 方式一：添加到本地市场

```bash
cd /path/to/my_claude_code_market
claude plugin marketplace add local ./my_claude_code_market
```

### 方式二：直接安装插件

```bash
# 使用 --plugin-dir 测试
claude --plugin-dir ./plugins/demo-case

# 或安装到项目
claude plugin install ./plugins/demo-case
```

### 方式三：从 GitHub 安装

```bash
# 推送后从 GitHub 安装
claude plugin install https://github.com/username/my_claude_code_market --plugin demo-case
```

## 📦 Plugin 结构详解

每个插件是一个自包含的目录：

| 目录/文件 | 作用 | 必需 |
|-----------|------|------|
| `.claude-plugin/plugin.json` | 插件元数据 | ✅ |
| `skills/*/SKILL.md` | Agent Skills | ❌ |
| `agents/*.md` | 自定义代理 | ❌ |
| `commands/*.md` | Slash 命令 | ❌ |
| `hooks/hooks.json` | 事件处理 | ❌ |
| `.mcp.json` | MCP 配置 | ❌ |
| `.lsp.json` | LSP 配置 | ❌ |
| `monitors/monitors.json` | 后台监视器 | ❌ |
| `bin/` | 可执行文件 | ❌ |
| `settings.json` | 默认设置 | ❌ |
| `README.md` | 文档 | ❌ |

## 📝 添加新插件

1. 创建插件目录：
   ```bash
   mkdir -p plugins/my-new-plugin/.claude-plugin
   ```

2. 创建 `plugin.json`：
   ```json
   {
     "name": "my-new-plugin",
     "version": "1.0.0",
     "description": "我的新插件"
   }
   ```

3. 添加技能、代理等组件

4. 更新 `.claude-plugin/marketplace.json`

5. 发布前校验（0 error 才能提交）：
   ```bash
   python plugins/plugin-validator/skills/plugin-validator/scripts/check_plugin.py plugins/my-new-plugin
   ```

6. 分发 skill 到各 agent（ZCode/MiniMax/OpenCode/Deep Code 读枢纽，Claude Code 走链接层）：
   ```bash
   python scripts/link_skills.py
   ```

7. 提交更改：
   ```bash
   git add .
   git commit -m "Add new plugin: my-new-plugin"
   git push
   ```

## 🔄 使用插件

安装后，通过命名空间调用：

```
# 使用技能
请帮我 /demo-case:quick-deploy 部署应用

# 使用代理
@debug-helper 帮我分析这个 bug
```

## 🛠 Skill 分发与多平台兼容

本仓库的插件面向 **Claude Code / ZCode / MiniMax Code** 三个运行时：

- 自研 skill 的正本在本仓库，由 [skill-distributor](plugins/skill-distributor/README.md) 以 junction 分发到各 agent 的发现目录（架构见 [ADR-0001](docs/adr/0001-dual-canon-hub-and-junction-distribution.md)）
- 三平台的组件支持差异与逐插件兼容状态见 [docs/plugin-compatibility.md](docs/plugin-compatibility.md)
- 仓库协作约定（issue tracker 分域、triage 标签、领域术语）见 [AGENTS.md](AGENTS.md) 与 [docs/agents/](docs/agents/)

## 📚 参考资料

- [Claude Code 官方插件文档](https://code.claude.com/docs/zh-CN/plugins)
- [插件参考文档](https://code.claude.com/docs/zh-CN/plugins-reference)
- [官方插件仓库](https://github.com/anthropics/claude-code/tree/main/plugins)
- [MiniMax-Code-Plugins 插件兼容性文档](https://github.com/minimax-ai/minimax-code-plugins/blob/main/docs/plugin-compatibility.md)

## 📖 License

MIT
