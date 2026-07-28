# My Claude Code Marketplace

> 个人常用的 Claude Code 插件市场

## 📁 项目结构

```
my_claude_code_market/
├── marketplace.json           # 市场配置文件
├── plugins/                   # 存放各个插件
│   └── my-utils/
│       ├── .claude-plugin/
│       │   └── plugin.json    # 插件元数据
│       ├── skills/            # Agent Skills
│       │   ├── quick-deploy/
│       │   │   └── SKILL.md
│       │   └── code-clean/
│       │       └── SKILL.md
│       ├── agents/            # 自定义代理
│       │   └── debug-helper.md
│       ├── commands/          # Slash 命令（可选）
│       ├── hooks/             # 事件处理（可选）
│       ├── .mcp.json          # MCP 配置（可选）
│       └── README.md          # 插件说明文档
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
claude --plugin-dir ./plugins/my-utils

# 或安装到项目
claude plugin install ./plugins/my-utils
```

### 方式三：从 GitHub 安装

```bash
# 推送后从 GitHub 安装
claude plugin install https://github.com/username/my_claude_code_market --plugin my-utils
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

4. 更新 `marketplace.json`

5. 提交更改：
   ```bash
   git add .
   git commit -m "Add new plugin: my-new-plugin"
   git push
   ```

## 🔄 使用插件

安装后，通过命名空间调用：

```
# 使用技能
请帮我 /my-utils:quick-deploy 部署应用

# 使用代理
@debug-helper 帮我分析这个 bug
```

## 📚 参考资料

- [Claude Code 官方插件文档](https://code.claude.com/docs/zh-CN/plugins)
- [插件参考文档](https://code.claude.com/docs/zh-CN/plugins-reference)
- [官方插件仓库](https://github.com/anthropics/claude-code/tree/main/plugins)

## 📖 License

MIT
