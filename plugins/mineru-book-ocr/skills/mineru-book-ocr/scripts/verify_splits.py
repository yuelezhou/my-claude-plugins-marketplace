# -*- coding: utf-8 -*-
"""校验拆分结果：分片页数之和是否等于原书页数，分片区间是否首尾相接。

用法：
    python verify_splits.py --parts "D:\\垃圾文件夹\\待处理" [--source "D:\\垃圾文件夹\\原书"]

--parts  存放分片 PDF 的目录（文件名形如 <原书名>_<序号>_<起始页>-<结束页>.pdf）
--source 存放整本 PDF 的目录（可选；给了才能核对页数守恒，否则只查区间自洽）

退出码：0 全部通过，1 有问题，2 没有找到任何分片。
"""
import argparse
import os
import re
import sys

from pypdf import PdfReader

PART_RE = re.compile(r"^(?P<stem>.+)_(?P<idx>\d+)_(?P<a>\d+)-(?P<b>\d+)\.pdf$", re.IGNORECASE)


def pages(path):
    return len(PdfReader(path).pages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", required=True, help="分片所在目录")
    ap.add_argument("--source", default=None, help="整本 PDF 所在目录（可选）")
    args = ap.parse_args()

    groups = {}
    odd = []
    for name in sorted(os.listdir(args.parts)):
        path = os.path.join(args.parts, name)
        if not os.path.isfile(path) or not name.lower().endswith(".pdf"):
            continue
        m = PART_RE.match(name)
        if not m:
            odd.append(name)
            continue
        groups.setdefault(m.group("stem"), []).append((int(m.group("idx")), m, name))

    if not groups:
        print("没有找到任何形如 <名>_<序号>_<起>-<止>.pdf 的分片")
        return 2

    print(f"分片组数: {len(groups)}")
    if odd:
        print(f"不符合分片命名、已忽略: {len(odd)} 个 -> {odd[:3]}")

    all_ok = True
    for stem in sorted(groups):
        entries = sorted(groups[stem], key=lambda t: t[0])
        total = 0
        contiguous = True
        prev_end = 0
        self_consistent = True
        for idx, m, name in entries:
            path = os.path.join(args.parts, name)
            n = pages(path)
            a, b = int(m.group("a")), int(m.group("b"))
            total += n
            if n != b - a + 1:
                self_consistent = False
            if a != prev_end + 1:
                contiguous = False
            prev_end = b

        src_pages = None
        if args.source:
            cand = os.path.join(args.source, stem + ".pdf")
            if os.path.exists(cand):
                src_pages = pages(cand)

        conserved = (src_pages == total) if src_pages is not None else None
        ok = self_consistent and contiguous and (conserved is not False)
        all_ok = all_ok and ok

        verdict = "PASS" if ok else "FAIL"
        bits = [f"分片{len(entries)}", f"合计{total}页"]
        if src_pages is not None:
            bits.append(f"原书{src_pages}页")
            bits.append(f"页数守恒={conserved}")
        else:
            bits.append("未提供原书，跳过页数守恒")
        bits.append(f"区间自洽={self_consistent}")
        bits.append(f"区间连续={contiguous}")
        print(f"  [{verdict}] {stem[:44]:46s} " + "  ".join(bits))

    print()
    print("总判定:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
