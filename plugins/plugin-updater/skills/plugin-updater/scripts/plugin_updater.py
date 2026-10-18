#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plugin_updater.py — 外部聚合插件的更新检查（check）与升级（update）。

市场里 source 为 github 引用式的外部聚合条目（如 mattpocock-skills）靠
marketplace.json 里的 metadata.pinnedRef/pinnedSha pin 在固定基线；本工具
用 git ls-remote 取上游 head 与 pin 比对（不走 GitHub API，避免匿名限流），
版本号从上游 raw 的 .claude-plugin/plugin.json 取（失败不致命，报「版本号未知」）。

check 三条线（票 01 pin 线 + 票 02 枢纽同步线 / 其他市场副本线）:
    pin 线      pin SHA vs 上游 head，附上游版本号；无 pin 报「无基线」附当前 head
    枢纽线      下载 pin 处 codeload tarball，动态派生族成员（skills/ 下
                engineering/productivity/misc 三分类的一级子目录，
                deprecated/in-progress 永不装入），对 ~/.agents/skills/ 里每个
                族实体比对内容基线：一致 -> 已同步；不一致 -> 与基线不一致
                （落后或手改，不做进一步区分——那是 update 用旧 pin 三方分类的事）；
                枢纽缺条目 -> 缺失。族清单增删是 update 的事，check 只报现状。
    副本线      读 ZCode / Claude Code 的插件安装记录，对装自其他市场的外部条目
                副本报已装版本/来源市场/上游 sha 并打印刷新命令（只打印不代跑）；
                未装的 agent（含无安装记录的 MiniMax）报「未安装」不报错。

update 仓库写半链（票 03）——对有新版的条目（或 --entry 指定条目）依序：
    下载新 SHA tarball（与 check 枢纽线共用一次下载）-> plugin-validator
    --standalone 校验门（解包树上跑，非 0 阻断 error 全链中止、零写入；
    「缺 .minimax-plugin」对外部引用式条目特判 N/A——本地无源码、不分发给
    MiniMax，见 2026-10-18 手动重 pin 先例）-> bump marketplace.json 该条目
    pinnedSha/pinnedAt（note 仅同步内嵌旧 SHA/日期的文字）-> 同步
    docs/plugin-compatibility.md「外部聚合插件」表格的 pin 列。
    全部条目先计划后写入（全或无）：任一条目失败就不写任何文件。
    无 pin 条目 update 时 pin 到当时 head 建基线（照走同一校验门，写齐
    pinnedRef（git ls-remote --symref 取默认分支）/pinnedSha/pinnedAt）。
    枢纽族实体同步与链接层同步是票 04，本链不触碰。

选项:
    check: --root / --hub（同上）
    update: --entry <名> 限定单条目；--yes 非交互确认（缺则拒绝一切变更）；
            --dry-run 只打印将做的变更不写文件；--root 同上

退出码: 0=全部最新且枢纽同步（check）/ 更新成功或无需更新（update）
       1=有更新/无基线/查询失败/枢纽有差异（check）/ 更新失败全链中止（update）
       2=用法/输入错误（含非交互缺 --yes）
       （副本线只报告不影响退出码——外部市场副本是常驻消费线，不是可消除的漂移）

设计约束:
    外部访问收敛为可注入 effect 函数（fetch_remote_head / fetch_upstream_version /
    fetch_tarball / fetch_remote_default_ref / run_validator），与纯决策逻辑
    （parse_external_entries / parse_ls_remote_output / parse_upstream_plugin_json /
    judge_entry / derive_family_members / judge_hub_members / collect_copy_line /
    build_report / build_hub_report / build_copy_report / decide_exit_code /
    judge_validator_output / parse_symref_output / apply_pin_bump /
    render_pin_cell / sync_compat_table）分离；编排（run_check / run_hub_check /
    plan_updates / apply_updates）只做组合。
    update 的解包树在校验门前用 normalize_tree_root 把目录名规范成 plugin.json
    的 name（codeload 顶层是 <repo>-<sha>，validator 校验 name 与目录名一致；
    手动重 pin 先例的 git clone 目录名天然对齐，tarball 链需显式补齐）。
    回归测试只走内存与 tmp 接缝，网络不进测试。
"""

import argparse
import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GITHUB_URL = "https://github.com/{repo}"
UPSTREAM_RAW = ("https://raw.githubusercontent.com/{repo}/{sha}"
                "/.claude-plugin/plugin.json")
CODELOAD_TARBALL = "https://codeload.github.com/{repo}/tar.gz/{sha}"
# 无 pin 条目查询上游 head 用的 ref
DEFAULT_REF = "HEAD"

# ---------------------------------------------------------------- update（票 03）
# 仓库内相对路径（--root 仓库根拼拼）：plugin-validator 校验门脚本与 compat 文档
VALIDATOR_REL = os.path.join("plugins", "plugin-validator", "skills",
                             "plugin-validator", "scripts", "check_plugin.py")
COMPAT_REL = os.path.join("docs", "plugin-compatibility.md")
# 校验门输出里 error 行与「缺 .minimax-plugin」的形态（check_plugin.py 的打印格式）
ERROR_LINE_RE = re.compile(r"^\s*ERROR\s+(.+?)\s*$", re.MULTILINE)
MINIMAX_MISSING_RE = re.compile(r"缺少 \.minimax-plugin/plugin\.json")
# 校验门放行的必要证据：check_plugin.py 末尾必有「结果: ...」汇总行，
# 没有 = 输出不可识别（脚本缺失/崩溃等），保守按未通过处理
GATE_SUMMARY_PREFIX = "结果:"

# update 计划的三种动作
ACTION_BUMP = "bump"          # 有 pin 且落后 -> 换新 SHA
ACTION_BASELINE = "baseline"  # 无 pin -> pin 到当时 head 建基线
ACTION_SKIP = "skip"          # pin==head -> 不动（幂等重跑的基础）
# 计划失败的阶段
STAGE_HEAD = "head"        # 上游 head 查询失败
STAGE_SYMREF = "symref"    # 默认分支解析失败（仅建基线条目）
STAGE_TARBALL = "tarball"  # 新版 tarball 下载/解包失败
STAGE_GATE = "gate"        # 校验门未通过（其余 error 照常阻断）
# UTF-8 BOM：Windows 工具链可能写入；读写 marketplace.json 时跟随原文件
BOM = "\\ufeff"  # UTF-8 BOM：Windows 工具链可能写入；读写 marketplace.json 时跟随原文件

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

# ---------------------------------------------------------------- 枢纽同步线
# 族成员只从这三个分类派生；deprecated/in-progress 结构上就不在扫描范围，
# 「永不装入」由清单派生规则保证而非运行时过滤。
FAMILY_CATEGORIES = ("engineering", "productivity", "misc")

HUB_STATUS_OK = "hub-ok"                # 条目级：tarball 下载/解包/派生成功
HUB_STATUS_ERROR = "hub-error"          # 条目级：枢纽线查询失败（可读错误在 error）
HUB_STATUS_SYNCED = "hub-in-sync"       # 成员级：枢纽实体与 pin 基线内容一致
HUB_STATUS_DRIFTED = "hub-drifted"      # 成员级：与基线不一致（落后或手改，不区分）
HUB_STATUS_MISSING = "hub-missing"      # 成员级：枢纽缺条目
HUB_LABEL = {
    HUB_STATUS_SYNCED: "已同步",
    HUB_STATUS_DRIFTED: "与基线不一致（落后或手改）",
    HUB_STATUS_MISSING: "缺失",
}

# ---------------------------------------------------------------- 其他市场副本线
COPY_STATUS_FOREIGN = "copy-foreign"          # 装自其他市场的外部条目副本
COPY_STATUS_OWN = "copy-own-market"           # 装自本仓库市场（不算外部副本）
COPY_STATUS_NOT_INSTALLED = "copy-not-installed"
COPY_LABEL = {
    COPY_STATUS_FOREIGN: "已装（其他市场）",
    COPY_STATUS_OWN: "已装（本仓库市场）",
    COPY_STATUS_NOT_INSTALLED: "未安装",
}

AGENT_ZCODE = "zcode"
AGENT_CLAUDE_CODE = "claude-code"
AGENT_MINIMAX = "minimax"
AGENT_LABEL = {
    AGENT_ZCODE: "ZCode",
    AGENT_CLAUDE_CODE: "Claude Code",
    AGENT_MINIMAX: "MiniMax",
}
MINIMAX_NOTE = "MiniMax 原生读枢纽 ~/.agents/skills，无独立插件安装记录"

# 默认路径指向真实 home；函数参数可注入（测试传 tmp 路径或直接传已加载的 dict）
DEFAULT_HUB_DIR = os.path.join(os.path.expanduser("~"), ".agents", "skills")
ZCODE_PLUGINS_DIR = os.path.join(os.path.expanduser("~"), ".zcode", "cli", "plugins")
CLAUDE_PLUGINS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "plugins")
ZCODE_INSTALLED_JSON = os.path.join(ZCODE_PLUGINS_DIR, "installed_plugins.json")
ZCODE_KNOWN_JSON = os.path.join(ZCODE_PLUGINS_DIR, "known_marketplaces.json")
CLAUDE_INSTALLED_JSON = os.path.join(CLAUDE_PLUGINS_DIR, "installed_plugins.json")
CLAUDE_KNOWN_JSON = os.path.join(CLAUDE_PLUGINS_DIR, "known_marketplaces.json")


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


def parse_symref_output(output):
    """从 `git ls-remote --symref <url> HEAD` 输出取默认分支短名。

    首行形如 `ref: refs/heads/main\\tHEAD`；没有 ref: 行就报错（与
    parse_ls_remote_output 同一纪律：静默兜底会 pin 错基线）。
    """
    for line in output.splitlines():
        if line.startswith("ref:"):
            refspec = line[len("ref:"):].split("\t")[0].strip()
            if refspec:
                return refspec.rsplit("/", 1)[-1]
    raise ValueError("ls-remote --symref 输出中没有 ref: 行")


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


def decide_exit_code(results, hub_results=None):
    """0=全部最新且枢纽全同步；有更新 / 无基线 / 查询失败 / 枢纽有差异 / 枢纽线
    查询失败都算「有事可报」-> 1。副本线只报告，不影响退出码（外部市场副本是
    常驻消费线，不是 check 能消除的漂移）。"""
    if any(r["status"] != STATUS_UPTODATE for r in results):
        return 1
    for r in hub_results or []:
        if r["status"] != HUB_STATUS_OK:
            return 1
        if any(m["status"] != HUB_STATUS_SYNCED for m in r["members"]):
            return 1
    return 0


# ---------------------------------------------------------------- update 纯决策层（票 03）

def render_pin_cell(ref, sha, date, version=None):
    """compat 表格 pin 列单元格：``main `49dd158`（2026-10-18，v1.3.1）`` 格式。

    版本号未知（上游拉取失败）时省略版本段，只写日期。
    """
    cell = f"{ref} `{(sha or '?')[:7]}`（{date}"
    if version:
        cell += f"，v{version}"
    return cell + "）"


def sync_compat_table(text, plugin_name, new_cell):
    """同步 compat 文档「外部聚合插件」表格某条目行的 pin 列（第 3 列）。

    精准行替换（正则锚定行首条目名，只动该行第 3 列），不整文件重写；
    上游列/三平台列/其余行/表格外正文一律不动。行不存在（该条目没进过表格）
    或单元格已是新值（幂等）都返回原文。返回 (新文本, 是否有变化)。
    """
    pattern = re.compile(
        r"^(\|[ \t]*" + re.escape(plugin_name) + r"[ \t]*\|[^|\n]*\|)([^|\n]*)(\|)",
        re.MULTILINE)
    m = pattern.search(text)
    if m is None or m.group(2).strip() == new_cell.strip():
        return text, False
    new_text = pattern.sub(
        lambda mm: f"{mm.group(1)} {new_cell} {mm.group(3)}", text, count=1)
    return new_text, new_text != text


def _sync_note_text(note, old_sha, new_sha, old_date, new_date):
    """note 字段只同步内嵌的旧 SHA / 旧日期文字（长串优先替换防前缀截断），
    其余内容原样保留（票面口径：note 是人工备注，工具不代拟）。"""
    out = note
    if old_sha and new_sha and old_sha.lower() != new_sha.lower():
        for form in (old_sha, old_sha[:12], old_sha[:7]):
            if form and form in out:
                out = out.replace(form, new_sha[:len(form)])
    if old_date and old_date != new_date and old_date in out:
        out = out.replace(old_date, new_date)
    return out


def apply_pin_bump(marketplace, name, new_sha, new_date, new_ref=None):
    """marketplace.json 单条目 pin bump（纯函数，不改入参 dict）。

    bump（有 pin）：pinnedSha -> 新 head、pinnedAt -> 当天，pinnedRef 原样；
    建基线（无 pin，new_ref 给默认分支）：新建 metadata 写齐
    pinnedRef/pinnedSha/pinnedAt（键序对齐现有条目排版）。
    note 仅同步内嵌旧 SHA/日期的文字。找不到条目报 ValueError。
    返回 (新 marketplace dict, 是否有变化)。
    """
    new_data = copy.deepcopy(marketplace)
    entry = next((p for p in new_data.get("plugins", [])
                  if isinstance(p, dict) and p.get("name") == name), None)
    if entry is None:
        raise ValueError(f"marketplace.json 中没有条目 {name}")
    meta = entry.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        entry["metadata"] = meta
    old_sha = meta.get("pinnedSha")
    old_date = meta.get("pinnedAt")
    if new_ref is not None:
        meta["pinnedRef"] = new_ref
    meta["pinnedSha"] = new_sha
    meta["pinnedAt"] = new_date
    if isinstance(meta.get("note"), str):
        meta["note"] = _sync_note_text(meta["note"], old_sha, new_sha,
                                       old_date, new_date)
    return new_data, new_data != marketplace


def serialize_marketplace_bytes(original_text, data):
    """按原文件排版序列化 marketplace：2 空格缩进、非 ASCII 原样、
    BOM / 行尾约定（CRLF 或 LF）/ 末尾换行都跟随原文件。返回 bytes。"""
    body = json.dumps(data, ensure_ascii=False, indent=2)
    nl = "\r\n" if "\r\n" in original_text else "\n"
    if original_text.startswith(BOM):
        body = BOM + body
    if original_text.endswith("\n"):
        body += "\n"
    return body.replace("\n", nl).encode("utf-8")


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
    """下载 pin 处 codeload tarball 到 dest_dir，返回本地路径。

    check 的枢纽线与票 03 update 的校验门/实体同步共用一次下载。
    网络失败抛 RuntimeError（消息含 URL 与原因，可读）；测试注入假件。
    """
    url = CODELOAD_TARBALL.format(repo=repo, sha=sha)
    dest = os.path.join(dest_dir, f"{repo.replace('/', '__')}-{sha}.tar.gz")
    return download_to_file(url, dest, timeout=timeout)


def download_to_file(url, dest, timeout=120):
    """把 URL 内容流式落到本地文件；HTTP 错误与网络错误都转成可读 RuntimeError。"""
    req = urllib.request.Request(url, headers={"User-Agent": "plugin-updater"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, \
                open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"tarball 下载失败（HTTP {exc.code}）: {url}") from exc
    except OSError as exc:
        raise RuntimeError(f"tarball 下载失败（网络错误）: {url}——{exc}") from exc
    return dest


def extract_tarball(tar_path, dest_dir):
    """解包 tar.gz 到 dest_dir/tree，返回上游树根（tarball 的单顶层目录）。

    codeload tarball 顶层目录名随请求 ref 变化（sha 全串/短串都有可能），
    不按名字猜：取解包后的唯一顶层目录；没有唯一顶层目录就以解包目录为根。
    """
    tree_dir = os.path.join(dest_dir, "tree")
    os.makedirs(tree_dir, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tf:
        try:
            tf.extractall(tree_dir, filter="data")
        except TypeError:  # Python < 3.12 没有 filter 参数
            tf.extractall(tree_dir)
    entries = sorted(os.listdir(tree_dir))
    if len(entries) == 1 and os.path.isdir(os.path.join(tree_dir, entries[0])):
        return os.path.join(tree_dir, entries[0])
    return tree_dir


def normalize_tree_root(tree_root):
    """把解包树根目录名规范成 plugin.json 的 name，返回（可能改名的）树根。

    codeload tarball 顶层目录是 <repo>-<sha>，而 validator 会校验 plugin.json
    name 与目录名一致——手动重 pin 先例（2026-10-18）用 git clone 出来的目录名
    天然对齐，tarball 解包链需要显式补齐这一步，否则会出假阻断 error。
    plugin.json 缺失/损坏/已对齐时原样返回（让校验门去报真正的 error）。
    """
    pj = os.path.join(tree_root, ".claude-plugin", "plugin.json")
    try:
        with open(pj, "r", encoding="utf-8-sig") as f:
            name = json.load(f).get("name")
    except (OSError, ValueError, AttributeError):
        return tree_root
    if not (isinstance(name, str) and name.strip()):
        return tree_root
    target = os.path.join(os.path.dirname(tree_root), name)
    if os.path.basename(tree_root) == name or os.path.exists(target):
        return tree_root
    try:
        os.rename(tree_root, target)
    except OSError:
        return tree_root
    return target


def derive_family_members(tree_root):
    """从 pin 处上游树动态派生族成员：skills/ 三分类的一级子目录（name -> 分类）。

    deprecated/in-progress 永不装入——它们不在 FAMILY_CATEGORIES 里，
    结构上就进不了族清单；分类下的散文件（README/NOTICE 等）按 isdir 排除。
    上游没有某分类时跳过该分类；整个 skills/ 目录缺失则报错（异常树形）。
    """
    skills_dir = os.path.join(tree_root, "skills")
    if not os.path.isdir(skills_dir):
        raise ValueError(f"上游树缺少 skills/ 目录: {tree_root}")
    family = {}
    for cat in FAMILY_CATEGORIES:
        cat_dir = os.path.join(skills_dir, cat)
        if not os.path.isdir(cat_dir):
            continue
        for name in sorted(os.listdir(cat_dir)):
            if os.path.isdir(os.path.join(cat_dir, name)):
                family[name] = cat
    return family


def _relative_files(root):
    """root 下全部文件的 相对路径 -> 绝对路径 映射（walk 不跟符号链接）。"""
    out = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if os.path.isfile(full):
                out[os.path.relpath(full, root)] = full
    return out


def _read_normalized(path):
    """读文件字节，CRLF 归一为 LF。

    codeload 基线是 LF，而 Windows 安装链（git clone / 解压）落盘常是 CRLF——
    行尾差异是安装链的产物不是内容漂移，比对前拉平；真正的手改/落后仍然可见。
    """
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def compare_tree(dir_a, dir_b):
    """两棵目录树内容一致：文件集合相同且逐文件内容相同（行尾归一后）。"""
    files_a = _relative_files(dir_a)
    files_b = _relative_files(dir_b)
    if set(files_a) != set(files_b):
        return False
    for rel, path_a in files_a.items():
        if _read_normalized(path_a) != _read_normalized(files_b[rel]):
            return False
    return True


def judge_hub_members(family, hub_dir, tree_root):
    """逐族实体比对枢纽内容 vs pin 基线，给三方状态（不做落后/手改区分）。

    枢纽目录整个不存在（新机器）时全部成员判缺失，不报错。
    """
    rows = []
    for name, cat in family.items():
        hub_entity = os.path.join(hub_dir, name)
        base_entity = os.path.join(tree_root, "skills", cat, name)
        if not os.path.exists(hub_entity):
            status = HUB_STATUS_MISSING
        elif (os.path.isdir(hub_entity) and os.path.isdir(base_entity)
                and compare_tree(hub_entity, base_entity)):
            status = HUB_STATUS_SYNCED
        else:
            status = HUB_STATUS_DRIFTED
        rows.append({"name": name, "category": cat, "status": status})
    return rows


def run_validator(tree_path, validator_script, timeout=300):
    """[票 03] 对解包的新版本树调 plugin-validator --standalone 校验门。

    返回合并后的输出文本（stdout+stderr）；是否放行由 judge_validator_output
    按输出内容判定（error 行 + 「结果:」汇总行），退出码只是诊断信息。
    validator 脚本不存在直接报错——门没有证据时绝不放行。
    测试注入假 runner（签名 validator(tree) -> 输出文本）。
    """
    if not os.path.isfile(validator_script):
        raise RuntimeError(f"validator 脚本不存在: {validator_script}")
    proc = subprocess.run(
        [sys.executable, validator_script, tree_path, "--standalone"],
        capture_output=True, timeout=timeout)
    # check_plugin.py 已把 stdout 重配置为 UTF-8；stderr 按容错解码
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    return out + err


def fetch_remote_default_ref(repo, timeout=60):
    """上游默认分支名（git ls-remote --symref HEAD，建基线条目写 pinnedRef 用）。"""
    proc = subprocess.run(
        ["git", "ls-remote", "--symref", GITHUB_URL.format(repo=repo), "HEAD"],
        capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-remote --symref 失败: {(proc.stderr or '').strip()}")
    return parse_symref_output(proc.stdout)


def judge_validator_output(output, external_ref=True):
    """校验门判定（纯函数）：解析 validator 输出，决定放行与否。

    - error 行（`ERROR ` 前缀）全部收集；
    - 「缺 .minimax-plugin/plugin.json」对外部引用式条目（github source，本地
      无源码、不分发给 MiniMax）特判 N/A 不阻断——2026-10-18 手动重 pin 先例；
      其余 error 照常阻断；
    - 无「结果:」汇总行 = 输出不可识别（脚本缺失/崩溃），保守按未通过处理。
    返回 {passed, blocking, waived, recognized}。
    """
    text = output or ""
    errors = ERROR_LINE_RE.findall(text)
    waived = [e for e in errors if external_ref and MINIMAX_MISSING_RE.search(e)]
    blocking = [e for e in errors
                if not (external_ref and MINIMAX_MISSING_RE.search(e))]
    recognized = any(line.lstrip().startswith(GATE_SUMMARY_PREFIX)
                     for line in text.splitlines())
    return {"passed": recognized and not blocking,
            "blocking": blocking, "waived": waived, "recognized": recognized}


# ---------------------------------------------------------------- 编排

def run_check(entries, fetch_head=None, fetch_version=None):
    """check 主编排（pin 线）：逐条目取 head/版本号并判定；单条目失败不中断其余条目。

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


def run_hub_check(entries, hub_dir, get_tarball=None, work_root=None):
    """check 枢纽线编排：带 pin 条目逐条下载 tarball 并比对枢纽实体。

    无 pin 条目不进枢纽线（无基线无族）。单条目下载/解包/派生失败记为
    hub-error（可读错误）后继续，不中断其余条目；临时工作目录用完即清。
    get_tarball 默认接真实 fetch_tarball，测试注入假件。
    """
    get_tarball = get_tarball or fetch_tarball
    if work_root:
        os.makedirs(work_root, exist_ok=True)
    results = []
    for e in entries:
        if not e.get("pinned_sha"):
            continue
        work = tempfile.mkdtemp(prefix="plugin-updater-hub-", dir=work_root)
        r = {"name": e["name"], "repo": e["repo"], "pinned_sha": e["pinned_sha"],
             "status": HUB_STATUS_OK, "members": [], "error": None}
        results.append(r)
        try:
            tar_path = get_tarball(e["repo"], e["pinned_sha"], work)
            tree = extract_tarball(tar_path, work)
            family = derive_family_members(tree)
            r["members"] = judge_hub_members(family, hub_dir, tree)
        except Exception as exc:  # 下载/解包/派生异常：记录后继续下一条目
            r["status"] = HUB_STATUS_ERROR
            r["error"] = str(exc)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return results


# ---------------------------------------------------------------- update 编排（票 03）
# 两阶段、全或无：先对全部目标条目做计划（下载 + 校验门，不写任何仓库文件），
# 任一条目失败就整链不进写盘阶段——失败的更新不留半成品。

def plan_updates(entries, fetch_head=None, fetch_version=None,
                 fetch_default_ref=None, get_tarball=None, validator=None,
                 validator_script=None, work_root=None, today=None):
    """update 阶段一（不写盘）：逐条目取 head -> 判动作 -> 下载新版 tarball ->
    校验门，产出计划或失败。单条目失败（head/默认分支/tarball/校验门）不中断
    其余条目的计划；是否全链写入由调用方按「有无失败」决定。

    plan 形态: {action: bump|baseline|skip, name, repo, ref, old_sha, new_sha,
    new_ref(仅建基线), date, version, waived}
    failure 形态: {name, repo, stage, error, detail(gate 时为阻断 error 清单)}
    所有外部访问走注入接缝（默认接真实 effect 函数）。
    """
    fetch_head = fetch_head or fetch_remote_head
    fetch_version = fetch_version or fetch_upstream_version
    fetch_default_ref = fetch_default_ref or fetch_remote_default_ref
    get_tarball = get_tarball or fetch_tarball
    if validator is None:
        if not validator_script:
            raise ValueError("plan_updates 需要 validator 或 validator_script")
        validator = lambda tree: run_validator(tree, validator_script)  # noqa: E731
    today = today or datetime.date.today().isoformat()

    plans, failures = [], []
    for e in entries:
        ref = e.get("pinned_ref") or DEFAULT_REF
        try:
            head = fetch_head(e["repo"], ref)
        except Exception as exc:
            failures.append({"name": e["name"], "repo": e["repo"],
                             "stage": STAGE_HEAD, "error": str(exc),
                             "detail": []})
            continue
        if e.get("pinned_sha") and e["pinned_sha"].lower() == (head or "").lower():
            plans.append({"action": ACTION_SKIP, "name": e["name"],
                          "repo": e["repo"], "ref": ref,
                          "old_sha": e["pinned_sha"], "new_sha": head,
                          "new_ref": None, "date": None, "version": None,
                          "waived": []})
            continue
        action = ACTION_BASELINE if not e.get("pinned_sha") else ACTION_BUMP
        new_ref = None
        if action == ACTION_BASELINE:
            try:
                new_ref = fetch_default_ref(e["repo"])
            except Exception as exc:
                failures.append({"name": e["name"], "repo": e["repo"],
                                 "stage": STAGE_SYMREF, "error": str(exc),
                                 "detail": []})
                continue
        work = tempfile.mkdtemp(prefix="plugin-updater-update-", dir=work_root)
        try:
            tar_path = get_tarball(e["repo"], head, work)
            tree = extract_tarball(tar_path, work)
            tree = normalize_tree_root(tree)
        except Exception as exc:
            failures.append({"name": e["name"], "repo": e["repo"],
                             "stage": STAGE_TARBALL, "error": str(exc),
                             "detail": []})
            shutil.rmtree(work, ignore_errors=True)
            continue
        try:
            output = validator(tree)
        except Exception as exc:
            failures.append({"name": e["name"], "repo": e["repo"],
                             "stage": STAGE_GATE,
                             "error": f"validator 调用失败: {exc}",
                             "detail": []})
            shutil.rmtree(work, ignore_errors=True)
            continue
        verdict = judge_validator_output(output, external_ref=True)
        if not verdict["passed"]:
            if verdict["blocking"]:
                error = f"{len(verdict['blocking'])} error"
                detail = verdict["blocking"]
            else:
                error = "validator 输出不可识别（无「结果:」汇总行）"
                detail = []
            if verdict["waived"]:
                error += (f"；已豁免 {len(verdict['waived'])} 项"
                          f"「缺 .minimax-plugin」（外部引用式条目 N/A）")
            failures.append({"name": e["name"], "repo": e["repo"],
                             "stage": STAGE_GATE, "error": error,
                             "detail": detail})
            shutil.rmtree(work, ignore_errors=True)
            continue
        plans.append({"action": action, "name": e["name"], "repo": e["repo"],
                      "ref": ref, "old_sha": e.get("pinned_sha"),
                      "new_sha": head, "new_ref": new_ref, "date": today,
                      "version": fetch_version(e["repo"], head),
                      "waived": verdict["waived"]})
        shutil.rmtree(work, ignore_errors=True)
    return plans, failures


def apply_updates(root, plans, dry_run=False, marketplace_path=None,
                  compat_path=None):
    """update 阶段二：把通过校验门的计划写进仓库（--dry-run 只算不写）。

    marketplace.json（pin bump / 建基线）与 compat 文档（pin 列）先全部算好、
    与原字节比对有变化才写盘——重复 apply 是字节级零改动（幂等兜底，正常路径
    的幂等在 plan_updates 的 skip 判定）。compat 表里没有该条目行时跳过该条目
    的表格同步并记入 skipped（建基线条目可能还没进过表格，不算失败）。
    返回 {marketplace: {changed, written}, compat: {changed, written, skipped}}。
    """
    mp_path = marketplace_path or os.path.join(root, ".claude-plugin",
                                               "marketplace.json")
    compat_path = compat_path or os.path.join(root, COMPAT_REL)
    result = {"marketplace": {"changed": False, "written": False},
              "compat": {"changed": False, "written": False, "skipped": []}}
    to_apply = [p for p in plans if p["action"] in (ACTION_BUMP, ACTION_BASELINE)]
    if not to_apply:
        return result

    with open(mp_path, "rb") as f:
        mp_bytes = f.read()
    mp_text = mp_bytes.decode("utf-8")
    data = json.loads(mp_text.lstrip(BOM))
    compat_bytes = open(compat_path, "rb").read()
    compat_text = compat_bytes.decode("utf-8")

    changed_mp = False
    for p in to_apply:
        data, ch = apply_pin_bump(data, p["name"], p["new_sha"], p["date"],
                                  new_ref=p["new_ref"])
        changed_mp = changed_mp or ch
    new_mp_bytes = serialize_marketplace_bytes(mp_text, data)
    result["marketplace"]["changed"] = new_mp_bytes != mp_bytes

    new_compat_text = compat_text
    for p in to_apply:
        cell_ref = p.get("new_ref") or p.get("ref") or DEFAULT_REF
        cell = render_pin_cell(cell_ref, p["new_sha"], p["date"], p.get("version"))
        new_compat_text, ch = sync_compat_table(new_compat_text, p["name"], cell)
        if not ch:
            result["compat"]["skipped"].append(p["name"])
    result["compat"]["changed"] = new_compat_text != compat_text

    if dry_run:
        return result
    if result["marketplace"]["changed"]:
        with open(mp_path, "wb") as f:
            f.write(new_mp_bytes)
        result["marketplace"]["written"] = True
    if result["compat"]["changed"]:
        with open(compat_path, "wb") as f:
            f.write(new_compat_text.encode("utf-8"))
        result["compat"]["written"] = True
    return result


# ---------------------------------------------------------------- 副本线纯决策层

def load_json_or_none(path):
    """读 JSON 文件；缺文件/坏 JSON 返回 None（调用方按未安装处理，不崩）。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _norm_path(path):
    """路径归一化比较（Windows 大小写/斜杠差异、相对路径、软链接都拉平）。"""
    return os.path.normcase(os.path.realpath(path)) if path else None


def zcode_own_market_ids(known_data, market_root):
    """ZCode known_marketplaces（列表格式）里指向本仓库市场的市场 id 集合。"""
    ids = set()
    if not isinstance(known_data, dict):
        return ids
    for m in known_data.get("marketplaces") or []:
        if not isinstance(m, dict):
            continue
        src = m.get("source") or {}
        if (src.get("source") == "directory"
                and _norm_path(src.get("path")) == _norm_path(market_root)):
            ids.add(m.get("id"))
    return ids


def claude_own_market_ids(known_data, market_root):
    """Claude Code known_marketplaces（字典格式）里指向本仓库市场的市场名集合。"""
    ids = set()
    if not isinstance(known_data, dict):
        return ids
    for name, m in known_data.items():
        if not isinstance(m, dict):
            continue
        src = m.get("source") or {}
        if (_norm_path(src.get("path")) == _norm_path(market_root)
                or _norm_path(m.get("installLocation")) == _norm_path(market_root)):
            ids.add(name)
    return ids


def zcode_installed_records(installed_data, plugin_name):
    """从 ZCode 安装记录（plugins 为列表）取指定插件的安装条目。"""
    recs = []
    if not isinstance(installed_data, dict):
        return recs
    for p in installed_data.get("plugins") or []:
        if isinstance(p, dict) and p.get("name") == plugin_name:
            src = p.get("source") or {}
            recs.append({
                "id": p.get("id") or f"{p.get('name')}@{p.get('marketplace')}",
                "marketplace": p.get("marketplace"),
                "version": p.get("version"),
                "sha": src.get("sha") or src.get("sha256"),
            })
    return recs


def claude_installed_records(installed_data, plugin_name):
    """从 Claude Code 安装记录（plugins 为 name@market -> 记录列表）取安装条目。"""
    recs = []
    if not isinstance(installed_data, dict):
        return recs
    plugins = installed_data.get("plugins")
    if not isinstance(plugins, dict):
        return recs
    for key, lst in plugins.items():
        name, _sep, market = key.partition("@")
        if name != plugin_name:
            continue
        first = (lst[0] if isinstance(lst, list) and lst
                 and isinstance(lst[0], dict) else {})
        recs.append({
            "id": key,
            "marketplace": market or None,
            "version": first.get("version"),
            "sha": first.get("gitCommitSha"),
        })
    return recs


def copy_refresh_commands(agent, rec):
    """某 agent 刷一条外部副本要敲的命令（只打印不代跑）。"""
    if agent == AGENT_ZCODE:
        return [f"zcode plugins marketplace update {rec['marketplace']}",
                f"zcode plugins plugin update {rec['id']}"]
    if agent == AGENT_CLAUDE_CODE:
        return [f"claude plugin update {rec['id']}"]
    return []


def collect_copy_line(entry_names, market_root,
                      zcode_installed_path=None, zcode_known_path=None,
                      claude_installed_path=None, claude_known_path=None):
    """副本线判定：外部条目 × agent（ZCode / Claude Code / MiniMax）报副本现状。

    来源市场无法确认属于本仓库市场时按其他市场报告（保守，宁报不漏）；
    known_marketplaces 缺失时同样无法识别本仓库市场，沿用该保守口径。
    MiniMax 没有插件安装记录，恒报未安装并附说明。
    路径缺省指向真实 home；测试传 tmp 路径（不存在的路径按未安装处理）。
    """
    zc_inst = load_json_or_none(zcode_installed_path)
    zc_known = load_json_or_none(zcode_known_path)
    cc_inst = load_json_or_none(claude_installed_path)
    cc_known = load_json_or_none(claude_known_path)
    zc_own = zcode_own_market_ids(zc_known, market_root)
    cc_own = claude_own_market_ids(cc_known, market_root)
    rows = []
    for name in entry_names:
        for agent, recs, own in (
                (AGENT_ZCODE, zcode_installed_records(zc_inst, name), zc_own),
                (AGENT_CLAUDE_CODE, claude_installed_records(cc_inst, name), cc_own),
                (AGENT_MINIMAX, [], set())):
            foreign = [r for r in recs if r.get("marketplace") not in own]
            if not recs:
                status, keep = COPY_STATUS_NOT_INSTALLED, []
            elif foreign:
                status, keep = COPY_STATUS_FOREIGN, foreign
            else:
                status, keep = COPY_STATUS_OWN, recs
            rows.append({
                "plugin": name,
                "agent": agent,
                "agent_label": AGENT_LABEL[agent],
                "status": status,
                "records": keep,
                "commands": [c for r in keep
                             for c in copy_refresh_commands(agent, r)],
                "note": MINIMAX_NOTE if agent == AGENT_MINIMAX else None,
            })
    return rows


# ---------------------------------------------------------------- 报告

def build_hub_report(hub_results, hub_dir=None, skipped=None):
    """枢纽线报告：逐成员中文状态 + 小结计数；跳过的无 pin 条目与失败条目注明。"""
    header = "== 枢纽同步线（基线 = pin 处 tarball）"
    if hub_dir:
        header += f"——枢纽: {hub_dir}"
    lines = ["", header]
    if skipped:
        lines.append(f"（跳过无 pin 条目: {', '.join(skipped)}——无基线无族）")
    for r in hub_results:
        lines.append("")
        pin_short = (r.get("pinned_sha") or "?")[:12]
        if r["status"] == HUB_STATUS_ERROR:
            lines.append(f"[{r['name']} @ pin {pin_short}]")
            lines.append(f"    结论 : 枢纽线查询失败——{r.get('error', '未知错误')}")
            continue
        lines.append(f"[{r['name']} @ pin {pin_short}] "
                     f"族成员 {len(r['members'])} 个（{'/'.join(FAMILY_CATEGORIES)}）:")
        for m in r["members"]:
            lines.append(f"    [{HUB_LABEL[m['status']]}] {m['name']}（{m['category']}）")
        counts = {s: 0 for s in HUB_LABEL}
        for m in r["members"]:
            counts[m["status"]] += 1
        lines.append("    小结 : " + " / ".join(
            f"{counts[s]} {HUB_LABEL[s]}"
            for s in (HUB_STATUS_SYNCED, HUB_STATUS_DRIFTED, HUB_STATUS_MISSING)))
    return lines


def build_copy_report(copy_rows):
    """副本线报告：外部市场副本报版本/来源/sha + 刷新命令；未安装/本市场来源注明。"""
    lines = ["", "== 其他市场插件副本（只报告，不代跑刷新命令）"]
    for r in copy_rows:
        lines.append("")
        head = f"[{r['agent_label']}] {r['plugin']}"
        if r["status"] == COPY_STATUS_NOT_INSTALLED:
            line = f"{head} : 未安装"
            if r.get("note"):
                line += f"（{r['note']}）"
            lines.append(line)
            continue
        lines.append(head)
        for rec in r["records"]:
            version = rec.get("version") or "版本未知"
            market = rec.get("marketplace") or "市场未知"
            if r["status"] == COPY_STATUS_OWN:
                lines.append(f"    已装 : {version}"
                             f"（来源市场: {market}，本仓库市场，无需处理）")
            else:
                sha = f" @ {rec['sha']}" if rec.get("sha") else ""
                lines.append(f"    已装 : {version}{sha}（来源市场: {market}）")
        if r["commands"]:
            lines.append("    刷新命令（人工执行）:")
            for c in r["commands"]:
                lines.append(f"      {c}")
    return lines


def build_update_report(plans, failures, apply_result=None, dry_run=False,
                        market_root=None):
    """update 报告：逐条目计划（含校验门豁免）、失败明细、写入结果。

    failures 非空时明确「全链中止、零写入」；apply_result 为 None 表示没进
    写盘阶段；dry_run 把写入段标成「将写入（dry-run，未写入）」。
    """
    header = "== update（市场根: " + (market_root or "?") + "）"
    if dry_run:
        header += "——dry-run，只看不做"
    lines = [header]
    counts = {ACTION_BUMP: 0, ACTION_BASELINE: 0, ACTION_SKIP: 0}
    for i, p in enumerate(plans, 1):
        counts[p["action"]] += 1
        lines.append("")
        if p["action"] == ACTION_SKIP:
            lines.append(f"[{i}/{len(plans)}] {p['name']} : 已最新，跳过")
            continue
        new_cell = render_pin_cell(p.get("new_ref") or p["ref"], p["new_sha"],
                                   p["date"], p.get("version"))
        if p["action"] == ACTION_BASELINE:
            lines.append(f"[{i}/{len(plans)}] {p['name']} : 建基线 {new_cell}")
        else:
            lines.append(f"[{i}/{len(plans)}] {p['name']} : bump pin "
                         f"{(p['old_sha'] or '?')[:7]} -> {new_cell}")
        if p.get("waived"):
            lines.append(f"    校验门: 通过（豁免 {len(p['waived'])} 项"
                         f"「缺 .minimax-plugin」——外部引用式条目 N/A）")
    if failures:
        lines.append("")
        lines.append("== 失败——全链中止、零写入（要更新先解决下列问题）")
        for f in failures:
            stage_label = {STAGE_HEAD: "head 查询失败", STAGE_SYMREF: "默认分支解析失败",
                           STAGE_TARBALL: "tarball 下载/解包失败",
                           STAGE_GATE: "校验门未通过"}[f["stage"]]
            lines.append(f"[{f['name']}] {stage_label}——{f['error']}")
            for e in f.get("detail") or []:
                lines.append(f"    ERROR   {e}")
    if apply_result is not None:
        lines.append("")
        if dry_run:
            lines.append("== 将写入（dry-run，未写入）")
        else:
            lines.append("== 写入")
        mp = apply_result["marketplace"]
        compat = apply_result["compat"]
        if mp["changed"]:
            n = sum(1 for p in plans if p["action"] in (ACTION_BUMP, ACTION_BASELINE))
            lines.append(f"  marketplace.json: {'已写入' if mp['written'] else '有变更未写入'}"
                         f"（{n} 条 pin 更新/建基线）")
        else:
            lines.append("  marketplace.json: 无变更")
        if compat["changed"]:
            lines.append(f"  docs/plugin-compatibility.md: "
                         f"{'已写入' if compat['written'] else '有变更未写入'}"
                         f"（pin 列已同步）")
        else:
            lines.append("  docs/plugin-compatibility.md: 无变更")
        if compat["skipped"]:
            lines.append(f"  （compat 表无行，跳过表格同步: {', '.join(compat['skipped'])}）")
    lines.append("")
    lines.append("汇总: " + " / ".join(
        f"{counts[a]} {label}" for a, label in
        ((ACTION_BUMP, "更新"), (ACTION_BASELINE, "建基线"), (ACTION_SKIP, "已最新")))
        + f" / 失败 {len(failures)}")
    return lines


# ---------------------------------------------------------------- 入口

def cmd_check(root=None, hub_dir=None):
    """check 入口：pin 线 + 枢纽线 + 副本线三段报告，退出码只看前两条线。"""
    base = repo_root(root)
    entries = parse_external_entries(load_marketplace(base))
    pin_results = run_check(entries)
    hub_dir = hub_dir or DEFAULT_HUB_DIR
    hub_results = run_hub_check(entries, hub_dir)
    copy_rows = collect_copy_line(
        [e["name"] for e in entries], base,
        zcode_installed_path=ZCODE_INSTALLED_JSON,
        zcode_known_path=ZCODE_KNOWN_JSON,
        claude_installed_path=CLAUDE_INSTALLED_JSON,
        claude_known_path=CLAUDE_KNOWN_JSON)
    skipped = [e["name"] for e in entries if not e.get("pinned_sha")]
    print("\n".join(build_report(pin_results, market_root=base)))
    print("\n".join(build_hub_report(hub_results, hub_dir=hub_dir,
                                     skipped=skipped)))
    print("\n".join(build_copy_report(copy_rows)))
    return decide_exit_code(pin_results, hub_results)


def cmd_update(root=None, entry=None, yes=False, dry_run=False, interactive=None,
               fetch_head=None, fetch_version=None, fetch_default_ref=None,
               get_tarball=None, validator=None, today=None):
    """update 入口：守卫 -> 计划（下载+校验门，零写入）-> 全或无写盘。

    非交互环境（stdin 非 tty）缺 --yes 时拒绝执行任何变更（--dry-run 不写文件
    所以豁免）——守卫在任何外部访问之前触发。任一条目失败（head/tarball/校验门）
    则全链不写盘。外部访问接缝可注入（测试用）。
    """
    base = repo_root(root)
    entries = parse_external_entries(load_marketplace(base))
    if entry:
        entries = [e for e in entries if e["name"] == entry]
        if not entries:
            print(f"错误：市场里没有名为 {entry} 的外部聚合条目"
                  f"（--entry 只接受 github 引用式条目名）")
            return 2
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not dry_run and not yes and not interactive:
        print("错误：非交互环境缺 --yes，拒绝执行任何变更；"
              "先用 --dry-run 预览将做的变更，确认后加 --yes 重跑")
        return 2
    validator_script = os.path.join(base, VALIDATOR_REL)
    plans, failures = plan_updates(
        entries, fetch_head=fetch_head, fetch_version=fetch_version,
        fetch_default_ref=fetch_default_ref, get_tarball=get_tarball,
        validator=validator, validator_script=validator_script, today=today)
    apply_result = None
    exit_code = 0
    if failures:
        exit_code = 1  # 全链中止：apply_updates 根本不进，仓库文件零改动
    else:
        try:
            apply_result = apply_updates(base, plans, dry_run=dry_run)
        except (OSError, ValueError) as exc:
            print(f"错误：写盘阶段失败（此前的写入已尽力而为，请检查仓库状态）: {exc}")
            return 1
    print("\n".join(build_update_report(plans, failures, apply_result,
                                        dry_run=dry_run, market_root=base)))
    return exit_code


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="plugin_updater.py",
        description="外部聚合插件的更新检查（check）与升级（update）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="检查外部聚合条目：pin 线 + 枢纽同步线 + "
                                      "其他市场副本线")
    ck.add_argument("--root", help="market 仓库根（默认从脚本位置向上推导，"
                                   "或环境变量 MARKET_REPO）")
    ck.add_argument("--hub", help="枢纽 skills 目录（默认 ~/.agents/skills）")
    up = sub.add_parser("update", help="有新版条目走完仓库写半链：下载新版 tarball -> "
                                       "plugin-validator 校验门 -> bump pin -> "
                                       "同步 compat 表格（枢纽实体同步是后续票）")
    up.add_argument("--root", help="market 仓库根（默认从脚本位置向上推导，"
                                   "或环境变量 MARKET_REPO）")
    up.add_argument("--entry", help="只处理指定条目（外部聚合条目名）")
    up.add_argument("--yes", action="store_true",
                    help="确认执行变更；非交互环境（非 tty）缺它拒绝一切变更")
    up.add_argument("--dry-run", action="store_true",
                    help="只打印将做的变更，不写任何文件（无需 --yes）")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args.root, hub_dir=args.hub)
    if args.cmd == "update":
        return cmd_update(args.root, entry=args.entry, yes=args.yes,
                          dry_run=args.dry_run)
    return 2


if __name__ == "__main__":
    sys.exit(main())
