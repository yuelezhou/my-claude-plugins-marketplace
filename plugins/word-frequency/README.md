# Word Frequency Plugin

英语材料的词频统计（学习向）：等级标注 + COCA 排名 + 词组识别，
开箱即用（自带词典与词表数据，无需联网）。支持 **txt / markdown / 非扫描版 PDF**。

## 功能

- **多格式输入**：txt 与 markdown 共用同一条链路（txt 视为"无结构的 markdown"）；
  PDF 走独立适配器（`pypdf` 可选依赖，缺失时 txt/markdown 照常可用）
- **等级标注**：中考 / 高考 / CET4 / CET6 / **专四 / 专八** / 考研 / 雅思 / 托福 / GRE
  + COCA 真实语料库词频排名
- **生词判定**：取该词的**最高**考试等级，只有落在基础三档（中考/高考/CET4）才隐藏；
  同时按 COCA 常见度阈值（默认 2000）挡掉超高频常识词
- **词形归并**：running / runs / ran → run（ECDICT exchange 精确变形映射，
  报告保留变形明细）；兜底候选必须通过词典验证，专名不会被砍成普通词
- **缩写还原**：`hasn't → has not`，计数计入还原后的完整形式
- **不丢词**：超长句按标点二次切分、必要时硬切，任何字符都不会被漏掉
- **词组识别**：16.8 万条词典短语按原形匹配（`took off` 命中 `take off`），
  真子串与母串只留长的，纯功能词短语（`try to` / `back to`）不进榜
- **注释区排除**：`## Vocabulary notes` / `## 生词表` 这类标题下的生词注释不参与统计
- **生词收敛**：known_words.txt 持续积累，报告里勾选→复制→`--mark` 回写
- **四种输出**：HTML 交互报告（搜索/等级筛选/例句展开/词组页同筛选）/
  Anki 导入 TSV / CSV / Markdown 摘要

## 使用

```bash
python skills/word-frequency/scripts/wordfreq.py 你的笔记.md
python skills/word-frequency/scripts/wordfreq.py 你的材料.pdf    # 需 pip install pypdf
python skills/word-frequency/scripts/wordfreq.py 笔记目录/        # 批量，按目录名输出
```

输出在 `wordfreq_output/`，主入口是同名 `.html` 报告。
单文件用材料名、多文件用所在目录名，两批材料不会互相覆盖。

| 选项 | 说明 |
|---|---|
| `--out DIR` | 输出目录（默认 `./wordfreq_output`） |
| `--all` | 不过滤，显示已会词、基础词、常识词与派生片段 |
| `--min-count N` | 只保留出现 ≥ N 次的词 |
| `--coca-rank N` | 隐藏 COCA 排名 ≤ N 的常识词（默认 2000，`0` = 关闭） |
| `--function-words FILE` | 追加功能词（一行一个），滤掉更多纯功能词短语 |
| `--mark w1,w2` | 把已掌握的词追加进 known_words.txt 后退出 |
| `--no-anki` / `--no-open` | 跳过 Anki 文件 / 不自动打开浏览器 |

## 数据来源

- [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)（释义/音标/变形/考研雅思等标签）
- [mahavivo/english-wordlists](https://github.com/mahavivo/english-wordlists)
  （CET/托福/GRE 词表、COCA_20000、英语专业四八级词汇表——专四专八标签的唯一来源）

词典管释义、考纲词表管等级：ECDICT 不含专四专八标记，专四专八由
《英语专业四八级词汇表》星标拆分（星标=专八，非星标减专八=专四）。

## ⚠️ known_words.txt 是用户状态

`data/known_words.txt` 是你自己的已会词表，**插件更新时不要覆盖它**。
词典数据（dict/levels/lemma/coca/phrases）需要重建时用
`python skills/word-frequency/scripts/build_data.py`，重建后把词典文件拷回来即可，
`known_words.txt` 保持原样。
