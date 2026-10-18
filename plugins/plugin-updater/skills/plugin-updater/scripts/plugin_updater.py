#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plugin_updater.py — 外部聚合插件的更新检查（check）与升级（update，后续票交付）。

市场里 source 为 github 引用式的外部聚合条目（如 mattpocock-skills）靠
marketplace.json 里的 metadata.pinnedRef/pinnedSha pin 在固定基线；本工具
用 git ls-remote 取上游 head 与 pin 比对（不走 GitHub API，避免匿名限流），
版本号从上游 raw 的 .claude-plugin/plugin.json 取（失败不致命，报「版本号未知」）。

子命令:
    check    检查每条外部聚合条目：pin vs 上游 head、上游版本号；
             无 pin 条目报「无基线」并附当前 head

选项:
    --root    market 仓库根（默认从脚本位置向上推导，或环境变量 MARKET_REPO；
              对齐 skill-distributor 的惯例）

退出码: 0=全部最新  1=有更新或无基线或查询失败  2=用法/输入错误

设计约束（票 03 的 update 会复用）:
    外部访问收敛为可注入 effect 函数（fetch_remote_head / fetch_upstream_version /
    fetch_tarball / run_validator），与纯决策逻辑（parse_external_entries /
    parse_ls_remote_output / parse_upstream_plugin_json / judge_entry /
    build_report / decide_exit_code）分离；回归测试只走内存接缝，网络不进测试。
    本票 update 子链（tarball 下载、validator 校验门）只留接缝签名，未实现。
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GITHUB_URL = "https://github.com/{repo}"
UPSTREAM_RAW = ("https://raw.githubusercontent.com/{repo}/{sha}"
                "/.claude-plugin/plugin.json")
# 无 pin 条目查询上游 head 用的 ref
DEFAULT_REF = "HEAD"

STATUS_UPTODATE = "up-to-date"
STATUS_UPDATE = "update-available"
STATUS_NO_BASELINE = "no-baseline"
STATUS_ERROR = "error"
STATUS_LABEL = {
    STATUS_UPTODATE: "已最新",
    STATUS_UPDATE: "有更新",
    STATUS_NO_BASELINE: "无基线",
    STATUS_ERROR: "查询失败",
}


# ---------------------------------------------------------------- 仓库定位

def repo_root(explicit=None):
    """定位 market 仓库根（含 .claude-plugin/marketplace.json + plugins/）。

    顺序：--root 参数 > 环境变量 MARKET_REPO > 从脚本真实位置向上找
    （realpath 会把枢纽 junction 解析回仓库，经枢纽触发也能找到）。
    找不到时退出码 2。
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


def load_marketplace(root):
    with open(os.path.join(root, ".claude-plugin", "marketplace.json"),
              "r", encoding="utf-8-sig") as f:
        return json.load(f)


# ---------------------------------------------------------------- 纯决策层

def parse_external_entries(marketplace):
    """取外部聚合条目（source.source == "github"），pin 字段缺失兜底 None。

    本地路径条目（source 为字符串）不是治理对象，直接过滤。
    """
    entries = []
    for p in marketplace.get("plugins", []):
        if not isinstance(p, dict):
            continue
        src = p.get("source")
        if not (isinstance(src, dict) and src.get("source") == "github"):
            continue
        meta = p.get("metadata") or {}
        entries.append({
            "name": p.get("name", "?"),
            "repo": src.get("repo"),
            "pinned_ref": meta.get("pinnedRef"),
            "pinned_sha": meta.get("pinnedSha"),
        })
    return entries


def parse_ls_remote_output(output, ref):
    """从 git ls-remote 输出取 ref 对应的 head SHA。

    模式 `main` 会同时命中 refs/heads/changeset-release/main（git 按 refname
    尾段匹配模式），所以只认精确行：refs/heads/<ref> / refs/tags/<ref> / 原样。
    没有精确匹配就报错——静默取首行会把发布分支误当 head。
    """
    wanted = {ref, "refs/heads/" + ref, "refs/tags/" + ref}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        sha, name = parts[0].strip(), parts[1].strip()
        if name in wanted and sha:
            return sha
    raise ValueError(f"ls-remote 输出中没有精确匹配 {ref} 的行")


def parse_upstream_plugin_json(raw):
    """从上游 plugin.json 原始字节取 version；任何解析失败返回 None。"""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if isinstance(data, dict):
        v = data.get("version")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def judge_entry(entry, head_sha, upstream_version):
    """pin 比对：pin==head（大小写不敏感）-> up-to-date；无 pin -> no-baseline。"""
    r = dict(entry)
    r["head"] = head_sha
    r["upstream_version"] = upstream_version
    if not entry.get("pinned_sha"):
        r["status"] = STATUS_NO_BASELINE
    elif entry["pinned_sha"].lower() == (head_sha or "").lower():
        r["status"] = STATUS_UPTODATE
    else:
        r["status"] = STATUS_UPDATE
    return r


def build_report(results, market_root=None):
    """中文报告行。版本号拉取失败标「版本号未知」；无基线附当前 head。"""
    lines = []
    if market_root:
        lines.append(f"== 外部聚合插件更新检查（市场根: {market_root}）")
    else:
        lines.append("== 外部聚合插件更新检查")
    counts = {s: 0 for s in STATUS_LABEL}
    for i, r in enumerate(results, 1):
        counts[r["status"]] += 1
        lines.append("")
        lines.append(f"[{i}/{len(results)}] {r['name']}（{r['repo']}）")
        if r["status"] == STATUS_ERROR:
            lines.append(f"    结论 : 查询失败——{r.get('error', '未知错误')}")
            continue
        ref = r.get("pinned_ref") or DEFAULT_REF
        lines.append(f"    ref  : {ref}" + ("" if r.get("pinned_ref") else "（无 pin）"))
        if r["status"] == STATUS_NO_BASELINE:
            lines.append("    pin  : 无基线（marketplace.json 无 pinnedSha）")
        else:
            lines.append(f"    pin  : {r['pinned_sha']}")
        lines.append(f"    head : {r['head']}")
        if r.get("upstream_version"):
            lines.append(f"    版本 : {r['upstream_version']}")
        else:
            lines.append("    版本 : 版本号未知（上游拉取失败，不致命）")
        if r["status"] == STATUS_UPTODATE:
            lines.append("    结论 : 已最新")
        elif r["status"] == STATUS_UPDATE:
            lines.append(f"    结论 : 有更新——pin 落后于上游 head，"
                         f"人工确认后重 pin（update 子命令后续票交付）")
        else:
            lines.append("    结论 : 无基线——上游当前 head 见上，"
                         "人工确认后可 pin 建基线（update 子命令后续票交付）")
    lines.append("")
    lines.append("汇总: " + " / ".join(
        f"{counts[s]} {STATUS_LABEL[s]}" for s in
        (STATUS_UPTODATE, STATUS_UPDATE, STATUS_NO_BASELINE, STATUS_ERROR)))
    return lines


def decide_exit_code(results):
    """0=全部最新；有更新 / 无基线 / 查询失败都算「有事可报」-> 1。"""
    return 0 if all(r["status"] == STATUS_UPTODATE for r in results) else 1


# ---------------------------------------------------------------- effect 接缝
# 外部访问的唯一出入口；回归测试在这里注入假函数（见 test_plugin_updater.py）。

def fetch_remote_head(repo, ref, timeout=60):
    """上游 ref 的 head SHA（git ls-remote，不走 GitHub API）。"""
    proc = subprocess.run(
        ["git", "ls-remote", GITHUB_URL.format(repo=repo), ref],
        capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"git ls-remote 失败: {(proc.stderr or '').strip()}")
    return parse_ls_remote_output(proc.stdout, ref)


def fetch_upstream_version(repo, sha, timeout=30):
    """上游 head 处 plugin.json 的 version；任何网络/解析失败返回 None（不致命）。"""
    url = UPSTREAM_RAW.format(repo=repo, sha=sha)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return parse_upstream_plugin_json(resp.read())
    except (OSError, ValueError):
        return None


def fetch_tarball(repo, sha, dest_dir, timeout=120):
    """[票 03 接缝] 下载 codeload tarball 到 dest_dir，返回本地路径。

    update 子链一次下载同时服务校验门（解包后校验）与实体同步（拷贝来源）。
    本票未实现；测试注入假件。
    """
    raise NotImplementedError("update 子链（票 03）交付时实现")


def run_validator(tree_path):
    """[票 03 接缝] 对解包的新版本树调 plugin-validator --standalone 校验门。

    返回 (ok, 输出文本)；非 0 error 才放行写入。本票未实现；测试注入假件。
    """
    raise NotImplementedError("update 子链（票 03）交付时实现")


# ---------------------------------------------------------------- 编排

def run_check(entries, fetch_head=None, fetch_version=None):
    """check 主编排：逐条目取 head/版本号并判定；单条目失败不中断其余条目。

    fetch_head / fetch_version 默认接真实 effect 函数，测试注入假件。
    """
    fetch_head = fetch_head or fetch_remote_head
    fetch_version = fetch_version or fetch_upstream_version
    results = []
    for e in entries:
        ref = e.get("pinned_ref") or DEFAULT_REF
        try:
            head = fetch_head(e["repo"], ref)
        except Exception as exc:  # 网络/仓库异常：记录后继续下一条目
            r = dict(e)
            r.update(head=None, upstream_version=None,
                     status=STATUS_ERROR, error=str(exc))
            results.append(r)
            continue
        results.append(judge_entry(e, head, fetch_version(e["repo"], head)))
    return results


# ---------------------------------------------------------------- 入口

def cmd_check(root=None):
    base = repo_root(root)
    entries = parse_external_entries(load_marketplace(base))
    results = run_check(entries)
    print("\n".join(build_report(results, market_root=base)))
    return decide_exit_code(results)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="plugin_updater.py",
        description="外部聚合插件的更新检查与升级（update 后续票交付）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="检查外部聚合条目 pin 是否落后于上游")
    ck.add_argument("--root", help="market 仓库根（默认从脚本位置向上推导，"
                                   "或环境变量 MARKET_REPO）")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args.root)
    return 2


if __name__ == "__main__":
    sys.exit(main())
