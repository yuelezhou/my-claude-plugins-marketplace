#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_anki_cards.py — 校验 markdown_sync_to_anki / Obsidian Anki 格式的卡片 markdown 文件。

对应 anki-card-from-notes skill 的「硬性约束」与 references/card-format.md 格式契约。

校验项：
  1. YAML frontmatter 存在且以 --- 开头，含 anki: true
  2. deck / tags / note_type 字段格式合法
  3. 标题层级合法：卡片名用 ##，字段用 ####，元数据键用 #####（仅元数据段内），
     禁止使用 # / ### / ######
  4. 字段名只能是：正面 / 背面 / 笔记 / Text / Back Extra / 元数据（标准类型强制；
     自定义 note_type 下降级为提示，字段名以 Anki 模板为准）
  5. Basic 卡必须有「正面」+「背面」；Cloze 卡必须有含 {{c1::...}} 挖空的「Text」
     （自定义 note_type 跳过此完整性校验）
  6. Cloze 挖空编号 c1/c2/c3... 必须从 1 开始连续
  7. 新卡不允许出现 ##### id（已同步过的卡由同步工具回写 id，可忽略此条）
  8. fenced 代码块内不允许出现以 ## / #### 开头的行（会被解析器误识别为卡片/字段）

用法:
    python check_anki_cards.py <file.md> [<file.md> ...]
    python check_anki_cards.py <dir>            # 递归校验目录下所有 .md

退出码:
    0  通过（可含 warning）
    1  存在 error
    2  用法 / IO 错误
"""

import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIELD_NAMES = ("正面", "背面", "笔记", "Text", "Back Extra", "元数据")
META_KEYS = ("deck", "tags", "note_type", "id")
# 已知字段结构、可做完整性校验的 note_type；其余值视为 Anki 用户自定义类型（无法校验结构，仅提示）
KNOWN_STRUCT_TYPES = ("basic", "cloze", "正面-背面-笔记")

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
H2_RE = re.compile(r"^##\s+\S")
H4_RE = re.compile(r"^####\s+\S")
H5_RE = re.compile(r"^#####\s+\S")
BAD_H_RE = re.compile(r"^(#|###|######)\s+\S")
FIELD_RE = re.compile(r"^(正面|背面|笔记|Text|Back Extra|元数据)(?:\s|\(|（|$)")
CLOZE_RE = re.compile(r"\{\{(c\d+)::")
IN_CODE_BAD_RE = re.compile(r"^#{2,4}\s")

YAML_ANKI_RE = re.compile(r"^\s*anki\s*:\s*(true|false)\b", re.IGNORECASE)
DECK_RE = re.compile(r"^\s*deck\s*:\s*(.+?)\s*$")
TAGS_RE = re.compile(r"^\s*tags\s*:\s*(.+?)\s*$")
NOTE_TYPE_RE = re.compile(r"^\s*note_type\s*:\s*(.+?)\s*$")
TAGS_ARR_RE = re.compile(r"^\[[\w./-]+(\s*,\s*[\w./-]+)*\]$")
TAGS_STR_RE = re.compile(r"^[\w./-]+(\s*,\s*[\w./-]+)*$")


class Checker:
    def __init__(self, path, text):
        self.path = path
        self.lines = text.split("\n")
        self.errors = []
        self.warnings = []

    def error(self, lineno, msg):
        self.errors.append((lineno, msg))

    def warning(self, lineno, msg):
        self.warnings.append((lineno, msg))

    # ---------- frontmatter ----------

    def check_frontmatter(self):
        """返回 (fm, frontmatter_end_line_index)；frontmatter 有致命问题时返回 None。"""
        if not self.lines or not self.lines[0].strip().startswith("---"):
            self.error(1, "文件必须以 --- 开头的 YAML frontmatter 开始（缺少 frontmatter）")
            return None
        end = None
        for i in range(1, len(self.lines)):
            if self.lines[i].strip() == "---":
                end = i
                break
        if end is None:
            self.error(1, "frontmatter 缺少结束标记 ---")
            return None

        fm = {}
        anki_seen = False
        for i in range(1, end):
            line = self.lines[i]
            lineno = i + 1
            m = YAML_ANKI_RE.search(line)
            if m:
                anki_seen = True
                if m.group(1).lower() != "true":
                    self.error(lineno, "anki 必须是 true 才会被同步工具扫描（当前: %s）" % m.group(1))
            m = DECK_RE.match(line)
            if m and "deck" not in fm:
                fm["deck"] = m.group(1).strip("\"' ")
            m = TAGS_RE.match(line)
            if m and "tags" not in fm:
                fm["tags"] = m.group(1).strip()
            m = NOTE_TYPE_RE.match(line)
            if m and "note_type" not in fm:
                fm["note_type"] = m.group(1).strip("\"' ")

        if not anki_seen:
            self.error(2, "frontmatter 缺少 anki: true（同步工具靠它识别卡片文件）")
        if "deck" not in fm:
            self.warning(2, "frontmatter 缺少 deck（文件级默认牌组），同步时会落入未指定牌组")
        elif not fm["deck"]:
            self.warning(2, "deck 为空")
        if "tags" in fm:
            t = fm["tags"].strip()
            if not (TAGS_ARR_RE.match(t) or TAGS_STR_RE.match(t)):
                self.warning(2, "tags 格式可疑（应为 YAML 数组 [a, b] 或逗号分隔 a, b）: %r" % t)
        if "note_type" in fm:
            nt = fm["note_type"]
            if nt not in KNOWN_STRUCT_TYPES:
                self.warning(2, "note_type 是自定义类型: %r，无法校验字段结构，请确认字段与 Anki 模板一致"
                               "（可校验类型: basic / cloze / 正面-背面-笔记）" % nt)
        fm.setdefault("note_type", "basic")
        return fm, end

    # ---------- body ----------

    def check_body(self, fm, end):
        file_note_type = fm.get("note_type", "basic")
        in_code = False
        fence_char = None
        card_count = 0
        current_card_lineno = None
        current_field = None          # (name, lineno) 或 None
        in_metadata = False
        card_fields = {}              # field_name -> lineno
        card_meta = {}                # meta key -> value
        card_clozes = []
        card_has_id = False
        card_unknown_fields = []      # [(lineno, name)] 不在标准契约内的字段名

        def flush_card():
            nonlocal card_fields, card_meta, card_clozes, card_has_id, in_metadata, current_field
            nonlocal card_unknown_fields
            if current_card_lineno is None:
                return
            nt = card_meta.get("note_type", file_note_type)
            fields = set(card_fields)
            if nt == "cloze":
                if "Text" not in fields:
                    self.error(current_card_lineno, "Cloze 卡缺少 Text 字段")
                if not card_clozes:
                    self.error(current_card_lineno, "Cloze 卡的 Text 必须至少含一个 {{c1::...}} 挖空")
            elif nt in ("basic", "正面-背面-笔记"):
                if "正面" not in fields:
                    self.error(current_card_lineno, "Basic 卡缺少「正面」字段")
                if "背面" not in fields:
                    self.error(current_card_lineno, "Basic 卡缺少「背面」字段")
            else:
                self.warning(current_card_lineno, "自定义 note_type %r，跳过卡片结构校验（请确保字段与 Anki 模板一致）" % nt)
            if card_unknown_fields:
                if nt in KNOWN_STRUCT_TYPES:
                    for fl, name in card_unknown_fields:
                        self.error(fl, "未知字段名: %r（只能是 正面/背面/笔记/Text/Back Extra/元数据）" % name)
                else:
                    for fl, name in card_unknown_fields:
                        self.warning(fl, "自定义类型下字段名 %r 不在标准契约中，请确认与 Anki 模板一致" % name)
            if card_clozes:
                nums = sorted({int(n) for n in card_clozes})
                if nums != list(range(1, nums[-1] + 1)):
                    self.error(current_card_lineno, "Cloze 挖空编号不连续: c%s（应从 c1 开始递增）"
                               % ",".join(str(n) for n in nums))
            if card_has_id:
                self.warning(current_card_lineno, "本卡含 ##### id：新卡不应手写 id（若为同步工具回写，可忽略此条）")
            card_fields = {}
            card_meta = {}
            card_clozes = []
            card_has_id = False
            card_unknown_fields = []
            in_metadata = False
            current_field = None

        def next_nonempty(i):
            j = i + 1
            while j < len(self.lines) and not self.lines[j].strip():
                j += 1
            return j

        i = end + 1
        while i < len(self.lines):
            lineno = i + 1
            line = self.lines[i]
            stripped = line.strip()

            # fenced 代码块
            m = FENCE_RE.match(line)
            if m:
                ch = m.group(1)[0]
                if not in_code:
                    in_code = True
                    fence_char = ch
                elif ch == fence_char:
                    in_code = False
                    fence_char = None
                i += 1
                continue

            if in_code:
                if IN_CODE_BAD_RE.match(line):
                    self.error(lineno, "代码块内出现了以 ## / #### 开头的行（会被解析器误识别为卡片/字段），"
                                       "请改用 4 空格缩进代码块或挪到代码块外")
                i += 1
                continue

            if H2_RE.match(line):
                flush_card()
                card_count += 1
                current_card_lineno = lineno
            elif H4_RE.match(line):
                if current_card_lineno is None:
                    self.error(lineno, "#### 字段出现在任何卡片（## 标题）之外")
                else:
                    content = stripped[5:].strip()
                    fm_ = FIELD_RE.match(content)
                    if fm_:
                        name = fm_.group(1)
                        card_fields[name] = lineno
                        in_metadata = (name == "元数据")
                        current_field = name
                    else:
                        card_unknown_fields.append((lineno, content))
                        in_metadata = False
                        current_field = None
            elif H5_RE.match(line):
                if not in_metadata:
                    self.error(lineno, "##### 只能出现在 #### 元数据 段内")
                else:
                    key = stripped[5:].strip()
                    if key not in META_KEYS:
                        self.error(lineno, "元数据键只能是 deck / tags / note_type / id，当前: %r" % key)
                    elif key == "note_type":
                        j = next_nonempty(i)
                        val = self.lines[j].strip() if j < len(self.lines) else ""
                        if val not in KNOWN_STRUCT_TYPES:
                            self.warning(lineno, "卡级 note_type 是自定义类型: %r，无法校验字段结构"
                                       "（可校验类型: basic / cloze）" % val)
                        card_meta["note_type"] = val
                    elif key == "id":
                        card_has_id = True
            elif BAD_H_RE.match(line):
                self.error(lineno, "禁止的标题层级: %s（卡片名用 ##，字段用 ####，元数据键用 #####）"
                           % stripped.split()[0])
            else:
                # 普通文本：若在 Text 字段内，收集挖空
                if current_field == "Text":
                    for mm in CLOZE_RE.finditer(line):
                        card_clozes.append(int(mm.group(1)[1:]))
            i += 1

        flush_card()
        if card_count == 0:
            self.warning(1, "未找到任何卡片（正文里没有 ## 标题）")

    # ---------- run / report ----------

    def run(self):
        result = self.check_frontmatter()
        if result is None:
            return
        fm, end = result
        self.check_body(fm, end)

    def report(self):
        head = False
        for lineno, msg in self.errors:
            if not head:
                print("== %s ==" % self.path)
                head = True
            print("  error:   line %d: %s" % (lineno, msg))
        for lineno, msg in self.warnings:
            if not head:
                print("== %s ==" % self.path)
                head = True
            print("  warning: line %d: %s" % (lineno, msg))
        if not head:
            print("== %s ==  OK" % self.path)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    files = []
    for a in argv:
        if os.path.isdir(a):
            for root, _, names in os.walk(a):
                for n in sorted(names):
                    if n.endswith(".md"):
                        files.append(os.path.join(root, n))
        else:
            files.append(a)
    if not files:
        print("no markdown files found", file=sys.stderr)
        return 2

    total_e = total_w = 0
    bad = False
    for f in files:
        try:
            with open(f, encoding="utf-8-sig") as fh:
                text = fh.read()
        except OSError as e:
            print("%s: IO error: %s" % (f, e), file=sys.stderr)
            bad = True
            continue
        c = Checker(f, text)
        c.run()
        c.report()
        total_e += len(c.errors)
        total_w += len(c.warnings)
        if c.errors:
            bad = True
    print("\n%d error(s), %d warning(s), %d file(s)" % (total_e, total_w, len(files)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
