#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_wordfreq.py — wordfreq.py 的回归自测。

覆盖：专名判定（句中大写过滤、词典证据真词的小写推翻、词典零证据人名
不被小写泛滥救回、句首不作证据、功能词排除）、单字母噪声过滤（S01E01
标号拆出的 s/e）、基础档 CET4-6 边界（最高等级判据不回归）、--all 全量
模式与 pn 标记、Token 的大小写/句首传播。

用 analyze_materials 的内存接缝：材料是内存文本，词典是几条的小数据，
不碰真实 data/。

用法:
    python test_wordfreq.py

退出码:
    0  全部通过
    1  有用例失败
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wordfreq import (Lexicon, Material, analyze_materials, sentence_tokens)


def make_lexicon():
    """小词典：等级覆盖三档边界，coca 只放 abandon（2201，故意越过常识阈值）。

    peter 按真实 ECDICT 的情况收录为动词（peter out 逐渐消失）：有词典证据的
    真词，小写一票推翻专名判定就靠它验证。
    """
    return Lexicon(
        levels={
            "classroom": {"zk"},
            "influence": {"cet4", "cet6"},   # 最高档 cet6：新基础档，应滤
            "abandon": {"cet4", "ky"},       # 最高档 ky：交集判据会误伤，必须保留
            "grumble": {"tem4"},
        },
        dictionary={"abandon": ("ә'bændәn", "vt. 放弃", "3"),
                    "grumble": ("", "vi. 抱怨", ""),
                    "peter": ("'pi:tə", "vi. 逐渐消失", "")},
        lemma_map={"grumbling": "grumble"},
        coca={"abandon": 2201},
    )


def run(text, show_all=False, lexicon=None):
    material = Material(name="t.md", blocks=tuple(text.splitlines()), markdown=False)
    return analyze_materials([material], show_all, 1, lexicon or make_lexicon())


def shown_words(meta_words):
    return {x["w"] for x in meta_words[1]}


# ---------------------------------------------------------------- 专名判定

def test_proper_noun_filtered():
    """句中大写、从未小写 -> 判专名过滤；只在句首出现且不在 COCA 表也判专名。"""
    meta, words, _, _ = run(
        "Peter met Gloria in the park.\n"
        "Later Peter smiled.\n"
        "Gloria and I studied together.\n"
        "Abandon the plan.\n")
    ws = shown_words((meta, words))
    assert "peter" not in ws, "Peter 句中大写应被专名规则滤掉"
    assert "gloria" not in ws, "Gloria 句中大写应被专名规则滤掉"
    assert "later" not in ws, "只在句首出现且不在 COCA 表的大写词应判专名"
    assert meta["filtered_proper"] == 3, f"专名计数应为 3，实际 {meta['filtered_proper']}"
    # 只在句首出现、但 COCA 表收录了的词（Abandon the plan 的 abandon）按普通词保留
    assert "abandon" in ws, "COCA 表内的词不应因只在句首出现被判专名"
    # I 永远大写，但它是功能词，走功能词通道不算专名
    assert "i" not in ws, "功能词 I 应被功能词规则滤掉"
    assert "met" in ws and "park" in ws and "studied" in ws and "plan" in ws


def test_lowercase_refutes_proper():
    """有词典证据的真词：小写形态出现过一次 -> 推翻专名判定（peter out）。"""
    meta, words, _, _ = run(
        "Peter met Gloria in the park.\n"
        "Later Peter smiled.\n"
        "They watched the river peter out.\n")
    ws = shown_words((meta, words))
    assert "peter" in ws, "句中出现小写 peter 应推翻专名判定"
    row = next(x for x in words if x["w"] == "peter")
    assert row["pn"] is False, "非专名词的 pn 标记应为 False"
    assert meta["filtered_proper"] == 2, "Gloria（句中大写）与 later（句首未收录）被判专名"


def test_proper_noun_flag_in_all_mode():
    """--all 不过滤但 pn 标记透明可见。"""
    meta, words, _, _ = run(
        "Peter met Gloria in the park.\n"
        "Later Peter smiled.\n"
        "Gloria and I studied together.\n"
        "Abandon the plan.\n", show_all=True)
    assert meta["show_all"] is True
    rows = {x["w"]: x for x in words}
    assert len(rows) == 14, f"全量模式应显示全部 14 个原形，实际 {len(rows)}"
    assert rows["peter"]["pn"] is True and rows["gloria"]["pn"] is True
    assert rows["later"]["pn"] is True
    assert rows["abandon"]["pn"] is False, "COCA 表内的句首词不算专名"
    assert rows["met"]["pn"] is False and rows["park"]["pn"] is False


def test_dictless_names_survive_lowercase_flood():
    """词典零证据的人名：字幕材料里小写泛滥（"hey,leonard"）也判专名过滤。

    台词本实测 sheldon 小写 93 次 vs 大写 67 次，小写一票否决会把整个角色表
    漏进生词表；零证据词只要出现过一次句中大写就按专名处理。对照面：
    全程没有大写证据的零证据词（gonna 类）不受牵连，照常显示。
    """
    meta, words, _, _ = run(
        "hey, leonard. i am leonard. this is sheldon.\n"
        "listen, Leonard, listen to me.\n"
        "you work with leonard and sheldon.\n")
    ws = shown_words((meta, words))
    assert "leonard" not in ws, \
        "零证据 + 句中大写出现过，小写泛滥也应是专名"
    assert "sheldon" in ws, "全程无大写证据的零证据词不应被连坐"
    assert meta["filtered_proper"] == 1, f"应只判 leonard 一个专名，实际 {meta['filtered_proper']}"


def test_single_letter_noise_filtered():
    """集数标号 S01E01 被分词正则拆出的单字母是噪声：不进生词表，--all 可见。"""
    text = "Season S01E01 begins here.\nThe E2 marker moved.\n"
    meta, words, _, _ = run(text)
    ws = shown_words((meta, words))
    assert "s" not in ws and "e" not in ws, "单字母碎片应被单字母规则滤掉"
    assert meta["filtered_single"] == 2, f"单字母计数应为 2（s、e），实际 {meta['filtered_single']}"
    meta2, words2, _, _ = run(text, show_all=True)
    ws2 = shown_words((meta2, words2))
    assert "s" in ws2 and "e" in ws2, "--all 模式单字母应可见"


# ---------------------------------------------------------------- 基础档边界

def test_cet6_now_basic():
    """最高档 CET6 的词默认隐藏（新档位），COCA 阈值外也一样。"""
    meta, words, _, _ = run("Their influence shaped the debate.\n")
    assert "influence" not in shown_words((meta, words)), \
        "最高档 cet6 应被基础词规则滤掉"
    assert meta["filtered_basic"] == 1, f"基础词计数应为 1，实际 {meta['filtered_basic']}"


def test_highest_level_rule_holds():
    """CET4+考研 的 abandon：最高档是考研，仍显示 —— 判据是最高档不是集合相交。"""
    meta, words, _, _ = run("He will abandon the plan.\nThe dog kept grumbling.\n")
    ws = shown_words((meta, words))
    assert "abandon" in ws, "最高档为 ky 的词不应因含 cet4 被误滤"
    assert "grumble" in ws, "tem4 词应显示"
    assert "influence" not in ws  # 未出现在本文本，哨兵：确认词典没串味
    assert "grumbling" not in ws, "grumbling 应归并进 grumble"


# ---------------------------------------------------------------- 分词属性

def test_token_case_and_sent_start():
    """caps/sent_start 从表面形态传播：句首缩写展开的两半都算句首。"""
    toks = sentence_tokens("Don't panic.")
    by_text = {}
    for t in toks:
        by_text.setdefault(t.text, t)
    assert by_text["do"].caps is True and by_text["do"].sent_start is True
    assert by_text["not"].sent_start is True, "缩写展开出的词应继承句首标记"
    assert by_text["panic"].caps is False and by_text["panic"].sent_start is False

    toks = sentence_tokens("met Peter-Jackson yesterday")
    frag = [t for t in toks if t.fragment]
    whole = [t for t in toks if not t.fragment and t.text == "peter-jackson"]
    assert whole and whole[0].caps is True, "连字符整体应继承表面大写"
    assert {t.text for t in frag} == {"peter", "jackson"}, "连字符词应产出片段"


# ---------------------------------------------------------------- 入口

TESTS = [
    test_proper_noun_filtered,
    test_lowercase_refutes_proper,
    test_dictless_names_survive_lowercase_flood,
    test_single_letter_noise_filtered,
    test_proper_noun_flag_in_all_mode,
    test_cet6_now_basic,
    test_highest_level_rule_holds,
    test_token_case_and_sent_start,
]


def main():
    failed = []
    for fn in TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed.append(fn.__name__)
            print(f"FAIL  {fn.__name__}: {e}")
    total = len(TESTS)
    print(f"\n{total - len(failed)}/{total} 通过")
    if failed:
        print("失败用例: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
