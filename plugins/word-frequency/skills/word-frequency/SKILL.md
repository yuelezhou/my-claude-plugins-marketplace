---
name: word-frequency
description: 统计 txt / markdown / 非扫描版 PDF 英语材料的词频并标注专四/专八/CET4/CET6/考研/雅思/托福/GRE 等级和 COCA 词频排名，识别词典词组，生成 HTML 交互报告、Anki 导入文件和 CSV。当用户要"统计词频、整理生词、分析文章单词、生成单词本"时使用。
---

# 词频统计 (word-frequency)

输入英语材料（外刊精读笔记、中英对照 PDF、纯文本），输出带考试等级标注的生词表 + 词组 + 语境例句。

## 用法

```bash
python <skill目录>/scripts/wordfreq.py <md|txt|pdf文件|目录|通配符> [选项]
```

| 选项 | 说明 |
|---|---|
| `--out DIR` | 输出目录（默认 `./wordfreq_output`） |
| `--all` | 不过滤，显示已会词、基础词、常识词与派生片段 |
| `--min-count N` | 只保留出现 ≥ N 次的词 |
| `--coca-rank N` | 隐藏 COCA 排名 ≤ N 的常识词（默认 2000，`0` = 关闭） |
| `--function-words FILE` | 追加功能词（一行一个），滤掉更多纯功能词短语 |
| `--mark w1,w2` | 把已掌握的词追加进 known_words.txt 后退出 |
| `--no-anki` / `--no-open` | 跳过 Anki 文件 / 不自动打开浏览器 |

PDF 需要 `pypdf`（可选依赖，缺失时 txt / markdown 照常工作，PDF 会明确报错提示安装）。

## 标准工作流

1. 用户提供材料路径 → 运行脚本 → 把 **HTML 报告路径**（输出目录下同名 `.html`）告诉用户
2. 用户在 HTML 报告里勾选已会的词 → 点"复制已勾选" → 把词贴回来 →
   运行 `--mark 词1,词2` 记入 known_words.txt（下次统计自动过滤）
3. 要进 Anki：输出目录下 `*_anki.txt` 直接导入（分隔符 Tab、允许 HTML、第 3 列是标签）

## 数据说明（skill 目录 data/ 下）

- `dict.csv` 词典（word,phonetic,translation,collins）— 来自 ECDICT 基础版
- `levels.tsv` 等级词表 — 中考/高考/CET4/CET6/专四/专八/考研/雅思/托福/GRE
  （专四专八来自《英语专业四八级词汇表》星标拆分，ECDICT 无 TEM 标签）
- `lemma.tsv` 变形→原形映射（ECDICT exchange 字段）
- `coca.tsv` COCA 20000 排名
- `phrases.tsv` 词组词典（ECDICT 多词条目 + 专四专八表内短语）
- `known_words.txt` **用户的已会词表**（持久积累，勿覆盖删除）
- ⚠️ 上面 5 个词典文件就是运行时需要的全部数据（约 9.4 MB）。
  `data/raw/`（65 MB 的 ECDICT 原始词典 + 8 个考纲词表）**不是运行时依赖**，
  只有 `scripts/build_data.py` 重建数据时才需要 —— 重建步骤见
  `references/rebuild-data.md`。
- ⚠️ 仓库与 skill 各有一份 `data/`，**没有自动同步**。重建后要手动把 dict/levels/
  lemma/coca/phrases 拷到 skill 目录（`known_words.txt` 不要拷）。

## 行为要点

- **逐行二分**：材料块就是一行。一行要么整体保留要么整体丢弃，块内不做字符级过滤。
  中文块里的英文不回收（译文里的术语拿不出可用例句）
- **结构性剔噪**：噪声行判据是"英文词数少 + 非语言字符占比高"或"无句末标点 + 大写占比过高"，
  不写死黑名单正则
- **排除区块**：`## Vocabulary notes` / `## 生词表` 这类标题下的注释不参与统计
- 清洗：剥离 frontmatter/代码块/行内代码/HTML/链接URL/图片，忽略中文，连字符词拆分计数
- 词形归并到原形（running/runs/ran → run），**兜底候选必须通过词典验证**，
  否则保留原词形（`Peter` 不会被砍成 `pet`）
- 缩写归并前还原：`hasn't → has not`，计数计入还原后的完整形式
- 分词支持 Unicode 字母（`café` 完整）并排除 CJK；长句按标点二次切分，**不丢词**
- 连字符词同时产出整体形式（可查询、可被词组匹配）与片段（片段参与计数但不作为独立生词展示）
- 默认隐藏：known_words.txt 中的词 + **最高**等级属于基础三档的词 + COCA 高频常识词。
  判据是"最高等级"而非"等级集合相交"，所以 abandon / abstract / absorb 这类
  同时属于 CET4 和 GRE 的真难词不会被误藏
- 词组 = 词典登记过的短语在文中真实出现，按原形匹配（`took off` 命中 `take off`）；
  真子串与母串同时命中时只留长的；纯功能词短语不进榜
- 多文件输入时输出文件名按材料（目录名）区分，两批材料不会互相覆盖；
  报告与 CSV 列出每个词出现在哪些材料
- 例句按长度升序取，短的在前
