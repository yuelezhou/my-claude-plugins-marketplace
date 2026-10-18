#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_plugin_updater.py — plugin_updater.py 的回归自测（pin 线 + 枢纽同步线 + 副本线）。

覆盖（票 01 pin 线）：外部条目解析（github 引用式过滤、pin 字段提取、无 metadata 兜底）、
git ls-remote 输出解析（`main` 模式同时命中 changeset-release/main 时取精确行）、
pin 比对（已最新 / 有更新 / 无基线，SHA 大小写不敏感）、
上游版本号解析（合法 JSON / 坏 JSON / 缺字段 / 非对象）、
run_check 注入编排（假 head / 假版本号 / 单条目远端失败不中断其余条目）、
报告生成（中文措辞、版本号未知、无基线附 head、汇总行）、
退出码（全部最新 0 / 有更新或无基线或查询失败 1）。

覆盖（票 02 枢纽线 + 副本线）：
族派生（三分类一级子目录、deprecated/in-progress 与散文件排除、缺 skills/ 报错）、
枢纽三方状态（已同步 / 与基线不一致（落后或手改）/ 缺失，tmp 枢纽 + tmp 假 tarball）、
run_hub_check 编排（无 pin 条目跳过、tarball 下载失败进 hub-error 不崩）、
download_to_file 的 file:// 离线路径、
副本线（ZCode 列表格式 / Claude Code 字典格式安装记录解析、本仓库市场识别、
外部副本判定与刷新命令、缺安装文件按未安装处理）、
枢纽线报告与副本线报告措辞、退出码纳入枢纽漂移。

接缝全在内存 / tmp：远端 head、版本号、tarball 都是注入的假函数或 tmp 夹具，
不碰网络（真实网络路径靠真跑一次 check 覆盖，见票 01/02 验收）。

覆盖（票 03 update 仓库写半链）：
校验门判定（0 error 放行、「缺 .minimax-plugin」对外部引用式条目特判 N/A、
其余 error 阻断、无「结果:」行的不可识别输出保守拦截）、
git ls-remote --symref 输出解析（默认分支）、
marketplace pin bump（pinnedSha/pinnedAt 双字段、note 仅同步内嵌旧 SHA/日期的文字、
原 dict 不被修改、已同步值重跑零改动、无 pin 条目建基线写齐三字段且键序固定）、
compat 表格 pin 列同步（精准行替换、其余行列不动、已同步零改动、无该行跳过）、
plan_updates 编排（bump/建基线/跳过三分、单条目校验失败不中断其余条目、
head 查询失败进失败通道、无 pin 条目才查默认分支、下载用新 head SHA、
校验门前树根目录名规范成 plugin.json 的 name——codeload 顶层 <repo>-<sha>
会让 validator 的 name/目录名检查出假阻断）、
apply_updates（tmp 假仓库双文件产物正确且保持 CRLF/缩进、dry-run 零写入、
重复 apply 字节级零改动）、cmd_update（非交互无 --yes 拒绝、校验门失败全链中止
零写入、--entry 单条目、--dry-run、成功后重跑已最新零改动）。

用法:
    python test_plugin_updater.py

退出码:
    0  全部通过
    1  有用例失败
"""

import json
import os
import pathlib
import shutil
import sys
import tarfile
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plugin_updater import (
    apply_pin_bump,
    apply_updates,
    build_copy_report,
    build_hub_report,
    build_report,
    build_update_report,
    cmd_update,
    collect_copy_line,
    decide_exit_code,
    derive_family_members,
    download_to_file,
    judge_entry,
    judge_hub_members,
    judge_validator_output,
    normalize_tree_root,
    parse_external_entries,
    parse_ls_remote_output,
    parse_symref_output,
    parse_upstream_plugin_json,
    plan_updates,
    render_pin_cell,
    run_check,
    run_hub_check,
    sync_compat_table,
)


def make_marketplace():
    """迷你市场：本地路径条目 / github+pin / github 无 metadata 三种形态各一。"""
    return {
        "plugins": [
            {"name": "local-plugin", "description": "本地条目",
             "source": "./plugins/local-plugin"},
            {"name": "mattpocock-skills", "description": "外部聚合带 pin",
             "source": {"source": "github", "repo": "mattpocock/skills"},
             "metadata": {"pinnedRef": "main", "pinnedSha": "49dd158d1076"}},
            {"name": "obsidian-skills", "description": "外部无 pin",
             "source": {"source": "github", "repo": "kepano/obsidian-skills"}},
        ]
    }


def make_results():
    """用与真实市场同构的两条目走一遍注入的 run_check，供报告/退出码用例复用。"""
    entries = parse_external_entries(make_marketplace())
    heads = {("mattpocock/skills", "main"): "49dd158d1076",
             ("kepano/obsidian-skills", "HEAD"): "abc999ff00"}
    versions = {("mattpocock/skills", "49dd158d1076"): "1.3.1",
                ("kepano/obsidian-skills", "abc999ff00"): None}
    return run_check(entries,
                     fetch_head=lambda repo, ref: heads[(repo, ref)],
                     fetch_version=lambda repo, sha: versions[(repo, sha)])


# ---------------------------------------------------------------- 条目解析

def test_parse_external_entries():
    """只取 source.source==github 的条目；pin 字段进 dict，无 metadata 兜底 None。"""
    entries = parse_external_entries(make_marketplace())
    assert [e["name"] for e in entries] == ["mattpocock-skills", "obsidian-skills"], \
        "本地路径条目应被过滤，github 条目按市场顺序保留"
    assert entries[0]["repo"] == "mattpocock/skills"
    assert entries[0]["pinned_ref"] == "main"
    assert entries[0]["pinned_sha"] == "49dd158d1076"
    assert entries[1]["repo"] == "kepano/obsidian-skills"
    assert entries[1]["pinned_ref"] is None and entries[1]["pinned_sha"] is None, \
        "无 metadata 的 github 条目应兜底为无 pin"


def test_parse_ls_remote_exact_ref():
    """`main` 模式会同时命中 refs/heads/changeset-release/main——必须取精确 ref 行。"""
    out = ("f7f05086e564eff660e11273608469644c86c1c1\trefs/heads/changeset-release/main\n"
           "49dd158d1076134a641b33efb035946536778336\trefs/heads/main\n")
    assert parse_ls_remote_output(
        out, "main") == "49dd158d1076134a641b33efb035946536778336", \
        "changeset-release/main 在前也不能误当 head"
    assert parse_ls_remote_output("abc111\tHEAD\n", "HEAD") == "abc111"
    assert parse_ls_remote_output("abc222\trefs/tags/v1.2.3\n", "v1.2.3") == "abc222"
    try:
        parse_ls_remote_output(out, "no-such-ref")
        raise AssertionError("无匹配 ref 的输出应报错而不是静默返回")
    except ValueError:
        pass


# ---------------------------------------------------------------- pin 比对

def test_judge_up_to_date_and_update():
    """pin==head（大小写不敏感）-> 已最新；不等 -> 有更新，head/版本号随行。"""
    r = judge_entry({"name": "m", "repo": "a/b", "pinned_ref": "main",
                     "pinned_sha": "49DD158D"}, "49dd158d", "1.3.1")
    assert r["status"] == "up-to-date", "SHA 比对应大小写不敏感"
    assert r["head"] == "49dd158d" and r["upstream_version"] == "1.3.1"

    r = judge_entry({"name": "m", "repo": "a/b", "pinned_ref": "main",
                     "pinned_sha": "000000"}, "49dd158d", "1.3.1")
    assert r["status"] == "update-available"


def test_judge_no_baseline():
    """无 pin 条目 -> 无基线，但仍带当前 head 供人工确认。"""
    r = judge_entry({"name": "o", "repo": "c/d", "pinned_ref": None,
                     "pinned_sha": None}, "abc999", "0.2.1")
    assert r["status"] == "no-baseline"
    assert r["head"] == "abc999" and r["upstream_version"] == "0.2.1", \
        "无基线报告要附上游当前 head"


# ---------------------------------------------------------------- 版本号解析

def test_parse_upstream_plugin_json():
    """合法 JSON 取 version；坏 JSON / 缺字段 / 非对象都返回 None（版本号未知）。"""
    assert parse_upstream_plugin_json(
        b'{"name": "skills", "version": "1.3.1"}') == "1.3.1"
    assert parse_upstream_plugin_json(b'<html>502</html>') is None
    assert parse_upstream_plugin_json(b'{"name": "skills"}') is None
    assert parse_upstream_plugin_json(b'["not", "an", "object"]') is None
    assert parse_upstream_plugin_json('{"version": "中文1.0"}'.encode("utf-8")) == "中文1.0"


# ---------------------------------------------------------------- 编排（注入接缝）

def test_run_check_wires_injected_seams():
    """假 head/假版本号注入后，pin 线判定按条目独立成立。"""
    results = make_results()
    by_name = {r["name"]: r for r in results}
    assert by_name["mattpocock-skills"]["status"] == "up-to-date"
    assert by_name["mattpocock-skills"]["upstream_version"] == "1.3.1"
    assert by_name["obsidian-skills"]["status"] == "no-baseline"
    assert by_name["obsidian-skills"]["head"] == "abc999ff00"
    assert by_name["obsidian-skills"]["upstream_version"] is None, \
        "拉不到版本号不致命，只是未知"


def test_run_check_fetch_failure_isolated():
    """单条目远端查询失败 -> 该条目 status=error，其余条目照常判定。"""
    entries = parse_external_entries(make_marketplace())

    def boom(repo, ref):
        if repo.startswith("mattpocock"):
            raise RuntimeError("网络断了")
        return "abc999ff00"

    results = run_check(entries, fetch_head=boom, fetch_version=lambda repo, sha: None)
    by_name = {r["name"]: r for r in results}
    assert by_name["mattpocock-skills"]["status"] == "error"
    assert "网络断了" in by_name["mattpocock-skills"]["error"]
    assert by_name["obsidian-skills"]["status"] == "no-baseline", \
        "一条查不到不应中断其余条目的检查"


# ---------------------------------------------------------------- 报告与退出码

def mk_result(status):
    return {"name": "x", "repo": "a/b", "pinned_ref": "main",
            "pinned_sha": "s", "head": "h", "upstream_version": None,
            "status": status}


def test_build_report():
    """报告逐条目中文措辞：已最新 / 无基线附 head / 版本号未知 / 汇总计数。"""
    lines = build_report(make_results())
    text = "\n".join(lines)
    assert "已最新" in text and "mattpocock-skills" in text
    assert "1.3.1" in text, "有版本号时应展示上游版本"
    assert "无基线" in text and "abc999ff00" in text, "无基线结论要附当前 head"
    assert "版本号未知" in text, "拉不到版本号要明说未知"
    assert "汇总" in text and "1" in text and "1" in text, "汇总行给各结论计数"


def test_build_report_error_entry():
    """查询失败的条目在报告里有失败说明而不是被吞掉。"""
    entries = parse_external_entries(make_marketplace())

    def boom(repo, ref):
        raise RuntimeError("远端不可达")

    lines = build_report(run_check(entries, fetch_head=boom,
                                   fetch_version=lambda repo, sha: None))
    text = "\n".join(lines)
    assert "远端不可达" in text, "失败原因要进报告"
    assert "查询失败" in text


def test_decide_exit_code():
    """全部最新 -> 0；有更新 / 无基线 / 查询失败 -> 1。"""
    assert decide_exit_code([mk_result("up-to-date"),
                             mk_result("up-to-date")]) == 0
    assert decide_exit_code([mk_result("up-to-date"),
                             mk_result("update-available")]) == 1
    assert decide_exit_code([mk_result("no-baseline")]) == 1
    assert decide_exit_code([mk_result("error")]) == 1


# ---------------------------------------------------------------- 族派生（票 02）

def test_derive_family_members():
    """族成员 = skills/ 下三分类的一级子目录；deprecated/in-progress 与散文件排除。"""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "tree")
        expected = make_upstream_tree(tree)
        fam = derive_family_members(tree)
        assert fam == expected, \
            "族清单应只含 engineering/productivity/misc 的一级子目录（含分类归属），" \
            "deprecated/in-progress 成员与 README/NOTICE 散文件一律排除"


def test_derive_family_members_missing_skills_dir():
    """上游树缺 skills/ 目录 -> ValueError（进 hub-error 通道，不静默当空族）。"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            derive_family_members(tmp)
            raise AssertionError("缺 skills/ 目录应报错而不是返回空族")
        except ValueError:
            pass


# ---------------------------------------------------------------- 枢纽三方状态（票 02）

def test_judge_hub_members_three_states():
    """枢纽实体 vs pin tarball 内容：一致/不一致（手改或多文件）/缺失三分。"""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "tree")
        make_upstream_tree(tree)
        hub = make_hub_from_tree(tmp, tree)
        # code-review：内容被手改 -> 不一致
        with open(os.path.join(hub, "code-review", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改一行\n")
        # wizard：多出一个基线没有的文件 -> 不一致
        write_text(os.path.join(hub, "wizard", "EXTRA.md"), "x\n")
        # grilling：枢纽整个缺 -> 缺失
        shutil.rmtree(os.path.join(hub, "grilling"))
        # tdd：连子目录（references/）原样拷贝 -> 已同步（子树内容也参与比对）

        fam = derive_family_members(tree)
        rows = judge_hub_members(fam, hub, tree)
        by = {r["name"]: r for r in rows}
        assert by["tdd"]["status"] == "hub-in-sync", "整树一致（含子目录）应判已同步"
        assert by["tdd"]["category"] == "engineering"
        assert by["code-review"]["status"] == "hub-drifted", "内容被手改应判不一致"
        assert by["wizard"]["status"] == "hub-drifted", "多出文件也应判不一致"
        assert by["grilling"]["status"] == "hub-missing", "枢纽缺条目应判缺失"

        # 枢纽里同名实体是个文件而不是目录 -> 也算不一致
        write_text(os.path.join(hub, "as-file"), "x")
        rows2 = judge_hub_members({"as-file": "misc"}, hub, tree)
        assert rows2[0]["status"] == "hub-drifted"


def test_judge_hub_members_missing_hub_dir():
    """枢纽目录整个不存在（新机器）-> 全部缺失，不崩。"""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "tree")
        make_upstream_tree(tree)
        fam = derive_family_members(tree)
        rows = judge_hub_members(fam, os.path.join(tmp, "no-such-hub"), tree)
        assert rows and all(r["status"] == "hub-missing" for r in rows)


def test_judge_hub_members_ignores_crlf():
    """行尾差异不算内容漂移：codeload 基线是 LF，Windows 安装链落盘常是 CRLF。"""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "tree")
        make_upstream_tree(tree)
        hub = make_hub_from_tree(tmp, tree)
        # 把 tdd 实体重写为 CRLF 行尾（字节内容因此与基线不同，行内容相同）
        for dirpath, _dirnames, filenames in os.walk(os.path.join(hub, "tdd")):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                with open(p, "rb") as f:
                    data = f.read().replace(b"\r\n", b"\n")
                with open(p, "wb") as f:
                    f.write(data.replace(b"\n", b"\r\n"))
        rows = judge_hub_members(derive_family_members(tree), hub, tree)
        by = {r["name"]: r["status"] for r in rows}
        assert by["tdd"] == "hub-in-sync", "仅行尾不同（CRLF vs LF）应判已同步"
        assert by["code-review"] == "hub-in-sync"


# ---------------------------------------------------------------- 枢纽线编排（票 02）

def test_run_hub_check_skips_no_pin_and_judges():
    """无 pin 条目不进枢纽线；带 pin 条目下载 tarball 解包后逐成员判三方状态。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, tree = make_pin_tarball(tmp)
        hub = make_hub_from_tree(tmp, tree)
        calls = []

        def fake_tar(repo, sha, dest_dir, timeout=120):
            calls.append((repo, sha))
            assert os.path.isdir(dest_dir), "下载目标目录应由编排方建好"
            return tar_path

        results = run_hub_check(make_pinned_entries(), hub,
                                get_tarball=fake_tar,
                                work_root=os.path.join(tmp, "work"))
        assert calls == [("mattpocock/skills", "49dd158d1076")], \
            "只对带 pin 条目下载，且用 pinnedSha 而非 head"
        assert [r["name"] for r in results] == ["mattpocock-skills"], \
            "obsidian-skills 无 pin 无族，不进枢纽线"
        r = results[0]
        assert r["status"] == "hub-ok" and r["pinned_sha"] == "49dd158d1076"
        assert {m["name"]: m["status"] for m in r["members"]} == {
            "tdd": "hub-in-sync", "code-review": "hub-in-sync",
            "grilling": "hub-in-sync", "wizard": "hub-in-sync"}, \
            "从 tarball 动态派生的族实体在枢纽全部一致 -> 全部已同步"


def test_run_hub_check_reports_drift_and_missing():
    """枢纽与基线有差异时逐成员报不一致/缺失，而不是整条失败。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, tree = make_pin_tarball(tmp)
        hub = make_hub_from_tree(tmp, tree, omit=("grilling",))
        with open(os.path.join(hub, "tdd", "SKILL.md"), "a", encoding="utf-8") as f:
            f.write("手改\n")

        results = run_hub_check(make_pinned_entries()[:1], hub,
                                get_tarball=lambda repo, sha, dest_dir, timeout=120: tar_path,
                                work_root=os.path.join(tmp, "work"))
        by = {m["name"]: m["status"] for m in results[0]["members"]}
        assert by == {"tdd": "hub-drifted", "code-review": "hub-in-sync",
                      "wizard": "hub-in-sync", "grilling": "hub-missing"}
        assert results[0]["status"] == "hub-ok", \
            "成员级差异不改变条目状态，由报告与退出码表达"


def test_run_hub_check_download_failure_isolated():
    """tarball 下载失败（网络抖动）-> 该条目 hub-error 带可读错误，不崩不中断。"""
    with tempfile.TemporaryDirectory() as tmp:
        def boom(repo, sha, dest_dir, timeout=120):
            raise RuntimeError(
                f"tarball 下载失败（网络错误）: "
                f"https://codeload.github.com/{repo}/tar.gz/{sha}——连接超时")

        results = run_hub_check(make_pinned_entries(), os.path.join(tmp, "hub"),
                                get_tarball=boom,
                                work_root=os.path.join(tmp, "work"))
        assert len(results) == 1
        r = results[0]
        assert r["status"] == "hub-error"
        assert "HTTP" not in r["error"] and "codeload" in r["error"], "错误信息可读"
        assert r["members"] == []
        assert os.listdir(os.path.join(tmp, "work")) == [], \
            "失败后临时工作目录应被清理，不留半成品"


def test_download_to_file_offline():
    """download_to_file 的离线机制：file:// URL 也能拉到本地同内容文件。"""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src.tar.gz")
        with open(src, "wb") as f:
            f.write(b"tarball-payload-\xe4\xb8\xad")
        dest = os.path.join(tmp, "out.tar.gz")
        download_to_file(pathlib.Path(src).as_uri(), dest, timeout=10)
        with open(dest, "rb") as f:
            assert f.read() == b"tarball-payload-\xe4\xb8\xad"


# ---------------------------------------------------------------- 副本线（票 02）

def test_collect_copy_line_from_tmp_files():
    """tmp 假安装记录：外部市场副本报版本/来源/sha+刷新命令；本市场副本不算；缺装报未安装。"""
    with tempfile.TemporaryDirectory() as tmp:
        root, (zc_inst, zc_known, cc_inst, cc_known) = make_copy_fixtures(tmp)
        rows = collect_copy_line(["mattpocock-skills", "obsidian-skills"], root,
                                 zcode_installed_path=zc_inst,
                                 zcode_known_path=zc_known,
                                 claude_installed_path=cc_inst,
                                 claude_known_path=cc_known)
        by = {(r["agent"], r["plugin"]): r for r in rows}

        zc = by[("zcode", "mattpocock-skills")]
        assert zc["status"] == "copy-foreign"
        rec = zc["records"][0]
        assert rec["version"] == "1.2.3", "已装版本要报出"
        assert rec["marketplace"] == "claude-plugins-official", "来源市场要报出"
        assert rec["sha"] == "3cca18b3ffff", "记录里的上游 sha 要报出"
        assert zc["commands"] == [
            "zcode plugins marketplace update claude-plugins-official",
            "zcode plugins plugin update mattpocock-skills@claude-plugins-official"], \
            "ZCode 外部副本附两条刷新命令"

        assert by[("zcode", "obsidian-skills")]["status"] == "copy-own-market", \
            "装自本仓库市场的副本不算其他市场副本（ZCode 侧 own-market 识别）"

        cc = by[("claude-code", "mattpocock-skills")]
        assert cc["status"] == "copy-foreign"
        assert cc["records"][0]["version"] == "1.2.3"
        assert cc["commands"] == [
            "claude plugin update mattpocock-skills@claude-plugins-official"], \
            "Claude Code 外部副本附一条刷新命令"

        assert by[("claude-code", "obsidian-skills")]["status"] == "copy-own-market", \
            "装自本仓库市场的副本不算其他市场副本，不打印刷新命令"

        for plugin in ("mattpocock-skills", "obsidian-skills"):
            row = by[("minimax", plugin)]
            assert row["status"] == "copy-not-installed"
            assert row["commands"] == []
            assert row["note"], "MiniMax 无独立安装记录，未安装附说明"

        # video-agent-kit 不是市场里的外部条目，整行不应出现
        assert all(r["plugin"] in ("mattpocock-skills", "obsidian-skills")
                   for r in rows)


def test_collect_copy_line_missing_files():
    """安装记录文件全缺（新机器）-> 各 agent 全报未安装，不抛异常。"""
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "nope.json")
        rows = collect_copy_line(["mattpocock-skills"], tmp,
                                 zcode_installed_path=missing,
                                 zcode_known_path=missing,
                                 claude_installed_path=missing,
                                 claude_known_path=missing)
        assert len(rows) == 3
        assert all(r["status"] == "copy-not-installed" for r in rows)
        assert all(r["commands"] == [] for r in rows)


# ---------------------------------------------------------------- 报告与退出码（票 02）

def test_build_hub_report():
    """枢纽线报告：逐成员中文状态、跳过无 pin 条目、失败条目带原因、小结计数。"""
    results = [hub_result(member_statuses=("hub-in-sync", "hub-drifted", "hub-missing")),
               hub_result(status="hub-error")]
    text = "\n".join(build_hub_report(results, hub_dir="HUB",
                                      skipped=["obsidian-skills"]))
    assert "枢纽同步线" in text
    assert "obsidian-skills" in text, "被跳过的无 pin 条目要有说明"
    assert "已同步" in text and "与基线不一致（落后或手改）" in text and "缺失" in text
    assert "49dd158d1076" in text, "逐条目标明基线 pin"
    assert "1 已同步" in text, "小结给各状态计数"
    assert "tarball 下载失败" in text, "枢纽线失败的条目带可读原因"


def test_build_copy_report():
    """副本线报告：版本/来源市场/sha、两条 ZCode 命令、一条 Claude 命令、未安装。"""
    with tempfile.TemporaryDirectory() as tmp:
        root, (zc_inst, zc_known, cc_inst, cc_known) = make_copy_fixtures(tmp)
        rows = collect_copy_line(["mattpocock-skills", "obsidian-skills"], root,
                                 zcode_installed_path=zc_inst,
                                 zcode_known_path=zc_known,
                                 claude_installed_path=cc_inst,
                                 claude_known_path=cc_known)
        text = "\n".join(build_copy_report(rows))
        assert "其他市场插件副本" in text
        assert "1.2.3" in text and "3cca18b3ffff" in text
        assert "claude-plugins-official" in text
        assert "zcode plugins marketplace update claude-plugins-official" in text
        assert "zcode plugins plugin update mattpocock-skills@claude-plugins-official" in text
        assert "claude plugin update mattpocock-skills@claude-plugins-official" in text
        assert "未安装" in text, "未装的 agent 要报未安装"
        assert "本仓库市场" in text, "本市场来源的副本要标明无需处理"


def test_decide_exit_code_with_hub():
    """退出码纳入枢纽线：全同步才 0；不一致/缺失/枢纽线失败任一 -> 1；副本线不影响。"""
    pin_ok = [mk_result("up-to-date")]
    assert decide_exit_code(pin_ok, [hub_result()]) == 0
    assert decide_exit_code(pin_ok, [hub_result(member_statuses=("hub-drifted",))]) == 1
    assert decide_exit_code(pin_ok, [hub_result(member_statuses=("hub-missing",))]) == 1
    assert decide_exit_code(pin_ok, [hub_result(status="hub-error")]) == 1
    assert decide_exit_code([mk_result("update-available")], [hub_result()]) == 1


# ---------------------------------------------------------------- update 校验门判定（票 03）

GATE_PASS_OUTPUT = ("== /tmp/tree\n"
                    "  全部检查通过\n"
                    "\n"
                    "结果: 0 error, 2 warning — 通过（warning 请逐条人工确认后发布）\n")
GATE_NA_OUTPUT = ("== /tmp/tree\n"
                  "  ERROR   缺少 .minimax-plugin/plugin.json（MiniMax Plugin V1 入口清单）\n"
                  "  ERROR   skills/x/SKILL.md frontmatter 缺少 name\n"
                  "结果: 2 error, 1 warning — 未通过，修完 error 才能发布\n")


def test_judge_validator_output():
    """0 error 放行；「缺 .minimax-plugin」对外部条目 N/A、其余 error 阻断；
    无「结果:」行的不可识别输出保守拦截（0 error 也必须有证据）。"""
    verdict = judge_validator_output(GATE_PASS_OUTPUT, external_ref=True)
    assert verdict["passed"] and verdict["blocking"] == [] and verdict["waived"] == []

    verdict = judge_validator_output(GATE_NA_OUTPUT, external_ref=True)
    assert not verdict["passed"]
    assert len(verdict["waived"]) == 1 and "缺少 .minimax-plugin" in verdict["waived"][0], \
        "外部引用式条目的「缺 .minimax-plugin」error 特判 N/A（2026-10-18 手动重 pin 先例）"
    assert len(verdict["blocking"]) == 1 and "缺少 name" in verdict["blocking"][0], \
        "其余 error 照常阻断"

    verdict = judge_validator_output(GATE_NA_OUTPUT, external_ref=False)
    assert len(verdict["blocking"]) == 2 and verdict["waived"] == [], \
        "非外部引用式条目不豁免任何 error"

    verdict = judge_validator_output("Traceback (most recent call last): ...", external_ref=True)
    assert not verdict["passed"] and not verdict["recognized"], \
        "无「结果:」行 = validator 输出不可识别，保守按未通过处理"


# ---------------------------------------------------------------- update 默认分支解析（票 03）

def test_parse_symref_output():
    """`git ls-remote --symref` 首行 ref: refs/heads/<名> 取默认分支短名。"""
    out = ("ref: refs/heads/main\tHEAD\n"
           "0f9e8d7c6b5a4444444444444444444444444444\tHEAD\n")
    assert parse_symref_output(out) == "main"
    assert parse_symref_output("ref: refs/heads/master\tHEAD\n") == "master"
    try:
        parse_symref_output("abc\tHEAD\n")
        raise AssertionError("没有 ref: 行应报错而不是静默返回")
    except ValueError:
        pass


# ---------------------------------------------------------------- pin bump 纯决策（票 03）

def alpha_entry():
    """与真实市场同构的带 pin 条目（note 内嵌旧短 SHA + 旧日期）。"""
    return {"name": "alpha-skills", "description": "外部聚合带 pin",
            "source": {"source": "github", "repo": "alpha/one"},
            "metadata": {"pinnedRef": "main", "pinnedSha": OLD_SHA,
                         "pinnedAt": OLD_DATE,
                         "note": f"外部聚合插件（引用式 + pin SHA）；"
                                 f"旧基线 {OLD_SHA[:7]}（{OLD_DATE}）重 pin，校验 0 error"}}


def test_apply_pin_bump_syncs_note_and_idempotent():
    """bump 双字段 + note 只同步内嵌旧 SHA/日期的文字；原 dict 不动；重跑零改动。"""
    mp = {"plugins": [alpha_entry(),
                      {"name": "gamma-skills", "source": {"source": "github", "repo": "g/h"},
                       "metadata": {"pinnedRef": "main", "pinnedSha": OLD_SHA,
                                    "pinnedAt": OLD_DATE,
                                    "note": f"全串 pin {OLD_SHA}，人工核对过"}}]}
    new_mp, changed = apply_pin_bump(mp, "alpha-skills", NEW_SHA, NEW_DATE)
    assert changed
    meta = new_mp["plugins"][0]["metadata"]
    assert meta["pinnedSha"] == NEW_SHA and meta["pinnedAt"] == NEW_DATE
    assert meta["pinnedRef"] == "main"
    assert meta["note"] == (f"外部聚合插件（引用式 + pin SHA）；"
                            f"旧基线 {NEW_SHA[:7]}（{NEW_DATE}）重 pin，校验 0 error"), \
        "note 里内嵌的旧短 SHA 与旧日期被替换，其余文字原样保留"
    assert mp["plugins"][0]["metadata"]["pinnedSha"] == OLD_SHA, "原 marketplace dict 不被修改"

    new_mp2, changed2 = apply_pin_bump(new_mp, "alpha-skills", NEW_SHA, NEW_DATE)
    assert not changed2, "对已同步条目重跑（旧值==新值）零改动"

    # 内嵌全串 SHA 的 note 同步为全串新 SHA
    new_mp3, _ = apply_pin_bump(mp, "gamma-skills", NEW_SHA, NEW_DATE)
    assert new_mp3["plugins"][1]["metadata"]["note"] == f"全串 pin {NEW_SHA}，人工核对过"


def test_apply_pin_bump_baseline_creates_metadata():
    """无 pin 条目建基线：新建 metadata 写齐 pinnedRef/pinnedSha/pinnedAt（键序固定）。"""
    mp = {"plugins": [{"name": "beta-skills", "description": "外部聚合无 pin",
                       "source": {"source": "github", "repo": "beta/two"}}]}
    new_mp, changed = apply_pin_bump(mp, "beta-skills", BASE_SHA, NEW_DATE, new_ref="main")
    assert changed
    meta = new_mp["plugins"][0]["metadata"]
    assert meta == {"pinnedRef": "main", "pinnedSha": BASE_SHA, "pinnedAt": NEW_DATE}
    assert list(meta.keys()) == ["pinnedRef", "pinnedSha", "pinnedAt"], \
        "基线三字段按 pinnedRef/pinnedSha/pinnedAt 的顺序写（对齐现有条目排版）"


# ---------------------------------------------------------------- compat 表格同步（票 03）

def test_render_pin_cell():
    """pin 列格式 `main `<短sha>`（日期，v版本）`；版本号未知时省略版本段。"""
    assert render_pin_cell("main", NEW_SHA, NEW_DATE, "2.0.0") == \
        f"main `{NEW_SHA[:7]}`（{NEW_DATE}，v2.0.0）"
    assert render_pin_cell("main", NEW_SHA, NEW_DATE, None) == \
        f"main `{NEW_SHA[:7]}`（{NEW_DATE}）"


def make_compat_text():
    """与真实 docs/plugin-compatibility.md「外部聚合插件」节同构的最小表格。"""
    return ("# 兼容性\n\n## 外部聚合插件（引用式 + pin SHA）\n\n"
            "| 插件 | 上游 | pin | 三平台 |\n"
            "|---|---|---|---|\n"
            f"| alpha-skills | [alpha/one](https://github.com/alpha/one) "
            f"| main `{OLD_SHA[:7]}`（{OLD_DATE}，v1.0.0） | ✅✅✅ 纯 skills |\n"
            "| beta-skills | [beta/two](https://github.com/beta/two) | 无 pin "
            "| ✅✅✅ 纯 skills |\n\n"
            "入库流程：clone → 校验 → 本表标注 → marketplace.json 加条目。\n")


def test_sync_compat_table():
    """只替换该条目行的 pin 列（第 3 列）；上游列/三平台列/其余行不动；幂等。"""
    text = make_compat_text()
    cell = f"main `{NEW_SHA[:7]}`（{NEW_DATE}，v2.0.0）"
    new_text, changed = sync_compat_table(text, "alpha-skills", cell)
    assert changed
    assert f"| alpha-skills | [alpha/one](https://github.com/alpha/one) | {cell} " \
           "| ✅✅✅ 纯 skills |" in new_text, "pin 列换新，同行其余列原样"
    assert "无 pin" in new_text, "其余条目的行不动"
    assert "入库流程" in new_text, "表格外的正文不动"

    again, changed2 = sync_compat_table(new_text, "alpha-skills", cell)
    assert not changed2 and again == new_text, "已同步的行重跑零改动"

    _, changed3 = sync_compat_table(text, "gamma-skills", cell)
    assert not changed3, "表里没有该条目行 -> 不改动（由调用方注明跳过）"


# ---------------------------------------------------------------- update 编排（票 03）

OLD_SHA = "a1b2c3d4e5f6000000000000000000000000000"
NEW_SHA = "f6e5d4c3b2a1999999999999999999999999999"
BASE_SHA = "0f9e8d7c6b5a4444444444444444444444444444"
OLD_DATE = "2026-01-02"
NEW_DATE = "2026-10-19"


def make_update_entries():
    """一 bump 一建基线，与真实市场外部条目同构。"""
    return [
        {"name": "alpha-skills", "repo": "alpha/one", "pinned_ref": "main",
         "pinned_sha": OLD_SHA},
        {"name": "beta-skills", "repo": "beta/two", "pinned_ref": None,
         "pinned_sha": None},
    ]


def make_update_seams(tar_path, validator_output=GATE_PASS_OUTPUT, head_map=None):
    """update 全套假接缝：head/版本号/默认分支/tarball/validator 全注入，调用可观测。

    返回 (calls, seams_dict)：seams_dict 的键与 plan_updates / cmd_update 的
    注入参数同名，可直接 ** 解包。
    """
    calls = {"tar": [], "validator": [], "symref": []}
    heads = head_map or {"alpha/one": NEW_SHA, "beta/two": BASE_SHA}

    def fetch_head(repo, ref):
        return heads[repo]

    def fetch_version(repo, sha):
        return "2.0.0" if repo == "alpha/one" else "0.9.0"

    def fetch_default_ref(repo):
        calls["symref"].append(repo)
        return "main"

    def get_tarball(repo, sha, dest_dir, timeout=120):
        calls["tar"].append((repo, sha))
        return tar_path

    def validator(tree):
        calls["validator"].append(tree)
        assert os.path.isdir(tree), "校验门拿到的应是解包后真实存在的树"
        return validator_output

    return calls, {"fetch_head": fetch_head, "fetch_version": fetch_version,
                   "fetch_default_ref": fetch_default_ref,
                   "get_tarball": get_tarball, "validator": validator}


def test_plan_updates_bump_and_baseline():
    """bump/建基线两类计划齐备：下载用新 head SHA、只有无 pin 条目查默认分支、全过校验门。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE, **seams)
        assert failures == []
        by = {p["name"]: p for p in plans}
        assert by["alpha-skills"]["action"] == "bump"
        assert by["alpha-skills"]["new_sha"] == NEW_SHA
        assert by["alpha-skills"]["old_sha"] == OLD_SHA
        assert by["alpha-skills"]["version"] == "2.0.0"
        assert by["beta-skills"]["action"] == "baseline"
        assert by["beta-skills"]["new_sha"] == BASE_SHA
        assert by["beta-skills"]["new_ref"] == "main", "建基线要带默认分支"
        assert by["beta-skills"]["date"] == NEW_DATE
        assert calls["tar"] == [("alpha/one", NEW_SHA), ("beta/two", BASE_SHA)], \
            "tarball 按新 head SHA 下载（校验门与实体同步共用一次下载）"
        assert calls["symref"] == ["beta/two"], "只有无 pin 条目才查默认分支"
        assert len(calls["validator"]) == 2, "两条目都过同一校验门"


def test_plan_updates_gate_failure_isolated():
    """校验门未通过 -> 该条目进失败通道（N/A 项不算阻断），其余条目照常出计划。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        _calls, seams = make_update_seams(tar_path)
        gate_calls = {"n": 0}

        def fail_first_gate(tree):
            gate_calls["n"] += 1
            # alpha（第一个进门的）校验不过，beta 照常通过——混合结果
            return GATE_NA_OUTPUT if gate_calls["n"] == 1 else GATE_PASS_OUTPUT

        seams["validator"] = fail_first_gate
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE, **seams)
        assert [p["name"] for p in plans] == ["beta-skills"], \
            "单条目校验失败不中断其余条目的计划"
        assert len(failures) == 1 and failures[0]["stage"] == "gate"
        assert failures[0]["name"] == "alpha-skills"
        blocking = failures[0]["detail"]
        assert any("缺少 name" in e for e in blocking), "真实 error 进阻断清单"
        assert not any("缺少 .minimax-plugin" in e for e in blocking), \
            "「缺 .minimax-plugin」N/A 不进阻断清单"


def test_plan_updates_skips_up_to_date():
    """pin==head 的条目出 skip 计划：不下载 tarball、不过校验门（幂等重跑的基础）。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(
            tar_path, head_map={"alpha/one": OLD_SHA, "beta/two": BASE_SHA})
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE, **seams)
        assert failures == []
        by = {p["name"]: p["action"] for p in plans}
        assert by["alpha-skills"] == "skip"
        assert by["beta-skills"] == "baseline"
        assert calls["tar"] == [("beta/two", BASE_SHA)], "已最新条目不下载"
        assert len(calls["validator"]) == 1, "已最新条目不过校验门"


def test_plan_updates_head_failure_isolated():
    """单条目 head 查询失败 -> 失败通道（stage=head），其余条目照常计划。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)

        def flaky_head(repo, ref):
            if repo == "alpha/one":
                raise RuntimeError("网络断了")
            return BASE_SHA

        seams["fetch_head"] = flaky_head
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE, **seams)
        assert [p["name"] for p in plans] == ["beta-skills"]
        assert len(failures) == 1 and failures[0]["stage"] == "head"
        assert failures[0]["name"] == "alpha-skills" and "网络断了" in failures[0]["error"]
        assert calls["tar"] == [("beta/two", BASE_SHA)], "失败条目不进入下载"


def test_normalize_tree_root_renames_to_plugin_name():
    """codeload 顶层目录是 <repo>-<sha>，校验门前把树根改名为 plugin.json 的
    name（对齐手动重 pin 先例里 git clone 的目录名），否则出假阻断 error。"""
    with tempfile.TemporaryDirectory() as tmp:
        top = os.path.join(tmp, "obsidian-skills-3ccff5338ea7")
        write_text(os.path.join(top, ".claude-plugin", "plugin.json"),
                   '{"name": "obsidian", "version": "1.0.1"}')
        write_text(os.path.join(top, "SKILL.md"), "---\nname: x\n---\nbody\n")
        renamed = normalize_tree_root(top)
        assert os.path.basename(renamed) == "obsidian"
        assert os.path.isdir(renamed) and not os.path.exists(top), "原目录已改名"
        assert os.path.isfile(os.path.join(renamed, ".claude-plugin", "plugin.json"))

        # 已对齐 / plugin.json 缺失 / 损坏 -> 原样返回（让校验门报真正的 error）
        assert normalize_tree_root(renamed) == renamed
        bare = os.path.join(tmp, "skills-49dd158d1076")
        os.makedirs(bare)
        assert normalize_tree_root(bare) == bare
        broken = os.path.join(tmp, "skills-broken")
        os.makedirs(broken)
        write_text(os.path.join(broken, ".claude-plugin", "plugin.json"), "<html>")
        assert normalize_tree_root(broken) == broken


def test_plan_updates_gate_receives_normalized_tree():
    """校验门拿到的树根目录名 == plugin.json 的 name（端到端走 tarball 解包链）。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 仿 codeload 形态：顶层 <repo>-<sha>，内含 plugin.json(name=one) + skills/
        top = os.path.join(tmp, "one-abcdef1234")
        write_text(os.path.join(top, ".claude-plugin", "plugin.json"),
                   '{"name": "one", "version": "2.0.0"}')
        write_text(os.path.join(top, "skills", "engineering", "tdd", "SKILL.md"),
                   "---\nname: tdd\n---\nbody\n")
        tar_path = os.path.join(tmp, "new.tar.gz")
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(top, arcname="one-abcdef1234")
        captured = []

        def validator(tree):
            captured.append(tree)
            return GATE_PASS_OUTPUT

        entries = [{"name": "alpha-skills", "repo": "alpha/one",
                    "pinned_ref": "main", "pinned_sha": OLD_SHA}]
        plans, failures = plan_updates(
            entries, fetch_head=lambda repo, ref: NEW_SHA,
            fetch_version=lambda repo, sha: "2.0.0",
            get_tarball=lambda repo, sha, dest_dir, timeout=120: tar_path,
            validator=validator, today=NEW_DATE)
        assert failures == [] and plans[0]["action"] == "bump"
        assert os.path.basename(captured[0]) == "one", \
            "校验门收到的是改名后的树根（name 与目录名一致，不出假阻断）"


# ---------------------------------------------------------------- update 写盘（票 03）

def make_bump_plans():
    """手搓两条计划（bump + 建基线），供 apply_updates 的产物用例复用。"""
    return [
        {"action": "bump", "name": "alpha-skills", "repo": "alpha/one", "ref": "main",
         "old_sha": OLD_SHA, "new_sha": NEW_SHA, "new_ref": None, "date": NEW_DATE,
         "version": "2.0.0", "waived": []},
        {"action": "baseline", "name": "beta-skills", "repo": "beta/two", "ref": "HEAD",
         "old_sha": None, "new_sha": BASE_SHA, "new_ref": "main", "date": NEW_DATE,
         "version": "0.9.0", "waived": []},
    ]


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def fake_repo_paths(root):
    return (os.path.join(root, ".claude-plugin", "marketplace.json"),
            os.path.join(root, "docs", "plugin-compatibility.md"))


def test_apply_updates_writes_both_files():
    """tmp 假仓库：双文件产物正确——双字段 bump + note 同步、基线三字段、
    compat 两行 pin 列同步；CRLF/LF 与 2 空格缩进保持；本地条目不受影响。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        mp_path, compat_path = fake_repo_paths(root)
        res = apply_updates(root, make_bump_plans())
        assert res["marketplace"]["written"] and res["compat"]["written"]

        mp_bytes = read_bytes(mp_path)
        assert b"\r\n" in mp_bytes and not mp_bytes.startswith(b"\xef\xbb\xbf"), \
            "marketplace.json 的 CRLF 行尾保持、不引入 BOM"
        assert mp_bytes.endswith(b"\r\n"), "文件末尾换行保持"
        assert b"\r\n  \"plugins\"" in mp_bytes, "2 空格缩进排版保持"
        data = json.loads(mp_bytes.decode("utf-8"))
        alpha = next(p for p in data["plugins"] if p["name"] == "alpha-skills")
        assert alpha["metadata"]["pinnedSha"] == NEW_SHA
        assert alpha["metadata"]["pinnedAt"] == NEW_DATE
        assert alpha["metadata"]["note"] == (f"外部聚合插件（引用式 + pin SHA）；"
                                             f"旧基线 {NEW_SHA[:7]}（{NEW_DATE}）重 pin，"
                                             f"校验 0 error")
        beta = next(p for p in data["plugins"] if p["name"] == "beta-skills")
        assert list(beta["metadata"].keys()) == ["pinnedRef", "pinnedSha", "pinnedAt"]
        assert beta["metadata"]["pinnedSha"] == BASE_SHA
        local = next(p for p in data["plugins"] if p["name"] == "local-plugin")
        assert "metadata" not in local, "本地条目不受影响"

        compat_text = read_bytes(compat_path).decode("utf-8")
        assert b"\r\n" not in read_bytes(compat_path), "compat 文档 LF 行尾保持"
        assert f"main `{NEW_SHA[:7]}`（{NEW_DATE}，v2.0.0）" in compat_text
        assert f"main `{BASE_SHA[:7]}`（{NEW_DATE}，v0.9.0）" in compat_text, \
            "建基线条目的 pin 列同步"
        assert "无 pin" not in compat_text.split("## 外部聚合插件")[1].split("\n\n")[1], \
            "表格里不再有未治理条目"


def test_apply_updates_dry_run_zero_write():
    """--dry-run 语义：算出将发生的变更但不落一个字节。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        mp_path, compat_path = fake_repo_paths(root)
        before = (read_bytes(mp_path), read_bytes(compat_path))
        res = apply_updates(root, make_bump_plans(), dry_run=True)
        assert res["marketplace"]["changed"] and not res["marketplace"]["written"]
        assert res["compat"]["changed"] and not res["compat"]["written"]
        assert (read_bytes(mp_path), read_bytes(compat_path)) == before, "零写入"


def test_apply_updates_idempotent_byte_level():
    """同一批计划重复 apply：第二遍算不出变更、不写盘、字节不变。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        mp_path, compat_path = fake_repo_paths(root)
        apply_updates(root, make_bump_plans())
        snapshot = (read_bytes(mp_path), read_bytes(compat_path))
        res2 = apply_updates(root, make_bump_plans())
        assert not res2["marketplace"]["changed"] and not res2["marketplace"]["written"]
        assert not res2["compat"]["changed"] and not res2["compat"]["written"]
        assert (read_bytes(mp_path), read_bytes(compat_path)) == snapshot, "字节级零改动"


# ---------------------------------------------------------------- update 命令层（票 03）

def test_cmd_update_end_to_end_idempotent():
    """假仓库全链：成功 bump 双文件 -> 重跑已最新零下载零写入（命令级幂等）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)
        rc = cmd_update(root, yes=True, today=NEW_DATE, **seams)
        assert rc == 0, "成功更新退出码 0"
        mp_path, compat_path = fake_repo_paths(root)
        assert NEW_SHA[:7] in read_bytes(compat_path).decode("utf-8")
        snapshot = (read_bytes(mp_path), read_bytes(compat_path))

        calls["tar"].clear()
        calls["validator"].clear()
        rc2 = cmd_update(root, yes=True, today=NEW_DATE, **seams)
        assert rc2 == 0, "重跑（已最新）也退出码 0"
        assert calls["tar"] == [] and calls["validator"] == [], \
            "已最新条目不下载、不校验"
        assert (read_bytes(mp_path), read_bytes(compat_path)) == snapshot, \
            "重跑零改动（幂等）"


def test_cmd_update_guard_noninteractive():
    """非交互环境无 --yes -> 退出码 2，拒绝执行任何变更（连网络都不碰）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)
        mp_path, compat_path = fake_repo_paths(root)
        before = (read_bytes(mp_path), read_bytes(compat_path))
        rc = cmd_update(root, interactive=False, yes=False, today=NEW_DATE, **seams)
        assert rc == 2
        assert calls == {"tar": [], "validator": [], "symref": []}, \
            "守卫在任何外部访问之前触发"
        assert (read_bytes(mp_path), read_bytes(compat_path)) == before, "零写入"


def test_cmd_update_gate_failure_aborts_zero_write():
    """校验门有 error -> 退出码 1、全链中止：beta 即便过了门也不写（全或无）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        _calls, seams = make_update_seams(tar_path)
        gate_calls = {"n": 0}

        def fail_first_gate(tree):
            gate_calls["n"] += 1
            # alpha（有 pin 的，第一个进门）校验不过；beta 过门
            return GATE_NA_OUTPUT if gate_calls["n"] == 1 else GATE_PASS_OUTPUT

        seams["validator"] = fail_first_gate
        mp_path, compat_path = fake_repo_paths(root)
        before = (read_bytes(mp_path), read_bytes(compat_path))
        rc = cmd_update(root, yes=True, today=NEW_DATE, **seams)
        assert rc == 1
        assert (read_bytes(mp_path), read_bytes(compat_path)) == before, \
            "任一校验失败 -> 全链中止、仓库文件零改动"
        data = json.loads(read_bytes(mp_path).decode("utf-8"))
        beta = next(p for p in data["plugins"] if p["name"] == "beta-skills")
        assert "metadata" not in beta, "其他条目即便过了门也不写（全或无）"


def test_cmd_update_dry_run_zero_write():
    """--dry-run 非交互可跑（不写入就不需要 --yes），退出码 0、零写入。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)
        mp_path, compat_path = fake_repo_paths(root)
        before = (read_bytes(mp_path), read_bytes(compat_path))
        rc = cmd_update(root, dry_run=True, interactive=False, today=NEW_DATE, **seams)
        assert rc == 0
        assert len(calls["validator"]) == 2, "dry-run 仍走完整校验门（报告才可信）"
        assert (read_bytes(mp_path), read_bytes(compat_path)) == before, "零写入"


def test_cmd_update_entry_filter():
    """--entry 只影响指定条目：alpha bump 落盘，beta 的 marketplace/compat 原样。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        _calls, seams = make_update_seams(tar_path)
        rc = cmd_update(root, entry="alpha-skills", yes=True, today=NEW_DATE, **seams)
        assert rc == 0
        mp_path, compat_path = fake_repo_paths(root)
        data = json.loads(read_bytes(mp_path).decode("utf-8"))
        alpha = next(p for p in data["plugins"] if p["name"] == "alpha-skills")
        beta = next(p for p in data["plugins"] if p["name"] == "beta-skills")
        assert alpha["metadata"]["pinnedSha"] == NEW_SHA
        assert "metadata" not in beta, "未指定条目不建基线"
        compat_beta = [ln for ln in read_bytes(compat_path).decode("utf-8").splitlines()
                       if ln.startswith("| beta-skills")]
        assert compat_beta == ["| beta-skills | [beta/two](https://github.com/beta/two) "
                               "| 无 pin | ✅✅✅ 纯 skills |"], "未指定条目的表格行原样"


def test_cmd_update_entry_unknown():
    """--entry 给了市场里不存在的名字 -> 退出码 2。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        _calls, seams = make_update_seams(tar_path)
        rc = cmd_update(root, entry="no-such", yes=True, today=NEW_DATE, **seams)
        assert rc == 2


def test_build_update_report():
    """报告措辞：计划/跳过/失败（含阻断明细）/写入与 dry-run 标注。"""
    plans = make_bump_plans() + [
        {"action": "skip", "name": "gamma-skills", "repo": "g/h", "ref": "main",
         "old_sha": NEW_SHA, "new_sha": NEW_SHA, "new_ref": None, "date": None,
         "version": None, "waived": []}]
    text = "\n".join(build_update_report(plans, [], None, market_root="R"))
    assert "bump" in text and "建基线" in text and "已最新" in text
    assert "f6e5d4c" in text and "0f9e8d7" in text, "计划里给新旧短 SHA"

    failures = [{"name": "alpha-skills", "repo": "alpha/one", "stage": "gate",
                 "error": "校验门未通过（1 error）",
                 "detail": ["skills/x/SKILL.md frontmatter 缺少 name"]}]
    text2 = "\n".join(build_update_report(plans, failures, None, market_root="R"))
    assert "全链中止" in text2 and "零写入" in text2
    assert "缺少 name" in text2, "阻断 error 明细进报告"

    applied = {"marketplace": {"changed": True, "written": True},
               "compat": {"changed": True, "written": True, "skipped": []}}
    text3 = "\n".join(build_update_report(plans, [], applied, market_root="R"))
    assert "已写入" in text3
    text4 = "\n".join(build_update_report(plans, [], applied, dry_run=True,
                                          market_root="R"))
    assert "dry-run" in text4 and "未写入" in text4




def write_text(path, text):
    """小工具：按 UTF-8 + LF 落一个文本文件（目录不存在则建）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make_upstream_tree(tree_root):
    """搭一棵 pin 处上游树：三分类成员 + deprecated/in-progress 干扰 + 散文件。

    返回族成员期望值（name -> category）。
    """
    expected = {}
    for cat, names in (("engineering", ["tdd", "code-review"]),
                       ("productivity", ["grilling"]),
                       ("misc", ["wizard"])):
        for n in names:
            write_text(os.path.join(tree_root, "skills", cat, n, "SKILL.md"),
                       f"---\nname: {n}\n---\nbody of {n}\n")
            expected[n] = cat
    # 永不装入的分类：deprecated / in-progress 各放一个成员
    for cat in ("deprecated", "in-progress"):
        write_text(os.path.join(tree_root, "skills", cat, "old-skill", "SKILL.md"),
                   "old\n")
    # 散文件与子目录内容：不影响族清单，但参与内容比对
    write_text(os.path.join(tree_root, "skills", "README.md"), "readme\n")
    write_text(os.path.join(tree_root, "skills", "engineering", "NOTICE.txt"), "notice\n")
    write_text(os.path.join(tree_root, "skills", "engineering", "tdd",
                            "references", "tests.md"), "tests md\n")
    return expected


def make_pin_tarball(tmp, top_name="skills-49dd158d"):
    """把上游树打成 codeload 形态的 tar.gz（单顶层目录），返回 (tar_path, tree_root)。"""
    tree_root = os.path.join(tmp, top_name)
    make_upstream_tree(tree_root)
    tar_path = os.path.join(tmp, "pin.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(tree_root, arcname=top_name)
    return tar_path, tree_root


def make_hub_from_tree(tmp, tree_root, omit=()):
    """按上游树把枢纽实体原样拷出来（全部已同步的枢纽），返回枢纽目录。"""
    hub = os.path.join(tmp, "hub")
    fam = derive_family_members(tree_root)
    for name, cat in fam.items():
        if name in omit:
            continue
        shutil.copytree(os.path.join(tree_root, "skills", cat, name),
                        os.path.join(hub, name))
    return hub


def make_pinned_entries():
    """一条带 pin 一条无 pin，与真实市场同构。"""
    return [
        {"name": "mattpocock-skills", "repo": "mattpocock/skills",
         "pinned_ref": "main", "pinned_sha": "49dd158d1076"},
        {"name": "obsidian-skills", "repo": "kepano/obsidian-skills",
         "pinned_ref": None, "pinned_sha": None},
    ]


def make_fake_repo(tmp):
    """tmp 假 market 仓库：marketplace.json（CRLF、2 空格缩进，带 pin/无 pin/本地
    三种条目）+ compat 文档（LF，外部聚合插件表格）+ plugins/ 目录
    （repo_root 的定位判据是 marketplace.json + plugins/，形态对齐真实仓库）。
    行尾形态对齐真实仓库（marketplace.json CRLF / compat LF）。"""
    root = os.path.join(tmp, "market")
    os.makedirs(os.path.join(root, ".claude-plugin"))
    os.makedirs(os.path.join(root, "docs"))
    os.makedirs(os.path.join(root, "plugins"))
    mp = {
        "name": "fake-market",
        "plugins": [
            alpha_entry(),
            {"name": "beta-skills", "description": "外部聚合无 pin",
             "source": {"source": "github", "repo": "beta/two"}},
            {"name": "local-plugin", "description": "本地条目",
             "source": "./plugins/local-plugin"},
        ],
    }
    body = json.dumps(mp, ensure_ascii=False, indent=2) + "\n"
    with open(os.path.join(root, ".claude-plugin", "marketplace.json"), "wb") as f:
        f.write(body.replace("\n", "\r\n").encode("utf-8"))
    with open(os.path.join(root, "docs", "plugin-compatibility.md"), "wb") as f:
        f.write(make_compat_text().encode("utf-8"))
    return root


# ---------------------------------------------------------------- 副本线夹具

def make_copy_fixtures(tmp):
    """tmp 假安装记录：ZCode 列表格式 / Claude Code 字典格式，形态对齐真实文件。

    ZCode：mattpocock 来自 claude-plugins-official（外部副本，v1.2.3 @ 3cca18b3）、
    obsidian 装自本仓库市场（不算外部副本）；
    Claude Code：obsidian 装自本仓库市场、mattpocock 来自官方市场（外部副本）。
    返回 (market_root, 四个 json 路径)。
    """
    root = os.path.join(tmp, "market")
    os.makedirs(root)
    zc_inst = os.path.join(tmp, "zcode_installed.json")
    with open(zc_inst, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "plugins": [
            {"id": "mattpocock-skills@claude-plugins-official",
             "name": "mattpocock-skills", "marketplace": "claude-plugins-official",
             "version": "1.2.3",
             "source": {"source": "url",
                        "url": "https://github.com/mattpocock/skills.git",
                        "sha": "3cca18b3ffff"}},
            {"id": "obsidian-skills@my-claude-market",
             "name": "obsidian-skills", "marketplace": "my-claude-market",
             "version": "1.0.1", "source": {"source": "directory"}},
            {"id": "video-agent-kit@zcode-plugins-official",
             "name": "video-agent-kit", "marketplace": "zcode-plugins-official",
             "version": "0.4.3", "source": {"source": "url"}},
        ]}, f)
    zc_known = os.path.join(tmp, "zcode_known.json")
    with open(zc_known, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "marketplaces": [
            # 故意用正斜杠路径：验证路径归一化（normcase/realpath）后仍能识别本仓库市场
            {"id": "my-claude-market",
             "source": {"source": "directory", "path": root.replace("\\", "/")}},
            {"id": "claude-plugins-official",
             "source": {"source": "github",
                        "repo": "anthropics/claude-plugins-official"}},
        ]}, f)
    cc_inst = os.path.join(tmp, "claude_installed.json")
    with open(cc_inst, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "plugins": {
            "mattpocock-skills@claude-plugins-official": [
                {"scope": "user", "version": "1.2.3",
                 "installPath": os.path.join(tmp, "cache", "m")}],
            "obsidian-skills@my-claude-market": [
                {"scope": "user", "version": "1.0.1",
                 "gitCommitSha": "01591573"}],
        }}, f)
    cc_known = os.path.join(tmp, "claude_known.json")
    with open(cc_known, "w", encoding="utf-8") as f:
        json.dump({
            "claude-plugins-official": {"source": {"source": "github",
                                                   "repo": "anthropics/claude-plugins-official"}},
            "my-claude-market": {"source": {"source": "directory", "path": root},
                                 "installLocation": root},
        }, f)
    return root, (zc_inst, zc_known, cc_inst, cc_known)


def hub_result(status="hub-ok", member_statuses=("hub-in-sync",)):
    """手搓一条枢纽线结果，供报告 / 退出码用例使用。"""
    return {"name": "mattpocock-skills", "repo": "mattpocock/skills",
            "pinned_sha": "49dd158d1076", "status": status,
            "members": [{"name": f"skill-{i}", "category": "engineering",
                         "status": st}
                        for i, st in enumerate(member_statuses)],
            "error": "tarball 下载失败（HTTP 502）: https://codeload.example"
                     if status == "hub-error" else None}


# ---------------------------------------------------------------- 入口

TESTS = [
    test_parse_external_entries,
    test_parse_ls_remote_exact_ref,
    test_judge_up_to_date_and_update,
    test_judge_no_baseline,
    test_parse_upstream_plugin_json,
    test_run_check_wires_injected_seams,
    test_run_check_fetch_failure_isolated,
    test_build_report,
    test_build_report_error_entry,
    test_decide_exit_code,
    test_derive_family_members,
    test_derive_family_members_missing_skills_dir,
    test_judge_hub_members_three_states,
    test_judge_hub_members_missing_hub_dir,
    test_judge_hub_members_ignores_crlf,
    test_run_hub_check_skips_no_pin_and_judges,
    test_run_hub_check_reports_drift_and_missing,
    test_run_hub_check_download_failure_isolated,
    test_download_to_file_offline,
    test_collect_copy_line_from_tmp_files,
    test_collect_copy_line_missing_files,
    test_build_hub_report,
    test_build_copy_report,
    test_decide_exit_code_with_hub,
    test_judge_validator_output,
    test_parse_symref_output,
    test_apply_pin_bump_syncs_note_and_idempotent,
    test_apply_pin_bump_baseline_creates_metadata,
    test_render_pin_cell,
    test_sync_compat_table,
    test_plan_updates_bump_and_baseline,
    test_plan_updates_gate_failure_isolated,
    test_plan_updates_skips_up_to_date,
    test_plan_updates_head_failure_isolated,
    test_normalize_tree_root_renames_to_plugin_name,
    test_plan_updates_gate_receives_normalized_tree,
    test_apply_updates_writes_both_files,
    test_apply_updates_dry_run_zero_write,
    test_apply_updates_idempotent_byte_level,
    test_cmd_update_end_to_end_idempotent,
    test_cmd_update_guard_noninteractive,
    test_cmd_update_gate_failure_aborts_zero_write,
    test_cmd_update_dry_run_zero_write,
    test_cmd_update_entry_filter,
    test_cmd_update_entry_unknown,
    test_build_update_report,
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
