---
name: quick-deploy
description: 快速部署工具 - 自动化构建和部署流程。当用户说"部署"、"deploy"、"发布"时使用此技能。
---

# Quick Deploy Skill

快速部署工具帮你自动化构建和部署流程。

## 使用场景

- 部署应用到生产环境
- 部署到测试环境
- 构建和发布新版本

## 部署步骤

1. 检查 git 状态，确保所有更改已提交
2. 运行构建命令
3. 运行测试
4. 部署到目标环境
5. 验证部署结果

## 配置

在你的项目根目录添加 `deploy.config.json`：

```json
{
  "buildCommand": "npm run build",
  "testCommand": "npm test",
  "deployCommand": "npm run deploy",
  "env": "production"
}
```

## 示例

用户说："部署到生产环境"

Claude 会执行：
1. 检查 git 状态
2. 运行 `npm run build`
3. 运行 `npm test`
4. 运行 `npm run deploy`
5. 报告部署结果
