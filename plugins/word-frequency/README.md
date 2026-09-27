# Word Frequency Plugin

Markdown 英语材料的词频统计（学习向）：等级标注 + COCA 排名 + 词组识别，
开箱即用（自带词典与词表数据，无需联网）。

## 功能

- **等级标注**：中考 / 高考 / CET4 / CET6 / **专四 / 专八** / 考研 / 雅思 / 托福 / GRE
  + COCA 真实语料库词频排名
- **词形归并**：running / runs / ran → run（ECDICT exchange 精确变形映射，
  报告保留变形明细）
- **词组识别**：16.8 万条词典短语在文中匹配（如 `in terms of`、`take off`）
- **生词收敛**：默认隐藏已会词和基础词；known_words.txt 持续积累，
  报告里勾选→复制→`--mark` 回写
- **四种输出**：HTML 交互报告（搜索/等级筛选/例句展开）/ Anki 导入 TSV / CSV / Markdown

## 使用

```bash
python skills/word-frequency/scripts/wordfreq.py 你的笔记.md
```

输出在 `wordfreq_output/`，主入口是同名 `.html` 报告。

## 数据来源

- [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)（释义/音标/变形/考研雅思等标签）
- [mahavivo/english-wordlists](https://github.com/mahavivo/english-wordlists)
  （CET/托福/GRE 词表、COCA_20000、英语专业四八级词汇表——专四专八标签的唯一来源）

词典管释义、考纲词表管等级：ECDICT 不含专四专八标记，专四专八由
《英语专业四八级词汇表》星标拆分（星标=专八，非星标减专八=专四）。

## ⚠️ known_words.txt 是用户状态

插件更新会重置它。更新前请备份（详见 SKILL.md）。
