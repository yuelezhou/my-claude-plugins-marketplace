# -*- coding: utf-8 -*-
"""把 MinerU 产物归档为读书笔记目录（坚果云 编程读书笔记 规范）。

流程对应 .模板/miner_u导入模板/SKILL.md 与 .模板/目录结构规范_README.md：
  1. 按 dir 名里的页码区间排序 MinerU 分片目录（<分片名>.pdf-<uuid>）
  2. 初始化书目录（原文/章节、原文/images、笔记、anki_cards、延伸阅读、_work）
  3. 合并各分片 full.md -> 原文/full.md（图片路径保持 images/... 不变）
  4. 围栏感知地按章节标题拆分 -> 原文/章节/chapter-NN-标题.md（图片路径改 ../images/）
  5. 生成 笔记/ 骨架（导读/TL;DR 留 TODO 给模型填，问答留空给用户）
  6. 打包源分片 -> _work/<书名>_miner_u_YYYYMMDD.zip 并校验
  7. 全量校验，任何一项失败退出码 1

拆不出的书（常见于英文书章节标题不规整）按规范降级：只保留 full.md 不强行拆，
并明确报告。导读/TL;DR 正文与 anki_cards 由模型按 SKILL.md 流程另行生成。

用法：
  python archive_to_notes.py --src "<分片1>" "<分片2>" --book "<书目录>" --title "<书名>"
  python archive_to_notes.py --src "D:\\垃圾文件夹\\minuer_u未处理" --pick "Drools 8 规则引擎" --book ... --title ...
"""
import argparse
import datetime
import glob
import os
import re
import shutil
import sys
import zipfile

CHAP_PATTERNS = [
    re.compile(r"^第\s*(\d+)\s*章\s*[：:．.\s]?\s*(.*)$"),
    re.compile(r"^Chapter\s+(\d+)\s*[：:．.\s]?\s*(.*)$", re.I),
]
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
ILLEGAL = r'/\\:*?<>|"'

NOTE_TMPL = """> 📕《{title}》读书笔记 ｜ 原文：[{chap}](../原文/章节/{chap}.md)

{nav}

# {heading}

## 导读

<!-- TODO(AI)：写导读。本章在全书中的位置与作用、核心主张、读后应建立的自觉；
     结尾给一个「带着问题读」的提问。参考 凤凰架构/笔记/第02章 的写法。 -->

## TL;DR（Too Long; Don't Read）

<!-- TODO(AI)：按本章知识点列要点 bullets，术语加粗，覆盖主干概念与关键结论。 -->

## 问答

> 本节由我提问后补充。格式：`### Q：……` ＋ 正文作答。

*(暂无，等待提问)*
"""


def log(msg):
    print(msg, flush=True)


def find_chunks(src, pick):
    """返回排序后的分片目录列表。src 可以是分片目录本身或包含多个分片的父目录。"""
    dirs = []
    for s in src:
        if os.path.isdir(os.path.join(s, "images")) and os.path.exists(os.path.join(s, "full.md")):
            dirs.append(s)
            continue
        pattern = os.path.join(s, "*") if os.path.isdir(s) else s
        for cand in glob.glob(pattern):
            if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "full.md")):
                dirs.append(cand)
    if pick:
        dirs = [d for d in dirs if any(p.lower() in os.path.basename(d).lower() for p in pick)]
    if not dirs:
        return []

    def page_key(d):
        m = re.search(r"_(\d+)_(\d+)-(\d+)\.pdf-", os.path.basename(d.rstrip("\\/")))
        return (int(m.group(2)) if m else 0, d)

    return sorted(dirs, key=page_key)


def common_title(dirs):
    names = [os.path.basename(d.rstrip("\\/")) for d in dirs]
    stems = [re.sub(r"_\d+_\d+-\d+\.pdf-.{8,}$", "", n) for n in names]
    if not stems:
        return "未命名书"
    shortest = min(stems, key=len)
    return shortest


def scan_headings(lines):
    """围栏感知地收集真实标题：(行号, 级别, 文本)。代码块里的 # 不算。"""
    out, in_fence = [], False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        m = HEAD_RE.match(line)
        if m and not in_fence:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def next_title_text(lines, start):
    """章节标题行没有标题文字时，向后找下一行非空文本当标题。"""
    for j in range(start + 1, min(start + 6, len(lines))):
        s = lines[j].strip()
        if not s:
            continue
        if s.startswith("```"):
            return None
        m = HEAD_RE.match(s)
        if m:
            return m.group(2).strip()
        return s
    return None


# 相邻章标记的最小行距：小于该值视为目录页/重复命中；幸存标记数与跨度不足则视为无有效章结构
MIN_CHAP_GAP = 60
MIN_CHAPTERS = 3


def detect_chapters(text, extra_patterns):
    """收集章标记。章标题模式（第N章/Chapter N/自定义）不受代码围栏状态限制：
    OCR 产物里存在不成对的 ``` 野围栏，会把大量真实章标题吞进"代码块"
    （LangGraph/Vue/股权架构 实测各丢 2~7 章）。作为补偿，用最小行距过滤
    目录页命中（相邻标记都在书末几十行内，Grokking 英文版实测），并用
    标记跨度 < 全文 25% 或幸存 < 3 章判定为无有效章结构，降级为不拆。"""
    lines = text.split("\n")
    pats = CHAP_PATTERNS + [re.compile(p, re.I) for p in extra_patterns]

    marks = []  # (行号, 章号, 章标题)
    for i, line in enumerate(lines):
        m = HEAD_RE.match(line)
        if not m:
            continue
        t = m.group(2).strip()
        for pat in pats:
            pm = pat.match(t)
            if pm:
                num = int(pm.group(1))
                title = (pm.group(2) or "").strip() if pm.lastindex and pm.lastindex >= 2 else ""
                if not title:
                    nxt = next_title_text(lines, i)
                    if nxt:
                        title = re.sub(r"^#+\s*", "", nxt).strip()
                marks.append((i, num, f"第{num}章 {title}".strip()))
                break

    if not marks:
        return None, lines

    # 去重（同一章取首次出现）
    seen, uniq = set(), []
    for i, num, title in marks:
        if num not in seen:
            seen.add(num)
            uniq.append((i, num, title))

    # 相邻标记行距过近的丢弃后者（吸收目录簇）
    kept = []
    for mk in uniq:
        if kept and mk[0] - kept[-1][0] < MIN_CHAP_GAP:
            continue
        kept.append(mk)

    if len(kept) < MIN_CHAPTERS or kept[-1][0] - kept[0][0] < 0.25 * len(lines):
        return None, lines
    return kept, lines


def safe_name(s):
    for ch in ILLEGAL:
        s = s.replace(ch, " ")
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    return s


def split_chapters(text, extra_patterns):
    """返回 [(文件名, 章标题, 正文文本)]；拆不出返回 None。"""
    marks, lines = detect_chapters(text, extra_patterns)
    if not marks:
        return None
    out = []
    # 第一个章节之前的内容 -> 前言
    first_line = marks[0][0]
    pre = "\n".join(lines[:first_line]).strip()
    if len(pre.splitlines()) >= 10:
        out.append(("chapter-00-前言", "前言", pre))
    for k, (i, num, title) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        body = "\n".join(lines[i:end]).strip()
        name = f"chapter-{num:02d}-{safe_name(title.split(' ', 1)[-1] or title)[:40]}"
        out.append((name, title, body))
    return out


def copy_images(src_dirs, img_dir):
    os.makedirs(img_dir, exist_ok=True)
    total = dup = 0
    for d in src_dirs:
        src_img = os.path.join(d, "images")
        if not os.path.isdir(src_img):
            continue
        for name in sorted(os.listdir(src_img)):
            s = os.path.join(src_img, name)
            if not os.path.isfile(s):
                continue
            t = os.path.join(img_dir, name)
            if os.path.exists(t):
                # copy2 保留了源文件 mtime，同名且同大小同 mtime 视为上次已拷贝，跳过
                if (os.path.getsize(s) == os.path.getsize(t)
                        and os.path.getmtime(s) == os.path.getmtime(t)):
                    continue
                stem, ext = os.path.splitext(name)
                k = 1
                while os.path.exists(t):
                    t = os.path.join(img_dir, f"{stem}_{k}{ext}")
                    k += 1
                dup += 1
            shutil.copy2(s, t)
            total += 1
    return total, dup


def make_note(book_dir, title, name, heading, prev_name, next_name):
    nav_parts = []
    # 笔记之间是同目录引用（参考 凤凰架构 范例），不要加 ../笔记/ 前缀
    nav_parts.append(f"[◀ {prev_name}]({prev_name}.md)" if prev_name else "")
    nav_parts.append("**本章**")
    nav_parts.append(f"[▶ {next_name}]({next_name}.md)" if next_name else "")
    nav = " ｜ ".join(p for p in nav_parts if p)
    content = NOTE_TMPL.format(title=title, chap=name, nav=nav, heading=heading)
    with open(os.path.join(book_dir, "笔记", f"{name}.md"), "w", encoding="utf-8") as f:
        f.write(content)


def zip_sources(src_dirs, book_dir, title):
    work = os.path.join(book_dir, "_work")
    os.makedirs(work, exist_ok=True)
    stamp = datetime.date.today().strftime("%Y%m%d")
    zp = os.path.join(work, f"{safe_name(title)}_miner_u_{stamp}.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
        for d in src_dirs:
            base = os.path.basename(d.rstrip("\\/"))
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arc = os.path.join(base, os.path.relpath(fp, d))
                    z.write(fp, arc)
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        bad = z.testzip()
    fulls = sum(1 for n in names if n.endswith("full.md"))
    ok = bad is None and fulls >= len(src_dirs)
    return zp, len(names), ok


def validate(book_dir, src_dirs):
    problems = []
    full = os.path.join(book_dir, "原文", "full.md")
    if not os.path.isfile(full) or os.path.getsize(full) == 0:
        problems.append("原文/full.md 不存在或为空")
    chap = os.path.join(book_dir, "原文", "章节")
    if os.path.isdir(chap):
        for root, dirs, files in os.walk(chap):
            if root != chap or dirs:
                problems.append("原文/章节/ 下出现了子文件夹")
                break
            bad = [f for f in files if not f.endswith(".md")]
            if bad:
                problems.append(f"原文/章节/ 下有非 md 文件: {bad[:3]}")
        for f in files_glob(chap):
            t = open(f, encoding="utf-8").read()
            stray = re.findall(r"\]\((?:\./)?images/", t)
            if stray:
                problems.append(f"{os.path.basename(f)}: 有 {len(stray)} 处图片路径未改为 ../images/")
                break
    n_img = len([f for f in files_glob(os.path.join(book_dir, "原文", "images"))])
    n_src = 0
    for d in src_dirs:
        di = os.path.join(d, "images")
        if os.path.isdir(di):
            n_src += len([f for f in os.listdir(di) if os.path.isfile(os.path.join(di, f))])
    if n_img < n_src:
        problems.append(f"images 数量不足: 目标 {n_img} < 源合计 {n_src}")
    return problems, n_img


def files_glob(d):
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, f))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", nargs="+", required=True,
                    help="MinerU 分片目录（可多个，或其父目录/通配符）")
    ap.add_argument("--pick", nargs="*", default=None,
                    help="从 --src 父目录中按名称子串挑选属于同一本书的分片")
    ap.add_argument("--book", required=True, help="目标书目录（不存在则初始化）")
    ap.add_argument("--title", default=None, help="书名（默认取分片名的公共前缀）")
    ap.add_argument("--pattern", nargs="*", default=[], action="extend",
                    help="额外章节标题正则（追加到默认 第N章/Chapter N 之后；可多次出现，累加不覆盖）")
    ap.add_argument("--no-zip", action="store_true", help="跳过源分片打包")
    ap.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的 原文/full.md")
    args = ap.parse_args()

    chunks = find_chunks(args.src, args.pick)
    if not chunks:
        log("错误：没有找到包含 full.md 的分片目录")
        return 2
    title = args.title or common_title(chunks)
    log(f"分片 {len(chunks)} 个 -> 书《{title}》")
    for c in chunks:
        log(f"  {os.path.basename(c.rstrip(chr(92)+'/'))}")

    book = args.book
    exists = os.path.exists(os.path.join(book, "原文", "full.md"))
    if exists and not args.overwrite:
        log(f"错误：{book}/原文/full.md 已存在（加 --overwrite 才覆盖）")
        return 2
    for sub in ("原文/章节", "原文/images", "笔记", "anki_cards", "延伸阅读", "_work"):
        os.makedirs(os.path.join(book, sub), exist_ok=True)

    # 1) 合并 full.md
    merged = []
    for c in chunks:
        t = open(os.path.join(c, "full.md"), encoding="utf-8").read().rstrip("\n")
        merged.append(t)
    full_text = "\n\n".join(merged)
    with open(os.path.join(book, "原文", "full.md"), "w", encoding="utf-8") as f:
        f.write(full_text)
    log(f"[1/5] 合并 full.md：{len(full_text)} 字符")

    # 2) 拆章节
    parts = split_chapters(full_text, args.pattern)
    chap_dir = os.path.join(book, "原文", "章节")
    if parts:
        for name, heading, body in parts:
            body = body.replace("](images/", "](../images/").replace('src="images/', 'src="../images/')
            with open(os.path.join(chap_dir, f"{name}.md"), "w", encoding="utf-8") as f:
                f.write(body + "\n")
        log(f"[2/5] 拆分 {len(parts)} 个章节 -> 原文/章节/")
    else:
        log("[2/5] 未匹配到章节标题，按规范降级：只保留 full.md，不强行拆分")

    # 3) 图片
    n_img, n_dup = copy_images(chunks, os.path.join(book, "原文", "images"))
    log(f"[3/5] 拷贝图片 {n_img} 张（重名改号 {n_dup} 张）")

    # 4) 笔记骨架
    if parts:
        names = [p[0] for p in parts]
        for k, (name, heading, _b) in enumerate(parts):
            make_note(book, title, name, heading,
                      names[k - 1] if k > 0 else None,
                      names[k + 1] if k + 1 < len(names) else None)
        log(f"[4/5] 生成 {len(parts)} 份笔记骨架（导读/TL;DR 待模型填写，问答留给用户）")
    else:
        log("[4/5] 跳过笔记骨架（无章节可对应）")

    # 5) 打包
    if args.no_zip:
        log("[5/5] 跳过打包（--no-zip）")
        zp = None
    else:
        zp, n_files, ok = zip_sources(chunks, book, title)
        log(f"[5/5] 打包 {os.path.basename(zp)}：{n_files} 个条目，完整性 {'OK' if ok else 'FAIL'}")
        if not ok:
            log("错误：zip 校验不通过，不要删除源分片")
            return 1

    problems, n_img_chk = validate(book, chunks)
    if problems:
        log("\n校验失败：")
        for p in problems:
            log("  -", p)
        return 1
    log(f"\n校验通过（原文/images 共 {n_img_chk} 张）。")
    if parts:
        log("下一步（模型执行）：逐章填写 笔记/ 的导读与 TL;DR；再按 anki-card-from-notes 生成 anki_cards/。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
