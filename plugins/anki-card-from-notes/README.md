# Anki Card From Notes Plugin

把笔记 / 讲义 / 书摘 / 文章转成 Anki 卡片 markdown 文件，兼容 `markdown_sync_to_anki`（或 Obsidian Anki 插件）的格式，可直接走同步工具推到 Anki。

## 📦 包含内容

### Skills

- **anki-card-from-notes** - 笔记转 Anki 卡片
  - `SKILL.md`：执行规则（选卡标准、卡片类型、字段写法、硬性约束、失败处理）
  - `references/card-format.md`：完整格式契约（标题层级语义、字段规范、3 个完整范例、严格禁止清单）

## 🚀 安装

```bash
# 从本地市场安装
cd /path/to/my_claude_code_market
claude plugin marketplace add local ./my_claude_code_market
claude plugin install anki-card-from-notes

# 或直接安装插件目录
claude plugin install ./plugins/anki-card-from-notes
```

## 📝 使用

安装后，让 Claude Code 把资料转成 Anki 卡片：

```
帮我把这段《算法导论》第 12 章 BST 的讲义转成 Anki 卡片，
deck 用 编程::算法导论::第12章，tags 用 algo,bst
```

## 📄 License

MIT
