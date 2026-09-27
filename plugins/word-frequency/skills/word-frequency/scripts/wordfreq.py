#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wordfreq.py — Markdown 词频统计（英语学习向）

用法:
    python wordfreq.py <md文件|目录|通配符> [--out 输出目录] [--all] [--min-count N] [--no-anki]
    python wordfreq.py --mark word1,word2        # 把已掌握的词追加进 known_words.txt

流程: 清洗 markdown → 分词 → 词形归并(running→run) → 词频统计 → 词典短语匹配
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
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

LEVEL_ORDER = ["zk", "gk", "cet4", "cet6", "tem4", "tem8", "ky", "ielts", "toefl", "gre"]
LEVEL_NAMES = {
    "zk": "中考", "gk": "高考", "cet4": "CET4", "cet6": "CET6",
    "tem4": "专四", "tem8": "专八", "ky": "考研", "ielts": "雅思",
    "toefl": "托福", "gre": "GRE",
}
LEVEL_COLORS = {
    "zk": "#9aa0a6", "gk": "#9aa0a6", "cet4": "#8ab4f8", "cet6": "#4285f4",
    "tem4": "#f9ab00", "tem8": "#e8710a", "ky": "#a142f4", "ielts": "#e5186d",
    "toefl": "#12b5cb", "gre": "#d93025", "none": "#bbb",
}
BASIC_LEVELS = {"zk", "gk", "cet4"}  # 默认隐藏的基础等级

TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*")


# ---------------------------------------------------------------- 数据加载

def _open(path, encoding="utf-8"):
    for enc in (encoding, "utf-8-sig", "gbk"):
        try:
            return open(path, "r", encoding=enc), enc
        except UnicodeDecodeError:
            continue
    return open(path, "r", encoding="utf-8", errors="replace"), "utf-8"


def load_levels():
    """word -> set(level keys)"""
    levels = defaultdict(set)
    p = DATA_DIR / "levels.tsv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2 and parts[1]:
                    levels[parts[0]] = set(x for x in parts[1].split("|") if x)
    return levels


def load_dict():
    """word -> (phonetic, translation, collins)"""
    d = {}
    p = DATA_DIR / "dict.csv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) >= 3:
                    d[row[0]] = (row[1], row[2], row[3] if len(row) > 3 else "")
    return d


def load_lemma():
    """变形 -> 原形"""
    m = {}
    p = DATA_DIR / "lemma.tsv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2:
                    m[parts[0]] = parts[1]
    return m


def load_coca():
    """word -> 排名"""
    c = {}
    p = DATA_DIR / "coca.tsv"
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


def load_phrases():
    """[(phrase, translation)]"""
    out = []
    p = DATA_DIR / "phrases.tsv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 1 and parts[0].strip():
                    out.append((parts[0].strip().lower(), parts[1].strip() if len(parts) > 1 else ""))
    return out


def load_known():
    p = DATA_DIR / "known_words.txt"
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


# ---------------------------------------------------------------- markdown 清洗

def clean_markdown(text):
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n?", " ", text, flags=re.S)   # frontmatter
    text = re.sub(r"```.*?```", " ", text, flags=re.S)                   # 代码块
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)                               # 行内代码
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)                  # HTML 注释
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)                    # 图片(整体丢弃)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)                 # 链接保留文字
    text = re.sub(r"<[^>]+>", " ", text)                                 # HTML 标签
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)                   # URL
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", " ", text)                 # 邮箱
    return text


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|(?<=[。！？；])")

def split_sentences(text):
    sents = []
    for chunk in _SENT_SPLIT_RE.split(text):
        s = chunk.strip()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[*_~`]+", "", s)  # 去掉残留的强调标记
        s = s.strip(" \t#>|=-—–,.:;!?()[]{}\"'“”‘’…·")
        if 2 <= len(s) <= 300 and TOKEN_RE.search(s):
            sents.append(s)
    return sents


def sentence_tokens(sent):
    """句子 -> 小写词元列表(连字符拆开、去所有格)"""
    toks = []
    for t in TOKEN_RE.findall(sent):
        t = t.replace("’", "'").lower()
        t = re.sub(r"'s?$", "", t)
        if "-" in t:
            toks.extend(x for x in t.split("-") if x)
        else:
            toks.append(t)
    return [t for t in toks if t]


# ---------------------------------------------------------------- 词形归并

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
        cands.append(w[:-3]); cands.append(w[:-2])
    if w.endswith("er") and len(w) > 4:
        cands.append(w[:-2]); cands.append(w[:-1])
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
        for c in rule_candidates(w):
            if c in self.valid or c in self.map:
                return self.map.get(c, c)
        # 兜底: 单纯去屈折后缀
        for c in rule_candidates(w):
            return c
        return w


# ---------------------------------------------------------------- 统计主流程

class WordStat:
    __slots__ = ("count", "variants", "examples", "order")

    def __init__(self):
        self.count = 0
        self.variants = Counter()
        self.examples = []
        self.order = 0


def collect_inputs(spec):
    p = Path(spec)
    if any(ch in spec for ch in "*?["):
        import glob
        return [Path(x) for x in sorted(glob.glob(spec))]
    if p.is_dir():
        return sorted(p.rglob("*.md"))
    return [p]


def analyze(files, show_all, min_count):
    levels = load_levels()
    dictionary = load_dict()
    lemma_map = load_lemma()
    coca = load_coca()
    phrase_list = load_phrases()
    known, known_path = load_known()

    valid_words = set(dictionary) | set(levels) | set(coca)
    lemma_of = Lemmatizer(lemma_map, valid_words)

    words = defaultdict(WordStat)
    total_tokens = 0
    sentences_all = []          # (lower_sentence, original_sentence)
    file_names = []

    for fp in files:
        f, _ = _open(fp)
        text = f.read()
        f.close()
        cleaned = clean_markdown(text)
        file_names.append(fp.name)
        for orig in split_sentences(cleaned):
            low = orig.lower()
            sentences_all.append((low, orig))
            for tok in sentence_tokens(orig):
                total_tokens += 1
                lemma = lemma_of(tok)
                st = words[lemma]
                st.count += 1
                st.variants[tok] += 1

    # 例句: 每词最多 3 条(优先较短的)
    for lemma, st in words.items():
        st.order = len(words)
    for low, orig in sentences_all:
        for tok in set(sentence_tokens(low)):
            lemma = lemma_of(tok)
            st = words.get(lemma)
            if st and len(st.examples) < 3 and orig not in st.examples:
                st.examples.append(orig)

    # 词组匹配: 只扫「词组所有单词都出现在本文」的短语
    doc_vocab = set()
    for st in words.values():
        doc_vocab.update(st.variants)
    phrase_hits = []
    if phrase_list:
        cand = [(p, t) for p, t in phrase_list if all(w in doc_vocab for w in p.split())]
        phrase_res = []
        for p, trans in cand:
            pat = re.compile(r"\b" + r"[\s\-]+".join(re.escape(w) for w in p.split()) + r"\b")
            cnt = 0
            exs = []
            for low, orig in sentences_all:
                ms = pat.findall(low)
                if ms:
                    cnt += len(ms)
                    if len(exs) < 2 and orig not in exs:
                        exs.append(orig)
            if cnt:
                phrase_res.append({"p": p, "c": cnt, "def": trans, "ex": exs})
        phrase_res.sort(key=lambda x: -x["c"])
        phrase_hits = phrase_res

    # 过滤
    shown, filtered_known, filtered_basic = [], 0, 0
    for lemma, st in words.items():
        if st.count < min_count:
            continue
        lv = levels.get(lemma, set())
        if not show_all:
            if lemma in known:
                filtered_known += 1
                continue
            if lv & BASIC_LEVELS:
                filtered_basic += 1
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
        })
    shown.sort(key=lambda x: -x["c"])
    meta = {
        "files": file_names,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_tokens": total_tokens,
        "unique": len(words),
        "filtered_known": filtered_known,
        "filtered_basic": filtered_basic,
        "shown": len(shown),
        "phrase_count": len(phrase_hits),
        "show_all": show_all,
    }
    return meta, shown, phrase_hits, known_path


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
                      "音标", "释义", "例句1"])
        for x in words:
            wtr.writerow([x["w"], x["c"], x["v"],
                          "/".join(LEVEL_NAMES.get(k, k) for k in x["lv"]),
                          x["coca"] or "", x["col"], x["phon"], x["def"],
                          x["ex"][0] if x["ex"] else ""])


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
             f"生词 {meta['shown']}（已过滤已会 {meta['filtered_known']}、基础词 {meta['filtered_basic']}）"
             f"｜ 命中词组 {meta['phrase_count']}")
    L.append("")
    L.append("> 完整交互版(可搜索/筛选/展开例句)请打开同名 `.html` 报告")
    L.append("")
    L.append("## 生词表（按词频排序，前 300）")
    L.append("")
    L.append("| 单词 | 词次 | 等级 | COCA | 释义 |")
    L.append("|---|---|---|---|---|")
    for x in words[:300]:
        lv = " ".join(f"`{LEVEL_NAMES.get(k, k)}`" for k in x["lv"]) or "`未收录`"
        d = x["def"].replace("\n", " ")[:40]
        L.append(f"| **{x['w']}** | {x['c']} | {lv} | {x['coca'] or '-'} | {d} |")
    if phrases:
        L.append("")
        L.append("## 词组")
        L.append("")
        L.append("| 词组 | 次数 | 释义 |")
        L.append("|---|---|---|")
        for x in phrases[:200]:
            L.append(f"| **{x['p']}** | {x['c']} | {x['def'].replace(chr(10), ' ')[:40]} |")
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
    `（已过滤 已会 ${m.filtered_known} ＋ 基础词 ${m.filtered_basic}）｜ 命中词组 <b>${m.phrase_count}</b>` +
    (m.show_all ? " ｜ <b>全量模式（未过滤）</b>" : "");
}

function initChips() {
  const used = new Set();
  DATA.words.forEach(w => w.lv.forEach(k => used.add(k)));
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
  let list = state.tab === "words" ? DATA.words.slice() : DATA.phrases.slice();
  if (state.tab === "words") {
    if (levelFilter.size) list = list.filter(w => {
      const hit = w.lv.some(k => levelFilter.has(k)) || (!w.lv.length && levelFilter.has("none"));
      return hit;
    });
  }
  const q = state.q.trim().toLowerCase();
  if (q) list = list.filter(w => (w.w||w.p).toLowerCase().includes(q) || (w.def||"").toLowerCase().includes(q));
  if (state.tab === "words") {
    if (state.sort === "freq") list.sort((a,b) => b.c - a.c);
    else if (state.sort === "alpha") list.sort((a,b) => a.w.localeCompare(b.w));
    else list.sort((a,b) => (a.coca||1e9) - (b.coca||1e9));
  }
  return list;
}

function render() {
  const wrap = $("#tablewrap");
  const list = rows();
  if (!list.length) { wrap.innerHTML = `<div class="empty">没有匹配的结果</div>`; return; }
  if (state.tab === "words") {
    let h = `<table><tr>
      <th style="width:34px"></th><th>单词</th><th style="width:150px">词次</th>
      <th>等级</th><th style="width:90px">COCA</th><th>释义</th></tr>`;
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
        <td>${esc((w.def||"").slice(0,60))}</td></tr>`;
      if (state.open.has(id)) {
        h += `<tr class="exrow"><td></td><td colspan="5">${
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
    let h = `<table><tr><th>词组</th><th style="width:70px">次数</th><th>释义</th><th>例句</th></tr>`;
    for (const p of list) {
      h += `<tr class="mainrow"><td><span class="w">${esc(p.p)}</span></td>
        <td><span class="cnt">${p.c}</span></td>
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
    ap = argparse.ArgumentParser(description="Markdown 词频统计（英语学习向）")
    ap.add_argument("input", nargs="?", help="md 文件 / 目录 / 通配符")
    ap.add_argument("--out", default="wordfreq_output", help="输出目录 (默认 ./wordfreq_output)")
    ap.add_argument("--all", action="store_true", help="不过滤（显示已会词和基础词）")
    ap.add_argument("--min-count", type=int, default=1, help="最少出现次数 (默认 1)")
    ap.add_argument("--no-anki", action="store_true", help="不生成 Anki 文件")
    ap.add_argument("--no-open", action="store_true", help="不自动打开 HTML 报告")
    ap.add_argument("--mark", help="逗号分隔的已会词, 追加到 known_words.txt 后退出")
    args = ap.parse_args()

    if args.mark:
        _, kp = load_known()
        mark_known([w for w in re.split(r"[,，\s]+", args.mark) if w], kp)
        return

    if not args.input:
        ap.error("需要输入: md 文件 / 目录 / 通配符")

    files = collect_inputs(args.input)
    files = [f for f in files if f.exists()]
    if not files:
        print(f"找不到输入文件: {args.input}")
        sys.exit(1)

    if not (DATA_DIR / "dict.csv").exists():
        print(f"[警告] 数据未构建 ({DATA_DIR} 缺少 dict.csv)，等级/释义将不可用")
        print("       请先运行 scripts/build_data.py")

    t0 = time.time()
    meta, words, phrases, _ = analyze(files, args.all, args.min_count)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(files[0]).stem if len(files) == 1 else "词频报告"

    html_path = out_dir / f"{stem}.html"
    out_html(meta, words, phrases, html_path)
    out_csv(words, out_dir / f"{stem}.csv")
    out_md(meta, words, phrases, out_dir / f"{stem}.md")
    if not args.no_anki:
        out_anki(words, out_dir / f"{stem}_anki.txt")

    print(f"✔ {len(files)} 个文件, {meta['total_tokens']} 词次, "
          f"生词 {meta['shown']} 个, 词组命中 {meta['phrase_count']} 个 "
          f"({time.time()-t0:.1f}s)")
    print(f"  过滤: 已会 {meta['filtered_known']} + 基础词(中考/高考/CET4) {meta['filtered_basic']}"
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
