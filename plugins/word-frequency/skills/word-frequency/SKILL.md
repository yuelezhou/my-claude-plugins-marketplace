---
name: word-frequency
description: |
  统计 markdown 英语材料的词频并标注考试等级（中考/高考/CET4/CET6/专四/专八/
  考研/雅思/托福/GRE）和 COCA 词频排名，识别词典词组，生成 HTML 交互报告、
  Anki 导入文件和 CSV。
  触发：用户说"统计词频、整理生词、分析这篇文章的单词、给我做个生词表、
  生成单词本"时使用。
---

# 词频统计 (word-frequency)

输入 markdown 英语材料（外刊精读笔记、中英对照等），输出带考试等级标注的
生词表 + 词组 + 语境例句。

## 用法

```bash
python <skill目录>/scripts/wordfreq.py <md文件|目录|通配符> [选项]
```

| 选项 | 说明 |
|---|---|
| `--out DIR` | 输出目录（默认 `./wordfreq_output`） |
| `--all` | 不过滤，显示已会词和中考/高考/CET4 基础词 |
| `--min-count N` | 只保留出现 ≥ N 次的词 |
| `--mark w1,w2` | 把已掌握的词追加进 known_words.txt 后退出 |
| `--no-anki` / `--no-open` | 跳过 Anki 文件 / 不自动打开浏览器 |

## 标准工作流

1. 用户提供 md 材料路径 → 运行脚本 → 把 **HTML 报告路径**（输出目录下同名
   `.html`）告诉用户
2. 用户在 HTML 报告里勾选已会的词 → 点"复制已勾选" → 把词贴回来 →
   运行 `--mark 词1,词2` 记入 known_words.txt（下次统计自动过滤）
3. 要进 Anki：输出目录下 `*_anki.txt` 直接导入（分隔符 Tab、允许 HTML、
   第 3 列是标签）

## 数据说明（skill 目录 data/ 下，开箱即用）

- `dict.csv` 词典（word,phonetic,translation,collins）— 来自 ECDICT 基础版
- `levels.tsv` 等级词表 — 中考/高考/CET4/CET6/专四/专八/考研/雅思/托福/GRE
  （专四专八来自《英语专业四八级词汇表》星标拆分，ECDICT 无 TEM 标签）
- `lemma.tsv` 变形→原形映射（ECDICT exchange 字段，如 ran→run）
- `coca.tsv` COCA 20000 排名
- `phrases.tsv` 词组词典（ECDICT 多词条目 + 专四专八表内短语，16.8 万条）
- `known_words.txt` **用户的已会词表（用户状态，持续积累）**

⚠️ 插件更新会重置 known_words.txt——如果用户积累了已会词，更新前先备份
该文件（或把内容让用户贴出来，更新后 `--mark` 写回）。

## 行为要点

- 清洗：剥离 frontmatter/代码块/行内代码/HTML/链接URL/图片，忽略中文，
  连字符词拆分计数
- 词形归并到原形（running/runs/ran → run），变形明细保留在报告里
- 默认隐藏：known_words.txt 中的词 + 含任一中考/高考/CET4 标签的基础词
  （专四大纲覆盖 CET 词，必须按"交集"判断）；未收录词（人名/拼写怪词）
  以"未收录"标签单独显示
- 词组 = 词典登记过的短语在文中真实出现（大小写不敏感、允许词内连字符），
  非统计算法；已知限制：含变形的词组（如 ran out of）不匹配

## 数据重建（可选）

数据源均为公开仓库，`data/raw/` 不随插件分发。需要重建时下载：
skywind3000/ECDICT 的 `ecdict.csv`（63MB）和 mahavivo/english-wordlists 的
8 个词表到 `data/raw/`，然后运行 `scripts/build_data.py`。
