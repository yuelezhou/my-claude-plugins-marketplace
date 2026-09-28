# 重建词典数据

`data/raw/` 里的原始词表**不是运行时依赖**。`wordfreq.py` 只读 `data/` 顶层的 6 个产物文件
（约 9.4 MB）；`data/raw/`（约 65 MB）只有 `scripts/build_data.py` 会读，是"重建"的原料。

所以日常使用、测试、发布都不需要 `data/raw/`。只有在你**想重新生成词典数据**时才需要它。

## 原料 → 产物

| `data/raw/` 输入 | 大小 | 来自 | 产出 |
|---|---|---|---|
| `ecdict.csv` | 65.9 MB | [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT) 基础版 | `dict.csv`（释义/音标/柯林斯星级）、`lemma.tsv`（变形→原形）、`phrases.tsv`（多词条目） |
| `CET4_edited.txt` | 0.2 MB | [mahavivo/english-wordlists](https://github.com/mahavivo/english-wordlists) | `levels.tsv`、`phrases.tsv` |
| `CET6_edited.txt` | 0.2 MB | 同上 | `levels.tsv` |
| `Highschool_edited.txt` | 0.02 MB | 同上 | `levels.tsv`（高考档） |
| `TOEFL.txt` | 0.3 MB | 同上 | `levels.tsv` |
| `GRE_8000_Words.txt` | 0.4 MB | 同上 | `levels.tsv` |
| `英语专业四八级词汇表.txt` | 0.9 MB | 同上 | `levels.tsv`（专四/专八的唯一来源）、`phrases.tsv` |
| `英语专业星标八级词汇.txt` | 0.3 MB | 同上 | `levels.tsv`（星标=专八） |
| `COCA_20000.txt` | 0.2 MB | 同上 | `coca.tsv`（词频排名） |

产物：

| 文件 | 大小 | 用途 |
|---|---|---|
| `dict.csv` | 1.7 MB | 词 → 音标 / 释义 / 柯林斯星级 |
| `levels.tsv` | 0.4 MB | 词 → 等级集合（中考…GRE） |
| `lemma.tsv` | 0.5 MB | 变形 → 原形（ECDICT `exchange` 字段） |
| `coca.tsv` | 0.3 MB | 词 → COCA 排名 |
| `phrases.tsv` | 7.0 MB | 词典登记的词组 |
| `known_words.txt` | — | **你的已会词表，重建时不会被覆盖** |

专四/专八标签只能来自《英语专业四八级词汇表》：ECDICT 不含 TEM 标记，脚本按星标拆分
（星标 = 专八，非星标减专八 = 专四）。

## 步骤

```bash
# 1) 把 9 个原料文件放进 data/raw/，文件名必须与上表完全一致
#    （中文文件名注意编码：UTF-8）
#
# 2) 重建
python scripts/build_data.py
```

脚本会逐个检查原料是否齐全，缺哪个就报哪个：

```
[错误] 缺少原始文件 ...\data\raw\ecdict.csv，请先下载到 data/raw/
```

## 安全提示

- **`known_words.txt` 不会被覆盖** —— `build_data.py` 里是 `if not kp.exists()` 才创建。
  这是你的个人状态，重建后仍然有效。
- 其余 5 个产物会**原地覆盖**。重建前若对产物有改动，先备份。
- 重建后建议跑一次测试确认产物格式没变：
  `python -m unittest discover -s tests -t .`

## 重建后同步到各处

仓库是唯一源。改了产物后要同步到两个安装点（`known_words.txt` 不要拷）：

```bash
cp data/dict.csv data/levels.tsv data/lemma.tsv data/coca.tsv data/phrases.tsv \
   ~/.agents/skills/word-frequency/data/

cp data/dict.csv data/levels.tsv data/lemma.tsv data/coca.tsv data/phrases.tsv \
   D:/code/toy_and_tools/my_claude_code_market/plugins/word-frequency/skills/word-frequency/data/
```

同步完可以用哈希核对三处是否一致：

```bash
python -c "import hashlib,pathlib;[print(f, hashlib.sha256(p.read_bytes()).hexdigest()[:12]) for f in ('dict.csv','levels.tsv','lemma.tsv','coca.tsv','phrases.tsv') for p in (pathlib.Path('data')/f,)]"
```
