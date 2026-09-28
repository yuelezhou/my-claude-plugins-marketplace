#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_distributor.py — 本地 skill 分发、盘点与重复拷贝清理。

自研 skill 正本在仓库 plugins/<插件>/skills/<名>/；junction（Windows）/
symlink（其他平台）把它们暴露到两层：枢纽 ~/.agents/skills/（ZCode、MiniMax、
OpenCode、Deep Code 原生读）与 Claude Code 层 ~/.claude/skills/（只认这里）。

子命令:
    link     分发：建齐/修复两层链接（幂等可重跑）
    status   盘点：各层条目类型、自研链接一致性、同名多拷贝漂移
    audit    核对：status 之外再按 PROMPT-INSTALL.md 台账逐行给「装了/没装」
    dupes    查看：重复拷贝清单（位置、内容一致否、正本是谁、clean 会清哪些）
    clean    清理：删除私有目录里与正本内容一致的残留拷贝（删前逐项确认；
             内容不一致的默认保留，--force 才清；非交互环境必须 --yes）

选项:
    --also a,b   link 时把枢纽里的第三方 skill 也链进 Claude Code 层
    --prune      清理指向本仓库但目标已消失的悬空链接
    --yes        clean 跳过逐项确认（先向用户展示 dupes 并获同意后使用）
    --force      clean 连内容与正本不一致的拷贝一并删除

退出码: 0=就绪/一致 1=有缺失/漂移/被中止 2=用法错误
"""

import argparse
import hashlib
import os
import re
import shutil
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IS_WIN = os.name == "nt"
HOME = os.path.expanduser("~")
HUB = os.path.join(HOME, ".agents", "skills")
CC = os.path.join(HOME, ".claude", "skills")
# 其他 agent 的私有 skill 目录：出现同名实体拷贝即为清理候选
EXTRA_DIRS = [
    ("ZCode", os.path.join(HOME, ".zcode", "skills")),
    ("MiniMax", os.path.join(HOME, ".minimax", "skills")),
    ("Codex", os.path.join(HOME, ".codex", "skills")),
]
KEBAB_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def repo_root(explicit=None):
    """定位 market 仓库根（含 .claude-plugin/marketplace.json + plugins/）。

    顺序：--root 参数 > 环境变量 MARKET_REPO > 从脚本真实位置向上找
    （realpath 会把枢纽 junction 解析回仓库，所以经枢纽触发也能找到）。
    marketplace 独立安装时三层都没有——必须 --root 或 MARKET_REPO 指定 clone。
    """
    cands = []
    if explicit:
        cands.append(explicit)
    env = os.environ.get("MARKET_REPO")
    if env:
        cands.append(env)
    d = os.path.dirname(os.path.realpath(__file__))
    for _ in range(8):
        cands.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    for c in cands:
        if (os.path.isfile(os.path.join(c, ".claude-plugin", "marketplace.json"))
                and os.path.isdir(os.path.join(c, "plugins"))):
            return c
    print("错误：未找到 market 仓库根（需含 .claude-plugin/marketplace.json 与 plugins/）")
    print("解决：在仓库 clone 内运行；或 --root <仓库路径>；或设环境变量 MARKET_REPO")
    sys.exit(2)


def is_link(path):
    if os.path.islink(path):
        return True
    if hasattr(os.path, "isjunction"):
        return os.path.isjunction(path)
    return False


def make_junction_win(target, link):
    import _winapi
    _winapi.CreateJunction(target, link)


def create_link(target, link):
    """在 link 处建指向 target 的链接。返回 (状态, 说明)：ok/skip/fail。"""
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.lexists(link):
        if is_link(link):
            if os.path.realpath(link) == os.path.realpath(target):
                return "skip", "已就绪"
            os.rmdir(link)  # 只摘除链接本身，不碰目标内容
        else:
            return "fail", "已存在实体，拒绝覆盖（先人工迁移）"
    if IS_WIN:
        make_junction_win(target, link)
    else:
        os.symlink(target, link)
    if os.path.realpath(link) == os.path.realpath(target):
        return "ok", "已创建"
    return "fail", "创建后校验失败"


def find_own_skills(root):
    """[(skill名, 正本绝对路径)]，正本 = plugins/*/skills/*/SKILL.md。"""
    out = []
    plugins_dir = os.path.join(root, "plugins")
    for plugin in sorted(os.listdir(plugins_dir)):
        skills_dir = os.path.join(plugins_dir, plugin, "skills")
        if not os.path.isdir(skills_dir):
            continue
        for name in sorted(os.listdir(skills_dir)):
            path = os.path.join(skills_dir, name)
            if os.path.isdir(path) and os.path.isfile(os.path.join(path, "SKILL.md")):
                out.append((name, path))
    return out


def entry_kind(path):
    if is_link(path):
        return "JUNCTION"
    if os.path.isdir(path):
        return "实体"
    return "缺失"


def skill_md_hash(path):
    """skill 指纹：SKILL.md 的 md5，用于同名拷贝的漂移比较。"""
    p = os.path.join(path, "SKILL.md")
    if not os.path.isfile(p):
        return None
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def scan_layers():
    """构建 layers 与 inventory；skill = 含 SKILL.md 的目录（.archive 等管理目录不算）。"""
    layers = [("枢纽", HUB), ("ClaudeCode", CC)] + [(t, p) for t, p in EXTRA_DIRS if os.path.isdir(p)]
    inventory = {}
    for title, layer in layers:
        rows = []
        if os.path.isdir(layer):
            for name in sorted(os.listdir(layer)):
                path = os.path.join(layer, name)
                if not os.path.isdir(path) or not os.path.isfile(os.path.join(path, "SKILL.md")):
                    continue
                kind = entry_kind(path)
                real = os.path.realpath(path) if is_link(path) else ""
                rows.append((name, kind, real))
        inventory[title] = rows
    return layers, inventory


def find_duplicates(layers, inventory, own_paths):
    """找出重复拷贝。

    返回 findings，每项:
        name          skill 名
        own           是否自研（正本在仓库）
        canonical     正本位置描述（显示用）
        remove        [(层名, 实体路径)] clean 的对象（全部为实体、全部在私有目录）
        content_match 与正本内容是否一致（None = 无法比较）
        note          不能自动处理的问题（如枢纽内是实体）
    只在私有目录里存在实体拷贝时产出；枢纽独占、单一私有目录独占（如 MiniMax
    云端 skill）均属合法形态，不产出。
    """
    layer_paths = {t: p for t, p in layers}
    seen = {}
    for title, _ in layers:
        for name, kind, real in inventory[title]:
            seen.setdefault(name, []).append((title, kind, real))
    findings = []
    for name, hits in sorted(seen.items()):
        if name in own_paths:
            hub_hit = next(((t, k) for t, k, _ in hits if t == "枢纽"), None)
            stray = [h for h in hits if h[0] not in ("枢纽", "ClaudeCode")]
            if not stray and (not hub_hit or hub_hit[1] == "JUNCTION"):
                continue
            repo_path = own_paths[name]
            fps = {skill_md_hash(repo_path)}
            remove = []
            for t, k, r in stray:
                base = r if (k == "JUNCTION" and r) else os.path.join(layer_paths[t], name)
                remove.append((t, base))
                fps.add(skill_md_hash(base))
            fps.discard(None)
            findings.append({
                "name": name,
                "own": True,
                "canonical": f"仓库 {repo_path}",
                "remove": remove,
                "content_match": len(fps) <= 1 if fps else None,
                "note": None if (hub_hit and hub_hit[1] == "JUNCTION") else "枢纽内不是 junction（人工处理）",
            })
            continue
        hub_hits = [h for h in hits if h[0] == "枢纽"]
        extras = [h for h in hits if h[0] not in ("枢纽", "ClaudeCode")]
        if not extras:
            continue
        if not hub_hits and len(extras) < 2:
            continue  # 单一私有目录独占（如 MiniMax 云端 skill）——合法形态
        compare = [(h[0], name, h[1], h[2]) for h in hub_hits + extras]
        fps = {skill_md_hash(real if (k == "JUNCTION" and r) else os.path.join(layer_paths[t], n))
               for t, n, k, r in compare}
        remove = []
        note = None
        if not hub_hits:
            # 无枢纽正本：互为拷贝，自动删会连最后一份一起删掉——交人工迁移
            note = "无枢纽正本：clean 不自动删；先人工把一份移入枢纽再清"
        else:
            remove = [(t, os.path.join(layer_paths[t], name)) for t, _, _ in extras]
        findings.append({
            "name": name,
            "own": False,
            "canonical": (os.path.join(HUB, name) if hub_hits
                          else "无枢纽正本（多私有目录互为拷贝）"),
            "remove": remove,
            "content_match": len({fp for fp in fps if fp}) <= 1 if any(fps) else None,
            "note": note,
        })
    return findings


def prune_dangling(layer):
    """清理悬空链接（目标已不存在的 junction/symlink），只摘链接不碰目标。"""
    removed = 0
    if not os.path.isdir(layer):
        return removed
    for name in sorted(os.listdir(layer)):
        path = os.path.join(layer, name)
        if not is_link(path):
            continue
        if not os.path.exists(path):
            os.rmdir(path)
            print(f"  PRUNE    {layer}{os.sep}{name}（目标已消失）")
            removed += 1
    return removed


def cmd_link(root, also, do_prune):
    own = find_own_skills(root)
    if not own:
        print("未找到自研 skill（plugins/*/skills/*/SKILL.md）")
        return 1
    failures = 0

    print(f"== 运行时枢纽 {HUB}")
    for name, path in own:
        state, msg = create_link(path, os.path.join(HUB, name))
        print(f"  {state.upper():8} {name} -> {path}" + (f"（{msg}）" if state != "ok" else ""))
        failures += state == "fail"

    print(f"== Claude Code 层 {CC}")
    for name in sorted({n for n, _ in own} | set(also)):
        hub_entry = os.path.join(HUB, name)
        if not os.path.isdir(hub_entry):
            print(f"  SKIP     {name}（枢纽中不存在）")
            failures += name in {n for n, _ in own}
            continue
        state, msg = create_link(hub_entry, os.path.join(CC, name))
        print(f"  {state.upper():8} {name} -> {hub_entry}" + (f"（{msg}）" if state != "ok" else ""))
        failures += state == "fail"

    if do_prune:
        print("== 清理悬空链接")
        prune_dangling(HUB)
        prune_dangling(CC)

    print()
    print(f"结果: {len(own)} 个自研 skill 两层链接{'全部就绪' if not failures else f'，{failures} 项失败'}")
    return 1 if failures else 0


def collect_state(root):
    """status/audit 共用：打印条目、自研链接一致性、漂移检测。返回 (own_names, problems, layers, inventory)。"""
    own = find_own_skills(root)
    own_names = {n for n, _ in own}
    layers, inventory = scan_layers()

    print("== 各层条目")
    for title, _ in layers:
        print(f"  [{title}] {len(inventory[title])} 项")
        for name, kind, real in inventory[title]:
            if kind == "JUNCTION":
                print(f"    {name:32} JUNCTION -> {real}")
            else:
                print(f"    {name:32} {kind}")

    print("== 自研链接一致性")
    hub_map = {n: (k, r) for n, k, r in inventory.get("枢纽", [])}
    cc_map = {n: (k, r) for n, k, r in inventory.get("ClaudeCode", [])}
    problems = []
    for name, path in own:
        kind, real = hub_map.get(name, ("缺失", ""))
        if kind != "JUNCTION" or os.path.normcase(real) != os.path.normcase(os.path.realpath(path)):
            print(f"  DRIFT    枢纽/{name}：应为指向仓库的 JUNCTION，实际 {kind or '缺失'}")
            problems.append(f"枢纽自研链接异常: {name}")
        else:
            print(f"  OK       枢纽/{name} -> 仓库正本")
        kind, real = cc_map.get(name, ("缺失", ""))
        if kind != "JUNCTION":
            print(f"  DRIFT    ClaudeCode/{name}：应为 JUNCTION（→枢纽），实际 {kind or '缺失'}")
            problems.append(f"Claude Code 层自研链接异常: {name}")
        else:
            print(f"  OK       ClaudeCode/{name} -> 枢纽")

    print("== 悬空链接检测")
    layer_paths = {t: p for t, p in layers}
    for title in ("枢纽", "ClaudeCode"):
        for name, kind, real in inventory.get(title, []):
            path = os.path.join(layer_paths[title], name)
            if kind == "JUNCTION" and not os.path.exists(path):
                print(f"  DRIFT    {title}/{name}：悬空链接（目标已消失，用 link --prune 清理）")
                problems.append(f"{title} 悬空链接: {name}")

    print("== 同名多拷贝漂移检测")
    for f in find_duplicates(layers, inventory, dict(own)):
        if f["own"]:
            print(f"  DRIFT    自研「{f['name']}」：" +
                  "；".join(filter(None, [f["note"], "私有目录残留拷贝: " +
                          ", ".join(f"{t}" for t, _ in f["remove"])])))
            problems.append(f"自研 skill 拷贝残留: {f['name']}")
        elif not f["content_match"]:
            print(f"  DRIFT    第三方「{f['name']}」多处内容不一致——以枢纽为正本修复")
            problems.append(f"第三方漂移: {f['name']}")
        else:
            print(f"  DUP      第三方「{f['name']}」在私有目录有相同拷贝——建议清理（clean）")
            problems.append(f"第三方重复拷贝: {f['name']}")

    return own_names, problems, layers, inventory


def parse_ledger(root):
    """解析 PROMPT-INSTALL.md 第三方表：[(条目名, 安装方式, 是否族)]。"""
    ledger_path = os.path.join(root, "PROMPT-INSTALL.md")
    if not os.path.isfile(ledger_path):
        return None
    rows, in_section = [], False
    with open(ledger_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("## "):
                in_section = line.strip().startswith("## 第三方 skill")
                continue
            if not in_section or not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2 or set(cells[0]) <= {"-", ":", " "} or cells[0] in ("skill", "Skill", "名称"):
                continue
            raw, install = cells[0], cells[1] if len(cells) > 1 else ""
            parts = [p.strip() for p in raw.split("、")]
            if all(KEBAB_RE.match(p) for p in parts):
                for p in parts:
                    rows.append((p, install, False))
            else:
                rows.append((raw, install, True))
    return rows


def cmd_status(root):
    _, problems, _, _ = collect_state(root)
    print()
    if problems:
        print(f"结果: {len(problems)} 项异常 —— ")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("结果: 各层一致，无漂移")
    return 0


def cmd_audit(root):
    own_names, problems, layers, inventory = collect_state(root)
    print("== 台账核对（PROMPT-INSTALL.md）")
    rows = parse_ledger(root)
    if rows is None:
        print("  未找到 PROMPT-INSTALL.md，跳过台账核对")
    else:
        hub_names = {n for n, _, _ in inventory.get("枢纽", [])}
        cc_names = {n for n, _, _ in inventory.get("ClaudeCode", [])}
        private_owner = {}
        for title, _ in layers:
            if title in ("枢纽", "ClaudeCode"):
                continue
            for n, _, _ in inventory.get(title, []):
                private_owner.setdefault(n, []).append(title)
        repo_names = own_names
        for name, install, family in rows:
            if family:
                print(f"  族条目  「{name}」——按成员对照上方枢纽清单核对")
                continue
            if name in repo_names:
                state = "已装" if name in hub_names else "缺链接"
                note = "自研：跑 link" if state != "已装" else "自研"
                print(f"  {state:6} {name:32} {note}")
                continue
            in_hub, in_cc = name in hub_names, name in cc_names
            if in_hub:
                print(f"  已装    {name:32} 枢纽实体｜cc 层{'已链' if in_cc else '未链(按需 --also)'}")
            elif name in private_owner:
                print(f"  已装    {name:32} 仅 {'/'.join(private_owner[name])} 私有目录｜{install}")
            else:
                print(f"  未装    {name:32} 安装方式: {install}")
    print()
    print("核对说明：结果不回写台账（声明式）；未装项按「安装方式」补装后重跑 audit")
    if problems:
        print(f"另有 {len(problems)} 项结构异常（见上方 DRIFT/DUP），建议先修复")
        return 1
    return 0


def cmd_dupes(root):
    own = dict(find_own_skills(root))
    layers, inventory = scan_layers()
    findings = find_duplicates(layers, inventory, own)
    if not findings:
        print("无重复拷贝——各 skill 均只在正本位置存在")
        return 0
    print("== 重复拷贝清单（[清]=clean 可删，[留]=需 --force，[正本]=不动，[?]=人工裁决）")
    for f in findings:
        print(f"  {f['name']}  正本: {f['canonical']}")
        remove_set = {p for _, p in f["remove"]}
        all_hits = []
        for title, rows in [(t, inventory[t]) for t, _ in layers]:
            all_hits += [(title, row) for row in rows if row[0] == f["name"]]
        for title, (name, kind, real) in all_hits:
            path = real if (kind == "JUNCTION" and real) else os.path.join(dict(layers)[title], name)
            if kind == "JUNCTION" and path not in remove_set:
                continue  # 链接是引用不是拷贝，不在清理范围
            if title == "枢纽" and path not in remove_set:
                print(f"    [正本] {title} {kind}  {path}")
                continue
            cleanable = path in remove_set and bool(f["content_match"])
            if cleanable:
                print(f"    [清] {title} {kind}  {path}")
            elif path in remove_set:
                print(f"    [留] {title} {kind}  {path}（内容不一致，--force 才清）")
            else:
                print(f"    [?] {title} {kind}  {path}（无法比较内容，人工裁决）")
        if f["note"]:
            print(f"    [?] {f['note']}")
    print()
    print("处理：python skill_distributor.py clean（逐项确认）或 clean --yes（已获用户同意）")
    return 0


def cmd_clean(root, yes, force):
    own = dict(find_own_skills(root))
    layers, inventory = scan_layers()
    findings = find_duplicates(layers, inventory, own)
    if not findings:
        print("无重复拷贝，无需清理")
        return 0

    eligible, kept = [], []
    for f in findings:
        for title, path in f["remove"]:
            if f["own"] or f["content_match"] or force:
                eligible.append(path)
            else:
                kept.append((f["name"], title, path))
    for name, title, path in kept:
        print(f"  KEEP    {title}/{name} 内容与正本不一致（可能含独有修改），--force 才清")
    if not eligible:
        print("没有可自动清理的拷贝")
        return 1 if kept else 0

    if not yes:
        if not sys.stdin.isatty():
            print("非交互环境：先用 dupes 向用户展示清单，用户同意后加 --yes 重跑")
            return 1
        print("将逐项确认删除（y=删 / n=跳过 / a=全部删除）：")
    extra_prefixes = [os.path.normcase(p) for _, p in EXTRA_DIRS]
    deleted, aborted = 0, False
    for path in eligible:
        if not yes:
            try:
                ans = input(f"  删除 {path} ? [y/N/a] ").strip().lower()
            except EOFError:
                print("  输入中断，未删除")
                aborted = True
                break
            if ans == "a":
                yes = True
            elif ans != "y":
                print(f"  SKIP    {path}")
                continue
        # 双重保险：只删私有目录下的实体，绝不动链接与枢纽
        if is_link(path) or not any(os.path.normcase(path).startswith(p) for p in extra_prefixes):
            print(f"  SKIP    {path}（非私有目录实体，拒绝删除）")
            continue
        shutil.rmtree(path)
        print(f"  DEL     {path}")
        deleted += 1

    residual = len(find_duplicates(*scan_layers(), own))
    print()
    if aborted:
        print(f"结果: 已删 {deleted} 项，确认中断——重跑 clean 继续")
        return 1
    print(f"结果: 删除 {deleted} 项" + (f"，残留 {residual} 项重复/漂移" if residual else "，已无重复拷贝"))
    if kept:
        print(f"保留 {len(kept)} 项内容不一致的拷贝待人工裁决（--force 强制清）")
    return 1 if (aborted or residual or kept) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="本地 skill 分发、盘点与重复拷贝清理")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_root_arg(p):
        p.add_argument("--root", default=None,
                       help="market 仓库根（默认：脚本真实位置向上找，或环境变量 MARKET_REPO）")

    p_link = sub.add_parser("link", help="分发：建齐/修复两层链接")
    p_link.add_argument("--also", default="", help="额外链进 Claude Code 层的枢纽第三方 skill，逗号分隔")
    p_link.add_argument("--prune", action="store_true", help="清理指向本仓库的悬空链接")
    add_root_arg(p_link)
    for name, help_text in (("status", "盘点：条目类型/链接一致性/漂移"),
                            ("audit", "核对：status + PROMPT-INSTALL.md 逐行装没装"),
                            ("dupes", "查看：重复拷贝清单")):
        p = sub.add_parser(name, help=help_text)
        add_root_arg(p)
    p_clean = sub.add_parser("clean", help="清理：删除与正本一致的残留拷贝（删前确认）")
    p_clean.add_argument("--yes", action="store_true", help="跳过逐项确认（先向用户展示 dupes 并获同意）")
    p_clean.add_argument("--force", action="store_true", help="连内容与正本不一致的拷贝一并删除")
    add_root_arg(p_clean)
    args = ap.parse_args(argv)

    root = repo_root(args.root)
    if args.cmd == "link":
        also = {n.strip() for n in args.also.split(",") if n.strip()}
        return cmd_link(root, also, args.prune)
    if args.cmd == "status":
        return cmd_status(root)
    if args.cmd == "audit":
        return cmd_audit(root)
    if args.cmd == "dupes":
        return cmd_dupes(root)
    return cmd_clean(root, args.yes, args.force)


if __name__ == "__main__":
    sys.exit(main())
