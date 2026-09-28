#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wordfreq.py — 词频统计（英语学习向）

用法:
    python wordfreq.py <md文件|txt文件|目录|通配符> [--out 输出目录] [--all] [--min-count N] [--no-anki]
    python wordfreq.py --mark word1,word2        # 把已掌握的词追加进 known_words.txt

流程: 适配器(材料→材料块) → 剔噪 → 剥 markdown 语法 → 逐行二分出英材
      → 分句分词 → 词形归并(running→run) → 词频统计 → 词典短语匹配
      → 等级标注(中考..GRE/专四/专八) + COCA 排名 → 默认隐藏已会词和基础词
输出: HTML 交互报告 / Anki 导入 txt / CSV / Markdown 摘要
"""
import argparse
import csv
import html as html_mod
import json
import re
import sys
import time
import webbrowser
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

LEVEL_ORDER = ["zk", "gk", "cet4", "cet6", "tem4", "tem8", "ky", "ielts", "toefl", "gre"]
LEVEL_NAMES = {
    "zk": "中考", "gk": "高考", "cet4": "CET4", "cet6": "CET6",
    "tem4": "专四", "tem8": "专八", "ky": "考研", "ielts": "雅思",
    "toefl": "托福", "gre": "GRE",
}
BASIC_LEVELS = {"zk", "gk", "cet4"}  # 基础三档：默认隐藏
#: COCA 常见度阈值。排名在这个区间内（数字越小越常见）视为常识词，默认隐藏。
#: 0 < rank <= 阈值 才算常识词：rank 为 0 表示该词不在 COCA 表里，而表外的多半是
#: 专名或生僻词，那些是真生词，不能误藏。设 0 关闭这条规则。
#:
#: 取 2000 而不是更宽：abandon 的排名是 2201、abstract 4045、absorb 3145，
#: 阈值一旦越过 2201 就把 abandon 挡掉了，而它按定义是真难词。
COCA_COMMON_RANK = 2000


# ---------------------------------------------------------------- 数据加载

def _open(path, encoding="utf-8"):
    for enc in (encoding, "utf-8-sig", "gbk"):
        try:
            return open(path, "r", encoding=enc), enc
        except UnicodeDecodeError:
            continue
    return open(path, "r", encoding="utf-8", errors="replace"), "utf-8"


def load_levels(data_dir=None):
    """word -> set(level keys)"""
    levels = defaultdict(set)
    p = Path(data_dir or DATA_DIR) / "levels.tsv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2 and parts[1]:
                    levels[parts[0]] = set(x for x in parts[1].split("|") if x)
    return levels


def load_dict(data_dir=None):
    """word -> (phonetic, translation, collins)"""
    d = {}
    p = Path(data_dir or DATA_DIR) / "dict.csv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) >= 3:
                    d[row[0]] = (row[1], row[2], row[3] if len(row) > 3 else "")
    return d


def load_lemma(data_dir=None):
    """变形 -> 原形"""
    m = {}
    p = Path(data_dir or DATA_DIR) / "lemma.tsv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2:
                    m[parts[0]] = parts[1]
    return m


def load_coca(data_dir=None):
    """word -> 排名"""
    c = {}
    p = Path(data_dir or DATA_DIR) / "coca.tsv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2:
                    try:
                        c[parts[0]] = int(parts[1])
                    except ValueError:
                        pass
    return c


def load_phrases(data_dir=None):
    """[(phrase, translation)]"""
    out = []
    p = Path(data_dir or DATA_DIR) / "phrases.tsv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 1 and parts[0].strip():
                    out.append((parts[0].strip().lower(), parts[1].strip() if len(parts) > 1 else ""))
    return out


def load_known(data_dir=None):
    p = Path(data_dir or DATA_DIR) / "known_words.txt"
    known = set()
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w and not w.startswith("#"):
                    known.add(w)
    return known, p


def mark_known(words, path):
    existing, _ = load_known()
    added = []
    for w in words:
        w = w.strip().lower()
        if w and w not in existing:
            existing.add(w)
            added.append(w)
    if added:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(added) + "\n")
    print(f"已追加 {len(added)} 个已会词到 {path}")
    if not added:
        print("（没有新词，全部已在列表中）")


@dataclass(frozen=True)
class Lexicon:
    """统计所需的全部数据。

    这是本 spec 唯一的接缝：CLI 从磁盘加载它，测试注入小规模内存数据，
    于是统计主流程不用碰 14MB 真实词典也能跑。
    """
    levels: dict = field(default_factory=dict)      # word -> set(level keys)
    dictionary: dict = field(default_factory=dict)  # word -> (音标, 释义, 柯林斯星级)
    lemma_map: dict = field(default_factory=dict)   # 变形 -> 原形
    coca: dict = field(default_factory=dict)         # word -> 排名
    phrase_list: tuple = ()                         # [(短语, 释义)]
    known: frozenset = frozenset()                  # 已知词：用户声明已掌握、要永久隐去的词
    known_path: object = None                       # known_words.txt 的位置


def load_lexicon(data_dir=None):
    """唯一读词典数据的地方。"""
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    known, known_path = load_known(data_dir)
    return Lexicon(
        levels=load_levels(data_dir),
        dictionary=load_dict(data_dir),
        lemma_map=load_lemma(data_dir),
        coca=load_coca(data_dir),
        phrase_list=tuple(load_phrases(data_dir)),
        known=frozenset(known),
        known_path=known_path,
    )


# ---------------------------------------------------------------- 适配器 (Adapter)
#
# 材料 (Material) = 适配器产出的规范化输入。材料块 (Block) = 一行。
# 英材 (English run) = 判定为英文的块按原序组成的序列，是词频统计的真正输入。
#
# 块内不做字符级过滤：一行要么整体保留，要么整体丢弃。选它是因为判据可解释 ——
# "为什么这个词没进统计"永远能一句话答完。
#
# 链路边界的阈值都写在这里并标注依据，不藏在函数体里。

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}

#: 一行内 CJK 字符占比超过它就判为中文块。依据：逐行二分的材料里，中文译文行
#: 的 CJK 占比接近 1，含少量中文注释的英文行实测在 0.10-0.25 之间。
CJK_RATIO_LIMIT = 0.3
#: 规则 A —— 英文词数低于它，才进一步看非语言字符占比（避免误杀正常短句）。
NOISE_MAX_ENGLISH_WORDS = 3
#: 规则 A —— 非语言字符（符号、装饰符）占比高于它即判为噪声行。
NOISE_MAX_SYMBOL_RATIO = 0.35
#: 规则 B —— 字母里大写占比高于它，且整行无句末标点，判为标签/大字报行。
NOISE_MIN_UPPER_RATIO = 0.7
#: 规则 B —— 只对短行生效。长句即便全大写也当正文，不动。
NOISE_MAX_WORDS_UPPER = 8
#: 句末标点。用于规则 B。
SENTENCE_END = ".!?…。！？；"

# CJK 汉字 + CJK 标点 + 全角形式。探针脚本实测用的就是这组码位。
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
                     r"\u3000-\u303f\uff00-\uffef]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
# 语言字符 = 字母数字下划线 + 词内连字符撇号。CJK 字符算语言字符不算装饰。
_LANG_CHAR_RE = re.compile(r"[\w]|['’\-]")

_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_LIST_RE = re.compile(r"^\s{0,3}([-*+]|\d+[.)])\s+")
_QUOTE_RE = re.compile(r"^\s{0,3}(?:>\s?)+")
# 强调标记只在词边界上剥，避免把 snake_case_name 啃成 snakecasename。
_EMPHASIS_RE = re.compile(r"(?<!\w)[*_~]+|[*_~]+(?!\w)")
_INLINE_SUBS = (
    (re.compile(r"`[^`\n]*`"), " "),                          # 行内代码
    (re.compile(r"<!--.*?-->", re.S), " "),                   # HTML 注释
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),               # 图片（整体丢弃）
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),            # 链接保留文字
    (re.compile(r"<[^>]+>"), " "),                            # HTML 标签
    (re.compile(r"https?://\S+|www\.\S+"), " "),              # URL
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), " "),            # 邮箱
    (_EMPHASIS_RE, ""),                                       # 强调标记
)


class AdapterError(RuntimeError):
    """输入无法交给任何适配器，或适配器缺少运行条件。"""


@dataclass(frozen=True)
class Material:
    """规范化材料：按原序排列的材料块（一行一块）。"""
    name: str
    blocks: tuple
    #: 这份材料是不是 markdown。txt 与 PDF 都是 False，剥不剥语法由它决定，
    #: 统计主流程因此不需要知道适配器。
    markdown: bool = False


class Adapter:
    """把某一种文件格式变成规范化材料。"""
    #: 是否剥离 markdown 语法。txt 与 PDF 都是 False。
    strip_markdown = False

    def read(self, path):
        raise NotImplementedError


class TextAdapter(Adapter):
    """txt 与 markdown 共用的一条链路，唯一差别是 strip_markdown 开关。

    txt 被视为"无结构的 markdown"：它走同一条链路，只是不剥语法。
    """
    def __init__(self, strip_markdown=True):
        self.strip_markdown = bool(strip_markdown)

    def material_from_text(self, text, name):
        return Material(name=name, blocks=tuple(text.splitlines()),
                        markdown=self.strip_markdown)

    def read(self, path):
        path = Path(path)
        f, _ = _open(path)
        try:
            text = f.read()
        finally:
            f.close()
        return self.material_from_text(text, path.name)


# ---------------------------------------------------------------- PDF 适配器

#: 连字码位 -> 普通字母。PDF 声明了 ToUnicode 映射时这些码位会完整保留在抽取
#: 结果里，所以修复是零猜测的：一张替换表就够，不需要词典校验或模式推断。
#: 只收这六个码位 —— 别的连字形态本机没测到，不凭空扩表。
LIGATURES = {
    "ﬀ": "ff",   # ff
    "ﬁ": "fi",   # fi
    "ﬂ": "fl",   # fl
    "ﬃ": "ffi",  # ffi
    "ﬄ": "ffl",  # ffl
    "ﬆ": "st",   # st
}


def fix_ligatures(text):
    """把连字码位还原成普通字母。零猜测：只查表。"""
    for src, dst in LIGATURES.items():
        if src in text:
            text = text.replace(src, dst)
    return text


class PdfAdapter(Adapter):
    """非扫描版 PDF。pypdf 是可选依赖（见 ADR 0003）。

    只负责出文本：逐页 extract_text 后按页序拼接，保留原始换行 ——
    材料块是行，判中英与剔噪是 001 已建好的链路的事。
    """
    strip_markdown = False

    def read(self, path):
        path = Path(path)
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise AdapterError(
                "处理 PDF 需要 pip install pypdf（txt / markdown 不受影响，照常可用）") from e
        try:
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as e:
            raise AdapterError(f"PDF 解析失败: {path.name}: {e}") from e
        text = "\n".join(pages)
        if not text.strip():
            raise AdapterError(
                f"{path.name} 没有文字层，可能是扫描版。请先做 OCR，或换一份能复制文字的 PDF；"
                f"本工具只承诺非扫描版，不做 OCR。")
        return Material(name=path.name,
                        blocks=tuple(fix_ligatures(text).splitlines()))


def get_adapter(path):
    """按扩展名路由到适配器。"""
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return TextAdapter(strip_markdown=suffix in MARKDOWN_SUFFIXES)
    if suffix == ".pdf":
        return PdfAdapter()
    raise AdapterError(
        f"暂不支持的输入类型: {Path(path).name}"
        f"（本轮支持 {'/'.join(sorted(TEXT_SUFFIXES))} 与 .pdf）")


# ---------------------------------------------------------------- 剔噪与剥语法

def is_noise(line):
    """结构性剔噪。不写死黑名单正则，只看可解释的结构特征。"""
    stripped = line.strip()
    if not stripped:
        return False
    words = _LATIN_WORD_RE.findall(stripped)

    # 规则 A: 英文词数少 + 非语言字符占比高 → 推广行、装饰行
    # 至少要有一个英文词。没有英文词的符号行（`---`、` ``` `）产不出词元，
    # 动它没有收益，却会把 markdown 的围栏拆散、让后半篇文档被整段吞掉。
    if words and len(words) < NOISE_MAX_ENGLISH_WORDS:
        visible = [ch for ch in stripped if not ch.isspace()]
        symbols = [ch for ch in visible if not _LANG_CHAR_RE.match(ch)]
        if symbols and len(symbols) / len(visible) > NOISE_MAX_SYMBOL_RATIO:
            return True

    # 规则 B: 无句末标点 + 大写占比过高 → 标签行、大字报行
    if words and len(words) <= NOISE_MAX_WORDS_UPPER:
        if not any(ch in SENTENCE_END for ch in stripped):
            letters = _LATIN_LETTER_RE.findall(stripped)
            upper = sum(1 for ch in letters if ch.isupper())
            if letters and upper / len(letters) >= NOISE_MIN_UPPER_RATIO:
                return True
    return False


def _strip_inline_markdown(line):
    if _HR_RE.match(line):
        return ""
    line = _HEADING_RE.sub("", line)
    line = _QUOTE_RE.sub("", line)
    line = _LIST_RE.sub("", line)
    for pat, repl in _INLINE_SUBS:
        line = pat.sub(repl, line)
    return line


def strip_markdown_syntax(blocks):
    """按行剥离 markdown 语法，保留"一行一块"的结构。

    逐行而非整篇处理，是为了让标题层级活到这一步之后 —— 007 的排除区块
    要靠标题定位区间。

    围栏没闭合时把整段还回来：宁可把代码当正文，也不能静默丢掉半篇材料。
    """
    out = []
    fenced = []          # 当前围栏内的行，围栏未闭合时要还回来
    fence = None
    start = 0
    first = next((i for i, ln in enumerate(blocks) if ln.strip()), None)
    if first is not None and blocks[first].strip() == "---":     # frontmatter
        for j in range(first + 1, len(blocks)):
            if blocks[j].strip() in ("---", "..."):
                start = j + 1
                break
    for line in blocks[start:]:
        m = _FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
                fenced = []
            else:
                fenced.append(line)
            continue
        if m:
            fence = m.group(1)
            fenced.append(line)
            continue
        out.append(_strip_inline_markdown(line))
    if fence is not None:
        out.extend(_strip_inline_markdown(ln) for ln in fenced)
    return out


# ---------------------------------------------------------------- 排除区块

#: 默认排除的中英文生词注释标题（标题文字匹配，大小写不敏感）。可由用户替换。
DEFAULT_EXCLUDE_HEADINGS = (
    "vocabulary notes", "vocabulary", "new words", "words to learn", "word list",
    "生词", "生词表", "生词本", "生词注释", "词汇", "词汇表", "单词表", "重点词",
)
_HEADING_LINE_RE = re.compile(r"^\s{0,3}(#{1,6})\s*(.*)$")
# 注释区里的内容长这样：列表项、引用块，或 `word: 释义` 的对照行。
_NOTE_ITEM_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+|^\s{0,3}>\s?|^\s*[\w' \-]{1,30}[:：]\s*\S")


def _is_note_item(line):
    return bool(line.strip()) and bool(_NOTE_ITEM_RE.match(line))


def exclude_blocks(blocks, headings=DEFAULT_EXCLUDE_HEADINGS):
    """按 markdown 标题排除区块。

    从命中的标题起，到**下一个同级或更高级标题**为止；若先遇到第一行正文
    （既不是空行也不是注释条目）也收尾 —— 样例里的注释区后面并没有新标题，
    只按标题层级排会把后面的正文一起吃掉。

    判据全是结构性的：标题文字、标题层级、条目形状，不猜哪段是注释。
    """
    wanted = {h.strip().lower() for h in headings}
    out = []
    level = None                      # 非 None = 正在排除，且这是排除区的标题层级
    for line in blocks:
        m = _HEADING_LINE_RE.match(line)
        if m:
            depth = len(m.group(1))
            title = m.group(2).strip().lower()
            if level is not None and depth <= level:
                level = None           # 同级或更高级标题 -> 排除区结束
                out.append(line)       # 这个标题本身属于正文
            elif title in wanted:
                level = depth          # 进入排除区，标题行自己也不参与统计
            elif level is None:
                out.append(line)       # 普通标题
            # 否则是排除区里的更深层标题，整行丢掉
            continue
        if level is None:
            out.append(line)
        elif not line.strip() or _is_note_item(line):
            continue
        else:
            level = None               # 遇到正文，收尾
            out.append(line)
    return out


def prepare_blocks(material, exclude_headings=DEFAULT_EXCLUDE_HEADINGS):
    """适配 → 排除区块 → 剔噪 → 剥 markdown 语法。

    排除区块排在最前面，两个原因：剥语法会把 `#` 标记去掉，那时标题层级就丢了；
    剔噪的规则 B（大写占比高、无句末标点）会吃掉 `## VOCABULARY NOTES` 这种全大写
    标题。两者都会让排除区间算不出来 —— 结构性元素必须比结构性规则先活下来。
    """
    blocks = list(material.blocks)
    markdown = material.markdown
    if exclude_headings and markdown:
        blocks = exclude_blocks(blocks, exclude_headings)
    blocks = [b for b in blocks if not is_noise(b)]
    if markdown:
        blocks = strip_markdown_syntax(blocks)
    return blocks


# ---------------------------------------------------------------- 英材二分

def cjk_ratio(line):
    visible = [ch for ch in line if not ch.isspace()]
    if not visible:
        return 0.0
    return sum(1 for ch in visible if _CJK_RE.match(ch)) / len(visible)


def english_run(blocks):
    """英材 = 判定为英文的块按原序组成的序列。

    中文块里的英文不回收：译文里的术语拿不出可用例句，回收它还得引入
    "多少个英文词才算术语行"的阈值启发式。
    """
    return [b for b in blocks if b.strip() and cjk_ratio(b) <= CJK_RATIO_LIMIT]


# ---------------------------------------------------------------- 分句与分词

#: 超过它就二次切分，绝不整句丢弃。
MAX_SENTENCE_CHARS = 300
#: 只用来剔掉无字母的碎片，不再用来卡长度上限。
MIN_SENTENCE_CHARS = 2
#: 每词最多几条例句。
MAX_EXAMPLES = 3

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|(?<=[。！？；])")
# 超长句的二次切点。不含连字符，否则会把 office-centric 这类复合词切开。
_SECONDARY_SPLIT_RE = re.compile(r"(?<=[,，、:：;；—–])\s+")

# 分词认的"字母"：Unicode 字母，但排除 CJK 汉字与假名 —— 它们在 \w 里，
# 不显式排除的话中文会被切成一堆假词。码位与 _CJK_RE 保持一致。
# 分词认的"字母"：Unicode 字母，但排除 CJK 汉字与假名 —— 它们在 \w 里，
# 不显式排除的话中文会被切成一堆假词。码位与 _CJK_RE 保持一致。
_TOKEN_LETTER = r"[^\W\d_぀-ヿ㐀-䶿一-鿿豈-﫿]"
TOKEN_RE = re.compile(rf"{_TOKEN_LETTER}+(?:['’\-]{_TOKEN_LETTER}+)*")

# 常见英语缩写。还原后计数计入完整形式，hasn't 的这一次出现就算进 has。
# 规则显式列出，不做模式推断。
_NEGATIVE_CONTRACTIONS = {
    "isn't": "is not", "aren't": "are not", "wasn't": "was not",
    "weren't": "were not", "hasn't": "has not", "haven't": "have not",
    "hadn't": "had not", "doesn't": "does not", "don't": "do not",
    "didn't": "did not", "couldn't": "could not", "wouldn't": "would not",
    "shouldn't": "should not", "mustn't": "must not", "needn't": "need not",
    "mightn't": "might not", "daren't": "dare not",
    "can't": "can not", "won't": "will not", "shan't": "shall not",
}
# he’s / she’s 在 is 与 has 之间有歧义，一律取 is。两种读法下实词都是 he/she，
# 差别只落在一个基础助动词上，不影响生词表。
_OTHER_CONTRACTIONS = {
    "i'm": "i am", "you're": "you are", "we're": "we are", "they're": "they are",
    "he's": "he is", "she's": "she is", "it's": "it is", "that's": "that is",
    "there's": "there is", "what's": "what is", "who's": "who is",
    "here's": "here is", "how's": "how is", "where's": "where is",
    "i've": "i have", "you've": "you have", "we've": "we have",
    "they've": "they have",
    "i'd": "i would", "you'd": "you would", "we'd": "we would",
    "they'd": "they would", "he'd": "he would", "she'd": "she would",
    "it'd": "it would",
    "i'll": "i will", "you'll": "you will", "we'll": "we will",
    "they'll": "they will", "he'll": "he will", "she'll": "she will",
    "it'll": "it will",
    "let's": "let us",
}
CONTRACTIONS = {**_NEGATIVE_CONTRACTIONS, **_OTHER_CONTRACTIONS}


class Token(NamedTuple):
    """一个词元。fragment=True 表示它是派生片段，本身不是待学词。"""
    text: str
    fragment: bool = False


def expand_token(surface):
    """表面形式 -> 它代表的词元文本列表（缩写还原 + 去所有格）。"""
    text = surface.replace("’", "'").lower()
    if text in CONTRACTIONS:
        return CONTRACTIONS[text].split()
    if text.endswith("'s"):        # 单数所有格 the government's
        text = text[:-2]
    elif text.endswith("'"):       # 复数所有格 dogs'
        text = text[:-1]
    return [text]


def sentence_tokens(sent):
    """句子 -> 词元列表。

    连字符词同时产出整体形式与各片段：整体形式可被查询与词组匹配命中，
    片段照常参与计数，但标记为派生片段，不作为独立生词展示。
    """
    toks = []
    for surface in TOKEN_RE.findall(sent):
        for text in expand_token(surface):
            if not text:
                continue
            if "-" in text:
                toks.append(Token(text, False))
                toks.extend(Token(frag, True) for frag in text.split("-") if frag)
            else:
                toks.append(Token(text, False))
    return toks


def _normalize_sentence(raw):
    s = raw.strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[*_~`]+", "", s)  # 去掉残留的强调标记
    return s.strip(" \t#>|=-—–,.:;!?()[]{}\"'“”‘’…·")


def _hard_split(s, limit):
    """切不动了就按最大长度硬切，优先落在词边界上。"""
    out = []
    rest = s
    while len(rest) > limit:
        cut = rest[:limit + 1].rfind(" ")
        if cut <= 0:
            cut = limit
        piece = rest[:cut].strip()
        if piece:
            out.append(piece)
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out


def _split_oversized(s, limit=MAX_SENTENCE_CHARS):
    """超长句按标点二次切分，仍切不动就硬切。保证任何字符都不被丢弃。"""
    if len(s) <= limit:
        return [s]
    out = []
    for part in _SECONDARY_SPLIT_RE.split(s):
        part = part.strip()
        if not part:
            continue
        if len(part) <= limit:
            out.append(part)
        else:
            out.extend(_hard_split(part, limit))
    return out


def split_sentences(text):
    sents = []
    for raw in _SENT_SPLIT_RE.split(text):
        for piece in _split_oversized(_normalize_sentence(raw)):
            if len(piece) >= MIN_SENTENCE_CHARS and TOKEN_RE.search(piece):
                sents.append(piece)
    return sents


def attach_examples(words, sentences_all, lemma_of, max_examples=MAX_EXAMPLES):
    """给每个词挑例句：按长度升序取，短的在前，最多 max_examples 条。"""
    for low, orig in sentences_all:
        for text in {t.text for t in sentence_tokens(low)}:
            st = words.get(lemma_of(text))
            if st is not None and orig not in st.examples:
                st.examples.append(orig)
    for st in words.values():
        st.examples.sort(key=len)
        del st.examples[max_examples:]


# ---------------------------------------------------------------- 词形归并

#: -er / -est 的基词至少要这么长，才认为它是派生而不是巧合。
#: pet + er = peter 是人名不是派生词，所以 3 字母基词的候选不予采纳；
#: 而 run / work / farm 这类真基词本身就在词典里，根本走不到这条规则。
DERIV_MIN_BASE = 4


def rule_candidates(w):
    cands = []
    if w.endswith("ies") and len(w) > 4:
        cands.append(w[:-3] + "y")
    if w.endswith("sses") and len(w) > 5:
        cands.append(w[:-2])
    if w.endswith(("shes", "ches", "xes", "zes")) and len(w) > 5:
        cands.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        cands.append(w[:-1])
    if w.endswith("ied") and len(w) > 4:
        cands.append(w[:-3] + "y")
    if w.endswith("ed") and len(w) > 4:
        cands.append(w[:-2])
        cands.append(w[:-1])
    if w.endswith("ying") and len(w) > 5:
        cands.append(w[:-4] + "ie")
    if w.endswith("iing") and len(w) > 5:  # skiing->ski 之类少见,保守处理
        pass
    if w.endswith("ing") and len(w) > 5:
        base = w[:-3]
        cands.append(base)
        cands.append(base + "e")                      # making->make
        if len(base) > 2 and base[-1] == base[-2]:    # running->run
            cands.append(base[:-1])
    if w.endswith("est") and len(w) > 5:
        if len(w[:-3]) >= DERIV_MIN_BASE:
            cands.append(w[:-3])
        if len(w[:-2]) >= DERIV_MIN_BASE:
            cands.append(w[:-2])
    if w.endswith("er") and len(w) > 4:
        if len(w[:-2]) >= DERIV_MIN_BASE:
            cands.append(w[:-2])
        if len(w[:-1]) >= DERIV_MIN_BASE:
            cands.append(w[:-1])
    return cands


class Lemmatizer:
    def __init__(self, lemma_map, valid_words):
        self.map = lemma_map
        self.valid = valid_words

    def __call__(self, w):
        if w in self.map:
            return self.map[w]
        if w in self.valid:
            return w
        # 兜底候选必须通过词典验证才可采纳。全部候选都没通过时保留原词形，
        # 归入未收录 —— 否则 Peter 会被砍成 manchest，Kubernetes 会被砍成 kubernete。
        #
        # 注意规则路径只对"既不在词典也不在变形表"里的词生效，也就是专名、拼写
        # 怪词、外来词：真正的英语变形都由 lemma.tsv 或词典本身接住了。
        for c in rule_candidates(w):
            if c in self.valid or c in self.map:
                return self.map.get(c, c)
        return w


# ---------------------------------------------------------------- 词组匹配

#: 完全由这些词构成的短语不进词组榜 —— 它们不构成可学习的搭配。
#: 显式列出，不做隐式启发式。可配置：命令行 --function-words 追加，
#: 或直接改这里。try / back 来自 spec 点名的例子（try to / back to）。
FUNCTION_WORDS = frozenset({
    # 介词
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "into", "onto",
    "about", "over", "under", "after", "before", "between", "through", "during",
    "against", "within", "without", "upon", "among", "along", "across", "behind",
    "beyond", "toward", "towards", "up", "down", "out", "off", "as", "than",
    # 冠词、限定词、代词
    "a", "an", "the", "this", "that", "these", "those", "there", "here",
    "it", "its", "he", "him", "his", "she", "her", "hers", "they", "them",
    "their", "we", "us", "our", "you", "your", "i", "me", "my", "one", "ones",
    # 系动词、助动词、情态动词
    "be", "is", "am", "are", "was", "were", "been", "being",
    "do", "does", "did", "have", "has", "had", "will", "would", "can", "could",
    "shall", "should", "may", "might", "must",
    # 副词、连词、否定与量化
    "not", "no", "or", "and", "but", "if", "so", "such", "then", "also",
    "some", "any", "all", "both", "each", "other", "another", "more", "most",
    # spec 点名要滤掉的两个
    "try", "back",
})


def is_function_phrase(lemmas, function_words=FUNCTION_WORDS):
    """短语完全由功能词构成 -> 不值得学。"""
    return bool(lemmas) and all(w in function_words for w in lemmas)


def _word_seq_contains(big, small):
    """small 的词序列是否被 big 连续包含。"""
    n, k = len(big), len(small)
    return k < n and any(big[i:i + k] == small for i in range(n - k + 1))


def _phrase_frequency(phrase, coca):
    """词组各词的 COCA 排名之和；没收录的词按无穷大算（越常见越靠前）。

    用来在"归并后完全等价"的重复项之间挑一个：in terms of 比 in term of 常见，
    take off 比 taking off 常见。这是数据驱动的取舍，不是手写规则。
    """
    if not coca:
        return float("inf")
    total = 0
    for word in phrase.split():
        rank = coca.get(word, 0)
        if not rank:
            return float("inf")
        total += rank
    return total


def prune_substring_phrases(entries, lemma_of=None, coca=None):
    """真子串与母串同时命中时只留长的那条。

    比较用**原形序列**，因为匹配是在原形序列上做的 —— 只比字面词形的话，
    `in term of` 与 `in terms of`、`take off` 与 `taking off` 会被当成两条不同的
    词组同时上榜，而它们归并后是同一个搭配。

    原形序列完全等价时，取更常见的那个（见 _phrase_frequency）。

    entries: [(phrase, [count, trans, examples])] -> 只含该留的。
    """
    seqs = {phrase: phrase.split() for phrase, _ in entries}
    lemmas = {phrase: [lemma_of(w) for w in seqs[phrase]] for phrase in seqs} \
        if lemma_of else {phrase: seqs[phrase] for phrase in seqs}

    dropped = set()
    for phrase in seqs:
        for other in seqs:
            if other == phrase or phrase in dropped:
                continue
            if _word_seq_contains(lemmas[other], lemmas[phrase]):
                dropped.add(phrase)          # 真子串：留长的
                break
            if lemmas[other] == lemmas[phrase] and phrase not in dropped:
                # 归并后等价：留更常见的那个
                if _phrase_frequency(phrase, coca) > _phrase_frequency(other, coca):
                    dropped.add(phrase)
                    break
    return [(p, rec) for p, rec in entries if p not in dropped]


def find_phrases(sentences, phrase_list, lemma_of, levels=None, coca=None,
                 function_words=FUNCTION_WORDS, max_examples=2):
    """在已归并的句子词元序列上匹配词组。

    sentences: [(lemma 序列, 原文)]
    匹配走原形序列而不是字面正则，所以 `took off` 能命中 `take off`。
    短语一律来自词典登记，不做 n-gram 统计算法。

    levels 给了就把词组的等级也算出来（取各词等级的并集），词组页因此能和
    单词页共用同一套等级筛选。
    """
    if function_words is None:
        function_words = FUNCTION_WORDS
    index = {}                                   # 首词 -> [(词序列, 短语, 释义)]
    for phrase, trans in phrase_list:
        lemmas = [lemma_of(w) for w in phrase.split()]
        if not lemmas or is_function_phrase(lemmas, function_words):
            continue
        index.setdefault(lemmas[0], []).append((lemmas, phrase, trans))

    found = {}                                   # 短语 -> [次数, 释义, 例句]
    for lemmas, orig in sentences:
        for i, first in enumerate(lemmas):
            for cand, phrase, trans in index.get(first, ()):
                if lemmas[i:i + len(cand)] == cand:
                    rec = found.setdefault(phrase, [0, trans, []])
                    rec[0] += 1
                    if len(rec[2]) < max_examples and orig not in rec[2]:
                        rec[2].append(orig)

    hits = []
    for phrase, rec in prune_substring_phrases(list(found.items()),
                                               lemma_of=lemma_of, coca=coca):
        hit = {"p": phrase, "c": rec[0], "def": rec[1], "ex": rec[2]}
        hit["lv"] = phrase_levels(phrase, levels, lemma_of) if levels else []
        hits.append(hit)
    hits.sort(key=lambda x: -x["c"])
    return hits


def phrase_levels(phrase, levels, lemma_of):
    """词组的等级 = 它各词里的**最高**等级。

    与生词判定同一个口径：难的是最难的那个词。用并集的话不行 ——
    `in terms of` 里 in/of 都是中考词，并集会让每个基础档 chip 都命中所有词组，
    筛选就等于没筛。
    """
    if not levels:
        return []
    got = set()
    for word in phrase.split():
        got.update(levels.get(lemma_of(word), set()))
    top = top_level(got)
    return [top] if top else []


# ---------------------------------------------------------------- 统计主流程

class WordStat:
    __slots__ = ("count", "variants", "examples", "standalone", "fragments", "files")

    def __init__(self):
        self.count = 0
        self.variants = Counter()
        self.examples = []
        self.standalone = 0
        self.fragments = 0
        self.files = []            # 这个词出现在哪些材料里（按首次出现排序）

    @property
    def is_fragment_only(self):
        """只作为派生片段出现过 —— 不是独立待学词，不进生词表主列表。"""
        return self.standalone == 0


def output_stem(files, spec):
    """输出文件名的主干。多文件时按材料（目录名）区分，不再恒为"词频报告"。

    跑两次不同的材料不会互相覆盖，报告里也能一眼看出这是哪一批。
    """
    if len(files) == 1:
        return Path(files[0]).stem
    p = Path(spec)
    if p.is_dir():
        return p.name or "词频报告"
    parents = {Path(f).parent.resolve() for f in files}
    if len(parents) == 1:
        parent = parents.pop()
        if parent.name:
            return parent.name
    return "词频报告"


#: 目录扫描时直接跳过的目录名。隐藏目录、缓存目录与工具的默认输出目录里
#: 都不是学习材料 —— 扫进去等于把上一份报告当材料再统计一遍。
SKIP_DIR_NAMES = {"__pycache__", "node_modules", "wordfreq_output"}


def is_output_artifact(path):
    """是不是本工具自己生成的产物。"""
    name = Path(path).name
    return name.endswith("_anki.txt") or name.endswith("_报告.md")


def _is_skipped_dir_part(part):
    return part in SKIP_DIR_NAMES or part.startswith(".")


def collect_inputs(spec, exclude_dirs=()):
    """展开输入。目录输入会跳过：隐藏/缓存目录、工具自己的数据目录、
    输出目录，以及本工具生成的产物（*_anki.txt / *_报告.md）。

    不跳过的话，对仓库根目录跑一次就会把 data/raw/ 的考纲词表、known_words.txt
    和上一份报告当材料统计进去 —— 静默产出错数据。
    """
    p = Path(spec)
    if any(ch in spec for ch in "*?["):
        import glob
        return [Path(x) for x in sorted(glob.glob(spec))]
    if not p.is_dir():
        return [p]
    try:
        skip_roots = {Path(d).resolve() for d in exclude_dirs}
    except OSError:
        skip_roots = set()
    skip_roots.add(DATA_DIR.resolve())
    found = []
    for f in sorted(p.rglob("*")):
        if f.suffix.lower() not in TEXT_SUFFIXES or is_output_artifact(f):
            continue
        try:
            resolved = f.resolve()
        except OSError:
            continue
        if any(_is_skipped_dir_part(part) for part in resolved.parts):
            continue
        if any(resolved == s or s in resolved.parents for s in skip_roots):
            continue
        found.append(f)
    return found


def analyze_materials(materials, show_all, min_count, lexicon,
                      function_words=FUNCTION_WORDS, coca_common_rank=COCA_COMMON_RANK):
    """统计主流程：输入是规范化材料与已加载的词典，不碰文件系统。

    这是测试用的主接缝：材料可以是内存里的文本，词典可以是几百条的小数据。
    """
    levels = lexicon.levels
    dictionary = lexicon.dictionary
    coca = lexicon.coca
    phrase_list = lexicon.phrase_list
    known = lexicon.known

    valid_words = set(dictionary) | set(levels) | set(coca)
    lemma_of = Lemmatizer(lexicon.lemma_map, valid_words)

    words = defaultdict(WordStat)
    total_tokens = 0
    sentences_all = []          # (lower_sentence, original_sentence)
    phrase_input = []           # (lemma 序列, 原文) —— 词组匹配走归并后的序列
    file_names = []

    for material in materials:
        file_names.append(material.name)
        run = english_run(prepare_blocks(material))
        for orig in split_sentences("\n".join(run)):
            low = orig.lower()
            sentences_all.append((low, orig))
            lemmas = []
            for tok in sentence_tokens(orig):
                total_tokens += 1
                lemma = lemma_of(tok.text)
                lemmas.append(lemma)
                st = words[lemma]
                st.count += 1
                st.variants[tok.text] += 1
                if material.name not in st.files:
                    st.files.append(material.name)
                if tok.fragment:
                    st.fragments += 1
                else:
                    st.standalone += 1
            phrase_input.append((lemmas, orig))

    # 例句: 每词最多 MAX_EXAMPLES 条，按长度升序（短的在前）
    attach_examples(words, sentences_all, lemma_of)

    phrase_hits = find_phrases(phrase_input, phrase_list, lemma_of, levels=levels,
                               coca=coca, function_words=function_words)

    # 过滤
    shown = []
    filtered_known = filtered_basic = filtered_common = filtered_fragments = 0
    for lemma, st in words.items():
        if st.count < min_count:
            continue
        lv = levels.get(lemma, set())
        if not show_all:
            if lemma in known:
                filtered_known += 1
                continue
            if is_basic_word(lv):          # 最高等级判据，不是集合相交
                filtered_basic += 1
                continue
            if is_common_word(coca.get(lemma, 0), coca_common_rank):
                filtered_common += 1
                continue
            if is_function_word(lemma, function_words):
                filtered_common += 1
                continue
            if st.is_fragment_only:   # 派生片段不是待学词
                filtered_fragments += 1
                continue
        phon, trans, collins = dictionary.get(lemma, ("", "", ""))
        shown.append({
            "w": lemma, "c": st.count,
            "v": ", ".join(f"{x}×{n}" for x, n in st.variants.most_common(6)),
            "lv": [k for k in LEVEL_ORDER if k in lv],
            "coca": coca.get(lemma, 0),
            "phon": phon, "def": trans, "col": collins,
            "ex": st.examples,
            "known": lemma in known,
            "files": st.files,
        })
    shown.sort(key=lambda x: -x["c"])
    meta = {
        "files": file_names,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_tokens": total_tokens,
        "unique": len(words),
        "filtered_known": filtered_known,
        "filtered_basic": filtered_basic,
        "filtered_common": filtered_common,
        "filtered_fragments": filtered_fragments,
        "shown": len(shown),
        "phrase_count": len(phrase_hits),
        "show_all": show_all,
    }
    return meta, shown, phrase_hits, lexicon.known_path


def analyze(files, show_all, min_count, lexicon=None, function_words=FUNCTION_WORDS,
            coca_common_rank=COCA_COMMON_RANK):
    """CLI 入口：按扩展名路由到适配器读出材料，再走纯统计主流程。"""
    if lexicon is None:
        lexicon = load_lexicon()
    materials = [get_adapter(fp).read(fp) for fp in files]
    return analyze_materials(materials, show_all, min_count, lexicon,
                             function_words=function_words,
                             coca_common_rank=coca_common_rank)


# ---------------------------------------------------------------- 生词判定

def top_level(levels):
    """该词在等级序列里最靠后的一档；没有收录返回 None。"""
    for key in reversed(LEVEL_ORDER):
        if key in levels:
            return key
    return None


def is_basic_word(levels):
    """是不是基础词（基础三档 = 中考/高考/CET4）：只看**最高**等级，不看等级集合相交。

    用相交判定会误伤 5292 个同时属于基础档与进阶档的词（abandon / abstract /
    absorb 都是 CET4 + GRE），它们是真难词。实测 5292 这个数字与 spec 一致。
    """
    return top_level(levels) in BASIC_LEVELS


def is_common_word(rank, limit=COCA_COMMON_RANK):
    """是不是 COCA 高频常识词。rank=0 表示不在 COCA 表里，不算常识词。"""
    return bool(limit) and 0 < rank <= limit


def is_function_word(word, function_words=FUNCTION_WORDS):
    """显式功能词表里的词不是生词。

    COCA 表收不到的高频词（an / are）由这条兜住 —— 它们的等级最高档是专四，
    但对 CET4 以上的学习者显然不是生词。
    """
    return word in function_words


# ---------------------------------------------------------------- 输出

def out_html(meta, words, phrases, out_path):
    data = json.dumps({"meta": meta, "words": words, "phrases": phrases},
                      ensure_ascii=False)
    data = data.replace("</", "<\\/")  # 防止释义文本意外闭合 <script>
    page = HTML_TEMPLATE.replace("__DATA__", data)
    out_path.write_text(page, encoding="utf-8")


def out_csv(words, out_path):
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        wtr = csv.writer(f)
        wtr.writerow(["单词", "词次", "变形明细", "等级", "COCA排名", "柯林斯星级",
                      "音标", "释义", "例句1", "出现材料"])
        for x in words:
            wtr.writerow([x["w"], x["c"], x["v"],
                          "/".join(LEVEL_NAMES.get(k, k) for k in x["lv"]),
                          x["coca"] or "", x["col"], x["phon"], x["def"],
                          x["ex"][0] if x["ex"] else "",
                          " / ".join(x.get("files", []))])


def out_anki(words, out_path):
    lines = ["#separator:tab", "#html:true", "#tags column:3"]
    for x in words:
        if not x["def"]:
            continue
        lv = "/".join(LEVEL_NAMES.get(k, k) for k in x["lv"]) or "未收录"
        head = f"[{html_mod.escape(x['phon'])}] {html_mod.escape(lv)}" if x["phon"] \
            else html_mod.escape(lv)
        back = "<br>".join([head, html_mod.escape(x["def"])])
        if x["ex"]:
            back += "<br><br>❝ " + html_mod.escape(x["ex"][0]) + " ❞"
        lines.append(f"{x['w']}\t{back}\t词频")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def out_md(meta, words, phrases, out_path):
    L = []
    L.append(f"# 词频学习报告")
    L.append("")
    L.append(f"- 材料: {', '.join(meta['files'])}")
    L.append(f"- 生成时间: {meta['generated']}")
    L.append(f"- 总词次 {meta['total_tokens']} ｜ 不同原形 {meta['unique']} ｜ "
             f"生词 {meta['shown']}（已过滤已会 {meta['filtered_known']}、"
             f"基础词 {meta['filtered_basic']}、常识词 {meta['filtered_common']}、"
             f"派生片段 {meta['filtered_fragments']}）"
             f"｜ 命中词组 {meta['phrase_count']}")
    L.append("")
    L.append("> 完整交互版(可搜索/筛选/展开例句)请打开同名 `.html` 报告")
    L.append("")
    L.append("## 生词表（按词频排序，前 300）")
    L.append("")
    L.append("| 单词 | 词次 | 等级 | COCA | 出现材料 | 释义 |")
    L.append("|---|---|---|---|---|---|")
    for x in words[:300]:
        lv = " ".join(f"`{LEVEL_NAMES.get(k, k)}`" for k in x["lv"]) or "`未收录`"
        d = x["def"].replace("\n", " ")[:40]
        files = " ".join(f"`{f}`" for f in x.get("files", []))
        L.append(f"| **{x['w']}** | {x['c']} | {lv} | {x['coca'] or '-'} | {files} | {d} |")
    if phrases:
        L.append("")
        L.append("## 词组")
        L.append("")
        L.append("| 词组 | 次数 | 等级 | 释义 |")
        L.append("|---|---|---|---|")
        for x in phrases[:200]:
            lv = " ".join(f"`{LEVEL_NAMES.get(k, k)}`" for k in x.get("lv", [])) or "`未收录`"
            L.append(f"| **{x['p']}** | {x['c']} | {lv} | {x['def'].replace(chr(10), ' ')[:40]} |")
    out_path.write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------- HTML 模板

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>词频学习报告</title>
<style>
  :root { --bg:#fafafa; --card:#fff; --ink:#202124; --sub:#5f6368; --line:#e0e0e0; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
         background:var(--bg); color:var(--ink); }
  header { padding:18px 24px 10px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .stats { color:var(--sub); font-size:13px; line-height:1.7; }
  .bar { position:sticky; top:0; z-index:5; background:var(--card);
         border-bottom:1px solid var(--line); padding:10px 24px;
         display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  input[type=search] { padding:7px 12px; border:1px solid var(--line); border-radius:18px;
         width:220px; font-size:13px; outline:none; }
  select { padding:6px 8px; border:1px solid var(--line); border-radius:8px; font-size:13px; }
  .chip { padding:3px 10px; border-radius:12px; border:1px solid var(--line);
          font-size:12px; cursor:pointer; user-select:none; background:var(--card); }
  .chip.on { color:#fff; border-color:transparent; }
  .tabs { margin-left:auto; display:flex; gap:4px; }
  .tab { padding:5px 14px; border-radius:8px; cursor:pointer; font-size:13px; }
  .tab.on { background:#e8f0fe; color:#1967d2; font-weight:600; }
  main { padding:8px 24px 60px; }
  table { border-collapse:collapse; width:100%; background:var(--card);
          border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  th { text-align:left; font-size:12px; color:var(--sub); padding:8px 10px;
       border-bottom:1px solid var(--line); background:#f5f5f5; cursor:pointer; }
  td { padding:7px 10px; border-bottom:1px solid #f0f0f0; font-size:14px; vertical-align:top; }
  tr.mainrow:hover { background:#f8f9ff; cursor:pointer; }
  .w { font-weight:600; font-size:16px; }
  .phon { color:var(--sub); font-size:12px; margin-left:6px; }
  .cnt { font-weight:700; }
  .vars { color:var(--sub); font-size:12px; }
  .lv { display:inline-block; padding:1px 7px; border-radius:9px; color:#fff;
        font-size:11px; margin-right:3px; }
  .exrow td { background:#fffde7; font-size:13px; color:#5f6368; }
  .footer { position:fixed; bottom:0; left:0; right:0; background:var(--card);
            border-top:1px solid var(--line); padding:8px 24px; font-size:13px;
            display:flex; gap:14px; align-items:center; }
  .footer button { padding:6px 14px; border:none; border-radius:8px; background:#1967d2;
            color:#fff; cursor:pointer; font-size:13px; }
  .empty { padding:30px; color:var(--sub); text-align:center; }
  .ph-def { color:var(--sub); font-size:13px; }
</style>
</head>
<body>
<header>
  <h1>📖 词频学习报告</h1>
  <div class="stats" id="stats"></div>
</header>
<div class="bar">
  <input type="search" id="q" placeholder="搜单词 / 中文释义…">
  <select id="sort">
    <option value="freq">按词频</option>
    <option value="coca">按COCA排名</option>
    <option value="alpha">按字母</option>
  </select>
  <span id="chips"></span>
  <span class="tabs">
    <span class="tab on" data-tab="words">单词</span>
    <span class="tab" data-tab="phrases">词组</span>
  </span>
</div>
<main><div id="tablewrap"></div></main>
<div class="footer">
  <span>勾选已掌握的词 →</span>
  <button id="copyKnown">复制已勾选 (0)</button>
  <span style="color:var(--sub)">粘贴到 skill 的 data/known_words.txt，下次统计自动过滤</span>
</div>
<script>
const DATA = __DATA__;
const LV_NAMES = {"zk":"中考","gk":"高考","cet4":"CET4","cet6":"CET6","tem4":"专四","tem8":"专八","ky":"考研","ielts":"雅思","toefl":"托福","gre":"GRE"};
const LV_COLORS = {"zk":"#9aa0a6","gk":"#9aa0a6","cet4":"#8ab4f8","cet6":"#4285f4","tem4":"#f9ab00","tem8":"#e8710a","ky":"#a142f4","ielts":"#e5186d","toefl":"#12b5cb","gre":"#d93025","none":"#9aa0a6"};
const state = { tab:"words", q:"", sort:"freq", sel:new Set(), open:new Set() };
let levelFilter = new Set();

const $ = s => document.querySelector(s);
const esc = s => (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function initStats() {
  const m = DATA.meta;
  $("#stats").innerHTML =
    `材料: ${esc(m.files.join(", "))} &nbsp;|&nbsp; ${m.generated}<br>` +
    `总词次 <b>${m.total_tokens}</b> ｜ 不同原形 <b>${m.unique}</b> ｜ 生词 <b>${m.shown}</b>` +
    `（已过滤 已会 ${m.filtered_known} ＋ 基础词 ${m.filtered_basic} ＋ 常识词 ${m.filtered_common} ＋ 派生片段 ${m.filtered_fragments}）｜ 命中词组 <b>${m.phrase_count}</b>` +
    (m.show_all ? " ｜ <b>全量模式（未过滤）</b>" : "");
}

function initChips() {
  const used = new Set();
  DATA.words.forEach(w => w.lv.forEach(k => used.add(k)));
  DATA.phrases.forEach(p => (p.lv||[]).forEach(k => used.add(k)));   // 词组页共用同一套 chip
  if (DATA.words.some(w => !w.lv.length)) used.add("none");
  const order = ["zk","gk","cet4","cet6","tem4","tem8","ky","ielts","toefl","gre","none"].filter(k => used.has(k));
  const box = $("#chips");
  box.innerHTML = "";
  order.forEach(k => {
    const el = document.createElement("span");
    el.className = "chip"; el.textContent = k === "none" ? "未收录" : LV_NAMES[k];
    el.dataset.k = k;
    el.onclick = () => { levelFilter.has(k) ? levelFilter.delete(k) : levelFilter.add(k); paint(); };
    box.appendChild(el);
  });
  function paint() {
    box.querySelectorAll(".chip").forEach(el => {
      const on = levelFilter.has(el.dataset.k);
      el.classList.toggle("on", on);
      el.style.background = on ? LV_COLORS[el.dataset.k] : "";
    });
    render();
  }
  paint._box = box; window._paintChips = paint;
}

function rows() {
  // 单词页与词组页共用等级筛选与排序
  let list = state.tab === "words" ? DATA.words.slice() : DATA.phrases.slice();
  if (levelFilter.size) list = list.filter(w => {
    const lv = w.lv || [];
    return lv.some(k => levelFilter.has(k)) || (!lv.length && levelFilter.has("none"));
  });
  const q = state.q.trim().toLowerCase();
  if (q) list = list.filter(w => (w.w||w.p).toLowerCase().includes(q) || (w.def||"").toLowerCase().includes(q));
  const name = w => w.w || w.p || "";
  if (state.sort === "freq") list.sort((a,b) => b.c - a.c);
  else if (state.sort === "alpha") list.sort((a,b) => name(a).localeCompare(name(b)));
  else list.sort((a,b) => (a.coca||1e9) - (b.coca||1e9));
  return list;
}

function render() {
  const wrap = $("#tablewrap");
  const list = rows();
  if (!list.length) { wrap.innerHTML = `<div class="empty">没有匹配的结果</div>`; return; }
  if (state.tab === "words") {
    let h = `<table><tr>
      <th style="width:34px"></th><th>单词</th><th style="width:150px">词次">
      <th>等级</th><th style="width:90px">COCA</th><th>释义</th>
      <th style="width:120px">出现材料</th></tr>`;
    for (const w of list) {
      const id = w.w;
      const chips = w.lv.map(k =>
        `<span class="lv" style="background:${LV_COLORS[k]}">${LV_NAMES[k]}</span>`).join("")
        || `<span class="lv" style="background:${LV_COLORS.none}">未收录</span>`;
      h += `<tr class="mainrow" data-id="${esc(id)}">
        <td><input type=checkbox data-k="${esc(id)}" ${state.sel.has(id)?"checked":""}></td>
        <td><span class="w">${esc(w.w)}</span><span class="phon">${esc(w.phon)}</span></td>
        <td><span class="cnt">${w.c}</span><div class="vars">${esc(w.v)}</div></td>
        <td>${chips}</td>
        <td>${w.coca || "-"}</td>
        <td>${esc((w.def||"").slice(0,60))}</td>
        <td class="ph-def">${esc((w.files||[]).join(" / "))}</td></tr>`;
      if (state.open.has(id)) {
        h += `<tr class="exrow"><td></td><td colspan="6">${
          w.ex.length ? w.ex.map(e => "• " + esc(e)).join("<br>") : "（无例句）"}</td></tr>`;
      }
    }
    wrap.innerHTML = h + "</table>";
    wrap.querySelectorAll("tr.mainrow").forEach(tr => {
      tr.onclick = e => {
        if (e.target.tagName === "INPUT") return;
        const id = tr.dataset.id;
        state.open.has(id) ? state.open.delete(id) : state.open.add(id);
        render();
      };
    });
    wrap.querySelectorAll("input[type=checkbox]").forEach(cb => {
      cb.onclick = e => {
        e.stopPropagation();
        cb.checked ? state.sel.add(cb.dataset.k) : state.sel.delete(cb.dataset.k);
        $("#copyKnown").textContent = `复制已勾选 (${state.sel.size})`;
      };
    });
  } else {
    let h = `<table><tr><th>词组</th><th style="width:70px">次数</th><th>等级</th><th>释义</th><th>例句</th></tr>`;
    for (const p of list) {
      const chips = (p.lv||[]).map(k =>
        `<span class="lv" style="background:${LV_COLORS[k]}">${LV_NAMES[k]}</span>`).join("")
        || `<span class="lv" style="background:${LV_COLORS.none}">未收录</span>`;
      h += `<tr class="mainrow"><td><span class="w">${esc(p.p)}</span></td>
        <td><span class="cnt">${p.c}</span></td>
        <td>${chips}</td>
        <td class="ph-def">${esc((p.def||"").slice(0,60))}</td>
        <td class="ph-def">${p.ex.length ? esc(p.ex[0].slice(0,80)) : ""}</td></tr>`;
    }
    wrap.innerHTML = h + "</table>";
  }
}

$("#q").oninput = e => { state.q = e.target.value; render(); };
$("#sort").onchange = e => { state.sort = e.target.value; render(); };
document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("on"));
  t.classList.add("on");
  state.tab = t.dataset.tab; render();
});
$("#copyKnown").onclick = () => {
  const s = [...state.sel].join("\n");
  navigator.clipboard.writeText(s).then(() => {
    $("#copyKnown").textContent = "已复制 ✓";
    setTimeout(() => $("#copyKnown").textContent = `复制已勾选 (${state.sel.size})`, 1200);
  });
};
initStats(); initChips(); render();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- main

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="词频统计（英语学习向）")
    ap.add_argument("input", nargs="?", help="材料文件（.md/.txt） / 目录 / 通配符")
    ap.add_argument("--out", default="wordfreq_output", help="输出目录 (默认 ./wordfreq_output)")
    ap.add_argument("--all", action="store_true", help="不过滤（显示已会词和基础词）")
    ap.add_argument("--min-count", type=int, default=1, help="最少出现次数 (默认 1)")
    ap.add_argument("--no-anki", action="store_true", help="不生成 Anki 文件")
    ap.add_argument("--no-open", action="store_true", help="不自动打开 HTML 报告")
    ap.add_argument("--mark", help="逗号分隔的已会词, 追加到 known_words.txt 后退出")
    ap.add_argument("--function-words", help="追加功能词的文件（一行一个词），用于滤掉更多纯功能词短语")
    ap.add_argument("--coca-rank", type=int, default=COCA_COMMON_RANK,
                    help=f"隐藏 COCA 排名 ≤ N 的常识词 (默认 {COCA_COMMON_RANK}，0 = 关闭)")
    args = ap.parse_args()

    if args.mark:
        _, kp = load_known()
        mark_known([w for w in re.split(r"[,，\s]+", args.mark) if w], kp)
        return

    function_words = FUNCTION_WORDS
    if args.function_words:
        p = Path(args.function_words)
        if not p.exists():
            print(f"找不到功能词文件: {p}")
            sys.exit(1)
        extra = {w.strip().lower() for w in p.read_text(encoding="utf-8").splitlines()
                 if w.strip() and not w.strip().startswith("#")}
        function_words = FUNCTION_WORDS | extra
        print(f"功能词表: 默认 {len(FUNCTION_WORDS)} 个 + 自定义 {len(extra)} 个")

    if not args.input:
        ap.error("需要输入: 材料文件（.md/.txt） / 目录 / 通配符")

    files = collect_inputs(args.input, exclude_dirs=[args.out])
    files = [f for f in files if f.exists()]
    if not files:
        print(f"找不到输入文件: {args.input}")
        sys.exit(1)

    if not (DATA_DIR / "dict.csv").exists():
        print(f"[警告] 数据未构建 ({DATA_DIR} 缺少 dict.csv)，等级/释义将不可用")
        print("       请先运行 scripts/build_data.py")

    t0 = time.time()
    try:
        meta, words, phrases, _ = analyze(files, args.all, args.min_count,
                                          function_words=function_words,
                                          coca_common_rank=args.coca_rank)
    except AdapterError as e:
        print(f"[错误] {e}")
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = output_stem(files, args.input)

    html_path = out_dir / f"{stem}.html"
    out_html(meta, words, phrases, html_path)
    out_csv(words, out_dir / f"{stem}.csv")
    # 报告名与材料同名会盖掉材料本身（--out 指到输入目录时就会发生），加后缀躲开
    report_md = out_dir / f"{stem}.md"
    if report_md.resolve() in {f.resolve() for f in files}:
        report_md = out_dir / f"{stem}_报告.md"
    out_md(meta, words, phrases, report_md)
    if not args.no_anki:
        out_anki(words, out_dir / f"{stem}_anki.txt")

    print(f"✔ {len(files)} 个文件, {meta['total_tokens']} 词次, "
          f"生词 {meta['shown']} 个, 词组命中 {meta['phrase_count']} 个 "
          f"({time.time()-t0:.1f}s)")
    print(f"  过滤: 已会 {meta['filtered_known']} + 基础词(中考/高考/CET4) {meta['filtered_basic']}"
          f" + 常识词(COCA≤{args.coca_rank}) {meta['filtered_common']}"
          f" + 派生片段 {meta['filtered_fragments']}"
          + ("  [全量模式]" if args.all else ""))
    print(f"  输出目录: {out_dir.resolve()}")
    print(f"  → HTML 报告: {html_path.resolve()}")
    top = words[:15]
    if top:
        print("  高频生词预览: " + ", ".join(f"{w['w']}×{w['c']}" for w in top))
    if not args.no_open:
        try:
            webbrowser.open(html_path.resolve().as_uri())
        except Exception:
            pass


if __name__ == "__main__":
    main()
