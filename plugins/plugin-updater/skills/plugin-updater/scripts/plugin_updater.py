#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plugin_updater.py — 外部聚合插件的更新检查（check）与升级（update，后续票交付）。

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

选项:
    --root    market 仓库根（默认从脚本位置向上推导，或环境变量 MARKET_REPO；
              对齐 skill-distributor 的惯例）
    --hub     枢纽 skills 目录（默认 ~/.agents/skills）

退出码: 0=全部最新且枢纽同步  1=有更新/无基线/查询失败/枢纽有差异  2=用法/输入错误
       （副本线只报告不影响退出码——外部市场副本是常驻消费线，不是可消除的漂移）

设计约束（票 03 的 update 会复用）:
    外部访问收敛为可注入 effect 函数（fetch_remote_head / fetch_upstream_version /
    fetch_tarball / run_validator），与纯决策逻辑（parse_external_entries /
    parse_ls_remote_output / parse_upstream_plugin_json / judge_entry /
    derive_family_members / judge_hub_members / collect_copy_line /
    build_report / build_hub_report / build_copy_report / decide_exit_code）分离；
    回归测试只走内存与 tmp 接缝，网络不进测试。
    update 子链（validator 校验门、pin bump、枢纽三方同步）仍留接缝未实现。
"""

import argparse
import json
import os
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


def run_validator(tree_path):
    """[票 03 接缝] 对解包的新版本树调 plugin-validator --standalone 校验门。

    返回 (ok, 输出文本)；非 0 error 才放行写入。本票未实现；测试注入假件。
    """
    raise NotImplementedError("update 子链（票 03）交付时实现")


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


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="plugin_updater.py",
        description="外部聚合插件的更新检查与升级（update 后续票交付）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="检查外部聚合条目：pin 线 + 枢纽同步线 + "
                                      "其他市场副本线")
    ck.add_argument("--root", help="market 仓库根（默认从脚本位置向上推导，"
                                   "或环境变量 MARKET_REPO）")
    ck.add_argument("--hub", help="枢纽 skills 目录（默认 ~/.agents/skills）")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args.root, hub_dir=args.hub)
    return 2


if __name__ == "__main__":
    sys.exit(main())
