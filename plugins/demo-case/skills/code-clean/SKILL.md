---
name: code-clean
description: 代码清理工具 - 移除未使用的导入、格式化代码、清理注释。当用户说"清理代码"、"clean"、"格式化"时使用此技能。
---

# Code Clean Skill

代码清理工具帮你保持代码整洁。

## 功能

1. 移除未使用的导入
2. 格式化代码
3. 清理过时的注释
4. 统一代码风格

## 支持的语言

- JavaScript/TypeScript
- Python
- Go
- Rust

## 使用方式

用户说："清理代码"

Claude 会执行：
1. 扫描项目中的代码文件
2. 识别未使用的导入
3. 移除未使用的导入
4. 格式化代码
5. 清理过时注释
6. 报告清理结果

## 示例

```typescript
// 清理前
import { unused, used } from './module'
const x = used()

// 清理后
import { used } from './module'
const x = used()
```
