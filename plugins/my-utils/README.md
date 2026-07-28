# My Utils Plugin

个人常用工具集合插件。

## 📦 包含内容

### Skills

- **quick-deploy** - 快速部署工具
- **code-clean** - 代码清理工具

### Agents

- **debug-helper** - 调试助手

## 🚀 安装

```bash
claude plugin install ./plugins/my-utils
```

## 📝 使用

```bash
# 使用技能
请帮我 /my-utils:quick-deploy 部署应用

# 使用代理
@debug-helper 帮我分析这个 bug
```

## 🔧 配置

### 部署配置

在项目根目录创建 `deploy.config.json`：

```json
{
  "buildCommand": "npm run build",
  "testCommand": "npm test",
  "deployCommand": "npm run deploy",
  "env": "production"
}
```

## 📄 License

MIT
