#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_check_anki_cards.py — check_anki_cards.py 的回归自测。

覆盖：frontmatter、标题层级、字段名、Basic/Cloze 完整性、挖空编号、
元数据段、代码块误识别、目录模式、无参数、IO 错误。

用法:
    python test_check_anki_cards.py

退出码:
    0  全部通过
    1  有用例失败
"""

import os
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_anki_cards.py")

FM = "---\nanki: true\n---\n"
CARD = "\n## 卡\n\n#### 正面\nq\n\n#### 背面\na\n"

# (name, content, expected_exit, must_contain, must_not_contain)
CASES = [
    # ---- frontmatter ----
    ("empty", "", 1, ["必须以 --- 开头的 YAML frontmatter"], []),
    ("no_frontmatter", CARD, 1, ["必须以 --- 开头的 YAML frontmatter"], []),
    ("unclosed_frontmatter", "---\nanki: true\n", 1, ["缺少结束标记"], []),
    ("fm_only", "---\nanki: true\ndeck: 测试::A\ntags: [t]\nnote_type: basic\n---\n", 0, ["未找到任何卡片"], []),
    ("missing_anki", "---\ndeck: 测试::A\n---\n" + CARD, 1, ["缺少 anki: true"], []),
    ("anki_false", "---\nanki: false\n---\n" + CARD, 1, ["anki 必须是 true"], []),
    ("deck_empty", "---\nanki: true\ndeck: \n---\n" + CARD, 0, ["deck 为空"], []),
    ("bad_tags", "---\nanki: true\ntags: [algo bst]\n---\n" + CARD, 0, ["tags 格式可疑"], []),
    ("custom_note_type_warns", "---\nanki: true\nnote_type: 概念卡\n---\n" + CARD, 0, ["自定义类型"], []),
    ("legacy_note_type", "---\nanki: true\nnote_type: 正面-背面-笔记\n---\n" + CARD, 0, [], []),
    ("fm_default_basic", FM + CARD, 0, [], []),

    # ---- 标题层级 ----
    ("h1_forbidden", FM + "\n# 一级标题\n", 1, ["禁止的标题层级: #"], []),
    ("h3_forbidden", FM + "\n### 三级标题\n", 1, ["禁止的标题层级: ###"], []),
    ("h6_forbidden", FM + "\n###### 六级标题\n", 1, ["禁止的标题层级: ######"], []),
    ("field_outside_card", FM + "\n#### 正面\nq\n", 1, ["字段出现在任何卡片"], []),
    ("h5_outside_meta", FM + "\n## 卡\n\n#### 正面\nq\n\n#### 背面\na\n\n##### deck\nx\n",
     1, ["只能出现在 #### 元数据"], []),

    # ---- 字段名 ----
    ("unknown_field", FM + "\n## 卡\n\n#### 问题\nq\n", 1, ["未知字段名"], []),
    ("field_with_comment", FM + "\n## 卡\n\n#### 正面\nq\n\n#### 背面\na\n\n#### 笔记（可选）\nnote\n", 0, [], []),
    ("back_extra_field", "---\nanki: true\nnote_type: cloze\n---\n\n## 卡\n\n#### Text\n{{c1::挖空}}\n\n#### Back Extra\n补充\n",
     0, [], []),

    # ---- Basic / Cloze 完整性 ----
    ("basic_missing_back", FM + "\n## 卡\n\n#### 正面\nq\n", 1, ["缺少「背面」"], []),
    ("basic_missing_front", FM + "\n## 卡\n\n#### 背面\na\n", 1, ["缺少「正面」"], []),
    ("cloze_no_cloze", FM + "\n## 卡\n\n#### Text\n没有挖空\n\n#### 元数据\n##### note_type\ncloze\n",
     1, ["必须至少含一个 {{c1::...}}"], []),
    ("cloze_no_text", FM + "\n## 卡\n\n#### 正面\nq\n\n#### 元数据\n##### note_type\ncloze\n",
     1, ["缺少 Text 字段"], []),
    ("cloze_c2_only", FM + "\n## 卡\n\n#### Text\n只有 {{c2::第二个}}\n\n#### 元数据\n##### note_type\ncloze\n",
     1, ["编号不连续"], []),
    ("cloze_jump", FM + "\n## 卡\n\n#### Text\n{{c1::一}} 和 {{c3::三}}\n\n#### 元数据\n##### note_type\ncloze\n",
     1, ["编号不连续"], []),
    ("cloze_ok_multi_line", FM + "\n## 卡\n\n#### Text\n跨行挖空 {{c1::第一}} 和\n{{c2::第二}}\n\n#### 元数据\n##### note_type\ncloze\n",
     0, [], []),
    ("cloze_meta_override", FM + "\n## 卡\n\n#### 正面\nq\n\n#### 背面\na\n\n#### 元数据\n##### note_type\ncloze\n",
     1, ["缺少 Text 字段"], []),

    # ---- 元数据段 ----
    ("meta_bad_key", FM + "\n## 卡\n\n#### 正面\nq\n\n#### 背面\na\n\n#### 元数据\n##### foobar\nx\n",
     1, ["元数据键只能是"], []),
    ("meta_custom_note_type", FM + "\n## 卡\n\n#### 正面\nq\n\n#### 背面\na\n\n#### 元数据\n##### note_type\n逐字翻译\n",
     0, ["卡级 note_type 是自定义类型"], []),
    ("custom_type_custom_field", "---\nanki: true\nnote_type: 概念卡\n---\n\n## 卡\n\n#### 术语\nfoo\n",
     0, ["跳过卡片结构校验", "不在标准契约中"], []),
    ("custom_type_basic_fields_ok", "---\nanki: true\nnote_type: 概念卡\n---\n" + CARD, 0, [], []),
    ("meta_id_warning", FM + "\n## 卡\n\n#### 正面\nq\n\n#### 背面\na\n\n#### 元数据\n##### id\n123\n",
     0, ["本卡含 ##### id"], []),
    ("meta_full_override", FM + "\n## 卡\n\n#### 正面\nq\n\n#### 背面\na\n\n#### 元数据\n##### deck\n其他::牌组\n##### tags\nx, y\n##### note_type\nbasic\n",
     0, [], []),

    # ---- 代码块 ----
    ("code_block_bad_heading", FM + CARD + "\n```js\n## 标题行\n```\n", 1, ["代码块内出现了"], []),
    ("code_block_indented_escape", FM + CARD + "\n```js\n    ## 缩进后不误识别\n```\n", 0, [], []),
    ("code_block_unclosed", FM + CARD + "\n```js\n## 未闭合块里的标题\n", 1, ["代码块内出现了"], []),
    ("code_block_ok", FM + CARD + "\n```js\nconst x = 1;\n```\n", 0, [], []),
]

# 特殊用例：目录模式 / 无参数 / 不存在的文件
SPECIAL = [
    ("no_args", [], 2, []),
    ("missing_file", ["no_such_file.md"], 1, ["IO error"]),
]


def run_script(args):
    r = subprocess.run([sys.executable, SCRIPT] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="anki_check_test_")
    failures = 0
    total = 0
    try:
        # 文件用例
        for name, content, want_exit, must, must_not in CASES:
            total += 1
            p = os.path.join(tmp, name + ".md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            code, out = run_script([p])
            ok = (code == want_exit
                  and all(s in out for s in must)
                  and all(s not in out for s in must_not))
            print("%s %s (exit=%d)" % ("PASS" if ok else "FAIL", name, code))
            if not ok:
                failures += 1
                print("  want exit=%d, must=%r, must_not=%r" % (want_exit, must, must_not))
                print("  got:\n%s" % out)

        # 目录模式：独立子目录（避免扫到其他用例文件）
        total += 1
        d_root = os.path.join(tmp, "dir_test")
        d_ok = os.path.join(d_root, "dir_ok")
        d_bad = os.path.join(d_root, "dir_bad")
        os.makedirs(d_ok)
        os.makedirs(d_bad)
        with open(os.path.join(d_ok, "a.md"), "w", encoding="utf-8") as f:
            f.write(FM + CARD)
        with open(os.path.join(d_bad, "b.md"), "w", encoding="utf-8") as f:
            f.write("---\nanki: false\n---\n" + CARD)
        code, out = run_script([d_root])
        ok = (code == 1 and "dir_ok" in out and "dir_bad" in out and "2 file(s)" in out)
        print("%s dir_mode (exit=%d)" % ("PASS" if ok else "FAIL", code))
        if not ok:
            failures += 1
            print("  got:\n%s" % out)

        # 特殊用例
        for name, args, want_exit, must in SPECIAL:
            total += 1
            code, out = run_script(args)
            ok = code == want_exit and all(s in out for s in must)
            print("%s %s (exit=%d)" % ("PASS" if ok else "FAIL", name, code))
            if not ok:
                failures += 1
                print("  want exit=%d, got %d, out:\n%s" % (want_exit, code, out))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("----")
    print("%d/%d passed" % (total - failures, total))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
