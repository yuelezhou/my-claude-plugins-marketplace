# -*- coding: utf-8 -*-
"""盯 MinerU 桌面版的任务进度，全部跑完后把产物搬进工作区。

用法：
    python wait_and_collect.py                      # 只盯进度，跑完打印结果
    python wait_and_collect.py --collect            # 跑完并把产物搬进 minuer_u未处理
    python wait_and_collect.py --collect --verify   # 搬完再逐份校验产物

产物来源目录是 MinerU 桌面版自己的历史目录（默认 C:\\Users\\yuele\\MinerU），
目录名形如 <分片名>.pdf-<uuid>，正好就是工作区里惯用的命名，所以直接搬、不改名。

注意：应用必须保持开着，否则它不会继续轮询云端状态。
"""
import argparse
import os
import re
import shutil
import sqlite3
import sys
import time

DEFAULT_DB = r"C:\Users\yuele\MinerU\data\mineru.db"
DEFAULT_DEST = r"D:\垃圾文件夹\minuer_u未处理"
TERMINAL = ("unzipped", "failed")


def snapshot(db):
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT file_name, state, unzip_file_output_path, extract_progress, err_msg "
            "FROM taskData ORDER BY file_name"
        ).fetchall()
    finally:
        con.close()
    return rows


def wait(db, timeout_min, interval=20):
    deadline = time.time() + timeout_min * 60
    last = None
    while True:
        rows = snapshot(db)
        total = len(rows)
        fin = sum(1 for r in rows if r[1] in TERMINAL)
        dist = {}
        for r in rows:
            dist[r[1]] = dist.get(r[1], 0) + 1
        cur = (fin, total, tuple(sorted(dist.items())))
        if cur != last:
            print(f"[{time.strftime('%H:%M:%S')}] 完成 {fin}/{total}  {dist}", flush=True)
            last = cur
        if total and fin >= total:
            print("全部任务到达终态", flush=True)
            return rows
        if time.time() > deadline:
            print(f"等待超时（{timeout_min} 分钟），仍有 {total - fin} 个未完成", flush=True)
            return rows
        time.sleep(interval)


def verify_dir(d):
    """返回问题列表；空列表表示这份产物没问题。"""
    problems = []
    md = os.path.join(d, "full.md")
    if not os.path.exists(md):
        return ["缺 full.md"]
    text = open(md, encoding="utf-8").read()
    cjk = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
    kanxi = sum(1 for c in text if 0x2F00 <= ord(c) <= 0x2FDF)
    if kanxi:
        problems.append(f"文字层含康熙部首码位 {kanxi} 个（字形正常但检索/翻译会错）")
    if cjk == 0:
        problems.append("没有汉字（英文原版书属正常，中文书则是抽取失败）")
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    missing = [r for r in refs if not os.path.exists(os.path.join(d, r))]
    if missing:
        problems.append(f"图片引用对不上文件 {len(missing)} 处，例如 {missing[:2]}")
    need = ("_content_list.json", "_model.json", "_origin.pdf", "layout.json")
    names = os.listdir(d)
    lacks = [k for k in need if not any(n.endswith(k) for n in names)]
    if lacks:
        problems.append(f"缺附属文件 {lacks}")
    return problems


def collect(rows, dest, do_verify):
    os.makedirs(dest, exist_ok=True)
    moved, skipped, bad = 0, [], []
    for name, state, out, prog, err in rows:
        if state != "unzipped":
            continue
        if not out or not os.path.isdir(out):
            skipped.append((name, "产物目录不存在"))
            continue
        base = os.path.basename(out.rstrip("\\/"))
        tgt = os.path.join(dest, base)
        if os.path.exists(tgt):
            skipped.append((name, "目标已存在同名目录"))
            continue
        shutil.move(out, tgt)
        moved += 1
        if do_verify:
            probs = verify_dir(tgt)
            if probs:
                bad.append((base, probs))
    print(f"\n已搬入 {dest}: {moved} 个目录")
    if skipped:
        print("跳过:")
        for s in skipped:
            print("  ", s)
    if do_verify:
        print(f"校验有问题的: {len(bad)} 个")
        for b in bad:
            print("  ", b[0][:60], "->", b[1])
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--timeout", type=float, default=120, help="等待上限（分钟）")
    ap.add_argument("--collect", action="store_true", help="到达终态后把产物搬进 --dest")
    ap.add_argument("--verify", action="store_true", help="搬运后逐份校验")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"找不到任务库: {args.db}（MinerU 桌面版跑过任务才会有）")
        return 2

    rows = wait(args.db, args.timeout)

    failed = [(r[0], r[4]) for r in rows if r[1] == "failed"]
    if failed:
        print(f"\n失败任务 {len(failed)} 个:")
        for name, err in failed:
            print(f"  {name[:56]}  err={err}")

    if args.collect:
        collect(rows, args.dest, args.verify)
    else:
        print("\n（未加 --collect，没有搬运产物）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
