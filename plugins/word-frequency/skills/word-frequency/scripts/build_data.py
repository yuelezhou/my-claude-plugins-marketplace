#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_data.py — 把 data/raw/ 的原始词表加工成 data/ 下紧凑可查的数据文件

原始来源(GitHub):
  skywind3000/ECDICT        ecdict.csv       76万词条基础版: 释义/音标/标签/变形
  mahavivo/english-wordlists  各等级词表 + COCA_20000 + 英语专业四八级词汇表

产出:
  data/dict.csv     word,phonetic,translation,collins   (紧凑词典)
  data/levels.tsv   word\tzk|gk|cet4|cet6|tem4|tem8|ky|ielts|toefl|gre
  data/lemma.tsv    变形\t原形   (来自 ECDICT exchange 字段反向映射)
  data/coca.tsv     word\t排名
  data/phrases.tsv  phrase\t释义 (ECDICT 多词条目 + 四八级表中的短语)
  data/known_words.txt  用户已会词(带注释头, 已存在则不动)
"""
import csv
import re
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
DATA = RAW.parent

VALID_TAGS = {"zk", "gk", "cet4", "cet6", "ky", "toefl", "ielts", "gre"}
POS_TAIL = re.compile(r"\s+(?:n|v|vt|vi|adj|adv|art|prep|conj|pron|num|int|aux|abbr|a|ad)\.$")


def die(msg):
    print(f"[错误] {msg}")
    sys.exit(1)


# ---------------------------------------------------------------- 词表解析

def extract_heads(line):
    """一行词条 -> (词头列表, 是否星标)。词头可能是 'a'/'a, an'/'a few' 等"""
    line = line.strip()
    star = line.startswith(("*", "＊"))
    if re.fullmatch(r"[A-Z]", line):
        return [], False
    line = line.lstrip("*＊·• ").rstrip()
    m = re.match(r"^([^\[\u4e00-\u9fff]+)", line)
    if not m:
        return [], star
    head = m.group(1).strip()
    head = POS_TAIL.sub("", head).strip(" ,;.")
    if not head or not head[0].isalpha():
        return [], star
    out = []
    for v in head.split(","):
        v = v.strip(" .;()'\"")
        if re.fullmatch(r"[A-Za-z][A-Za-z'\- ]*", v):
            out.append(v.lower())
    return out, star


def words_first_token(path):
    """每行取第一个英文词(适用于 CET/TOEFL/GRE/高中 一行一词的表)"""
    ws = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or not s[0].isascii() or not s[0].isalpha():
                continue
            if re.fullmatch(r"[A-Z]", s):
                continue
            m = re.match(r"[A-Za-z][A-Za-z'\-]*", s)
            if m:
                ws.add(m.group(0).lower())
    return ws


def load_tem48(path_all, path_star):
    """四八级总表(星标=专八) + 星标八级表 -> tem4, tem8, phrases"""
    tem4, tem8, phrases = set(), set(), set()
    with open(path_all, encoding="utf-8") as f:
        for line in f:
            heads, star = extract_heads(line)
            for h in heads:
                if " " in h:
                    if len(h.split()) <= 4:
                        phrases.add(h)
                elif star:
                    tem8.add(h)
                else:
                    tem4.add(h)
    with open(path_star, encoding="utf-8") as f:
        for line in f:
            heads, _ = extract_heads(line)
            for h in heads:
                if " " in h:
                    if len(h.split()) <= 4:
                        phrases.add(h)
                else:
                    tem8.add(h)
    return tem4 - tem8, tem8, phrases


def load_coca(path):
    c = {}
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            w = line.strip().lower()
            if w and w not in c:
                c[w] = i
    return c


# ---------------------------------------------------------------- 主流程

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    need = ["ecdict.csv", "CET4_edited.txt", "CET6_edited.txt", "TOEFL.txt",
            "GRE_8000_Words.txt", "Highschool_edited.txt", "COCA_20000.txt",
            "英语专业四八级词汇表.txt", "英语专业星标八级词汇.txt"]
    for n in need:
        if not (RAW / n).exists():
            die(f"缺少原始文件 {RAW / n}，请先下载到 data/raw/")

    print("读取各等级词表…")
    cet4 = words_first_token(RAW / "CET4_edited.txt")
    cet6 = words_first_token(RAW / "CET6_edited.txt")
    toefl = words_first_token(RAW / "TOEFL.txt")
    gre = words_first_token(RAW / "GRE_8000_Words.txt")
    gk = words_first_token(RAW / "Highschool_edited.txt")
    tem4, tem8, tem_phrases = load_tem48(RAW / "英语专业四八级词汇表.txt",
                                         RAW / "英语专业星标八级词汇.txt")
    coca = load_coca(RAW / "COCA_20000.txt")
    print(f"  高考{len(gk)} CET4 {len(cet4)} CET6 {len(cet6)} 专四{len(tem4)} "
          f"专八{len(tem8)} 托福{len(toefl)} GRE {len(gre)} COCA {len(coca)}")

    file_levels = {}
    for name, s in [("gk", gk), ("cet4", cet4), ("cet6", cet6), ("tem4", tem4),
                    ("tem8", tem8), ("toefl", toefl), ("gre", gre)]:
        for w in s:
            file_levels.setdefault(w, set()).add(name)

    # ---- ECDICT 扫描
    print("扫描 ECDICT (76万行)…")
    keepset = set(file_levels) | set(coca)
    # 短语收录门槛: 短语里每个词都是常用词(在考纲或COCA内), 避免几十万条冷僻组合
    phrase_vocab = keepset

    def clean_trans(s):
        return (s or "").replace("\r", " ").replace("\n", "；") \
                        .replace("\\r", " ").replace("\\n", "；").strip()
    dict_rows = {}          # word -> [phon, trans, collins]
    tag_levels = {}         # word -> set (来自 tag 字段)
    lemma_pairs = []        # (变形, 原形)
    ecdict_phrases = {}     # phrase -> translation
    n = 0
    with open(RAW / "ecdict.csv", encoding="utf-8", newline="") as f:
        rd = csv.reader(f)
        next(rd)  # header
        for row in rd:
            n += 1
            if len(row) < 11:
                continue
            word, phon, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange = row[:11]
            word = word.strip()
            if not word:
                continue
            tags = set(tag.split()) & VALID_TAGS
            try:
                col = int(collins) if collins else 0
            except ValueError:
                col = 0
            if tags:
                tag_levels.setdefault(word, set()).update(tags)
            if " " in word:
                # 多词条目 -> 词组词典(仅收全由常用词构成的)
                if translation and re.fullmatch(r"[A-Za-z][A-Za-z'\- ]{2,40}", word) \
                        and 2 <= len(word.split()) <= 4 \
                        and all(t in phrase_vocab for t in word.lower().split()):
                    ecdict_phrases[word.lower()] = clean_trans(translation)[:60]
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z'\-]{0,30}", word):
                continue
            keep = (word in keepset) or bool(tags) or col >= 3
            if not keep:
                continue
            wl = word.lower()
            trans = clean_trans(translation or definition)
            if wl not in dict_rows or len(trans) > len(dict_rows[wl][1]):
                dict_rows[wl] = [phon, trans, str(col)]
            # exchange: "0:X" 本词是X的变形; "d/p/i/3/r/t/s:X" X是本词的变形;
            # 多值用斜杠连接, 如 "d:was/were" 或 "s:am/are/is"
            if exchange:
                cur_key = None
                for item in exchange.split("/"):
                    if ":" in item:
                        cur_key, v = item.split(":", 1)
                    elif cur_key is not None:
                        v = item
                    else:
                        continue
                    v = v.strip().lower()
                    if not re.fullmatch(r"[a-z][a-z'\-]{1,30}", v):
                        continue
                    if cur_key == "0":
                        lemma_pairs.append((wl, v))
                    elif cur_key in ("d", "p", "i", "3", "r", "t", "s") and v != wl:
                        lemma_pairs.append((v, wl))
    print(f"  词条 {n} 行; 词典收录 {len(dict_rows)}; 标签词 {len(tag_levels)}; "
          f"变形对 {len(lemma_pairs)}; 词典短语 {len(ecdict_phrases)}")

    # ---- 合并等级
    levels = {}
    for w, s in file_levels.items():
        levels.setdefault(w, set()).update(s)
    for w, s in tag_levels.items():
        levels.setdefault(w, set()).update(s)

    # ---- 写出
    with open(DATA / "levels.tsv", "w", encoding="utf-8") as f:
        for w in sorted(levels):
            f.write(f"{w}\t{'|'.join(sorted(levels[w]))}\n")

    with open(DATA / "dict.csv", "w", encoding="utf-8", newline="") as f:
        wtr = csv.writer(f)
        for w in sorted(dict_rows):
            p, t, c = dict_rows[w]
            wtr.writerow([w, p, t, c])

    with open(DATA / "coca.tsv", "w", encoding="utf-8") as f:
        for w, r in coca.items():
            f.write(f"{w}\t{r}\n")

    # lemma: 仅保留「原形在词典/等级/coca 内」的映射, 去重后取第一条
    valid = set(dict_rows) | set(levels) | set(coca)
    seen, cnt = set(), 0
    with open(DATA / "lemma.tsv", "w", encoding="utf-8") as f:
        for form, base in lemma_pairs:
            if base in valid and form not in seen and form != base:
                f.write(f"{form}\t{base}\n")
                seen.add(form)
                cnt += 1
    print(f"  lemma.tsv: {cnt} 条")

    # phrases: ECDICT 的(带释义) + 四八级表短语(无释义)
    with open(DATA / "phrases.tsv", "w", encoding="utf-8") as f:
        for p, t in sorted(ecdict_phrases.items()):
            f.write(f"{p}\t{t}\n")
        for p in sorted(tem_phrases - set(ecdict_phrases)):
            f.write(f"{p}\t\n")

    kp = DATA / "known_words.txt"
    if not kp.exists():
        kp.write_text("# 已掌握的单词, 每行一个; # 开头为注释; 也可用 wordfreq.py --mark w1,w2 追加\n",
                      encoding="utf-8")

    print(f"完成 → {DATA}")


if __name__ == "__main__":
    main()
